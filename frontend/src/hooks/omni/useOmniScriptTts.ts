import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  areOmniScriptsEquivalent,
  computeTtsTextHash,
  isOriginalAudio,
  isValidSegmentTts,
  makeScriptJson,
  mergeSegmentTtsIntoScript,
  pickSegmentTtsFields,
} from "../../components/projectEdit/omni/omniScriptWorkspaceUtils";
import { TASK_SUBMITTED_EVENT } from "../../components/projectEdit/TaskQueueFloatingBall";
import { message } from "../../services/message";
import { projectService } from "../../services/projectService";
import type { Project, VideoScript } from "../../types/project";
import { useWsTaskProgress } from "../useWsTaskProgress";
import {
  getOmniScriptRevision,
  getOmniSegmentKey,
  useOmniScriptSessionManager,
} from "./useOmniScriptSessionManager";

export const OMNI_SCRIPT_TTS_SCOPE = "omni_script_tts";

type SegmentTtsJobResult = Awaited<ReturnType<typeof projectService.synthesizeOmniScriptSegmentTts>> | null;

const isTaskActive = (t?: { status?: string; type?: string } | null) => {
  if (!t) return false;
  const status = String(t?.status || "").toLowerCase();
  const type = String(t?.type || "").toLowerCase();
  return (
    status === "pending" ||
    status === "processing" ||
    status === "running" ||
    status === "queued" ||
    status === "waiting" ||
    type === "progress"
  );
};

const isTaskFinished = (t?: { status?: string; type?: string } | null) => {
  if (!t) return false;
  const status = String(t?.status || "").toLowerCase();
  const type = String(t?.type || "").toLowerCase();
  return (
    type === "completed" ||
    status === "completed" ||
    status === "failed" ||
    type === "error" ||
    status === "cancelled" ||
    type === "cancelled"
  );
};

export interface UseOmniScriptTtsOptions {
  project: Project;
  script: VideoScript | null;
  editedScript: string;
  setEditedScript: (s: string) => void;
  /** 服务端回写脚本（不触发自动保存 dirty） */
  setEditedScriptFromServer?: (s: string) => void;
  isSaving: boolean;
  refreshProject: () => Promise<void>;
  syncScriptToServer?: (scriptOverride?: VideoScript) => Promise<VideoScript | null>;
  /** 本地脚本相对服务端有未保存编辑时为 true */
  scriptDirty?: boolean;
  textHashes?: Record<number, string>;
  onSegmentTtsQueueActive?: (active: boolean) => void;
}

export function useOmniScriptTts({
  project,
  script,
  editedScript,
  setEditedScript,
  setEditedScriptFromServer,
  isSaving,
  refreshProject,
  syncScriptToServer,
  scriptDirty = false,
  textHashes = {},
  onSegmentTtsQueueActive,
}: UseOmniScriptTtsOptions) {
  const [bulkBusy, setBulkBusy] = useState(false);
  const [bulkProgress, setBulkProgress] = useState(0);
  const [bulkTaskId, setBulkTaskId] = useState<string | null>(null);

  const session = useOmniScriptSessionManager(script);
  const segmentTtsQueueRef = useRef<string[]>([]);
  const segmentTtsDrainingRef = useRef(false);
  const segmentTtsProcessingKeyRef = useRef<string | null>(null);
  const segmentTtsWaitersRef = useRef<
    Map<string, Array<{ resolve: (v: SegmentTtsJobResult) => void; reject: (e: unknown) => void }>>
  >(new Map());
  const scriptRef = useRef(script);
  scriptRef.current = script;
  const editedScriptRef = useRef(editedScript);
  editedScriptRef.current = editedScript;

  const notifySegmentTtsQueueActive = useCallback(
    (active: boolean) => {
      onSegmentTtsQueueActive?.(active);
    },
    [onSegmentTtsQueueActive]
  );

  useEffect(() => {
    session.dispatch({ type: "setBulkTtsRunning", running: bulkBusy });
  }, [bulkBusy, session.dispatch]);

  const dubbableCount = useMemo(() => {
    if (!script?.segments?.length) return 0;
    return script.segments.filter((s) => !isOriginalAudio(s) && String(s.text ?? "").trim()).length;
  }, [script?.segments]);

  const validDubbedCount = useMemo(() => {
    if (!script?.segments?.length) return 0;
    return script.segments.filter(
      (s, i) => !isOriginalAudio(s) && String(s.text ?? "").trim() && isValidSegmentTts(s, textHashes[i])
    ).length;
  }, [script?.segments, textHashes]);

  const allDubbed = dubbableCount > 0 && validDubbedCount >= dubbableCount;
  const hasAnyDubbed = validDubbedCount > 0;
  const bulkButtonLabel = allDubbed ? "重新配音" : "批量配音";

  const bulkDisabledReason = useMemo(() => {
    if (!script?.segments?.length) return "暂无脚本";
    if (dubbableCount === 0) return "没有可配音的解说段";
    if (isSaving) return "脚本保存中";
    if (bulkBusy) return "批量配音进行中";
    return undefined;
  }, [bulkBusy, dubbableCount, isSaving, script?.segments?.length]);

  useEffect(() => {
    if (!project.id) return;
    let cancelled = false;
    const load = async () => {
      try {
        const res = await projectService.getProjectRunningTasks(project.id);
        const t = res?.omni_script_tts;
        if (!cancelled && isTaskActive(t) && t?.task_id) {
          setBulkBusy(true);
          setBulkTaskId(String(t.task_id));
          setBulkProgress((prev) => Math.max(prev, Number(t.progress) || 1));
        }
      } catch {
        return;
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [project.id]);

  useEffect(() => {
    if (!bulkBusy || !project.id || !bulkTaskId) return;
    let stopped = false;
    const tick = async () => {
      try {
        const latest = await projectService.getProjectLatestTasks(project.id);
        const t = latest?.omni_script_tts;
        if (stopped || !t?.task_id || String(t.task_id) !== String(bulkTaskId)) return;
        if (isTaskActive(t)) {
          setBulkProgress((prev) => Math.max(prev, Number(t.progress) || prev));
          return;
        }
        if (isTaskFinished(t)) {
          setBulkBusy(false);
          setBulkTaskId(null);
          const status = String(t.status || "").toLowerCase();
          if (status === "completed") {
            setBulkProgress(100);
            message.success("批量配音已完成");
          } else if (status === "cancelled") {
            message.info(t.message || "批量配音已取消");
          } else {
            message.error(t.message || "批量配音失败");
          }
          await refreshProject();
        }
      } catch {
        return;
      }
    };
    void tick();
    const id = window.setInterval(() => void tick(), 1500);
    return () => {
      stopped = true;
      window.clearInterval(id);
    };
  }, [bulkBusy, bulkTaskId, project.id, refreshProject]);

  useWsTaskProgress({
    scope: bulkBusy ? OMNI_SCRIPT_TTS_SCOPE : "__omni_tts_idle__",
    projectId: project.id,
    taskId: bulkTaskId,
    onProgress: (p) => setBulkProgress((prev) => Math.max(prev, p)),
    onCompleted: async () => {
      setBulkBusy(false);
      setBulkProgress(100);
      message.success("批量配音已完成");
      await refreshProject();
    },
    onCancelled: () => {
      setBulkBusy(false);
      setBulkProgress(0);
      message.info("批量配音已取消");
      void refreshProject();
    },
    onError: (m) => {
      setBulkBusy(false);
      setBulkProgress(0);
      message.error(m.message || "批量配音失败");
    },
  });

  const applyScriptFromServer = useCallback(
    (nextScript: VideoScript) => {
      const json = makeScriptJson(nextScript);
      editedScriptRef.current = json;
      scriptRef.current = nextScript;
      (setEditedScriptFromServer ?? setEditedScript)(json);
    },
    [setEditedScript, setEditedScriptFromServer]
  );

  const alignScriptWithServer = useCallback(
    async (scriptOverride?: VideoScript) => {
      if (syncScriptToServer) {
        const saved = await syncScriptToServer(scriptOverride);
        if (saved) {
          const json = makeScriptJson(saved);
          editedScriptRef.current = json;
          scriptRef.current = saved;
        }
        return saved;
      }
      const raw = editedScriptRef.current;
      if (!raw.trim() && !scriptOverride) return null;
      await projectService.flushPendingUpdates(project.id);
      const scriptData = scriptOverride ?? (JSON.parse(raw) as VideoScript);
      const saved = await projectService.saveScript(
        project.id,
        scriptData,
        getOmniScriptRevision(scriptData)
      );
      const json = makeScriptJson(saved);
      editedScriptRef.current = json;
      scriptRef.current = saved;
      (setEditedScriptFromServer ?? setEditedScript)(json);
      await refreshProject();
      return saved;
    },
    [project.id, refreshProject, setEditedScript, setEditedScriptFromServer, syncScriptToServer]
  );

  const readLatestLocalScript = useCallback((): VideoScript | null => {
    try {
      return JSON.parse(editedScriptRef.current) as VideoScript;
    } catch {
      return scriptRef.current;
    }
  }, []);

  /** 单条配音接口会原子写回脚本；无本地未保存编辑时不必先 saveScript（避免 revision 冲突） */
  const ensureScriptSyncedBeforeTts = useCallback(async () => {
    await projectService.flushPendingUpdates(project.id);
    if (!scriptDirty) return;
    const latest = readLatestLocalScript();
    if (!latest) return;
    await alignScriptWithServer(latest);
  }, [alignScriptWithServer, project.id, readLatestLocalScript, scriptDirty]);

  const applySegmentTtsResult = useCallback(
    (index: number, data: NonNullable<SegmentTtsJobResult>) => {
      const idx = typeof data.segment_index === "number" ? data.segment_index : index;
      const serverSeg = data.script?.segments?.[idx];
      const fields = pickSegmentTtsFields({
        tts_audio_path: serverSeg?.tts_audio_path ?? data.tts_audio_path,
        tts_audio_duration: serverSeg?.tts_audio_duration ?? data.tts_audio_duration,
        tts_source: serverSeg?.tts_source ?? "manual",
        tts_text_hash: serverSeg?.tts_text_hash,
        tts_updated_at: serverSeg?.tts_updated_at,
      });
      if (!fields.tts_audio_path) return;

      let base: VideoScript;
      try {
        base = JSON.parse(editedScriptRef.current) as VideoScript;
      } catch {
        if (!data.script) return;
        base = data.script;
      }
      const merged = mergeSegmentTtsIntoScript(base, idx, fields);
      applyScriptFromServer(merged);
    },
    [applyScriptFromServer]
  );

  const handleBulkTts = useCallback(
    async (options?: { force?: boolean }) => {
      if (bulkDisabledReason) {
        message.error(bulkDisabledReason);
        return;
      }
      const force = typeof options?.force === "boolean" ? options.force : allDubbed;
      setBulkBusy(true);
      setBulkProgress(0);
      setBulkTaskId(null);
      try {
        await alignScriptWithServer();
        const res = await projectService.runOmniScriptBulkTts(project.id, { force });
        const tid = res?.task_id ? String(res.task_id) : "";
        if (!tid) {
          message.error(res?.message || "提交批量配音失败");
          setBulkBusy(false);
          return;
        }
        setBulkTaskId(tid);
        window.dispatchEvent(new CustomEvent(TASK_SUBMITTED_EVENT));
        message.success(
          res?.message || (force ? "重新配音任务已提交" : "批量配音任务已提交")
        );
      } catch (e) {
        message.error(e instanceof Error ? e.message : "提交批量配音失败");
        setBulkBusy(false);
      }
    },
    [allDubbed, alignScriptWithServer, bulkDisabledReason, project.id]
  );

  const syncSegmentTtsQueueState = useCallback(() => {
    session.dispatch({ type: "setQueue", keys: [...segmentTtsQueueRef.current] });
  }, [session.dispatch]);

  const isSegmentTtsPending = useCallback((key: string) => {
    return (
      segmentTtsQueueRef.current.includes(key) ||
      segmentTtsProcessingKeyRef.current === key
    );
  }, []);

  const findSegmentIndexByKey = useCallback((key: string) => {
    return (scriptRef.current?.segments ?? []).findIndex(
      (segment, index) => getOmniSegmentKey(segment, index) === key
    );
  }, []);

  const runOneSegmentTts = useCallback(
    async (key: string) => {
      const index = findSegmentIndexByKey(key);
      if (index < 0) return null;
      const latest = readLatestLocalScript();
      const seg = latest?.segments?.[index] ?? scriptRef.current?.segments?.[index];
      if (!seg) return null;
      const segId = seg.id ?? index + 1;
      const text = String(seg.text ?? "").trim();
      const expectedTextHash = await computeTtsTextHash(text);
      const data = await projectService.synthesizeOmniScriptSegmentTts(project.id, segId, {
        expectedTextHash,
      });
      if (data.script) {
        applyScriptFromServer(data.script);
      } else if (data?.tts_audio_path) {
        applySegmentTtsResult(index, data);
        if (scriptDirty) {
          const merged = readLatestLocalScript();
          if (merged) await alignScriptWithServer(merged);
        }
      }
      await refreshProject();
      message.success(`第 ${index + 1} 段配音已生成`);
      return data;
    },
    [
      alignScriptWithServer,
      applyScriptFromServer,
      applySegmentTtsResult,
      findSegmentIndexByKey,
      project.id,
      readLatestLocalScript,
      refreshProject,
      scriptDirty,
    ]
  );

  const drainSegmentTtsQueue = useCallback(async () => {
    if (segmentTtsDrainingRef.current) return;
    segmentTtsDrainingRef.current = true;
    notifySegmentTtsQueueActive(true);
    try {
      while (segmentTtsQueueRef.current.length > 0) {
        const key = segmentTtsQueueRef.current.shift()!;
        syncSegmentTtsQueueState();
        segmentTtsProcessingKeyRef.current = key;
        session.dispatch({ type: "setRunning", key });
        const waiters = segmentTtsWaitersRef.current.get(key) ?? [];
        segmentTtsWaitersRef.current.delete(key);
        try {
          await ensureScriptSyncedBeforeTts();
          const data = await runOneSegmentTts(key);
          waiters.forEach((w) => w.resolve(data));
        } catch (e) {
          const err = e instanceof Error ? e : new Error("单条配音失败");
          message.error(err.message);
          if (/revision|脚本|409|变化|更新/.test(err.message)) {
            await refreshProject();
          }
          waiters.forEach((w) => w.reject(err));
        } finally {
          segmentTtsProcessingKeyRef.current = null;
          session.dispatch({ type: "setRunning", key: null });
        }
      }
    } finally {
      segmentTtsDrainingRef.current = false;
      const stillQueued =
        segmentTtsQueueRef.current.length > 0 || segmentTtsProcessingKeyRef.current != null;
      if (!stillQueued) {
        notifySegmentTtsQueueActive(false);
        if (scriptDirty) {
          const latest = readLatestLocalScript();
          if (latest) void alignScriptWithServer(latest);
        }
      }
      if (segmentTtsQueueRef.current.length > 0) {
        void drainSegmentTtsQueue();
      }
    }
  }, [
    alignScriptWithServer,
    ensureScriptSyncedBeforeTts,
    notifySegmentTtsQueueActive,
    readLatestLocalScript,
    refreshProject,
    runOneSegmentTts,
    scriptDirty,
    session.dispatch,
    syncSegmentTtsQueueState,
  ]);

  const handleSegmentTts = useCallback(
    (index: number) => {
      const seg = scriptRef.current?.segments?.[index];
      if (!seg) return Promise.resolve(null);
      const key = getOmniSegmentKey(seg, index);
      if (isSegmentTtsPending(key)) {
        return new Promise<SegmentTtsJobResult>((resolve, reject) => {
          const list = segmentTtsWaitersRef.current.get(key) ?? [];
          list.push({ resolve, reject });
          segmentTtsWaitersRef.current.set(key, list);
        });
      }
      return new Promise<SegmentTtsJobResult>((resolve, reject) => {
        segmentTtsWaitersRef.current.set(key, [{ resolve, reject }]);
        segmentTtsQueueRef.current.push(key);
        syncSegmentTtsQueueState();
        notifySegmentTtsQueueActive(true);
        void drainSegmentTtsQueue();
      });
    },
    [drainSegmentTtsQueue, isSegmentTtsPending, notifySegmentTtsQueueActive, syncSegmentTtsQueueState]
  );

  useEffect(() => {
    if (!bulkBusy || !project.script) return;
    try {
      const local = JSON.parse(editedScript) as VideoScript;
      if (areOmniScriptsEquivalent(local, project.script)) return;
    } catch {
      /* 本地 JSON 无效时允许服务端覆盖 */
    }
    (setEditedScriptFromServer ?? setEditedScript)(makeScriptJson(project.script));
  }, [bulkBusy, editedScript, project.script, setEditedScript, setEditedScriptFromServer]);

  return {
    bulkBusy,
    bulkProgress,
    bulkDisabledReason,
    bulkButtonLabel,
    allDubbed,
    hasAnyDubbed,
    dubbableCount,
    validDubbedCount,
    segmentTtsProcessingIndex:
      session.operationKeys.runningKey == null
        ? null
        : session.segmentKeys.indexOf(session.operationKeys.runningKey),
    segmentTtsQueuedIndices: session.operationKeys.queuedKeys
      .map((key) => session.segmentKeys.indexOf(key))
      .filter((index) => index >= 0),
    segmentTtsOps: session.segmentOps,
    segmentKeys: session.segmentKeys,
    segmentTtsQueueActive: session.globalOps.segmentTtsQueueActive,
    handleBulkTts,
    handleSegmentTts,
  };
}

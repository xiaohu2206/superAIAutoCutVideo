import { useCallback, useEffect, useMemo, useRef, useState, type Dispatch, type SetStateAction } from "react";
import { useAuth } from "../../components/auth/AuthContext";
import { TASK_SUBMITTED_EVENT } from "../../components/projectEdit/TaskQueueFloatingBall";
import {
  fetchLicenseClientDeviceId,
  fetchMyLicenses,
  type LicenseRecord,
} from "../../components/auth/licenseApi";
import type { WebSocketMessage } from "../../services/clients";
import { message } from "../../services/message";
import { projectService } from "../../services/projectService";
import omniStep2PipelineService from "../../services/omniStep2PipelineService";
import {
  areOmniScriptsEquivalent,
  makeScriptJson,
} from "../../components/projectEdit/omni/omniScriptWorkspaceUtils";
import { getOmniScriptRevision } from "./useOmniScriptSessionManager";
import type { Project, ProjectLatestTasks, TaskProgressState, VideoScript } from "../../types/project";
import { useWsTaskProgress, type WsProgressLog } from "../useWsTaskProgress";

const OMNI_PIPELINE_LICENSE_GATE_MSG =
  "运行 Omni 全链路需要先登录，并在个人中心绑定处于生效中且包含本机的 License。";

/** 与 CreateProjectModal / useProjectEditUploadStep 中 Omni License 错误判定一致 */
const OMNI_LICENSE_ERROR_RE = /license|401|403|登录|未授权|无权限|过期|校验|绑定/i;

function readSacvAuthTokenTrimmed(): string {
  if (typeof localStorage === "undefined") return "";
  return localStorage.getItem("sacv_auth_token")?.trim() ?? "";
}

function licenseCoversDevice(lic: LicenseRecord, deviceId: string): boolean {
  if (String(lic.status).toLowerCase() !== "active") return false;
  if (lic.expireAt) {
    const t = new Date(lic.expireAt).getTime();
    if (!Number.isNaN(t) && t < Date.now()) return false;
  }
  return lic.devices.some((d) => String(d.deviceId) === String(deviceId));
}

function hasActiveLicenseForThisDevice(licenses: LicenseRecord[], deviceId: string): boolean {
  if (!deviceId) return false;
  return licenses.some((lic) => licenseCoversDevice(lic, deviceId));
}

/** 与后端 task scope 一致 */
export const OMNI_STEP_SCOPE = {
  embed: "omni_copywriting_embed",
  shotMatch: "omni_shot_match",
  generateScript: "omni_generate_script",
} as const;

const OMNI_WS_IDLE = "__omni_ws_idle__";
const OMNI_PROGRESS_POLL_INTERVAL_MS = 1500;

const clampProgress = (value: unknown, fallback = 0) => {
  if (typeof value !== "number" || !Number.isFinite(value)) return fallback;
  return Math.max(0, Math.min(100, value));
};

const appendTaskLog = (
  task: TaskProgressState,
  setLogs: Dispatch<SetStateAction<WsProgressLog[]>>
) => {
  if (!task.message) return;
  const log: WsProgressLog = {
    timestamp: task.timestamp || new Date().toISOString(),
    message: task.message,
    phase: task.phase,
    type: task.type || task.status,
  };
  setLogs((prev) => {
    const last = prev[prev.length - 1];
    const lastKey = last ? `${last.timestamp}|${last.type || ""}|${last.phase || ""}|${last.message}` : "";
    const nextKey = `${log.timestamp}|${log.type || ""}|${log.phase || ""}|${log.message}`;
    if (lastKey === nextKey) return prev;
    return [...prev.slice(-19), log];
  });
};

export type OmniStepTestPhase = keyof typeof OMNI_STEP_SCOPE;

export interface UseOmniFullNarrationPipelineOptions {
  project?: Project | null;
  refreshProject: () => Promise<void>;
  onShowLogin?: () => void;
  onShowProfile?: () => void;
}

const isOmniScriptRevisionConflict = (err: unknown): boolean => {
  if (!(err instanceof Error)) return false;
  return /revision|脚本已被其他任务更新|409/.test(err.message);
};

export interface UseOmniFullNarrationPipelineReturn {
  omniEditedScript: string;
  omniScriptDirty: boolean;
  setOmniEditedScript: (s: string) => void;
  setOmniEditedScriptFromServer: (s: string) => void;
  syncOmniScriptToServer: (scriptOverride?: VideoScript) => Promise<VideoScript | null>;
  omniSegmentTtsQueueActive: boolean;
  setOmniSegmentTtsQueueActive: (active: boolean) => void;
  omniScriptSaving: boolean;
  handleSaveOmniScript: () => void;
  omniPipelineBusy: boolean;
  omniStepTestBusy: boolean;
  omniStepTestPhase: OmniStepTestPhase | null;
  /** 全链路或任一单步运行中（用于与其它生成任务互斥） */
  omniAnyPipelineBusy: boolean;
  omniPipelineProgress: number;
  omniPipelineLogs: WsProgressLog[];
  omniPipelineDisabled: boolean;
  omniPipelineDisabledReason?: string;
  /** 勾选后第 4 步跳过大模型，直接用上一步镜头候选拼装解说脚本以省成本 */
  skipGenerateScriptLlm: boolean;
  setSkipGenerateScriptLlm: (value: boolean) => void;
  /** 「使用本地模型」是否开启（用于复选框默认与提示） */
  localModelPipelineEnabled: boolean;
  handleRunOmniFullNarrationPipeline: () => Promise<void>;
  handleRunOmniStepEmbed: () => Promise<void>;
  handleRunOmniStepShotMatch: () => Promise<void>;
  handleRunOmniStepGenerateScript: () => Promise<void>;
}

const LATEST_TASK_KEY: Record<string, keyof ProjectLatestTasks> = {
  [OMNI_STEP_SCOPE.embed]: "omni_copywriting_embed",
  [OMNI_STEP_SCOPE.shotMatch]: "omni_shot_match",
  [OMNI_STEP_SCOPE.generateScript]: "omni_generate_script",
};

const isTaskFinished = (task?: TaskProgressState | null) => {
  if (!task) return false;
  const status = String(task.status || "").toLowerCase();
  const type = String(task.type || "").toLowerCase();
  return (
    type === "completed" ||
    status === "completed" ||
    status === "failed" ||
    type === "error" ||
    status === "cancelled" ||
    type === "cancelled"
  );
};

const isTaskActive = (t?: TaskProgressState | null) => {
  if (!t) return false;
  const status = String(t?.status || "").toLowerCase();
  const type = String(t?.type || "").toLowerCase();
  return status === "pending" || status === "processing" || status === "running" || status === "queued" || status === "waiting" || type === "progress";
};

export function useOmniFullNarrationPipeline(
  options: UseOmniFullNarrationPipelineOptions
): UseOmniFullNarrationPipelineReturn {
  const project = options.project;
  const onShowLogin = options.onShowLogin;
  const onShowProfile = options.onShowProfile;
  const { isAuthenticated, token } = useAuth();

  const [omniEditedScript, setOmniEditedScript] = useState("");
  const omniEditedScriptRef = useRef(omniEditedScript);
  const [omniScriptDirty, setOmniScriptDirty] = useState(false);
  const [omniScriptSaving, setOmniScriptSaving] = useState(false);
  const [omniSegmentTtsQueueActive, setOmniSegmentTtsQueueActive] = useState(false);

  const [omniPipelineBusy, setOmniPipelineBusy] = useState(false);
  const [omniPipelineProgress, setOmniPipelineProgress] = useState(0);
  const [omniPipelineLogs, setOmniPipelineLogs] = useState<WsProgressLog[]>([]);
  const [omniPipelineTaskId, setOmniPipelineTaskId] = useState<string | null>(null);

  const [omniStepTestBusy, setOmniStepTestBusy] = useState(false);
  const [omniStepTestPhase, setOmniStepTestPhase] = useState<OmniStepTestPhase | null>(null);
  const [omniStepTestScope, setOmniStepTestScope] = useState<string | null>(null);
  const [omniStepTestTaskId, setOmniStepTestTaskId] = useState<string | null>(null);

  const [localModelPipelineEnabled, setLocalModelPipelineEnabled] = useState(false);
  const [skipGenerateScriptLlm, setSkipGenerateScriptLlmState] = useState(false);
  const skipGenerateScriptLlmTouchedRef = useRef(false);
  const skipGenerateScriptLlmRef = useRef(skipGenerateScriptLlm);

  useEffect(() => {
    skipGenerateScriptLlmRef.current = skipGenerateScriptLlm;
  }, [skipGenerateScriptLlm]);

  const setSkipGenerateScriptLlm = useCallback((value: boolean) => {
    skipGenerateScriptLlmTouchedRef.current = true;
    setSkipGenerateScriptLlmState(value);
  }, []);

  // 只跟随「文案模型使用本地模型」配置，视觉开关不应影响脚本 LLM。
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const res = await omniStep2PipelineService.get();
        const data = res?.data as
          | {
              use_local_text_model?: boolean;
              use_local_model_pipeline?: boolean;
            }
          | undefined;
        if (cancelled || !data) return;
        const enabled =
          typeof data.use_local_text_model === "boolean"
            ? data.use_local_text_model
            : Boolean(data.use_local_model_pipeline);
        setLocalModelPipelineEnabled(enabled);
        if (!skipGenerateScriptLlmTouchedRef.current) {
          setSkipGenerateScriptLlmState(enabled);
        }
      } catch {
        /* 配置读取失败时保持默认（不跳过） */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const setOmniEditedScriptSafe = useCallback((raw: string) => {
    omniEditedScriptRef.current = raw;
    setOmniEditedScript(raw);
    setOmniScriptDirty(false);
  }, []);

  const setOmniEditedScriptUser = useCallback((raw: string) => {
    omniEditedScriptRef.current = raw;
    setOmniEditedScript(raw);
    setOmniScriptDirty(true);
  }, []);

  useEffect(() => {
    omniEditedScriptRef.current = omniEditedScript;
  }, [omniEditedScript]);

  useEffect(() => {
    if (!project?.script || omniScriptDirty || omniScriptSaving) return;
    try {
      if (omniEditedScript.trim()) {
        const local = JSON.parse(omniEditedScript) as VideoScript;
        if (areOmniScriptsEquivalent(local, project.script)) return;
      }
    } catch {
      /* 本地 JSON 无效时仍允许用服务端覆盖 */
    }
    const next = JSON.stringify(project.script, null, 2);
    if (next !== omniEditedScript) {
      setOmniEditedScriptSafe(next);
    }
  }, [omniEditedScript, omniScriptDirty, omniScriptSaving, project?.script, setOmniEditedScriptSafe]);

  const subtitleReady =
    Boolean(project?.subtitle_path) && (project?.subtitle_status ? project.subtitle_status === "ready" : true);

  const omniPipelineDisabledReason = useMemo(() => {
    if (!project?.video_path) return "请先上传视频";
    if (project?.subtitle_status === "extracting") return "字幕提取中";
    if (!subtitleReady) return "请先提取字幕或上传字幕";
    if (!project?.narration_copywriting?.content) return "请先生成并保存解说文案";
    if (!String(project?.omni_multimodal_json_path || "").trim()) return "请先完成 Omni 多模态管线";
    return undefined;
  }, [
    project?.narration_copywriting?.content,
    project?.omni_multimodal_json_path,
    project?.subtitle_status,
    project?.video_path,
    subtitleReady,
  ]);

  const omniPipelineDisabled = Boolean(omniPipelineDisabledReason);

  const omniAnyPipelineBusy = omniPipelineBusy || omniStepTestBusy;

  const omniWsScope = useMemo(() => {
    if (omniPipelineBusy && omniPipelineTaskId) return "omni_full_narration_pipeline";
    if (omniStepTestBusy && omniStepTestScope && omniStepTestTaskId) return omniStepTestScope;
    return OMNI_WS_IDLE;
  }, [omniPipelineBusy, omniPipelineTaskId, omniStepTestBusy, omniStepTestScope, omniStepTestTaskId]);

  const omniWsTaskId = useMemo(() => {
    if (omniPipelineBusy && omniPipelineTaskId) return omniPipelineTaskId;
    if (omniStepTestBusy && omniStepTestTaskId) return omniStepTestTaskId;
    return null;
  }, [omniPipelineBusy, omniPipelineTaskId, omniStepTestBusy, omniStepTestTaskId]);

  useEffect(() => {
    if (!project?.id) return;
    let cancelled = false;
    const load = async () => {
      try {
        const res = await projectService.getProjectRunningTasks(project.id);
        if (cancelled || !res) return;

        const full = res.omni_full_narration_pipeline;
        if (isTaskActive(full) && full?.task_id) {
          setOmniPipelineBusy(true);
          setOmniPipelineTaskId(String(full.task_id));
          setOmniPipelineProgress((prev) => Math.max(prev, clampProgress(full.progress, 1)));
          appendTaskLog(full, setOmniPipelineLogs);
          return;
        }

        const embed = res.omni_copywriting_embed;
        if (isTaskActive(embed) && embed?.task_id) {
          setOmniStepTestBusy(true);
          setOmniStepTestPhase("embed");
          setOmniStepTestScope(OMNI_STEP_SCOPE.embed);
          setOmniStepTestTaskId(String(embed.task_id));
          setOmniPipelineProgress((prev) => Math.max(prev, clampProgress(embed.progress, 1)));
          appendTaskLog(embed, setOmniPipelineLogs);
          return;
        }

        const shot = res.omni_shot_match;
        if (isTaskActive(shot) && shot?.task_id) {
          setOmniStepTestBusy(true);
          setOmniStepTestPhase("shotMatch");
          setOmniStepTestScope(OMNI_STEP_SCOPE.shotMatch);
          setOmniStepTestTaskId(String(shot.task_id));
          setOmniPipelineProgress((prev) => Math.max(prev, clampProgress(shot.progress, 1)));
          appendTaskLog(shot, setOmniPipelineLogs);
          return;
        }

        const gen = res.omni_generate_script;
        if (isTaskActive(gen) && gen?.task_id) {
          setOmniStepTestBusy(true);
          setOmniStepTestPhase("generateScript");
          setOmniStepTestScope(OMNI_STEP_SCOPE.generateScript);
          setOmniStepTestTaskId(String(gen.task_id));
          setOmniPipelineProgress((prev) => Math.max(prev, clampProgress(gen.progress, 1)));
          appendTaskLog(gen, setOmniPipelineLogs);
        }
      } catch {
        return;
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [project?.id]);

  useEffect(() => {
    if (!omniPipelineBusy || !project?.id || !omniPipelineTaskId) return;
    let stopped = false;
    const tick = async () => {
      try {
        const latest: ProjectLatestTasks | null = await projectService.getProjectLatestTasks(project.id);
        if (stopped || !latest?.omni_full_narration_pipeline) return;
        const t = latest.omni_full_narration_pipeline;
        if (t?.task_id && String(t.task_id) !== String(omniPipelineTaskId)) return;
        if (t && isTaskActive(t)) {
          setOmniPipelineProgress((prev) => Math.max(prev, clampProgress(t.progress, 1)));
          appendTaskLog(t, setOmniPipelineLogs);
          return;
        }
        if (isTaskFinished(t)) {
          setOmniPipelineBusy(false);
          const status = String(t.status || "").toLowerCase();
          const type = String(t.type || "").toLowerCase();
          setOmniPipelineProgress(status === "completed" || type === "completed" ? 100 : 0);
          appendTaskLog(t, setOmniPipelineLogs);
          void options.refreshProject();
        }
      } catch {
        return;
      }
    };
    void tick();
    const id = window.setInterval(() => void tick(), OMNI_PROGRESS_POLL_INTERVAL_MS);
    return () => {
      stopped = true;
      window.clearInterval(id);
    };
  }, [omniPipelineBusy, omniPipelineTaskId, options, project?.id]);

  useEffect(() => {
    if (!omniStepTestBusy || !project?.id || !omniStepTestTaskId || !omniStepTestScope) return;
    const key = LATEST_TASK_KEY[omniStepTestScope];
    if (!key) return;
    let stopped = false;
    const tick = async () => {
      try {
        const latest: ProjectLatestTasks | null = await projectService.getProjectLatestTasks(project.id);
        if (stopped || !latest) return;
        const t = latest[key];
        if (t?.task_id && String(t.task_id) !== String(omniStepTestTaskId)) return;
        if (t && isTaskActive(t)) {
          setOmniPipelineProgress((prev) => Math.max(prev, clampProgress(t.progress, 1)));
          appendTaskLog(t, setOmniPipelineLogs);
          return;
        }
        if (isTaskFinished(t)) {
          setOmniStepTestBusy(false);
          setOmniStepTestTaskId(null);
          setOmniStepTestScope(null);
          setOmniStepTestPhase(null);
          const status = String(t?.status || "").toLowerCase();
          const type = String(t?.type || "").toLowerCase();
          setOmniPipelineProgress(status === "completed" || type === "completed" ? 100 : 0);
          if (t) appendTaskLog(t, setOmniPipelineLogs);
          void options.refreshProject();
        }
      } catch {
        return;
      }
    };
    void tick();
    const interval = window.setInterval(() => void tick(), OMNI_PROGRESS_POLL_INTERVAL_MS);
    return () => {
      stopped = true;
      window.clearInterval(interval);
    };
  }, [omniStepTestBusy, omniStepTestTaskId, omniStepTestScope, options, project?.id]);

  const handleRunOmniFullNarrationPipeline = useCallback(async () => {
    if (!project?.id) return;
    if (omniPipelineDisabled) {
      if (omniPipelineDisabledReason) message.error(omniPipelineDisabledReason);
      return;
    }
    if (omniStepTestBusy) return;
    if (omniPipelineBusy) return;

    const apiToken = (token?.trim() || readSacvAuthTokenTrimmed());
    if (!apiToken) {
      message.error(OMNI_PIPELINE_LICENSE_GATE_MSG);
      onShowLogin?.();
      return;
    }

    setOmniPipelineBusy(true);
    try {
      const deviceId = await fetchLicenseClientDeviceId();
      const licenses = await fetchMyLicenses(apiToken);
      if (!hasActiveLicenseForThisDevice(licenses, deviceId)) {
        message.error("请先在个人中心绑定处于生效中且包含本机的 License。");
        onShowProfile?.();
        setOmniPipelineBusy(false);
        return;
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      if (OMNI_LICENSE_ERROR_RE.test(msg)) {
        if (!isAuthenticated) onShowLogin?.();
        else onShowProfile?.();
      }
      message.error(msg);
      setOmniPipelineBusy(false);
      return;
    }

    setOmniPipelineProgress(0);
    setOmniPipelineLogs([]);
    setOmniPipelineTaskId(null);
    try {
      await projectService.flushPendingUpdates(project.id);
      const res = await projectService.runOmniFullNarrationPipeline(project.id, {
        force: false,
        skip_generate_script_llm: skipGenerateScriptLlmRef.current,
      });
      const tid = res?.task_id ? String(res.task_id) : "";
      if (!tid) {
        message.error(res?.message || "提交全链路任务失败");
        setOmniPipelineBusy(false);
        return;
      }
      setOmniPipelineTaskId(tid);
      window.dispatchEvent(new CustomEvent(TASK_SUBMITTED_EVENT));
      message.success(res?.message || "全链路任务已提交");
    } catch (e) {
      const msg = e instanceof Error ? e.message : "提交 Omni 全链路任务失败";
      if (OMNI_LICENSE_ERROR_RE.test(msg)) {
        if (!isAuthenticated) onShowLogin?.();
        else onShowProfile?.();
      }
      message.error(msg);
      setOmniPipelineBusy(false);
    }
  }, [
    isAuthenticated,
    omniPipelineBusy,
    omniPipelineDisabled,
    omniPipelineDisabledReason,
    omniStepTestBusy,
    onShowLogin,
    onShowProfile,
    project?.id,
    token,
  ]);

  const runOmniStep = useCallback(
    async (
      phase: OmniStepTestPhase,
      scope: string,
      submit: () => Promise<{ task_id?: string; status?: string; message?: string }>
    ) => {
      if (!project?.id) return;
      if (omniPipelineDisabled) {
        if (omniPipelineDisabledReason) message.error(omniPipelineDisabledReason);
        return;
      }
      if (omniPipelineBusy || omniStepTestBusy) return;
      setOmniStepTestBusy(true);
      setOmniStepTestPhase(phase);
      setOmniStepTestScope(scope);
      setOmniPipelineProgress(0);
      setOmniPipelineLogs([]);
      setOmniStepTestTaskId(null);
      try {
        await projectService.flushPendingUpdates(project.id);
        const res = await submit();
        const tid = res?.task_id ? String(res.task_id) : "";
        if (!tid) {
          message.error(res?.message || "提交任务失败");
          setOmniStepTestBusy(false);
          setOmniStepTestPhase(null);
          setOmniStepTestScope(null);
          return;
        }
        setOmniStepTestTaskId(tid);
        window.dispatchEvent(new CustomEvent(TASK_SUBMITTED_EVENT));
        message.success(res?.message || "任务已提交");
      } catch (e) {
        message.error(e instanceof Error ? e.message : "提交 Omni 单步任务失败");
        setOmniStepTestBusy(false);
        setOmniStepTestPhase(null);
        setOmniStepTestScope(null);
      }
    },
    [omniPipelineBusy, omniPipelineDisabled, omniPipelineDisabledReason, omniStepTestBusy, project?.id]
  );

  const handleRunOmniStepEmbed = useCallback(async () => {
    if (!project?.id) return;
    await runOmniStep("embed", OMNI_STEP_SCOPE.embed, () =>
      projectService.runOmniCopywritingStructEmbed(project.id, { force: false })
    );
  }, [project?.id, runOmniStep]);

  const handleRunOmniStepShotMatch = useCallback(async () => {
    if (!project?.id) return;
    await runOmniStep("shotMatch", OMNI_STEP_SCOPE.shotMatch, () =>
      projectService.runOmniShotMatch(project.id, { force: false })
    );
  }, [project?.id, runOmniStep]);

  const handleRunOmniStepGenerateScript = useCallback(async () => {
    if (!project?.id) return;
    await runOmniStep("generateScript", OMNI_STEP_SCOPE.generateScript, () =>
      projectService.runOmniStepGenerateScript(project.id, { force: false })
    );
  }, [project?.id, runOmniStep]);

  const syncOmniScriptToServer = useCallback(
    async (scriptOverride?: VideoScript): Promise<VideoScript | null> => {
      if (!project?.id) return null;
      await projectService.flushPendingUpdates(project.id);
      let scriptData: VideoScript;
      try {
        if (scriptOverride) {
          scriptData = scriptOverride;
        } else {
          const raw = omniEditedScriptRef.current;
          if (!raw.trim()) return null;
          scriptData = JSON.parse(raw) as VideoScript;
        }
      } catch (err) {
        if (err instanceof SyntaxError) {
          message.error("脚本格式错误，请检查 JSON 格式是否正确");
        }
        if (err instanceof Error && /revision|脚本|409|变化|更新/.test(err.message)) {
          await options.refreshProject();
        }
        return null;
      }
      setOmniScriptSaving(true);
      try {
        const saveOnce = async (payload: VideoScript): Promise<VideoScript> => {
          const expectedRevision = getOmniScriptRevision(payload);
          return projectService.saveScript(project.id, payload, expectedRevision);
        };

        let saved: VideoScript;
        try {
          saved = await saveOnce(scriptData);
        } catch (err) {
          if (!isOmniScriptRevisionConflict(err)) throw err;
          await options.refreshProject();
          const fresh = await projectService.getProject(project.id);
          const serverRev = getOmniScriptRevision(fresh.script);
          const retryPayload: VideoScript = {
            ...scriptData,
            metadata: { ...(scriptData.metadata ?? {}), omni_revision: serverRev },
          };
          saved = await saveOnce(retryPayload);
        }

        let localNow: VideoScript;
        try {
          localNow = JSON.parse(omniEditedScriptRef.current) as VideoScript;
        } catch {
          localNow = scriptData;
        }
        if (!areOmniScriptsEquivalent(localNow, scriptData)) {
          const patchedJson = makeScriptJson({
            ...localNow,
            metadata: {
              ...(localNow.metadata ?? {}),
              omni_revision: getOmniScriptRevision(saved),
              updated_at: saved.metadata?.updated_at ?? localNow.metadata?.updated_at,
            },
          });
          omniEditedScriptRef.current = patchedJson;
          setOmniEditedScript(patchedJson);
          return saved;
        }
        const savedJson = makeScriptJson(saved);
        omniEditedScriptRef.current = savedJson;
        setOmniEditedScriptSafe(savedJson);
        await options.refreshProject();
        return saved;
      } catch (err) {
        if (isOmniScriptRevisionConflict(err)) {
          await options.refreshProject();
        }
        message.error(err instanceof Error ? err.message : "保存脚本失败");
        return null;
      } finally {
        setOmniScriptSaving(false);
      }
    },
    [options, project?.id, setOmniEditedScriptSafe]
  );

  const handleSaveOmniScript = useCallback(
    async (opts?: { silent?: boolean }) => {
      if (!omniEditedScript.trim()) {
        if (!opts?.silent) message.error("脚本内容不能为空");
        return;
      }
      const saved = await syncOmniScriptToServer();
      if (saved && !opts?.silent) message.success("脚本保存成功！");
    },
    [omniEditedScript, syncOmniScriptToServer]
  );

  useEffect(() => {
    if (!omniScriptDirty || !omniEditedScript.trim() || !project?.id) {
      return undefined;
    }
    try {
      JSON.parse(omniEditedScript);
    } catch {
      return undefined;
    }
    const timer = window.setTimeout(() => {
      void handleSaveOmniScript({ silent: true });
    }, 800);
    return () => window.clearTimeout(timer);
  }, [handleSaveOmniScript, omniEditedScript, omniScriptDirty, project?.id]);

  useWsTaskProgress({
    scope: omniWsScope,
    projectId: project?.id,
    taskId: omniWsTaskId,
    onProgress: (progress) => setOmniPipelineProgress((prev) => Math.max(prev, progress)),
    onLog: (log) => setOmniPipelineLogs((prev) => [...prev.slice(-19), log]),
    onCompleted: (m: WebSocketMessage) => {
      const s = (m as { scope?: string }).scope;
      if (s === "omni_full_narration_pipeline") {
        setOmniPipelineBusy(false);
        setOmniPipelineProgress(100);
        message.success("Omni 解说脚本全链路已完成");
        void options.refreshProject();
        return;
      }
      if (s === OMNI_STEP_SCOPE.embed || s === OMNI_STEP_SCOPE.shotMatch || s === OMNI_STEP_SCOPE.generateScript) {
        setOmniStepTestBusy(false);
        setOmniStepTestTaskId(null);
        setOmniStepTestScope(null);
        setOmniStepTestPhase(null);
        setOmniPipelineProgress(100);
        const label = s === OMNI_STEP_SCOPE.embed ? "文案结构化+向量" : s === OMNI_STEP_SCOPE.shotMatch ? "镜头匹配" : "解说脚本生成";
        message.success(`Omni 单步（${label}）已完成`);
        void options.refreshProject();
      }
    },
    onCancelled: (m: WebSocketMessage) => {
      const s = (m as { scope?: string }).scope;
      if (s === "omni_full_narration_pipeline") {
        setOmniPipelineBusy(false);
        setOmniPipelineProgress(0);
        message.info(m.message || "全链路任务已取消");
        void options.refreshProject();
        return;
      }
      if (s === OMNI_STEP_SCOPE.embed || s === OMNI_STEP_SCOPE.shotMatch || s === OMNI_STEP_SCOPE.generateScript) {
        setOmniStepTestBusy(false);
        setOmniStepTestTaskId(null);
        setOmniStepTestScope(null);
        setOmniStepTestPhase(null);
        setOmniPipelineProgress(0);
        message.info(m.message || "单步任务已取消");
        void options.refreshProject();
      }
    },
    onError: (m: WebSocketMessage) => {
      const s = (m as { scope?: string }).scope;
      if (s === "omni_full_narration_pipeline") {
        setOmniPipelineBusy(false);
        setOmniPipelineProgress(0);
        message.error(m.message || "全链路任务失败");
        return;
      }
      if (s === OMNI_STEP_SCOPE.embed || s === OMNI_STEP_SCOPE.shotMatch || s === OMNI_STEP_SCOPE.generateScript) {
        setOmniStepTestBusy(false);
        setOmniStepTestTaskId(null);
        setOmniStepTestScope(null);
        setOmniStepTestPhase(null);
        setOmniPipelineProgress(0);
        message.error(m.message || "单步任务失败");
      }
    },
  });

  return {
    omniEditedScript,
    omniScriptDirty,
    setOmniEditedScript: setOmniEditedScriptUser,
    setOmniEditedScriptFromServer: setOmniEditedScriptSafe,
    syncOmniScriptToServer,
    omniSegmentTtsQueueActive,
    setOmniSegmentTtsQueueActive,
    omniScriptSaving,
    handleSaveOmniScript,
    omniPipelineBusy,
    omniStepTestBusy,
    omniStepTestPhase,
    omniAnyPipelineBusy,
    omniPipelineProgress,
    omniPipelineLogs,
    omniPipelineDisabled,
    omniPipelineDisabledReason,
    skipGenerateScriptLlm,
    setSkipGenerateScriptLlm,
    localModelPipelineEnabled,
    handleRunOmniFullNarrationPipeline,
    handleRunOmniStepEmbed,
    handleRunOmniStepShotMatch,
    handleRunOmniStepGenerateScript,
  };
}

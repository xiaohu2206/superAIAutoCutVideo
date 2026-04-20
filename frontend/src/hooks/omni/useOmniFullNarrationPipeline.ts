import { useCallback, useEffect, useMemo, useState } from "react";
import type { WebSocketMessage } from "../../services/clients";
import { message } from "../../services/message";
import { projectService } from "../../services/projectService";
import type { Project, ProjectLatestTasks, TaskProgressState, VideoScript } from "../../types/project";
import { useWsTaskProgress, type WsProgressLog } from "../useWsTaskProgress";

/** 与后端 task scope 一致 */
export const OMNI_STEP_SCOPE = {
  embed: "omni_copywriting_embed",
  shotMatch: "omni_shot_match",
  generateScript: "omni_generate_script",
} as const;

const OMNI_WS_IDLE = "__omni_ws_idle__";

export type OmniStepTestPhase = keyof typeof OMNI_STEP_SCOPE;

export interface UseOmniFullNarrationPipelineOptions {
  project?: Project | null;
  refreshProject: () => Promise<void>;
}

export interface UseOmniFullNarrationPipelineReturn {
  omniEditedScript: string;
  setOmniEditedScript: (s: string) => void;
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
  return status === "pending" || status === "processing" || status === "running" || type === "progress";
};

export function useOmniFullNarrationPipeline(
  options: UseOmniFullNarrationPipelineOptions
): UseOmniFullNarrationPipelineReturn {
  const project = options.project;

  const [omniEditedScript, setOmniEditedScript] = useState("");
  const [omniScriptDirty, setOmniScriptDirty] = useState(false);
  const [omniScriptSaving, setOmniScriptSaving] = useState(false);

  const [omniPipelineBusy, setOmniPipelineBusy] = useState(false);
  const [omniPipelineProgress, setOmniPipelineProgress] = useState(0);
  const [omniPipelineLogs, setOmniPipelineLogs] = useState<WsProgressLog[]>([]);
  const [omniPipelineTaskId, setOmniPipelineTaskId] = useState<string | null>(null);

  const [omniStepTestBusy, setOmniStepTestBusy] = useState(false);
  const [omniStepTestPhase, setOmniStepTestPhase] = useState<OmniStepTestPhase | null>(null);
  const [omniStepTestScope, setOmniStepTestScope] = useState<string | null>(null);
  const [omniStepTestTaskId, setOmniStepTestTaskId] = useState<string | null>(null);

  const setOmniEditedScriptSafe = useCallback((raw: string) => {
    setOmniEditedScript(raw);
    setOmniScriptDirty(false);
  }, []);

  const setOmniEditedScriptUser = useCallback((raw: string) => {
    setOmniEditedScript(raw);
    setOmniScriptDirty(true);
  }, []);

  useEffect(() => {
    if (!project?.script) return;
    const next = JSON.stringify(project.script, null, 2);
    if (!omniScriptDirty && next !== omniEditedScript) {
      setOmniEditedScriptSafe(next);
    }
  }, [omniEditedScript, omniScriptDirty, project?.script, setOmniEditedScriptSafe]);

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
          setOmniPipelineProgress(typeof full.progress === "number" ? full.progress : 1);
          if (full.message) {
            setOmniPipelineLogs([
              {
                timestamp: full.timestamp || new Date().toISOString(),
                message: full.message,
                type: full.type,
                phase: full.phase,
              },
            ]);
          }
          return;
        }

        const embed = res.omni_copywriting_embed;
        if (isTaskActive(embed) && embed?.task_id) {
          setOmniStepTestBusy(true);
          setOmniStepTestPhase("embed");
          setOmniStepTestScope(OMNI_STEP_SCOPE.embed);
          setOmniStepTestTaskId(String(embed.task_id));
          setOmniPipelineProgress(typeof embed.progress === "number" ? embed.progress : 1);
          if (embed.message) {
            setOmniPipelineLogs([
              {
                timestamp: embed.timestamp || new Date().toISOString(),
                message: embed.message,
                type: embed.type,
                phase: embed.phase,
              },
            ]);
          }
          return;
        }

        const shot = res.omni_shot_match;
        if (isTaskActive(shot) && shot?.task_id) {
          setOmniStepTestBusy(true);
          setOmniStepTestPhase("shotMatch");
          setOmniStepTestScope(OMNI_STEP_SCOPE.shotMatch);
          setOmniStepTestTaskId(String(shot.task_id));
          setOmniPipelineProgress(typeof shot.progress === "number" ? shot.progress : 1);
          if (shot.message) {
            setOmniPipelineLogs([
              {
                timestamp: shot.timestamp || new Date().toISOString(),
                message: shot.message,
                type: shot.type,
                phase: shot.phase,
              },
            ]);
          }
          return;
        }

        const gen = res.omni_generate_script;
        if (isTaskActive(gen) && gen?.task_id) {
          setOmniStepTestBusy(true);
          setOmniStepTestPhase("generateScript");
          setOmniStepTestScope(OMNI_STEP_SCOPE.generateScript);
          setOmniStepTestTaskId(String(gen.task_id));
          setOmniPipelineProgress(typeof gen.progress === "number" ? gen.progress : 1);
          if (gen.message) {
            setOmniPipelineLogs([
              {
                timestamp: gen.timestamp || new Date().toISOString(),
                message: gen.message,
                type: gen.type,
                phase: gen.phase,
              },
            ]);
          }
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
        if (isTaskFinished(t)) {
          setOmniPipelineBusy(false);
          setOmniPipelineProgress(100);
          void options.refreshProject();
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
        if (isTaskFinished(t)) {
          setOmniStepTestBusy(false);
          setOmniStepTestTaskId(null);
          setOmniStepTestScope(null);
          setOmniStepTestPhase(null);
          setOmniPipelineProgress(100);
          void options.refreshProject();
        }
      } catch {
        return;
      }
    };
    void tick();
    const interval = window.setInterval(() => void tick(), 1500);
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
    setOmniPipelineBusy(true);
    setOmniPipelineProgress(0);
    setOmniPipelineLogs([]);
    setOmniPipelineTaskId(null);
    try {
      await projectService.flushPendingUpdates(project.id);
      const res = await projectService.runOmniFullNarrationPipeline(project.id, { force: false });
      const tid = res?.task_id ? String(res.task_id) : "";
      if (!tid) {
        message.error(res?.message || "提交全链路任务失败");
        setOmniPipelineBusy(false);
        return;
      }
      setOmniPipelineTaskId(tid);
      message.success(res?.message || "全链路任务已提交");
    } catch (e) {
      message.error(e instanceof Error ? e.message : "提交 Omni 全链路任务失败");
      setOmniPipelineBusy(false);
    }
  }, [omniPipelineDisabled, omniPipelineDisabledReason, omniStepTestBusy, project?.id]);

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

  const handleSaveOmniScript = useCallback(async () => {
    if (!omniEditedScript.trim()) {
      message.error("脚本内容不能为空");
      return;
    }
    try {
      if (!project?.id) return;
      const scriptData: VideoScript = JSON.parse(omniEditedScript);
      setOmniScriptSaving(true);
      await projectService.saveScript(project.id, scriptData);
      setOmniScriptDirty(false);
      message.success("脚本保存成功！");
      void options.refreshProject();
    } catch (err) {
      if (err instanceof SyntaxError) {
        message.error("脚本格式错误，请检查 JSON 格式是否正确");
      } else {
        message.error(err instanceof Error ? err.message : "保存脚本失败");
      }
    } finally {
      setOmniScriptSaving(false);
    }
  }, [omniEditedScript, options, project?.id]);

  useWsTaskProgress({
    scope: omniWsScope,
    projectId: project?.id,
    taskId: omniWsTaskId,
    onProgress: setOmniPipelineProgress,
    onLog: (log) => setOmniPipelineLogs((prev) => [...prev, log]),
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
    setOmniEditedScript: setOmniEditedScriptUser,
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
    handleRunOmniFullNarrationPipeline,
    handleRunOmniStepEmbed,
    handleRunOmniStepShotMatch,
    handleRunOmniStepGenerateScript,
  };
}

import { useCallback, useEffect, useMemo, useState } from "react";
import type { WebSocketMessage } from "../../services/clients";
import { message } from "../../services/message";
import { projectService } from "../../services/projectService";
import type { Project, ProjectLatestTasks, TaskProgressState, VideoScript } from "../../types/project";
import { useWsTaskProgress, type WsProgressLog } from "../useWsTaskProgress";

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
  omniPipelineProgress: number;
  omniPipelineLogs: WsProgressLog[];
  omniPipelineDisabled: boolean;
  omniPipelineDisabledReason?: string;
  handleRunOmniFullNarrationPipeline: () => Promise<void>;
}

const isTaskFinished = (task?: TaskProgressState | null) => {
  if (!task) return false;
  const status = String(task.status || "").toLowerCase();
  const type = String(task.type || "").toLowerCase();
  return type === "completed" || status === "completed" || status === "failed" || type === "error" || status === "cancelled" || type === "cancelled";
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

  const subtitleReady = Boolean(project?.subtitle_path) &&
    (project?.subtitle_status ? project.subtitle_status === "ready" : true);

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

  useEffect(() => {
    if (!project?.id) return;
    let cancelled = false;
    const load = async () => {
      try {
        const res = await projectService.getProjectRunningTasks(project.id);
        if (cancelled || !res?.omni_full_narration_pipeline) return;
        const t = res.omni_full_narration_pipeline;
        const status = String(t?.status || "").toLowerCase();
        const type = String(t?.type || "").toLowerCase();
        const active =
          status === "pending" || status === "processing" || status === "running" || type === "progress";
        if (active && t?.task_id) {
          setOmniPipelineBusy(true);
          setOmniPipelineTaskId(String(t.task_id));
          setOmniPipelineProgress(typeof t.progress === "number" ? t.progress : 1);
          if (t.message) {
            setOmniPipelineLogs([
              { timestamp: t.timestamp || new Date().toISOString(), message: t.message, type: t.type, phase: t.phase },
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

  const handleRunOmniFullNarrationPipeline = useCallback(async () => {
    if (!project?.id) return;
    if (omniPipelineDisabled) {
      if (omniPipelineDisabledReason) message.error(omniPipelineDisabledReason);
      return;
    }
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
  }, [omniPipelineDisabled, omniPipelineDisabledReason, project?.id]);

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
    scope: "omni_full_narration_pipeline",
    projectId: project?.id,
    taskId: omniPipelineTaskId,
    onProgress: setOmniPipelineProgress,
    onLog: (log) => setOmniPipelineLogs((prev) => [...prev, log]),
    onCompleted: () => {
      setOmniPipelineBusy(false);
      setOmniPipelineProgress(100);
      message.success("Omni 解说脚本全链路已完成");
      void options.refreshProject();
    },
    onCancelled: (m: WebSocketMessage) => {
      setOmniPipelineBusy(false);
      setOmniPipelineProgress(0);
      message.info(m.message || "全链路任务已取消");
      void options.refreshProject();
    },
    onError: (m: WebSocketMessage) => {
      setOmniPipelineBusy(false);
      setOmniPipelineProgress(0);
      message.error(m.message || "全链路任务失败");
    },
  });

  return {
    omniEditedScript,
    setOmniEditedScript: setOmniEditedScriptUser,
    omniScriptSaving,
    handleSaveOmniScript,
    omniPipelineBusy,
    omniPipelineProgress,
    omniPipelineLogs,
    omniPipelineDisabled,
    omniPipelineDisabledReason,
    handleRunOmniFullNarrationPipeline,
  };
}

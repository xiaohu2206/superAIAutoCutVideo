import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { WebSocketMessage } from "../services/clients";
import { projectService } from "../services/projectService";
import { TASK_SUBMITTED_EVENT } from "../components/projectEdit/TaskQueueFloatingBall";
import type {
  GenerateCopywritingRequest,
  GenerateScriptRequest,
  NarrationCopywriting,
  Project,
  ProjectRunningTasks,
  TaskProgressState,
  VideoScript,
} from "../types/project";
import { useWsTaskProgress, type WsProgressLog } from "./useWsTaskProgress";

const PROGRESS_POLL_INTERVAL_MS = 1500;
const TERMINAL_STATUSES = new Set(["completed", "failed", "cancelled"]);
const ACTIVE_STATUSES = new Set(["running", "processing", "pending", "queued", "waiting"]);
const TERMINAL_TYPES = new Set(["completed", "error", "cancelled"]);

const clampProgress = (value: unknown, fallback = 0) => {
  if (typeof value !== "number" || !Number.isFinite(value)) return fallback;
  return Math.max(0, Math.min(100, value));
};

const taskTimestampMs = (task?: TaskProgressState | null) => {
  if (!task?.timestamp) return 0;
  const parsed = Date.parse(task.timestamp);
  return Number.isFinite(parsed) ? parsed : 0;
};

const taskLog = (task: TaskProgressState): WsProgressLog | null => {
  if (!task.message) return null;
  return {
    timestamp: task.timestamp || new Date().toISOString(),
    message: task.message,
    phase: task.phase,
    type: task.type || task.status,
  };
};

export interface UseProjectEditGenerateStepOptions {
  project?: Project | null;
  extractingSubtitle: boolean;
  generateCopywriting: (data: GenerateCopywritingRequest) => Promise<NarrationCopywriting>;
  saveCopywriting: (copywriting: NarrationCopywriting) => Promise<void>;
  generateScript: (data: GenerateScriptRequest) => Promise<VideoScript>;
  saveScript: (script: VideoScript) => Promise<void>;
  generateVideo: () => Promise<{ task_id: string; scope?: string } | null>;
  refreshProject: () => Promise<void>;
  showSuccess: (text: string, durationSec?: number) => void;
  showErrorText: (text: string, durationSec?: number) => void;
  showError: (err: unknown, fallback: string) => void;
}

export interface UseProjectEditGenerateStepReturn {
  isGeneratingCopywriting: boolean;
  handleGenerateCopywriting: () => void;
  handleStopGenerateCopywriting: () => void;
  isStoppingCopywriting: boolean;
  copywritingGenProgress: number;
  copywritingGenLogs: WsProgressLog[];
  editedCopywriting: string;
  setEditedCopywriting: (copywriting: string) => void;
  isSavingCopywriting: boolean;
  handleSaveCopywriting: (content?: string) => void;
  isGeneratingScript: boolean;
  handleGenerateScript: () => void;
  generateScriptDisabled: boolean;
  generateScriptDisabledReason?: string;
  scriptGenProgress: number;
  scriptGenLogs: WsProgressLog[];
  isGeneratingVideo: boolean;
  handleGenerateVideo: () => void;
  handleStopGenerateVideo: () => void;
  isStoppingVideo: boolean;
  videoGenProgress: number;
  videoGenLogs: WsProgressLog[];
  isGeneratingDraft: boolean;
  handleGenerateDraft: () => void;
  handleStopGenerateDraft: () => void;
  isStoppingDraft: boolean;
  draftGenProgress: number;
  draftGenLogs: WsProgressLog[];
  showMergedPreview: boolean;
  setShowMergedPreview: React.Dispatch<React.SetStateAction<boolean>>;
  editedScript: string;
  setEditedScript: (script: string) => void;
  isSaving: boolean;
  handleSaveScript: () => void;
}

export function useProjectEditGenerateStep(
  options: UseProjectEditGenerateStepOptions
): UseProjectEditGenerateStepReturn {
  const project = options.project;

  const [editedCopywriting, setEditedCopywriting] = useState<string>("");
  const [hasInitializedCopywriting, setHasInitializedCopywriting] = useState(false);
  const [copywritingDirty, setCopywritingDirty] = useState(false);
  const [isGeneratingCopywriting, setIsGeneratingCopywriting] = useState(false);
  const [isSavingCopywriting, setIsSavingCopywriting] = useState(false);

  const [editedScript, setEditedScript] = useState<string>("");
  const [hasInitializedScript, setHasInitializedScript] = useState(false);
  const [scriptDirty, setScriptDirty] = useState(false);
  const [isGeneratingScript, setIsGeneratingScript] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isGeneratingVideo, setIsGeneratingVideo] = useState(false);
  const [isGeneratingDraft, setIsGeneratingDraft] = useState(false);
  const [isStoppingCopywriting, setIsStoppingCopywriting] = useState(false);
  const [isStoppingVideo, setIsStoppingVideo] = useState(false);
  const [isStoppingDraft, setIsStoppingDraft] = useState(false);
  const [draftTaskId, setDraftTaskId] = useState<string | null>(null);
  const [videoTaskId, setVideoTaskId] = useState<string | null>(null);
  const [showMergedPreview, setShowMergedPreview] = useState(false);

  const [copywritingGenProgress, setCopywritingGenProgress] = useState<number>(0);
  const [copywritingGenLogs, setCopywritingGenLogs] = useState<WsProgressLog[]>([]);
  const [copywritingTaskId, setCopywritingTaskId] = useState<string | null>(null);
  const [scriptGenProgress, setScriptGenProgress] = useState<number>(0);
  const [scriptGenLogs, setScriptGenLogs] = useState<WsProgressLog[]>([]);
  const [videoGenProgress, setVideoGenProgress] = useState<number>(0);
  const [videoGenLogs, setVideoGenLogs] = useState<WsProgressLog[]>([]);
  const [draftGenProgress, setDraftGenProgress] = useState<number>(0);
  const [draftGenLogs, setDraftGenLogs] = useState<WsProgressLog[]>([]);
  const copywritingStartedAtRef = useRef<number>(0);
  const scriptStartedAtRef = useRef<number>(0);
  const videoStartedAtRef = useRef<number>(0);
  const draftStartedAtRef = useRef<number>(0);

  const isTaskActive = useCallback((task?: TaskProgressState | null) => {
    if (!task) return false;
    const status = String(task.status || "").toLowerCase();
    const type = String(task.type || "").toLowerCase();
    if (type === "progress") return true;
    return ACTIVE_STATUSES.has(status);
  }, []);

  const applyRunningTask = useCallback((task: TaskProgressState | null | undefined, apply: (t: TaskProgressState) => void) => {
    if (!task) return;
    if (!isTaskActive(task)) return;
    apply(task);
  }, [isTaskActive]);

  const isTaskFinished = useCallback((task: TaskProgressState | null | undefined) => {
    if (!task) return false;
    const status = String(task.status || "").toLowerCase();
    const type = String(task.type || "").toLowerCase();
    return TERMINAL_TYPES.has(type) || TERMINAL_STATUSES.has(status);
  }, []);

  const taskIsAfterStart = useCallback((task: TaskProgressState | null | undefined, startedAt: number) => {
    if (!task || !startedAt) return true;
    const ts = taskTimestampMs(task);
    return !ts || ts >= startedAt - 2000;
  }, []);

  const appendTaskLog = useCallback((task: TaskProgressState, setLogs: React.Dispatch<React.SetStateAction<WsProgressLog[]>>) => {
    const log = taskLog(task);
    if (!log) return;
    setLogs((prev) => {
      const key = `${log.timestamp}|${log.type || ""}|${log.phase || ""}|${log.message}`;
      const last = prev[prev.length - 1];
      const lastKey = last ? `${last.timestamp}|${last.type || ""}|${last.phase || ""}|${last.message}` : "";
      if (key === lastKey) return prev;
      return [...prev.slice(-19), log];
    });
  }, []);

  const applyTaskSnapshot = useCallback((
    task: TaskProgressState | null | undefined,
    startedAt: number,
    setBusy: React.Dispatch<React.SetStateAction<boolean>>,
    setProgress: React.Dispatch<React.SetStateAction<number>>,
    setLogs: React.Dispatch<React.SetStateAction<WsProgressLog[]>>,
    setTaskId?: React.Dispatch<React.SetStateAction<string | null>>,
  ) => {
    if (!task || !taskIsAfterStart(task, startedAt)) return;

    if (task.task_id && setTaskId) {
      setTaskId(task.task_id);
    }

    if (isTaskActive(task)) {
      setBusy(true);
      const fallback = String(task.status || "").toLowerCase() === "queued" ? 1 : 0;
      const next = clampProgress(task.progress, fallback);
      setProgress((prev) => Math.max(prev, next));
      appendTaskLog(task, setLogs);
      return;
    }

    if (isTaskFinished(task)) {
      setBusy(false);
      const status = String(task.status || "").toLowerCase();
      const type = String(task.type || "").toLowerCase();
      setProgress(status === "completed" || type === "completed" ? 100 : 0);
      appendTaskLog(task, setLogs);
    }
  }, [appendTaskLog, isTaskActive, isTaskFinished, taskIsAfterStart]);

  const setEditedCopywritingSafe = useCallback((copywriting: string) => {
    setEditedCopywriting(copywriting);
    setHasInitializedCopywriting(true);
    setCopywritingDirty(false);
  }, []);

  const setEditedCopywritingUser = useCallback((copywriting: string) => {
    setEditedCopywriting(copywriting);
    setHasInitializedCopywriting(true);
    setCopywritingDirty(true);
  }, []);

  const setEditedScriptSafe = useCallback((script: string) => {
    setEditedScript(script);
    setHasInitializedScript(true);
    setScriptDirty(false);
  }, []);

  const setEditedScriptUser = useCallback((script: string) => {
    setEditedScript(script);
    setHasInitializedScript(true);
    setScriptDirty(true);
  }, []);

  useEffect(() => {
    if (!project?.narration_copywriting) return;
    const next = String(project.narration_copywriting.content || "");
    if (!hasInitializedCopywriting || (!copywritingDirty && next !== editedCopywriting)) {
      setEditedCopywritingSafe(next);
    }
  }, [
    copywritingDirty,
    editedCopywriting,
    hasInitializedCopywriting,
    project?.narration_copywriting,
    setEditedCopywritingSafe,
  ]);

  useEffect(() => {
    if (!project?.script) return;
    const next = JSON.stringify(project.script, null, 2);
    if (!hasInitializedScript || (!scriptDirty && next !== editedScript)) {
      setEditedScriptSafe(next);
    }
  }, [editedScript, hasInitializedScript, project?.script, scriptDirty, setEditedScriptSafe]);

  const subtitleReady = Boolean(project?.subtitle_path) &&
    (project?.subtitle_status ? project.subtitle_status === "ready" : true);

  const generateScriptDisabledReason = useMemo(() => {
    if (!project?.video_path) return "请先上传视频";
    if (options.extractingSubtitle || project?.subtitle_status === "extracting") return "字幕提取中";
    if (!subtitleReady) return "请先提取字幕或上传字幕";
    if (!project?.narration_copywriting?.content) return "请先生成解说文案";
    return undefined;
  }, [
    options.extractingSubtitle,
    project?.narration_copywriting?.content,
    project?.subtitle_status,
    project?.video_path,
    subtitleReady,
  ]);

  const generateScriptDisabled = Boolean(generateScriptDisabledReason);

  useEffect(() => {
    if (!project?.id) return;
    let cancelled = false;
    const load = async () => {
      try {
        const res: ProjectRunningTasks | null = await projectService.getProjectRunningTasks(project.id);
        if (cancelled || !res) return;
        applyRunningTask(res.generate_copywriting, (task) => {
          applyTaskSnapshot(task, 0, setIsGeneratingCopywriting, setCopywritingGenProgress, setCopywritingGenLogs, setCopywritingTaskId);
        });
        applyRunningTask(res.generate_script, (task) => {
          applyTaskSnapshot(task, 0, setIsGeneratingScript, setScriptGenProgress, setScriptGenLogs);
        });
        applyRunningTask(res.generate_video, (task) => {
          applyTaskSnapshot(task, 0, setIsGeneratingVideo, setVideoGenProgress, setVideoGenLogs, setVideoTaskId);
        });
        applyRunningTask(res.generate_jianying_draft, (task) => {
          applyTaskSnapshot(task, 0, setIsGeneratingDraft, setDraftGenProgress, setDraftGenLogs, setDraftTaskId);
        });
      } catch {
        return;
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [applyRunningTask, applyTaskSnapshot, project?.id]);

  const copywritingPollActive =
    isGeneratingCopywriting || (copywritingGenProgress > 0 && copywritingGenProgress < 100);

  useEffect(() => {
    if (!project?.id) return;
    if (!copywritingPollActive && !isGeneratingScript && !isGeneratingDraft && !isGeneratingVideo) return;
    let stopped = false;
    const tick = async () => {
      try {
        const [latest, queue] = await Promise.all([
          projectService.getProjectLatestTasks(project.id).catch(() => null),
          projectService.getTaskQueue().catch(() => null),
        ]);
        if (stopped) return;

        const queueTasks: TaskProgressState[] = [];
        for (const task of queue?.active_tasks ?? []) {
          if (task?.project_id === project.id) {
            queueTasks.push(task as TaskProgressState);
          }
        }
        for (const waitingProject of queue?.waiting_projects ?? []) {
          if (waitingProject?.project_id !== project.id) continue;
          for (const task of waitingProject.tasks ?? []) {
            queueTasks.push({
              ...(task.task_state ?? {}),
              project_id: task.project_id,
              task_id: task.task_id,
              scope: task.scope,
              status: task.queue_status || task.task_state?.status || "queued",
              progress: typeof task.task_state?.progress === "number" ? task.task_state.progress : 1,
              message: task.task_state?.message || "任务已提交，等待队列调度",
              timestamp: task.task_state?.timestamp,
              type: task.task_state?.type || "progress",
            });
          }
        }

        const fromQueue = (scope: string) => queueTasks.find((task) => task.scope === scope);

        if (copywritingPollActive) {
          const t = fromQueue("generate_copywriting") || latest?.generate_copywriting;
          applyTaskSnapshot(t, copywritingStartedAtRef.current, setIsGeneratingCopywriting, setCopywritingGenProgress, setCopywritingGenLogs, setCopywritingTaskId);
          if (t?.task_id && !copywritingTaskId) {
            setCopywritingTaskId(t.task_id || null);
          }
          if (taskIsAfterStart(t, copywritingStartedAtRef.current) && isTaskFinished(t)) {
            setIsGeneratingCopywriting(false);
            const status = String(t?.status || "").toLowerCase();
            const type = String(t?.type || "").toLowerCase();
            if (status !== "completed" && type !== "completed") {
              setCopywritingGenProgress(0);
              setCopywritingGenLogs([]);
            }
            void options.refreshProject();
          }
        }

        if (isGeneratingScript) {
          const t = fromQueue("generate_script") || latest?.generate_script;
          applyTaskSnapshot(t, scriptStartedAtRef.current, setIsGeneratingScript, setScriptGenProgress, setScriptGenLogs);
          if (taskIsAfterStart(t, scriptStartedAtRef.current) && isTaskFinished(t)) {
            setIsGeneratingScript(false);
            void options.refreshProject();
          }
        }

        if (isGeneratingDraft) {
          const t = fromQueue("generate_jianying_draft") || latest?.generate_jianying_draft;
          applyTaskSnapshot(t, draftStartedAtRef.current, setIsGeneratingDraft, setDraftGenProgress, setDraftGenLogs, setDraftTaskId);
          if (t?.task_id && !draftTaskId) {
            setDraftTaskId(t.task_id || null);
          }
          if (taskIsAfterStart(t, draftStartedAtRef.current) && isTaskFinished(t)) {
            setIsGeneratingDraft(false);
            void options.refreshProject();
          }
        }

        if (isGeneratingVideo) {
          const t = fromQueue("generate_video") || latest?.generate_video;
          applyTaskSnapshot(t, videoStartedAtRef.current, setIsGeneratingVideo, setVideoGenProgress, setVideoGenLogs, setVideoTaskId);
          if (t?.task_id && !videoTaskId) {
            setVideoTaskId(t.task_id || null);
          }
          if (taskIsAfterStart(t, videoStartedAtRef.current) && isTaskFinished(t)) {
            setIsGeneratingVideo(false);
            void options.refreshProject();
          }
        }
      } catch {
        return;
      }
    };

    void tick();
    const id = window.setInterval(() => void tick(), PROGRESS_POLL_INTERVAL_MS);
    return () => {
      stopped = true;
      window.clearInterval(id);
    };
  }, [
    applyTaskSnapshot,
    copywritingPollActive,
    copywritingTaskId,
    draftTaskId,
    isGeneratingDraft,
    isGeneratingScript,
    isGeneratingVideo,
    isTaskFinished,
    options,
    project?.id,
    taskIsAfterStart,
    videoTaskId,
  ]);

  const handleGenerateCopywriting = useCallback(async () => {
    if (!project) return;
    if (!project?.video_path) {
      options.showErrorText("请先上传视频文件");
      return;
    }
    if (!project.subtitle_path) {
      options.showErrorText("请先提取字幕或上传字幕");
      return;
    }
    if (project.subtitle_status && project.subtitle_status !== "ready") {
      options.showErrorText("请先提取字幕或上传字幕");
      return;
    }
    copywritingStartedAtRef.current = Date.now();
    setIsGeneratingCopywriting(true);
    setCopywritingGenProgress(0);
    setCopywritingGenLogs([]);
    setCopywritingTaskId(null);

    try {
      await projectService.flushPendingUpdates(project.id);
      const copywriting = await options.generateCopywriting({
        project_id: project.id,
        video_path: project.video_path,
        subtitle_path: project.subtitle_path,
        narration_type: project.narration_type,
      });
      if (copywriting) {
        setEditedCopywritingSafe(String(copywriting.content || ""));
      }
      options.showSuccess("解说文案生成成功！");
    } catch (err) {
      options.showError(err, "生成解说文案失败");
      setCopywritingGenProgress(0);
      setCopywritingGenLogs([]);
    } finally {
      setIsGeneratingCopywriting(false);
      setCopywritingGenProgress(0);
      setCopywritingGenLogs([]);
    }
  }, [options, project, setEditedCopywritingSafe]);

  const handleStopGenerateCopywriting = useCallback(async () => {
    if (!project?.id) return;
    try {
      setIsStoppingCopywriting(true);
      options.showSuccess("正在停止文案生成...");
      await projectService.cancelTask(project.id, { scope: "generate_copywriting", task_id: copywritingTaskId });
    } catch (err) {
      options.showError(err, "停止生成失败");
    } finally {
      setIsStoppingCopywriting(false);
    }
  }, [copywritingTaskId, options, project?.id]);

  const handleGenerateScript = useCallback(async () => {
    if (!project) return;
    if (!project?.video_path) {
      options.showErrorText("请先上传视频文件");
      return;
    }
    if (!project.subtitle_path) {
      options.showErrorText("请先提取字幕或上传字幕");
      return;
    }
    if (project.subtitle_status && project.subtitle_status !== "ready") {
      // if (project.subtitle_status === "extracting") {
      //   options.showErrorText("字幕提取中，请稍后再试");
      //   return;
      // }
      options.showErrorText("请先提取字幕或上传字幕");
      return;
    }
    if (!project.narration_copywriting?.content) {
      options.showErrorText("请先生成解说文案");
      return;
    }

    scriptStartedAtRef.current = Date.now();
    setIsGeneratingScript(true);
    setScriptGenProgress(0);
    setScriptGenLogs([]);

    try {
      await projectService.flushPendingUpdates(project.id);
      const script = await options.generateScript({
        project_id: project.id,
        video_path: project.video_path,
        subtitle_path: project.subtitle_path,
        narration_type: project.narration_type,
      });

      if (script) {
        setEditedScriptSafe(JSON.stringify(script, null, 2));
      } else if (project.script) {
        setEditedScriptSafe(JSON.stringify(project.script, null, 2));
      }
      options.showSuccess("解说脚本生成成功！");
    } catch (err) {
      options.showError(err, "生成脚本失败");
    } finally {
      setIsGeneratingScript(false);
    }
  }, [options, project, setEditedScriptSafe]);

  const handleSaveScript = useCallback(async () => {
    if (!editedScript.trim()) {
      options.showErrorText("脚本内容不能为空");
      return;
    }

    try {
      const scriptData: VideoScript = JSON.parse(editedScript);
      setIsSaving(true);
      await options.saveScript(scriptData);
      setScriptDirty(false);
      options.showSuccess("脚本保存成功！");
    } catch (err) {
      if (err instanceof SyntaxError) {
        options.showErrorText("脚本格式错误，请检查 JSON 格式是否正确");
      } else {
        options.showError(err, "保存脚本失败");
      }
    } finally {
      setIsSaving(false);
    }
  }, [editedScript, options]);

  const handleSaveCopywriting = useCallback(async (content?: string) => {
    const contentToSave = typeof content === "string" ? content : editedCopywriting;

    if (!contentToSave.trim()) {
      options.showErrorText("文案内容不能为空");
      return;
    }

    try {
      const base: NarrationCopywriting = project?.narration_copywriting
        ? project.narration_copywriting
        : { version: "1.0", content: "" };
      const copywritingData: NarrationCopywriting = {
        ...base,
        content: contentToSave.trim(),
      };
      setIsSavingCopywriting(true);
      await options.saveCopywriting(copywritingData);
      
      // If content was passed, we should also update the local state to match
      if (typeof content === "string") {
        setEditedCopywritingSafe(content);
      }
      
      setCopywritingDirty(false);
      options.showSuccess("文案保存成功！");
    } catch (err) {
      options.showError(err, "保存文案失败");
    } finally {
      setIsSavingCopywriting(false);
    }
  }, [editedCopywriting, options, project?.narration_copywriting, setEditedCopywritingSafe]);

  const handleGenerateVideo = useCallback(async () => {
    if (!project) return;
    if (!project?.script) {
      options.showErrorText("请先生成并保存脚本");
      return;
    }
    if (!project.video_path) {
      options.showErrorText("请先上传原始视频文件");
      return;
    }
    videoStartedAtRef.current = Date.now();
    setIsGeneratingVideo(true);
    setVideoGenProgress(0);
    setVideoGenLogs([]);
    setVideoTaskId(null);
    try {
      const res = await options.generateVideo();
      const taskId = res?.task_id;
      if (taskId) {
        setVideoTaskId(taskId);
      } else {
        setIsGeneratingVideo(false);
        options.showErrorText("生成视频失败");
      }
    } catch (err) {
      options.showError(err, "生成视频失败");
      setIsGeneratingVideo(false);
    }
  }, [options, project?.script, project?.video_path]);

  const handleGenerateDraft = useCallback(async () => {
    if (!project) return;
    if (!project?.video_path) {
      options.showErrorText("请先上传原始视频文件");
      return;
    }
    draftStartedAtRef.current = Date.now();
    setIsGeneratingDraft(true);
    setDraftGenProgress(0);
    setDraftGenLogs([]);
    setDraftTaskId(null);
    try {
      const res = await projectService.startGenerateJianyingDraft(project.id);
      const taskId = res?.task_id;
      window.dispatchEvent(new CustomEvent(TASK_SUBMITTED_EVENT));
      if (taskId) {
        setDraftTaskId(taskId);
      } else {
        setIsGeneratingDraft(false);
        options.showErrorText("生成剪映草稿失败");
      }
    } catch (err) {
      options.showError(err, "生成剪映草稿失败");
      setIsGeneratingDraft(false);
    }
  }, [options, project?.id, project?.video_path]);

  const handleStopGenerateVideo = useCallback(async () => {
    if (!project?.id) return;
    try {
      setIsStoppingVideo(true);
      options.showSuccess("正在停止视频生成...");
      await projectService.cancelTask(project.id, { scope: "generate_video", task_id: videoTaskId });
    } catch (err) {
      options.showError(err, "停止生成失败");
    } finally {
      setIsStoppingVideo(false);
    }
  }, [options, project?.id, videoTaskId]);

  const handleStopGenerateDraft = useCallback(async () => {
    if (!project?.id) return;
    try {
      setIsStoppingDraft(true);
      options.showSuccess("正在停止剪映草稿生成...");
      await projectService.cancelTask(project.id, { scope: "generate_jianying_draft", task_id: draftTaskId });
    } catch (err) {
      options.showError(err, "停止生成失败");
    } finally {
      setIsStoppingDraft(false);
    }
  }, [draftTaskId, options, project?.id]);

  useWsTaskProgress({
    scope: "generate_copywriting",
    projectId: project?.id,
    onProgress: (progress) => setCopywritingGenProgress((prev) => Math.max(prev, progress)),
    onLog: (log) => setCopywritingGenLogs((prev) => [...prev, log]),
    onCompleted: () => {
      setIsGeneratingCopywriting(false);
      setCopywritingGenProgress(0);
      void options.refreshProject();
    },
    onCancelled: (m: WebSocketMessage) => {
      setIsGeneratingCopywriting(false);
      setCopywritingGenProgress(0);
      options.showSuccess(m.message || "文案生成已停止");
      void options.refreshProject();
    },
    onError: (m: WebSocketMessage) => {
      setIsGeneratingCopywriting(false);
      setCopywritingGenProgress(0);
      options.showErrorText(m.message || "生成文案失败");
    },
  });

  useWsTaskProgress({
    scope: "generate_script",
    projectId: project?.id,
    onProgress: (progress) => setScriptGenProgress((prev) => Math.max(prev, progress)),
    onLog: (log) => setScriptGenLogs((prev) => [...prev, log]),
    onCompleted: () => {
      setIsGeneratingScript(false);
      setScriptGenProgress(100);
      options.showSuccess("解说脚本生成成功！");
      void options.refreshProject();
    },
    onError: (m: WebSocketMessage) => {
      setIsGeneratingScript(false);
      setScriptGenProgress(0);
      options.showErrorText(m.message || "生成脚本失败");
    },
  });

  useWsTaskProgress({
    scope: "generate_video",
    projectId: project?.id,
    taskId: videoTaskId,
    onProgress: (progress) => setVideoGenProgress((prev) => Math.max(prev, progress)),
    onLog: (log) => setVideoGenLogs((prev) => [...prev, log]),
    onCompleted: () => {
      setIsGeneratingVideo(false);
      setVideoGenProgress(100);
      options.showSuccess("视频生成成功！");
      void options.refreshProject();
    },
    onCancelled: (m: WebSocketMessage) => {
      setIsGeneratingVideo(false);
      setVideoGenProgress(0);
      options.showSuccess(m.message || "视频生成已停止");
      void options.refreshProject();
    },
    onError: (m: WebSocketMessage) => {
      setIsGeneratingVideo(false);
      setVideoGenProgress(0);
      options.showErrorText(m.message || "生成视频失败");
    },
  });

  useWsTaskProgress({
    scope: "generate_jianying_draft",
    projectId: project?.id,
    taskId: draftTaskId,
    onProgress: (progress) => setDraftGenProgress((prev) => Math.max(prev, progress)),
    onLog: (log) => setDraftGenLogs((prev) => [...prev, log]),
    onCompleted: () => {
      setIsGeneratingDraft(false);
      setDraftGenProgress(100);
      options.showSuccess("剪映草稿生成成功！");
      void options.refreshProject();
    },
    onCancelled: (m: WebSocketMessage) => {
      setIsGeneratingDraft(false);
      setDraftGenProgress(0);
      options.showSuccess(m.message || "剪映草稿生成已停止");
      void options.refreshProject();
    },
    onError: (m: WebSocketMessage) => {
      setIsGeneratingDraft(false);
      setDraftGenProgress(0);
      options.showErrorText(m.message || "生成剪映草稿失败");
    },
  });

  return {
    isGeneratingCopywriting,
    handleGenerateCopywriting,
    handleStopGenerateCopywriting,
    isStoppingCopywriting,
    copywritingGenProgress,
    copywritingGenLogs,
    editedCopywriting,
    setEditedCopywriting: setEditedCopywritingUser,
    isSavingCopywriting,
    handleSaveCopywriting,
    isGeneratingScript,
    handleGenerateScript,
    generateScriptDisabled,
    generateScriptDisabledReason,
    scriptGenProgress,
    scriptGenLogs,
    isGeneratingVideo,
    handleGenerateVideo,
    handleStopGenerateVideo,
    isStoppingVideo,
    videoGenProgress,
    videoGenLogs,
    isGeneratingDraft,
    handleGenerateDraft,
    handleStopGenerateDraft,
    isStoppingDraft,
    draftGenProgress,
    draftGenLogs,
    showMergedPreview,
    setShowMergedPreview,
    editedScript,
    setEditedScript: setEditedScriptUser,
    isSaving,
    handleSaveScript,
  };
}

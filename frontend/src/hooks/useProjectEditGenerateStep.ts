import { useCallback, useEffect, useMemo, useState } from "react";
import type { WebSocketMessage } from "../services/clients";
import { projectService } from "../services/projectService";
import type { GenerateScriptRequest, Project, VideoScript } from "../types/project";
import { useWsTaskProgress, type WsProgressLog } from "./useWsTaskProgress";

export interface UseProjectEditGenerateStepOptions {
  project?: Project | null;
  extractingSubtitle: boolean;
  generateScript: (data: GenerateScriptRequest) => Promise<VideoScript>;
  saveScript: (script: VideoScript) => Promise<void>;
  generateVideo: () => Promise<string | null>;
  refreshProject: () => Promise<void>;
  showSuccess: (text: string, durationSec?: number) => void;
  showErrorText: (text: string, durationSec?: number) => void;
  showError: (err: unknown, fallback: string) => void;
}

export interface UseProjectEditGenerateStepReturn {
  isGeneratingScript: boolean;
  handleGenerateScript: () => void;
  generateScriptDisabled: boolean;
  generateScriptDisabledReason?: string;
  scriptGenProgress: number;
  scriptGenLogs: WsProgressLog[];
  isGeneratingVideo: boolean;
  handleGenerateVideo: () => void;
  videoGenProgress: number;
  videoGenLogs: WsProgressLog[];
  isGeneratingDraft: boolean;
  handleGenerateDraft: () => void;
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

  const [editedScript, setEditedScript] = useState<string>("");
  const [hasInitializedScript, setHasInitializedScript] = useState(false);
  const [isGeneratingScript, setIsGeneratingScript] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isGeneratingVideo, setIsGeneratingVideo] = useState(false);
  const [isGeneratingDraft, setIsGeneratingDraft] = useState(false);
  const [draftTaskId, setDraftTaskId] = useState<string | null>(null);
  const [showMergedPreview, setShowMergedPreview] = useState(false);

  const [scriptGenProgress, setScriptGenProgress] = useState<number>(0);
  const [scriptGenLogs, setScriptGenLogs] = useState<WsProgressLog[]>([]);
  const [videoGenProgress, setVideoGenProgress] = useState<number>(0);
  const [videoGenLogs, setVideoGenLogs] = useState<WsProgressLog[]>([]);
  const [draftGenProgress, setDraftGenProgress] = useState<number>(0);
  const [draftGenLogs, setDraftGenLogs] = useState<WsProgressLog[]>([]);

  const setEditedScriptSafe = useCallback((script: string) => {
    setEditedScript(script);
    setHasInitializedScript(true);
  }, []);

  useEffect(() => {
    if (project?.script && !hasInitializedScript) {
      setEditedScriptSafe(JSON.stringify(project.script, null, 2));
    }
  }, [hasInitializedScript, project?.script, setEditedScriptSafe]);

  const subtitleReady = Boolean(project?.subtitle_path) &&
    (project?.subtitle_status ? project.subtitle_status === "ready" : true);

  const generateScriptDisabledReason = useMemo(() => {
    if (!project?.video_path) return "请先上传视频";
    if (options.extractingSubtitle || project?.subtitle_status === "extracting") return "字幕提取中";
    if (!subtitleReady) return "请先提取字幕或上传字幕";
    return undefined;
  }, [options.extractingSubtitle, project?.subtitle_status, project?.video_path, subtitleReady]);

  const generateScriptDisabled = Boolean(generateScriptDisabledReason);

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
      if (project.subtitle_status === "extracting") {
        options.showErrorText("字幕提取中，请稍后再试");
        return;
      }
      options.showErrorText("请先提取字幕或上传字幕");
      return;
    }

    setIsGeneratingScript(true);
    setScriptGenProgress(0);
    setScriptGenLogs([]);

    try {
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
    setIsGeneratingVideo(true);
    setVideoGenProgress(0);
    setVideoGenLogs([]);
    try {
      const outputPath = await options.generateVideo();
      if (outputPath) {
        options.showSuccess("视频生成成功！");
      }
    } catch (err) {
      options.showError(err, "生成视频失败");
    } finally {
      setIsGeneratingVideo(false);
    }
  }, [options, project?.script, project?.video_path]);

  const handleGenerateDraft = useCallback(async () => {
    if (!project) return;
    if (!project?.video_path) {
      options.showErrorText("请先上传原始视频文件");
      return;
    }
    setIsGeneratingDraft(true);
    setDraftGenProgress(0);
    setDraftGenLogs([]);
    setDraftTaskId(null);
    try {
      const res = await projectService.startGenerateJianyingDraft(project.id);
      const taskId = res?.task_id;
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

  useWsTaskProgress({
    scope: "generate_script",
    projectId: project?.id,
    onProgress: setScriptGenProgress,
    onLog: (log) => setScriptGenLogs((prev) => [...prev, log]),
    onCompleted: () => options.showSuccess("解说脚本生成成功！"),
    onError: (m: WebSocketMessage) => options.showErrorText(m.message || "生成脚本失败"),
  });

  useWsTaskProgress({
    scope: "generate_video",
    projectId: project?.id,
    onProgress: setVideoGenProgress,
    onLog: (log) => setVideoGenLogs((prev) => [...prev, log]),
    onCompleted: () => options.showSuccess("视频生成成功！"),
    onError: (m: WebSocketMessage) => options.showErrorText(m.message || "生成视频失败"),
  });

  useWsTaskProgress({
    scope: "generate_jianying_draft",
    projectId: project?.id,
    taskId: draftTaskId,
    onProgress: setDraftGenProgress,
    onLog: (log) => setDraftGenLogs((prev) => [...prev, log]),
    onCompleted: () => {
      setIsGeneratingDraft(false);
      options.showSuccess("剪映草稿生成成功！");
      void options.refreshProject();
    },
    onError: (m: WebSocketMessage) => {
      setIsGeneratingDraft(false);
      options.showErrorText(m.message || "生成剪映草稿失败");
    },
  });

  return {
    isGeneratingScript,
    handleGenerateScript,
    generateScriptDisabled,
    generateScriptDisabledReason,
    scriptGenProgress,
    scriptGenLogs,
    isGeneratingVideo,
    handleGenerateVideo,
    videoGenProgress,
    videoGenLogs,
    isGeneratingDraft,
    handleGenerateDraft,
    draftGenProgress,
    draftGenLogs,
    showMergedPreview,
    setShowMergedPreview,
    editedScript,
    setEditedScript: setEditedScriptSafe,
    isSaving,
    handleSaveScript,
  };
}

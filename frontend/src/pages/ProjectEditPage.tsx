// 项目编辑页面（二级页面）

import { convertFileSrc } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import {
  ArrowLeft,
  Loader
} from "lucide-react";
import React, { useCallback, useEffect, useRef, useState } from "react";
import { useProjectDetail } from "../hooks/useProjects";
import type { VideoScript } from "../types/project";
 
import AdvancedConfigSection from "../components/projectEdit/AdvancedConfigSection";
import ProjectOperations from "../components/projectEdit/ProjectOperations";
import ScriptEditor from "../components/projectEdit/ScriptEditor";
import SubtitleEditor from "../components/projectEdit/SubtitleEditor";
import VideoSourcesManager from "../components/projectEdit/VideoSourcesManager";
import type { WebSocketMessage } from "../services/clients";
import { wsClient } from "../services/clients";
import { message } from "../services/message";
import { projectService } from "../services/projectService";
import type { SubtitleSegment } from "../types/project";

interface ProjectEditPageProps {
  projectId: string;
  onBack: () => void;
}

/**
 * 项目编辑页面
 */
const ProjectEditPage: React.FC<ProjectEditPageProps> = ({
  projectId,
  onBack,
}) => {
  const {
    project,
    loading,
    error,
    uploadVideos,
    uploadSubtitle,
    deleteSubtitle,
    extractSubtitle,
    fetchSubtitle,
    saveSubtitle,
    subtitleSegments,
    subtitleMeta,
    subtitleLoading,
    deleteVideoItem,
    reorderVideos,
    generateScript,
    saveScript,
    generateVideo,
    mergeVideos,
    mergeProgress,
    merging,
    refreshProject,
  } = useProjectDetail(projectId);

  const [editedScript, setEditedScript] = useState<string>("");
  const [hasInitializedScript, setHasInitializedScript] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isGeneratingVideo, setIsGeneratingVideo] = useState(false);
  // 生成脚本进度 & 日志
  const [scriptGenProgress, setScriptGenProgress] = useState<number>(0);
  const [scriptGenLogs, setScriptGenLogs] = useState<
    { timestamp: string; message: string; phase?: string; type?: string }[]
  >([]);
  // 生成视频进度 & 日志
  const [videoGenProgress, setVideoGenProgress] = useState<number>(0);
  const [videoGenLogs, setVideoGenLogs] = useState<
    { timestamp: string; message: string; phase?: string; type?: string }[]
  >([]);
  const [isGeneratingDraft, setIsGeneratingDraft] = useState(false);
  const [draftGenProgress, setDraftGenProgress] = useState<number>(0);
  const [draftGenLogs, setDraftGenLogs] = useState<
    { timestamp: string; message: string; phase?: string; type?: string }[]
  >([]);
  const [draftTaskId, setDraftTaskId] = useState<string | null>(null);
  // 合并视频预览弹层
  const [showMergedPreview, setShowMergedPreview] = useState(false);
  const [extractingSubtitle, setExtractingSubtitle] = useState(false);
  const [subtitleExtractProgress, setSubtitleExtractProgress] = useState(0);
  const [subtitleExtractLogs, setSubtitleExtractLogs] = useState<
    { timestamp: string; message: string; phase?: string; type?: string }[]
  >([]);
  const [subtitleDraft, setSubtitleDraft] = useState<SubtitleSegment[]>([]);
  const [subtitleSaving, setSubtitleSaving] = useState(false);

  const videoInputRef = useRef<HTMLInputElement>(null);

  const setEditedScriptSafe = (script: string) => {
    setEditedScript(script);
    setHasInitializedScript(true);
  };

  const getErrorMessage = useCallback((err: unknown, fallback: string): string => {
    if (err && typeof err === "object") {
      const anyErr = err as any;
      if (typeof anyErr.message === "string" && anyErr.message) return anyErr.message;
      if (typeof anyErr.detail === "string" && anyErr.detail) return anyErr.detail;
    }
    if (typeof err === "string" && err) return err;
    return fallback;
  }, []);

  const showSuccess = useCallback((text: string, durationSec: number = 2) => {
    message.success(text, durationSec);
  }, []);

  const showErrorText = useCallback((text: string, durationSec: number = 3) => {
    message.error(text, durationSec);
  }, []);

  const showError = useCallback(
    (err: unknown, fallback: string) => {
      showErrorText(getErrorMessage(err, fallback));
    },
    [getErrorMessage, showErrorText]
  );

  useEffect(() => {
    if (error) showErrorText(error);
  }, [error]);
  
  // 视频顺序（可拖拽排序）
  const [videoOrder, setVideoOrder] = useState<string[]>([]);
  const [dragIndex, setDragIndex] = useState<number | null>(null);
  React.useEffect(() => {
    if (Array.isArray(project?.video_paths)) {
      setVideoOrder(project!.video_paths);
    } else {
      setVideoOrder([]);
    }
  }, [project?.video_paths]);
  
  // 拖拽排序交互（列表项）
  const handleItemDragStart = (index: number) => {
    setDragIndex(index);
  };

  const handleItemDragOver = (
    e: React.DragEvent<HTMLDivElement>,
    overIndex: number
  ) => {
    e.preventDefault();
    try {
      if (e.dataTransfer) {
        e.dataTransfer.dropEffect = "move";
      }
    } catch { void 0; }
    e.stopPropagation();
    if (dragIndex === null || dragIndex === overIndex) return;
    setVideoOrder((prev) => {
      const next = [...prev];
      const [moved] = next.splice(dragIndex, 1);
      next.splice(overIndex, 0, moved);
      return next;
    });
    setDragIndex(overIndex);
  };

  const handleItemDrop = async (
    e: React.DragEvent<HTMLDivElement>
  ) => {
    e.preventDefault();
    e.stopPropagation();
    setDragIndex(null);
    try {
      if (project && Array.isArray(project.video_paths)) {
        const before = project.video_paths.join("|");
        const after = videoOrder.join("|");
        if (before !== after) {
          await reorderVideos(videoOrder);
          showSuccess("排序已保存！", 2000);
        }
      }
    } catch (err) {
      await showError(err, "保存排序失败");
    }
  };

  const handleMergeClick = async () => {
    if (
      !project ||
      !Array.isArray(project.video_paths) ||
      project.video_paths.length < 2
    ) {
      return;
    }
    try {
      // 若本地排序与项目不一致，先保存排序
      const before = project.video_paths.join("|");
      const after = videoOrder.join("|");
      if (before !== after) {
        await reorderVideos(videoOrder);
      }
      await mergeVideos();
      showSuccess("合并视频完成！");
    } catch (err) {
      showError(err, "合并视频失败");
    }
  };
  

  // 拖拽上传状态
  const [isDraggingVideo, setIsDraggingVideo] = useState(false);
  
  // 上传进度与状态
  const [uploadingVideo, setUploadingVideo] = useState(false);
  
  const [videoUploadProgress, setVideoUploadProgress] = useState<number>(0);
  
  const [showAdvancedConfig, setShowAdvancedConfig] = useState(false);
  const [uploadingSubtitle, setUploadingSubtitle] = useState(false);
  const [subtitleUploadProgress, setSubtitleUploadProgress] = useState<number>(0);
  const [isDraggingSubtitle, setIsDraggingSubtitle] = useState(false);
  const uploadingVideoRef = React.useRef(false);
  React.useEffect(() => {
    uploadingVideoRef.current = uploadingVideo;
  }, [uploadingVideo]);

  /**
   * 处理视频文件选择
   */
  const handleVideoFileChange = async (
    e: React.ChangeEvent<HTMLInputElement>
  ) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    setUploadingVideo(true);
    setVideoUploadProgress(0);
    try {
      await uploadVideos(files, (p) => setVideoUploadProgress(p));
      showSuccess("视频文件上传成功！");
    } catch (err) {
      showError(err, "上传视频失败");
    } finally {
      setUploadingVideo(false);
      setTimeout(() => setVideoUploadProgress(0), 800);
    }
  };

  
  

  /**
   * 视频拖拽上传
   */
  const handleVideoDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    try {
      if (e.dataTransfer) {
        e.dataTransfer.dropEffect = "copy";
      }
    } catch { void 0; }
    setIsDraggingVideo(true);
  };

  const handleVideoDragLeave = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDraggingVideo(false);
  };

  const handleVideoDrop = async (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDraggingVideo(false);
    const files = e.dataTransfer.files;
    if (!files || files.length === 0) return;

    setUploadingVideo(true);
    setVideoUploadProgress(0);
    try {
      await uploadVideos(files, (p) => setVideoUploadProgress(p));
      showSuccess("视频文件上传成功！");
    } catch (err) {
      showError(err, "上传视频失败");
    } finally {
      setUploadingVideo(false);
      setTimeout(() => setVideoUploadProgress(0), 800);
    }
  };

  const handleSubtitleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.dataTransfer) {
      e.dataTransfer.dropEffect = "copy";
    }
    setIsDraggingSubtitle(true);
  };

  const handleSubtitleDragLeave = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDraggingSubtitle(false);
  };

  const handleSubtitleDrop = async (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDraggingSubtitle(false);
    const files = e.dataTransfer.files;
    if (!files || files.length === 0) return;
    const file = files[0];
    setUploadingSubtitle(true);
    setSubtitleUploadProgress(0);
    try {
      await uploadSubtitle(file, (p) => setSubtitleUploadProgress(p));
      showSuccess("字幕文件上传成功！");
    } catch (err) {
      showError(err, "上传字幕失败");
    } finally {
      setUploadingSubtitle(false);
      setTimeout(() => setSubtitleUploadProgress(0), 800);
    }
  };

  const handleSubtitleFileChange = async (
    e: React.ChangeEvent<HTMLInputElement>
  ) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;
    const file = files[0];
    setUploadingSubtitle(true);
    setSubtitleUploadProgress(0);
    try {
      await uploadSubtitle(file, (p) => setSubtitleUploadProgress(p));
      showSuccess("字幕文件上传成功！");
    } catch (err) {
      showError(err, "上传字幕失败");
    } finally {
      setUploadingSubtitle(false);
      setTimeout(() => setSubtitleUploadProgress(0), 800);
    }
  };

  const handleTauriPathsUpload = React.useCallback(
    async (paths: string[]) => {
      if (!paths || paths.length === 0) return;
      if (uploadingVideoRef.current) return;
      const videoExts = [".mp4", ".mov", ".mkv", ".avi", ".flv", ".wmv", ".webm", ".m4v"];
      const filtered = paths.filter((p) => {
        const lower = p.toLowerCase();
        return videoExts.some((ext) => lower.endsWith(ext));
      });
      if (filtered.length === 0) return;
      setUploadingVideo(true);
      setVideoUploadProgress(0);
      try {
        const files = await Promise.all(
          filtered.map(async (p) => {
            const url = convertFileSrc(p);
            const res = await fetch(url);
            if (!res.ok) throw new Error(`读取文件失败: ${p}`);
            const blob = await res.blob();
            const name = p.split(/[/\\]/).pop() || "file";
            return new File([blob], name, { type: blob.type || "application/octet-stream" });
          })
        );
        if (files.length > 0) {
          await uploadVideos(files, (pr) => setVideoUploadProgress(pr));
          showSuccess("视频文件上传成功！");
        }
      } catch (err) {
        showError(err, "上传视频失败");
      } finally {
        setUploadingVideo(false);
        setTimeout(() => setVideoUploadProgress(0), 800);
      }
    },
    [showError, showSuccess, uploadVideos]
  );

  React.useEffect(() => {
    const onGlobalDragOver = (ev: DragEvent) => {
      ev.preventDefault();
      try {
        if (ev.dataTransfer) {
          ev.dataTransfer.dropEffect = "copy";
        }
      } catch { void 0; }
    };
    const onGlobalDrop = (ev: DragEvent) => {
      ev.preventDefault();
    };
    window.addEventListener("dragover", onGlobalDragOver);
    window.addEventListener("drop", onGlobalDrop);

    let unlistenDrop: (() => void) | undefined;
    let unlistenHover: (() => void) | undefined;
    let unlistenCancel: (() => void) | undefined;
    const setup = async () => {
      try {
        unlistenHover = await listen<string[]>("tauri://file-drop-hovered", () => {
          setIsDraggingVideo(true);
        });
        unlistenCancel = await listen<string[]>("tauri://file-drop-cancelled", () => {
          setIsDraggingVideo(false);
        });
        unlistenDrop = await listen<string[]>("tauri://file-drop", async (event) => {
          setIsDraggingVideo(false);
          const paths = Array.isArray(event.payload) ? (event.payload as string[]) : [];
          await handleTauriPathsUpload(paths);
        });
      } catch (e) {
        console.error(e);
      }
    };
    setup();
    return () => {
      window.removeEventListener("dragover", onGlobalDragOver);
      window.removeEventListener("drop", onGlobalDrop);
      try {
        unlistenDrop?.();
        unlistenHover?.();
        unlistenCancel?.();
      } catch (e) {
        console.error(e);
      }
    };
  }, [handleTauriPathsUpload]);

  

  
  



  
  

  /**
   * 处理生成解说脚本
   */
  const handleGenerateScript = async () => {
    if (!project?.video_path) {
      showErrorText("请先上传视频文件");
      return;
    }
    if (!project?.subtitle_path) {
      showErrorText("请先提取字幕或上传字幕");
      return;
    }
    if (project?.subtitle_status && project.subtitle_status !== "ready") {
      if (project.subtitle_status === "extracting") {
        showErrorText("字幕提取中，请稍后再试");
        return;
      }
      showErrorText("请先提取字幕或上传字幕");
      return;
    }

    setIsGenerating(true);
    setScriptGenProgress(0);
    setScriptGenLogs([]);

    try {
      const script = await generateScript({
        project_id: project.id,
        video_path: project.video_path,
        subtitle_path: project.subtitle_path,
        narration_type: project.narration_type,
      });

      if (script) {
        setEditedScript(JSON.stringify(script, null, 2));
        setHasInitializedScript(true);
      } else if (project.script) {
        // 兜底：如果返回值为空，使用项目中的脚本
        setEditedScript(JSON.stringify(project.script, null, 2));
        setHasInitializedScript(true);
      }
      showSuccess("解说脚本生成成功！");
    } catch (err) {
      showError(err, "生成脚本失败");
    } finally {
      setIsGenerating(false);
    }
  };

  const handleExtractSubtitle = async () => {
    if (!project?.video_path) {
      showErrorText("请先上传视频文件");
      return;
    }
    if (project?.subtitle_source === "user" && project?.subtitle_path) {
      showErrorText("已上传字幕，需先删除才能提取");
      return;
    }
    if (project?.subtitle_status === "extracting") {
      showErrorText("正在提取中");
      return;
    }
    let force = false;
    if (project?.subtitle_updated_by_user) {
      force = window.confirm("字幕已被编辑，重新提取将覆盖修改内容，是否继续？");
      if (!force) return;
    }

    setExtractingSubtitle(true);
    setSubtitleExtractProgress(0);
    setSubtitleExtractLogs([]);
    try {
      await extractSubtitle(force);
      showSuccess("字幕提取成功！");
    } catch (err) {
      showError(err, "提取字幕失败");
      setExtractingSubtitle(false);
    }
  };

  const handleReloadSubtitle = async () => {
    try {
      await fetchSubtitle();
    } catch (err) {
      showError(err, "获取字幕失败");
    }
  };

  const handleSaveSubtitle = async () => {
    if (!subtitleDraft.length) {
      showErrorText("字幕内容为空");
      return;
    }
    setSubtitleSaving(true);
    try {
      await saveSubtitle({ segments: subtitleDraft });
      showSuccess("字幕保存成功！");
    } catch (err) {
      showError(err, "保存字幕失败");
    } finally {
      setSubtitleSaving(false);
    }
  };

  // 订阅 WebSocket 消息，获取生成脚本的实时进度
  React.useEffect(() => {
    const handler = (message: WebSocketMessage) => {
      if (
        message &&
        (message.type === "progress" || message.type === "completed" || message.type === "error") &&
        (message as any).scope === "generate_script" &&
        (message as any).project_id === project?.id
      ) {
        if (typeof message.progress === "number") {
          setScriptGenProgress(Math.max(0, Math.min(100, message.progress)));
        }
        const msgText = message.message || "";
        setScriptGenLogs((prev) => [
          ...prev,
          {
            timestamp: message.timestamp,
            message: msgText,
            phase: (message as any).phase,
            type: message.type,
          },
        ]);
        if (message.type === "completed") {
          showSuccess("解说脚本生成成功！");
        }
        if (message.type === "error") {
          showErrorText(msgText || "生成脚本失败");
        }
      }
    };

    wsClient.on("*", handler);
    return () => {
      wsClient.off("*", handler);
    };
  }, [project?.id, showSuccess, showErrorText]);

  React.useEffect(() => {
    const handler = (message: WebSocketMessage) => {
      if (
        message &&
        (message.type === "progress" || message.type === "completed" || message.type === "error") &&
        (message as any).scope === "extract_subtitle" &&
        (message as any).project_id === project?.id
      ) {
        if (typeof message.progress === "number") {
          setSubtitleExtractProgress(Math.max(0, Math.min(100, message.progress)));
        }
        const msgText = message.message || "";
        setSubtitleExtractLogs((prev) => [
          ...prev,
          {
            timestamp: message.timestamp,
            message: msgText,
            phase: (message as any).phase,
            type: message.type,
          },
        ]);
        if (message.type === "completed") {
          setExtractingSubtitle(false);
          showSuccess("字幕提取成功！");
          void refreshProject();
          void fetchSubtitle().catch(() => void 0);
        }
        if (message.type === "error") {
          setExtractingSubtitle(false);
          showErrorText(msgText || "字幕提取失败");
        }
      }
    };

    wsClient.on("*", handler);
    return () => {
      wsClient.off("*", handler);
    };
  }, [project?.id, refreshProject, fetchSubtitle, showSuccess, showErrorText]);

  React.useEffect(() => {
    if (project?.subtitle_path) {
      void fetchSubtitle().catch(() => void 0);
    } else {
      setSubtitleDraft([]);
    }
  }, [project?.id, project?.subtitle_path, fetchSubtitle]);

  React.useEffect(() => {
    setSubtitleDraft(subtitleSegments || []);
  }, [subtitleSegments]);

  /**
   * 处理保存脚本
   */
  const handleSaveScript = async () => {
    if (!editedScript.trim()) {
      showErrorText("脚本内容不能为空");
      return;
    }

    try {
      const scriptData: VideoScript = JSON.parse(editedScript);
      setIsSaving(true);

      await saveScript(scriptData);
      showSuccess("脚本保存成功！");
    } catch (err) {
      if (err instanceof SyntaxError) {
        showErrorText("脚本格式错误，请检查 JSON 格式是否正确");
      } else {
        showError(err, "保存脚本失败");
      }
    } finally {
      setIsSaving(false);
    }
  };

  /**
   * 处理生成输出视频
   */
  const handleGenerateVideo = async () => {
    if (!project?.script) {
      showErrorText("请先生成并保存脚本");
      return;
    }
    if (!project?.video_path) {
      showErrorText("请先上传原始视频文件");
      return;
    }
    setIsGeneratingVideo(true);
    setVideoGenProgress(0);
    setVideoGenLogs([]);
    try {
      const outputPath = await generateVideo();
      if (outputPath) {
        showSuccess("视频生成成功！");
      }
    } catch (err) {
      showError(err, "生成视频失败");
    } finally {
      setIsGeneratingVideo(false);
    }
  };

  const handleGenerateDraft = async () => {
    if (!project?.video_path) {
      showErrorText("请先上传原始视频文件");
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
        showErrorText("生成剪映草稿失败");
      }
    } catch (err) {
      showError(err, "生成剪映草稿失败");
      setIsGeneratingDraft(false);
    }
  };

  // 订阅 WebSocket 消息，获取生成视频的实时进度
  React.useEffect(() => {
    const handler = (message: WebSocketMessage) => {
      if (
        message &&
        (message.type === "progress" || message.type === "completed" || message.type === "error") &&
        (message as any).scope === "generate_video" &&
        (message as any).project_id === project?.id
      ) {
        if (typeof message.progress === "number") {
          setVideoGenProgress(Math.max(0, Math.min(100, message.progress)));
        }
        const msgText = message.message || "";
        setVideoGenLogs((prev) => [
          ...prev,
          {
            timestamp: message.timestamp,
            message: msgText,
            phase: (message as any).phase,
            type: message.type,
          },
        ]);
        if (message.type === "completed") {
          showSuccess("视频生成成功！");
        }
        if (message.type === "error") {
          showErrorText(msgText || "生成视频失败");
        }
      }
    };

    wsClient.on("*", handler);
    return () => {
      wsClient.off("*", handler);
    };
  }, [project?.id, showSuccess, showErrorText]);

  React.useEffect(() => {
    const handler = (message: WebSocketMessage) => {
      if (
        message &&
        (message.type === "progress" || message.type === "completed" || message.type === "error") &&
        (message as any).scope === "generate_jianying_draft" &&
        (message as any).project_id === project?.id
      ) {
        const msgTaskId = (message as any).task_id as string | undefined;
        if (draftTaskId && msgTaskId && msgTaskId !== draftTaskId) {
          return;
        }
        if (typeof message.progress === "number") {
          setDraftGenProgress(Math.max(0, Math.min(100, message.progress)));
        }
        const msgText = message.message || "";
        setDraftGenLogs((prev) => [
          ...prev,
          {
            timestamp: message.timestamp,
            message: msgText,
            phase: (message as any).phase,
            type: message.type,
          },
        ]);
        if (message.type === "completed") {
          setIsGeneratingDraft(false);
          showSuccess("剪映草稿生成成功！");
          void refreshProject();
        }
        if (message.type === "error") {
          setIsGeneratingDraft(false);
          showErrorText(msgText || "生成剪映草稿失败");
        }
      }
    };
    wsClient.on("*", handler);
    return () => {
      wsClient.off("*", handler);
    };
  }, [project?.id, draftTaskId, refreshProject, showSuccess]);

  const handleDeleteSubtitle = async () => {
    try {
      await deleteSubtitle();
      showSuccess("字幕已删除！");
    } catch (err) {
      showError(err, "删除字幕失败");
    }
  };

  const handleDeleteVideoItem = async (path: string) => {
    try {
      await deleteVideoItem(path);
      showSuccess("视频已删除！");
    } catch (err) {
      showError(err, "删除视频失败");
    }
  };

  /**
   * 处理解说类型变更
   */
  

  // 同步项目脚本到编辑器
  React.useEffect(() => {
    if (project?.script && !hasInitializedScript) {
      setEditedScript(JSON.stringify(project.script, null, 2));
      setHasInitializedScript(true);
    }
  }, [project?.script, hasInitializedScript]);

  if (loading && !project) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader className="h-8 w-8 animate-spin text-blue-600" />
        <span className="ml-3 text-gray-600">加载项目中...</span>
      </div>
    );
  }

  if (!project) {
    return (
      <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg">
        项目不存在或加载失败
      </div>
    );
  }

  const subtitleReady = Boolean(project.subtitle_path) && (project.subtitle_status ? project.subtitle_status === "ready" : true);
  const generateScriptDisabledReason = !project.video_path
    ? "请先上传视频"
    : extractingSubtitle || project.subtitle_status === "extracting"
      ? "字幕提取中"
      : !subtitleReady
        ? "请先提取字幕或上传字幕"
        : undefined;
  const generateScriptDisabled = Boolean(generateScriptDisabledReason);

  return (
    <div className="space-y-6">
      {/* 页面头部 */}
      <div className="bg-white rounded-lg shadow-md p-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-4">
            <button
              onClick={onBack}
              className="flex items-center justify-center w-10 h-10 bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors"
              title="返回"
            >
              <ArrowLeft className="h-5 w-5 text-gray-600" />
            </button>
            <div>
              <h1 className="text-2xl font-bold text-gray-900">
                {project.name}
              </h1>
              <p className="text-sm text-gray-600 mt-1">
                {project.description}
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* 项目配置区 */}
      <div className="bg-white rounded-lg shadow-md p-6 space-y-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-gray-900">项目配置</h2>
          <button
            onClick={() => setShowAdvancedConfig((v) => !v)}
            className="text-blue-600 hover:text-blue-800 text-sm"
          >
            <span className="text-xs text-gray-500">（支持上传-字幕、提示词）</span>
            高级配置
          </button>
        </div>
        <p className="text-xs text-gray-500 mb-2">
          自动解析字幕只支持中文语言
        </p>
        {/* 解说类型（Figma 风格选择框）*/}
        {/* <div>
          <label
            htmlFor="narration-type"
            className="block text-sm font-medium text-gray-700 mb-2"
          >
            解说类型
          </label>
          <div className="relative w-full md:w-1/2">
          <select
            id="narration-type"
            value={project.narration_type}
            onChange={handleNarrationTypeChange}
            className="appearance-none w-full pr-10 px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-violet-500 focus:border-transparent outline-none transition-all bg-white"
          >
            <option value={NarrationType.SHORT_DRAMA}>短剧解说</option>
            <option value={NarrationType.MOVIE}>电影解说</option>
          </select>
            <ChevronDown className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
          </div>
        </div> */}

        {showAdvancedConfig && (
          <AdvancedConfigSection
            projectId={projectId}
            uploadingSubtitle={uploadingSubtitle}
            subtitleUploadProgress={subtitleUploadProgress}
            subtitlePath={project.subtitle_path}
            narrationType={project.narration_type}
            onSubtitleFileChange={handleSubtitleFileChange}
            onDeleteSubtitle={handleDeleteSubtitle}
            isDraggingSubtitle={isDraggingSubtitle}
            onSubtitleDragOver={handleSubtitleDragOver}
            onSubtitleDragLeave={handleSubtitleDragLeave}
            onSubtitleDrop={handleSubtitleDrop}
          />
        )}

        {/* 视频源管理：上传 / 排序 / 合并（Figma 布局）*/}
        <VideoSourcesManager
          project={project}
          videoOrder={videoOrder}
          dragIndex={dragIndex}
          isDraggingVideo={isDraggingVideo}
          uploadingVideo={uploadingVideo}
          merging={merging}
          mergeProgress={mergeProgress}
          videoUploadProgress={videoUploadProgress}
          videoInputRef={videoInputRef}
          onVideoDragOver={handleVideoDragOver}
          onVideoDragLeave={handleVideoDragLeave}
          onVideoDrop={handleVideoDrop}
          onVideoFileChange={handleVideoFileChange}
          onMergeClick={handleMergeClick}
          onItemDragStart={handleItemDragStart}
          onItemDragOver={handleItemDragOver}
          onItemDrop={handleItemDrop}
          onDeleteVideoItem={handleDeleteVideoItem}
        />

        <ProjectOperations
          project={project}
          isGeneratingScript={isGenerating}
          handleGenerateScript={handleGenerateScript}
          generateScriptDisabled={generateScriptDisabled}
          generateScriptDisabledReason={generateScriptDisabledReason}
          scriptGenProgress={scriptGenProgress}
          scriptGenLogs={scriptGenLogs}
          isGeneratingVideo={isGeneratingVideo}
          handleGenerateVideo={handleGenerateVideo}
          videoGenProgress={videoGenProgress}
          videoGenLogs={videoGenLogs}
          isGeneratingDraft={isGeneratingDraft}
          handleGenerateDraft={handleGenerateDraft}
          draftGenProgress={draftGenProgress}
          draftGenLogs={draftGenLogs}
          showMergedPreview={showMergedPreview}
          setShowMergedPreview={setShowMergedPreview}
        />
      </div>

      <div className="bg-white rounded-lg shadow-md p-6 space-y-3">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div className="flex items-center gap-2 flex-wrap">
            <h2 className="text-lg font-semibold text-gray-900">字幕提取</h2>
            {project.subtitle_source === "user" && project.subtitle_path ? (
              <span className="text-xs px-2.5 py-1 bg-green-50 text-green-700 font-medium rounded-full border border-green-100">
                已上传字幕
              </span>
            ) : null}
            {project.subtitle_source === "extracted" && project.subtitle_path ? (
              <span className="text-xs px-2.5 py-1 bg-violet-50 text-violet-700 font-medium rounded-full border border-violet-100">
                已提取字幕
              </span>
            ) : null}
            {project.subtitle_updated_by_user ? (
              <span className="text-xs px-2.5 py-1 bg-amber-50 text-amber-700 font-medium rounded-full border border-amber-100">
                已编辑
              </span>
            ) : null}
          </div>
          <button
            onClick={handleExtractSubtitle}
            disabled={
              subtitleLoading ||
              extractingSubtitle ||
              !project.video_path ||
              (project.subtitle_source === "user" && Boolean(project.subtitle_path)) ||
              project.subtitle_status === "extracting"
            }
            className="flex items-center px-4 py-2 bg-violet-600 text-white rounded-lg hover:bg-violet-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {extractingSubtitle ? (
              <>
                <Loader className="h-4 w-4 mr-2 animate-spin" />
                提取中...
              </>
            ) : (
              <>提取字幕</>
            )}
          </button>
        </div>

        {(extractingSubtitle || (subtitleExtractProgress > 0 && subtitleExtractProgress < 100)) && (
          <div className="w-full">
            <div className="flex items-center justify-between text-xs text-gray-600 mb-1">
              <span>字幕提取进度</span>
              <span>{Math.round(subtitleExtractProgress)}%</span>
            </div>
            <div className="w-full h-2 bg-gray-200 rounded">
              <div
                className="h-2 bg-blue-600 rounded transition-all"
                style={{ width: `${Math.round(subtitleExtractProgress)}%` }}
              />
            </div>
            {subtitleExtractLogs.length > 0 ? (
              <div className="mt-2 text-xs text-gray-700 break-all">
                {subtitleExtractLogs.slice(-1)[0]?.message}
              </div>
            ) : null}
          </div>
        )}
      </div>

      <SubtitleEditor
        segments={subtitleDraft}
        subtitleMeta={subtitleMeta}
        loading={subtitleLoading}
        saving={subtitleSaving}
        onReload={handleReloadSubtitle}
        onSave={handleSaveSubtitle}
        onChange={setSubtitleDraft}
      />

      <ScriptEditor
        editedScript={editedScript}
        setEditedScript={setEditedScriptSafe}
        isSaving={isSaving}
        handleSaveScript={handleSaveScript}
      />
    </div>
  );
};

export default ProjectEditPage;

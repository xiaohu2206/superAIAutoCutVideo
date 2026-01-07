// 项目编辑页面（二级页面）

import {
  AlertCircle,
  ArrowLeft,
  CheckCircle,
  Loader,
} from "lucide-react";
import React, { useRef, useState } from "react";
import { useProjectDetail } from "../hooks/useProjects";
import type { VideoScript } from "../types/project";
 
import AdvancedConfigSection from "../components/projectEdit/AdvancedConfigSection";
import ProjectOperations from "../components/projectEdit/ProjectOperations";
import ScriptEditor from "../components/projectEdit/ScriptEditor";
import VideoSourcesManager from "../components/projectEdit/VideoSourcesManager";
import type { WebSocketMessage } from "../services/clients";
import { wsClient } from "../services/clients";
import { projectService } from "../services/projectService";

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
    deleteVideoItem,
    reorderVideos,
    generateScript,
    saveScript,
    generateVideo,
    downloadVideo,
    mergeVideos,
    mergeProgress,
    merging,
    refreshProject,
  } = useProjectDetail(projectId);

  const [editedScript, setEditedScript] = useState<string>("");
  const [isGenerating, setIsGenerating] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isGeneratingVideo, setIsGeneratingVideo] = useState(false);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [draftErrorMessage, setDraftErrorMessage] = useState<string | null>(null);
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
  // 输出视频预览弹层
  const [showOutputPreview, setShowOutputPreview] = useState(false);

  const videoInputRef = useRef<HTMLInputElement>(null);
  
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
          setSuccessMessage("排序已保存！");
          setTimeout(() => setSuccessMessage(null), 2000);
        }
      }
    } catch (err) {
      console.error("保存排序失败:", err);
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
    } catch (err) {
      console.error("合并视频失败:", err);
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

  /**
   * 处理视频文件选择
   */
  const handleVideoFileChange = async (
    e: React.ChangeEvent<HTMLInputElement>
  ) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    setSuccessMessage(null);

    setUploadingVideo(true);
    setVideoUploadProgress(0);
    try {
      await uploadVideos(files, (p) => setVideoUploadProgress(p));
      setSuccessMessage("视频文件上传成功！");
      setTimeout(() => setSuccessMessage(null), 3000);
    } catch (err) {
      console.error("上传视频失败:", err);
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
    setIsDraggingVideo(true);
  };

  const handleVideoDragLeave = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDraggingVideo(false);
  };

  const handleVideoDrop = async (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDraggingVideo(false);
    const files = e.dataTransfer.files;
    if (!files || files.length === 0) return;

    setSuccessMessage(null);

    setUploadingVideo(true);
    setVideoUploadProgress(0);
    try {
      await uploadVideos(files, (p) => setVideoUploadProgress(p));
      setSuccessMessage("视频文件上传成功！");
      setTimeout(() => setSuccessMessage(null), 3000);
    } catch (err) {
      console.error("上传视频失败:", err);
    } finally {
      setUploadingVideo(false);
      setTimeout(() => setVideoUploadProgress(0), 800);
    }
  };

  const handleSubtitleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDraggingSubtitle(true);
  };

  const handleSubtitleDragLeave = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDraggingSubtitle(false);
  };

  const handleSubtitleDrop = async (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDraggingSubtitle(false);
    const files = e.dataTransfer.files;
    if (!files || files.length === 0) return;
    const file = files[0];
    setSuccessMessage(null);
    setUploadingSubtitle(true);
    setSubtitleUploadProgress(0);
    try {
      await uploadSubtitle(file, (p) => setSubtitleUploadProgress(p));
      setSuccessMessage("字幕文件上传成功！");
      setTimeout(() => setSuccessMessage(null), 3000);
    } catch (err) {
      console.error(err);
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
    setSuccessMessage(null);
    setUploadingSubtitle(true);
    setSubtitleUploadProgress(0);
    try {
      await uploadSubtitle(file, (p) => setSubtitleUploadProgress(p));
      setSuccessMessage("字幕文件上传成功！");
      setTimeout(() => setSuccessMessage(null), 3000);
    } catch (err) {
      console.error(err);
    } finally {
      setUploadingSubtitle(false);
      setTimeout(() => setSubtitleUploadProgress(0), 800);
    }
  };

  

  
  



  
  

  /**
   * 处理生成解说脚本
   */
  const handleGenerateScript = async () => {
    if (!project?.video_path) {
      alert("请先上传视频文件");
      return;
    }

    setIsGenerating(true);
    setScriptGenProgress(0);
    setScriptGenLogs([]);
    setSuccessMessage(null);

    try {
      const script = await generateScript({
        project_id: project.id,
        video_path: project.video_path,
        subtitle_path: project.subtitle_path,
        narration_type: project.narration_type,
      });

      if (script) {
        setEditedScript(JSON.stringify(script, null, 2));
      } else if (project.script) {
        // 兜底：如果返回值为空，使用项目中的脚本
        setEditedScript(JSON.stringify(project.script, null, 2));
      }
      setSuccessMessage("解说脚本生成成功！");
      setTimeout(() => setSuccessMessage(null), 3000);
    } catch (err) {
      console.error("生成脚本失败:", err);
    } finally {
      setIsGenerating(false);
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
          setSuccessMessage("解说脚本生成成功！");
          setTimeout(() => setSuccessMessage(null), 3000);
        }
      }
    };

    wsClient.on("*", handler);
    return () => {
      wsClient.off("*", handler);
    };
  }, [project?.id]);

  /**
   * 处理保存脚本
   */
  const handleSaveScript = async () => {
    if (!editedScript.trim()) {
      alert("脚本内容不能为空");
      return;
    }

    try {
      const scriptData: VideoScript = JSON.parse(editedScript);
      setIsSaving(true);
      setSuccessMessage(null);

      await saveScript(scriptData);
      setSuccessMessage("脚本保存成功！");
      setTimeout(() => setSuccessMessage(null), 3000);
    } catch (err) {
      if (err instanceof SyntaxError) {
        alert("脚本格式错误，请检查 JSON 格式是否正确");
      } else {
        console.error("保存脚本失败:", err);
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
      alert("请先生成并保存脚本");
      return;
    }
    if (!project?.video_path) {
      alert("请先上传原始视频文件");
      return;
    }
    setIsGeneratingVideo(true);
    setVideoGenProgress(0);
    setVideoGenLogs([]);
    setSuccessMessage(null);
    try {
      const outputPath = await generateVideo();
      if (outputPath) {
        setSuccessMessage("视频生成成功！");
        setTimeout(() => setSuccessMessage(null), 3000);
      }
    } catch (err) {
      console.error("生成视频失败:", err);
    } finally {
      setIsGeneratingVideo(false);
    }
  };

  const handleGenerateDraft = async () => {
    if (!project?.video_path) {
      alert("请先上传原始视频文件");
      return;
    }
    setIsGeneratingDraft(true);
    setDraftGenProgress(0);
    setDraftGenLogs([]);
    setDraftTaskId(null);
    setSuccessMessage(null);
    setDraftErrorMessage(null);
    try {
      const res = await projectService.startGenerateJianyingDraft(project.id);
      const taskId = res?.task_id;
      if (taskId) {
        setDraftTaskId(taskId);
      }
    } catch (err) {
      console.error("生成剪映草稿失败:", err);
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
          setSuccessMessage("视频生成成功！");
          setTimeout(() => setSuccessMessage(null), 3000);
        }
      }
    };

    wsClient.on("*", handler);
    return () => {
      wsClient.off("*", handler);
    };
  }, [project?.id]);

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
          setDraftErrorMessage(null);
          setSuccessMessage("剪映草稿生成成功！");
          setTimeout(() => setSuccessMessage(null), 3000);
          void refreshProject();
        }
        if (message.type === "error") {
          setIsGeneratingDraft(false);
          setDraftErrorMessage(msgText);
        }
      }
    };
    wsClient.on("*", handler);
    return () => {
      wsClient.off("*", handler);
    };
  }, [project?.id, draftTaskId]);

  /**
   * 处理下载输出视频
   */
  const handleDownloadVideo = () => {
    if (!project?.output_video_path) {
      alert("尚未生成输出视频");
      return;
    }
    downloadVideo();
  };

  /**
   * 处理解说类型变更
   */
  

  // 同步项目脚本到编辑器
  React.useEffect(() => {
    if (project?.script && !editedScript) {
      setEditedScript(JSON.stringify(project.script, null, 2));
    }
  }, [project?.script, editedScript]);

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

      {/* 成功提示 */}
      {successMessage && (
        <div className="bg-green-50 border border-green-200 text-green-700 px-4 py-3 rounded-lg flex items-center">
          <CheckCircle className="h-5 w-5 mr-2" />
          {successMessage}
        </div>
      )}

      {/* 错误提示 */}
      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg flex items-center">
          <AlertCircle className="h-5 w-5 mr-2" />
          {error}
        </div>
      )}
      {draftErrorMessage && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg flex items-center">
          <AlertCircle className="h-5 w-5 mr-2" />
          {draftErrorMessage}
        </div>
      )}

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
            onDeleteSubtitle={deleteSubtitle}
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
          onDeleteVideoItem={deleteVideoItem}
          onShowMergedPreview={() => setShowMergedPreview(true)}
        />

        <ProjectOperations
          project={project}
          isGeneratingScript={isGenerating}
          handleGenerateScript={handleGenerateScript}
          scriptGenProgress={scriptGenProgress}
          scriptGenLogs={scriptGenLogs}
          isGeneratingVideo={isGeneratingVideo}
          handleGenerateVideo={handleGenerateVideo}
          videoGenProgress={videoGenProgress}
          videoGenLogs={videoGenLogs}
          handleDownloadVideo={handleDownloadVideo}
          isGeneratingDraft={isGeneratingDraft}
          handleGenerateDraft={handleGenerateDraft}
          draftGenProgress={draftGenProgress}
          draftGenLogs={draftGenLogs}
          showMergedPreview={showMergedPreview}
          setShowMergedPreview={setShowMergedPreview}
          showOutputPreview={showOutputPreview}
          setShowOutputPreview={setShowOutputPreview}
        />
      </div>

      <ScriptEditor
        editedScript={editedScript}
        setEditedScript={setEditedScript}
        isSaving={isSaving}
        handleSaveScript={handleSaveScript}
      />
    </div>
  );
};

export default ProjectEditPage;

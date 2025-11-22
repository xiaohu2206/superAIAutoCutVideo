// 项目编辑页面（二级页面）

import {
  AlertCircle,
  ArrowLeft,
  CheckCircle,
  Download,
  FileVideo,
  GripVertical,
  Loader,
  Save,
  Sparkles,
  ChevronDown,
  Upload,
  Video,
  DeleteIcon
} from "lucide-react";
import React, { useRef, useState } from "react";
import { useProjectDetail } from "../hooks/useProjects";
import type { VideoScript } from "../types/project";
import { NarrationType } from "../types/project";
import { wsClient } from "../services/clients";
import type { WebSocketMessage } from "../services/clients";
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
    updateProject,
    uploadVideos,
    deleteVideoItem,
    reorderVideos,
    generateScript,
    saveScript,
    generateVideo,
    downloadVideo,
    mergeVideos,
    mergeProgress,
    merging,
  } = useProjectDetail(projectId);

  const [editedScript, setEditedScript] = useState<string>("");
  const [isGenerating, setIsGenerating] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isGeneratingVideo, setIsGeneratingVideo] = useState(false);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
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
        const progress = typeof message.progress === "number" ? message.progress : scriptGenProgress;
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
  }, [project?.id, scriptGenProgress]);

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
  }, [project?.id, videoGenProgress]);

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
  const handleNarrationTypeChange = async (
    e: React.ChangeEvent<HTMLSelectElement>
  ) => {
    const newType = e.target.value as NarrationType;
    try {
      await updateProject({ narration_type: newType });
    } catch (err) {
      console.error("更新解说类型失败:", err);
    }
  };

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

      {/* 项目配置区 */}
      <div className="bg-white rounded-lg shadow-md p-6 space-y-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">项目配置</h2>

        {/* 解说类型（Figma 风格选择框）*/}
        <div>
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
            </select>
            <ChevronDown className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
          </div>
        </div>

        {/* 视频源管理：上传 / 排序 / 合并（Figma 布局）*/}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            视频源（上传、拖拽排序、合并）
          </label>
          <div className="text-xs text-gray-500 mb-2 flex items-center space-x-2">
            <span className="px-2 py-0.5 bg-gray-100 rounded">步骤 1：上传视频</span>
            <span className="px-2 py-0.5 bg-gray-100 rounded">步骤 2：拖拽排序</span>
            <span className="px-2 py-0.5 bg-gray-100 rounded">步骤 3：点击“合并视频”</span>
          </div>
          <div className="flex gap-6">
            {/* 左侧：上传区域（紫色虚线卡片、居中内容）*/}
            <div
              onDragOver={handleVideoDragOver}
              onDragLeave={handleVideoDragLeave}
              onDrop={handleVideoDrop}
              className={`flex-1 flex flex-col items-center justify-center text-center rounded-lg p-8 border border-dashed transition-colors ${
                isDraggingVideo ? "border-violet-500 bg-violet-50" : "border-violet-300 bg-violet-50"
              }`}
              aria-label="点击或拖拽视频至此"
            >
              <Upload className="h-12 w-12 text-violet-500 mb-4" />
              <div className="text-base font-semibold text-violet-600">点击或拖拽视频至此</div>
              <div className="text-xs text-gray-500 mt-2">支持多文件上传，自动排序</div>
              <button
                onClick={() => videoInputRef.current?.click()}
                disabled={uploadingVideo}
                className="mt-4 px-6 py-2 bg-violet-600 text-white rounded-md hover:bg-violet-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                选择文件
              </button>
              <input
                ref={videoInputRef}
                type="file"
                accept="video/*"
                multiple
                onChange={handleVideoFileChange}
                className="hidden"
              />
            </div>

            {/* 右侧：文件列表面板 */}
            <div className="flex-[2] flex flex-col space-y-3">
              <div className="flex items-center justify-between">
                <div className="text-base font-semibold text-gray-800">
                  已上传视频 ({Array.isArray(videoOrder) ? videoOrder.length : (Array.isArray(project.video_paths) ? project.video_paths.length : 0)})
                </div>
                {Array.isArray(project.video_paths) && project.video_paths.length >= 2 && (
                  <button
                    onClick={handleMergeClick}
                    disabled={uploadingVideo}
                    className="px-4 py-2 bg-violet-600 text-white rounded-md hover:bg-violet-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    合并视频
                  </button>
                )}
              </div>

              {Array.isArray(videoOrder) && videoOrder.length > 0 ? (
                <div className="max-h-72 overflow-auto space-y-2">
                  {videoOrder.map((vp, idx) => (
                    <div
                      key={vp}
                      className={`flex items-center justify-between text-sm bg-gray-50 border border-gray-200 rounded-md px-3 py-2 ${dragIndex===idx?"ring-2 ring-violet-300":""}`}
                      draggable
                      onDragStart={() => handleItemDragStart(idx)}
                      onDragOver={(e) => handleItemDragOver(e, idx)}
                      onDrop={handleItemDrop}
                    >
                      <div className="flex items-center space-x-3">
                        <span className="text-gray-300 font-mono">::</span>
                        <span className="truncate max-w-xs text-gray-800" title={vp}>{project.video_names?.[vp] || vp.split("/").pop()}</span>
                        <span className="text-xs text-gray-400">#{idx+1}</span>
                      </div>
                      <button
                        onClick={(e) => { e.stopPropagation(); deleteVideoItem(vp); }}
                        className="px-2 py-1 text-xs bg-red-100 text-red-700 border border-red-300 rounded hover:bg-red-200"
                        title="删除"
                      >
                        删除
                      </button>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-xs text-gray-500">暂无视频文件，请先上传</div>
              )}
            </div>
          </div>
        </div>
          {merging && Array.isArray(project.video_paths) && project.video_paths.length >= 2 && !project.merged_video_path && mergeProgress >= 0 && mergeProgress < 100 && (
            <div className="mt-2">
              <div className="flex items-center justify-between text-xs text-gray-600 mb-1">
                <span>合并进度</span>
                <span>{mergeProgress}%</span>
              </div>
              <div className="w-full h-2 bg-gray-200 rounded">
                <div
                  className="h-2 bg-purple-600 rounded transition-all"
                  style={{ width: `${mergeProgress}%` }}
                />
              </div>
            </div>
          )}
          {project.merged_video_path && (
            <div className="mt-3">
              <div className="mt-2 text-xs text-gray-700">
                已合并视频：
                <button
                  type="button"
                  onClick={() => setShowMergedPreview(true)}
                  className="ml-1 break-all text-blue-600 hover:underline"
                  title="点击预览合并视频"
                >
                  {project.merged_video_path}
                </button>
              </div>
            </div>
          )}
          {merging && project.merged_video_path && mergeProgress >= 0 && mergeProgress < 100 && (
            <div className="mt-2">
              <div className="flex items-center justify-between text-xs text-gray-600 mb-1">
                <span>合并进度</span>
                <span>{mergeProgress}%</span>
              </div>
              <div className="w-full h-2 bg-gray-200 rounded">
                <div
                  className="h-2 bg-purple-600 rounded transition-all"
                  style={{ width: `${mergeProgress}%` }}
                />
              </div>
            </div>
          )}
          {uploadingVideo && (
            <div className="mt-2">
              <div className="flex items-center justify-between text-xs text-gray-600 mb-1">
                <span>上传进度</span>
                <span>{videoUploadProgress}%</span>
              </div>
              <div className="w-full h-2 bg-gray-200 rounded">
                <div
                  className="h-2 bg-blue-600 rounded transition-all"
                  style={{ width: `${videoUploadProgress}%` }}
                />
              </div>
            </div>
          )}
        

        {/* 操作按钮：生成脚本 / 生成视频 / 下载视频（Figma 配色与风格） */}
        <div className="pt-4 border-t border-gray-200 flex items-center space-x-3 flex-wrap">
          <button
            onClick={handleGenerateScript}
            disabled={!project.video_path || isGenerating}
            className="bg-violet-600 mt-2 flex items-center px-6 py-3 bg-violet-300 text-white rounded-lg font-medium hover:bg-violet-800 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isGenerating ? (
              <>
                <Loader className="h-5 w-5 mr-2 animate-spin" />
                生成中...
              </>
            ) : (
              <>
                生成解说脚本
              </>
            )}
          </button>
          {/* 生成视频实时进度显示 */}
          {(isGeneratingVideo || (videoGenProgress > 0 && videoGenProgress < 100)) && (
            <div className="w-full mt-3">
              <div className="flex items-center justify-between text-xs text-gray-600 mb-1">
                <span>视频生成进度</span>
                <span>{Math.round(videoGenProgress)}%</span>
              </div>
              <div className="w-full h-2 bg-gray-200 rounded">
                <div
                  className="h-2 bg-blue-600 rounded transition-all"
                  style={{ width: `${Math.round(videoGenProgress)}%` }}
                />
              </div>
              {/* 步骤日志 */}
              {videoGenLogs.length > 0 && (
                <div className="mt-2 space-y-1">
                  {videoGenLogs.slice(-1).map((log, idx) => (
                    <div key={`${log.timestamp}-${idx}`} className="text-xs text-gray-700 flex items-center">
                      {log.type === "error" ? (
                        <AlertCircle className="h-3 w-3 mr-1 text-red-600" />
                      ) : (
                        <Loader className="h-3 w-3 mr-1 text-blue-600" />
                      )}
                      <span className="break-all">{log.message}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* 合并视频预览弹窗 */}
          {showMergedPreview && project?.merged_video_path && (
            <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center">
              <div className="bg-white rounded-lg shadow-xl w-full max-w-3xl mx-4">
                <div className="flex items-center justify-between p-3 border-b">
                  <div className="flex items-center text-sm font-medium text-gray-800">
                    <FileVideo className="h-4 w-4 mr-1" /> 合并视频预览
                  </div>
                  <button
                    onClick={() => setShowMergedPreview(false)}
                    className="text-gray-600 hover:text-gray-900"
                    title="关闭预览"
                  >
                    ✕
                  </button>
                </div>
                <div className="p-3">
                  <video
                    key={project.merged_video_path}
                    src={projectService.getMergedVideoUrl(project.id)}
                    controls
                    className="w-full rounded-lg bg-black max-h-[70vh]"
                    preload="metadata"
                  />
                </div>
              </div>
            </div>
          )}
          {/* 生成脚本实时进度显示 */}
          {(isGenerating || (scriptGenProgress > 0 && scriptGenProgress < 100)) && (
            <div className="w-full ml-0 mt-3">
              <div className="flex items-center justify-between text-xs text-gray-600 mb-1">
                <span>脚本生成进度</span>
                <span>{Math.round(scriptGenProgress)}%</span>
              </div>
              <div className="w-full h-2 mb-2 bg-gray-200 rounded">
                <div
                  className="h-2 bg-blue-600 rounded transition-all"
                  style={{ width: `${Math.round(scriptGenProgress)}%` }}
                />
              </div>
              {/* 步骤日志 */}
              {scriptGenLogs.length > 0 && (
                <div className="mb-2 space-y-1">
                  {scriptGenLogs.slice(-1).map((log, idx) => (
                    <div key={`${log.timestamp}-${idx}`} className="text-xs text-gray-700 flex items-center">
                      {log.type === "error" ? (
                        <AlertCircle className="h-3 w-3 mr-1 text-red-600" />
                      ) : (
                        <Loader className="h-3 w-3 mr-1 text-blue-600" />
                      )}
                      <span className="break-all">{log.message}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
          <button
            onClick={handleGenerateVideo}
            disabled={!project.script || !project.video_path || isGeneratingVideo}
            className="flex mt-2 items-center px-6 py-3 bg-violet-600 text-white rounded-lg font-medium shadow-md hover:bg-violet-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isGeneratingVideo ? (
              <>
                <Loader className="h-5 w-5 mr-2 animate-spin" />
                生成视频中...
              </>
            ) : (
              <>
                生成视频
              </>
            )}
          </button>
          <button
            onClick={handleDownloadVideo}
            disabled={!project.output_video_path}
            className="flex mt-2 items-center px-6 py-3 bg-white text-green-600 border border-green-500 rounded-lg font-medium hover:bg-green-50 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            下载视频
          </button>
          {project.output_video_path && (
            <div className="mt-2 text-xs text-gray-600">
              已生成：
              <button
                onClick={() => setShowOutputPreview(true)}
                className="ml-1 break-all text-blue-600 hover:underline"
                title="点击预览输出视频"
              >
                {project.output_video_path.split("/").pop()}
              </button>
            </div>
          )}
          {/* 输出视频预览弹窗 */}
          {showOutputPreview && project?.output_video_path && (
            <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center">
              <div className="bg-white rounded-lg shadow-xl w-full max-w-3xl mx-4">
                <div className="flex items-center justify-between p-3 border-b">
                  <div className="flex items-center text-sm font-medium text-gray-800">
                    <FileVideo className="h-4 w-4 mr-1" /> 输出视频预览
                  </div>
                  <button
                    onClick={() => setShowOutputPreview(false)}
                    className="text-gray-600 hover:text-gray-900"
                    title="关闭预览"
                  >
                    ✕
                  </button>
                </div>
                <div className="p-3">
                  <video
                    key={project.output_video_path}
                    src={projectService.getOutputVideoDownloadUrl(project.id)}
                    controls
                    className="w-full rounded-lg bg-black max-h-[70vh]"
                    preload="metadata"
                  />
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* 视频脚本编辑区 */}
      <div className="bg-white rounded-lg shadow-md p-6 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-gray-900">视频脚本</h2>
          <button
            onClick={handleSaveScript}
            disabled={!editedScript.trim() || isSaving}
            className="flex items-center px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isSaving ? (
              <>
                <Loader className="h-4 w-4 mr-2 animate-spin" />
                保存中...
              </>
            ) : (
              <>
                <Save className="h-4 w-4 mr-2" />
                保存脚本
              </>
            )}
          </button>
        </div>

        <p className="text-sm text-gray-600">
          点击"生成解说脚本"后，脚本数据将显示在下方的编辑器中，您可以修改后保存。
        </p>

        {/* JSON 编辑器 */}
        <div className="relative">
          <textarea
            value={editedScript}
            onChange={(e) => setEditedScript(e.target.value)}
            placeholder="脚本数据将以 JSON 格式显示在这里..."
            className="w-full h-96 px-4 py-3 font-mono text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none transition-all resize-none"
          />
          {editedScript && (
            <div className="absolute top-2 right-2 bg-gray-100 px-2 py-1 rounded text-xs text-gray-600">
              JSON 格式
            </div>
          )}
        </div>

        {/* 脚本示例提示 */}
        {!editedScript && (
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
            <p className="text-sm text-blue-800 font-medium mb-2">
              脚本 JSON 格式示例：
            </p>
            <pre className="text-xs text-blue-700 overflow-x-auto">
              {`{
  "version": "1.0",
  "total_duration": 120.5,
  "segments": [
    {
      "id": "1",
      "start_time": 0.0,
      "end_time": 5.5,
      "text": "这是解说文本",
      "subtitle": "对应的字幕"
    }
  ],
  "metadata": {
    "video_name": "视频名称",
    "created_at": "2024-01-01T00:00:00Z"
  }
}`}
            </pre>
          </div>
        )}
      </div>
    </div>
  );
};

export default ProjectEditPage;

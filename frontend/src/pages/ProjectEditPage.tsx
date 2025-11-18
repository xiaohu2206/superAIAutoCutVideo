// 项目编辑页面（二级页面）

import {
  AlertCircle,
  ArrowLeft,
  CheckCircle,
  Download,
  FileText,
  FileVideo,
  Loader,
  Save,
  Sparkles,
  Upload,
  Video,
} from "lucide-react";
import React, { useRef, useState } from "react";
import { useProjectDetail } from "../hooks/useProjects";
import type { VideoScript } from "../types/project";
import { NarrationType } from "../types/project";

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
    uploadVideo,
    uploadVideos,
    uploadSubtitle,
    deleteVideo,
    deleteVideoItem,
    deleteSubtitle,
    generateScript,
    saveScript,
    generateVideo,
    downloadVideo,
    mergeVideos,
    mergeProgress,
  } = useProjectDetail(projectId);

  const [editedScript, setEditedScript] = useState<string>("");
  const [isGenerating, setIsGenerating] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isGeneratingVideo, setIsGeneratingVideo] = useState(false);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const videoInputRef = useRef<HTMLInputElement>(null);
  const subtitleInputRef = useRef<HTMLInputElement>(null);

  // 拖拽上传状态
  const [isDraggingVideo, setIsDraggingVideo] = useState(false);
  const [isDraggingSubtitle, setIsDraggingSubtitle] = useState(false);
  // 上传进度与状态
  const [uploadingVideo, setUploadingVideo] = useState(false);
  const [uploadingSubtitle, setUploadingSubtitle] = useState(false);
  const [videoUploadProgress, setVideoUploadProgress] = useState<number>(0);
  const [subtitleUploadProgress, setSubtitleUploadProgress] = useState<number>(0);

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
   * 处理字幕文件选择
   */
  const handleSubtitleFileChange = async (
    e: React.ChangeEvent<HTMLInputElement>
  ) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (!file.name.endsWith(".srt")) {
      alert("请上传 .srt 格式的字幕文件");
      return;
    }

    setSuccessMessage(null);

    setUploadingSubtitle(true);
    setSubtitleUploadProgress(0);
    try {
      await uploadSubtitle(file, (p) => setSubtitleUploadProgress(p));
      setSuccessMessage("字幕文件上传成功！");
      setTimeout(() => setSuccessMessage(null), 3000);
    } catch (err) {
      console.error("上传字幕失败:", err);
    } finally {
      setUploadingSubtitle(false);
      setTimeout(() => setSubtitleUploadProgress(0), 800);
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
   * 字幕拖拽上传
   */
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
    const file = e.dataTransfer.files?.[0];
    if (!file) return;

    if (!file.name.endsWith(".srt")) {
      alert("请上传 .srt 格式的字幕文件");
      return;
    }

    setSuccessMessage(null);

    setUploadingSubtitle(true);
    setSubtitleUploadProgress(0);
    try {
      await uploadSubtitle(file, (p) => setSubtitleUploadProgress(p));
      setSuccessMessage("字幕文件上传成功！");
      setTimeout(() => setSuccessMessage(null), 3000);
    } catch (err) {
      console.error("上传字幕失败:", err);
    } finally {
      setUploadingSubtitle(false);
      setTimeout(() => setSubtitleUploadProgress(0), 800);
    }
  };

  /**
   * 删除视频文件
   */
  const handleDeleteVideo = async () => {
    if (!project?.video_path) return;
    setSuccessMessage(null);
    try {
      await deleteVideo();
      setSuccessMessage("视频文件已删除！");
      setTimeout(() => setSuccessMessage(null), 3000);
    } catch (err) {
      console.error("删除视频失败:", err);
    }
  };

  /**
   * 删除字幕文件
   */
  const handleDeleteSubtitle = async () => {
    if (!project?.subtitle_path) return;
    setSuccessMessage(null);
    try {
      await deleteSubtitle();
      setSuccessMessage("字幕文件已删除！");
      setTimeout(() => setSuccessMessage(null), 3000);
    } catch (err) {
      console.error("删除字幕失败:", err);
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
  console.log("mergeProgress", mergeProgress)
  return (
    <div className="space-y-6">
      {/* 页面头部 */}
      <div className="bg-white rounded-lg shadow-md p-6">
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
                {project.description || "编辑项目详细信息"}
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

        {/* 解说类型 */}
        <div>
          <label
            htmlFor="narration-type"
            className="block text-sm font-medium text-gray-700 mb-2"
          >
            解说类型
          </label>
          <select
            id="narration-type"
            value={project.narration_type}
            onChange={handleNarrationTypeChange}
            className="w-full md:w-1/2 px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none transition-all"
          >
            <option value={NarrationType.SHORT_DRAMA}>短剧解说</option>
          </select>
        </div>

        {/* 视频文件上传 */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            视频文件
          </label>
          <div
            onDragOver={handleVideoDragOver}
            onDragLeave={handleVideoDragLeave}
            onDrop={handleVideoDrop}
            className={`flex items-center space-x-4 border-2 border-dashed rounded-lg p-4 transition-colors ${
              isDraggingVideo ? "border-blue-500 bg-blue-50" : "border-gray-200"
            }`}
            aria-label="拖拽视频文件到此区域或点击上传"
          >
            <button
              onClick={() => videoInputRef.current?.click()}
              disabled={uploadingVideo}
              className="flex items-center px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <Upload className="h-4 w-4 mr-2" />
              上传视频
            </button>
            <input
              ref={videoInputRef}
              type="file"
              accept="video/*"
              multiple
              onChange={handleVideoFileChange}
              className="hidden"
            />
            <span className="text-xs text-gray-500">拖拽视频到此或点击“上传视频”</span>
            {Array.isArray(project.video_paths) && project.video_paths.length > 0 && (
              <div className="flex-1">
                <div className="flex flex-col space-y-1">
                  {project.video_paths.map((vp) => (
                    <div key={vp} className="flex items-center text-sm text-gray-600">
                      <FileVideo className="h-4 w-4 mr-2 text-green-500" />
                      <span className="truncate max-w-md">{vp.split("/").pop()}</span>
                      <button
                        onClick={() => deleteVideoItem(vp)}
                        className="ml-3 px-2 py-1 text-xs bg-red-100 text-red-700 border border-red-300 rounded hover:bg-red-200"
                      >
                        删除
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}
            {Array.isArray(project.video_paths) && project.video_paths.length >= 2 && (
              <button
                onClick={mergeVideos}
                disabled={uploadingVideo}
                className="ml-auto px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition-colors"
              >
                合并视频
              </button>
            )}
          </div>
          {Array.isArray(project.video_paths) && project.video_paths.length >= 2 && !project.merged_video_path && mergeProgress > 0 && mergeProgress < 100 && (
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
            <div className="mt-2 text-xs text-gray-700">
              已合并视频：
              <span className="ml-1 break-all">{project.merged_video_path}</span>
            </div>
          )}
          {project.merged_video_path && mergeProgress > 0 && mergeProgress < 100 && (
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
        </div>

        {/* 字幕文件上传 */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            上传字幕（.srt 格式）
          </label>
          <div
            onDragOver={handleSubtitleDragOver}
            onDragLeave={handleSubtitleDragLeave}
            onDrop={handleSubtitleDrop}
            className={`flex items-center space-x-4 border-2 border-dashed rounded-lg p-4 transition-colors ${
              isDraggingSubtitle ? "border-blue-500 bg-blue-50" : "border-gray-200"
            }`}
            aria-label="拖拽字幕文件到此区域或点击上传"
          >
            <button
              onClick={() => subtitleInputRef.current?.click()}
              disabled={uploadingSubtitle}
              className="flex items-center px-4 py-2 bg-gray-100 text-gray-700 border border-gray-300 rounded-lg hover:bg-gray-200 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <Upload className="h-4 w-4 mr-2" />
              上传字幕
            </button>
            <input
              ref={subtitleInputRef}
              type="file"
              accept=".srt"
              onChange={handleSubtitleFileChange}
              className="hidden"
            />
            <span className="text-xs text-gray-500">拖拽 .srt 字幕到此或点击“上传字幕”</span>
            {project.subtitle_path && (
              <div className="flex items-center text-sm text-gray-600">
                <FileText className="h-4 w-4 mr-2 text-green-500" />
                <span className="truncate max-w-md">
                  {project.subtitle_path.split("/").pop()}
                </span>
                <button
                  onClick={handleDeleteSubtitle}
                  className="ml-3 px-2 py-1 text-xs bg-red-100 text-red-700 border border-red-300 rounded hover:bg-red-200"
                >
                  删除字幕
                </button>
              </div>
            )}
          </div>
          {uploadingSubtitle && (
            <div className="mt-2">
              <div className="flex items-center justify-between text-xs text-gray-600 mb-1">
                <span>上传进度</span>
                <span>{subtitleUploadProgress}%</span>
              </div>
              <div className="w-full h-2 bg-gray-200 rounded">
                <div
                  className="h-2 bg-blue-600 rounded transition-all"
                  style={{ width: `${subtitleUploadProgress}%` }}
                />
              </div>
            </div>
          )}
        </div>

        {/* 操作按钮：生成脚本 / 生成视频 / 下载视频 */}
        <div className="pt-4 border-t border-gray-200 flex items-center space-x-3 flex-wrap">
          <button
            onClick={handleGenerateScript}
            disabled={!project.video_path || isGenerating}
            className="flex items-center px-6 py-3 bg-gradient-to-r from-purple-600 to-blue-600 text-white rounded-lg font-medium hover:from-purple-700 hover:to-blue-700 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isGenerating ? (
              <>
                <Loader className="h-5 w-5 mr-2 animate-spin" />
                生成中...
              </>
            ) : (
              <>
                <Sparkles className="h-5 w-5 mr-2" />
                生成解说脚本
              </>
            )}
          </button>
          <button
            onClick={handleGenerateVideo}
            disabled={!project.script || !project.video_path || isGeneratingVideo}
            className="flex items-center px-6 py-3 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isGeneratingVideo ? (
              <>
                <Loader className="h-5 w-5 mr-2 animate-spin" />
                生成视频中...
              </>
            ) : (
              <>
                <Video className="h-5 w-5 mr-2" />
                生成视频
              </>
            )}
          </button>
          <button
            onClick={handleDownloadVideo}
            disabled={!project.output_video_path}
            className="flex items-center px-6 py-3 bg-green-600 text-white rounded-lg font-medium hover:bg-green-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Download className="h-5 w-5 mr-2" />
            下载视频
          </button>
          {project.output_video_path && (
            <span className="text-xs text-gray-600">已生成：{project.output_video_path.split("/").pop()}</span>
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

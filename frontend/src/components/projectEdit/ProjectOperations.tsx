import { AlertCircle, Check, Clipboard, ChevronDown, Download, FileVideo, FolderOpen, Loader, Play, Scissors } from "lucide-react";
import React, { useEffect, useState } from "react";
import { projectService } from "../../services/projectService";
import { Project } from "../../types/project";
import { Dropdown } from "../ui/Dropdown";

interface ProjectOperationsProps {
  project: Project;
  isGeneratingScript: boolean;
  handleGenerateScript: () => void;
  scriptGenProgress: number;
  scriptGenLogs: { timestamp: string; message: string; type?: string }[];
  isGeneratingVideo: boolean;
  handleGenerateVideo: () => void;
  videoGenProgress: number;
  videoGenLogs: { timestamp: string; message: string; type?: string }[];
  handleDownloadVideo: () => void;
  isGeneratingDraft: boolean;
  handleGenerateDraft: () => void;
  draftGenProgress: number;
  draftGenLogs: { timestamp: string; message: string; type?: string }[];
  showMergedPreview: boolean;
  setShowMergedPreview: (show: boolean) => void;
  showOutputPreview: boolean;
  setShowOutputPreview: (show: boolean) => void;
}

const ProjectOperations: React.FC<ProjectOperationsProps> = ({
  project,
  isGeneratingScript,
  handleGenerateScript,
  scriptGenProgress,
  scriptGenLogs,
  isGeneratingVideo,
  handleGenerateVideo,
  videoGenProgress,
  videoGenLogs,
  handleDownloadVideo,
  isGeneratingDraft,
  handleGenerateDraft,
  draftGenProgress,
  draftGenLogs,
  showMergedPreview,
  setShowMergedPreview,
  showOutputPreview,
  setShowOutputPreview,
}) => {
  const [outputVideoCacheBust, setOutputVideoCacheBust] = useState<number>(0);
  const [copying, setCopying] = useState(false);
  const [opening, setOpening] = useState(false);

  const draftPath = project?.jianying_draft_last_dir || project?.jianying_draft_last_dir_web || "";

  useEffect(() => {
    if (showOutputPreview && project.output_video_path) {
      setOutputVideoCacheBust(Date.now());
    }
  }, [showOutputPreview, project.output_video_path]);

  useEffect(() => {
    if (!isGeneratingVideo && project.output_video_path) {
      setOutputVideoCacheBust(Date.now());
    }
  }, [isGeneratingVideo, project.output_video_path]);

  const handleCopyDraftPath = async () => {
    if (!draftPath) return;
    try {
      setCopying(true);
      await navigator.clipboard.writeText(draftPath.toString());
      alert("草稿路径已复制到剪贴板");
    } catch (e) {
      alert("复制失败");
    } finally {
      setCopying(false);
    }
  };

  const handleOpenDraftDir = async () => {
    if (!draftPath) {
      alert("尚未生成剪映草稿");
      return;
    }
    try {
      setOpening(true);
      await projectService.openPathInExplorer(project.id, draftPath.toString());
    } catch (e: any) {
      alert(e?.message || "打开文件管理器失败");
    } finally {
      setOpening(false);
    }
  };

  return (
    <div className="pt-4 border-t border-gray-200 flex items-center space-x-3 flex-wrap">
      <button
        onClick={handleGenerateScript}
        disabled={!project.video_path || isGeneratingScript}
        className="bg-violet-600 mt-2 flex items-center px-6 py-2 bg-violet-300 text-white rounded-lg font-medium hover:bg-violet-800 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {isGeneratingScript ? (
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

       {project.script && project.video_path && 
       <Dropdown
        trigger={
          <button className="flex mt-2 items-center px-6 py-2 bg-violet-600 text-white rounded-lg font-medium shadow-md hover:bg-violet-700 transition-colors">
            视频操作
            <ChevronDown className="ml-2 h-4 w-4" />
          </button>
        }
        items={[
          {
            label: (
              <>
                {isGeneratingVideo ? <Loader className="h-4 w-4 mr-2 animate-spin" /> : <Play className="h-4 w-4 mr-2" />}
                {isGeneratingVideo ? "生成视频中..." : "生成视频"}
              </>
            ),
            onClick: handleGenerateVideo,
            disabled: !project.script || !project.video_path || isGeneratingVideo,
          },
          {
            label: (
              <>
                <Download className="h-4 w-4 mr-2" />
                下载视频
              </>
            ),
            onClick: handleDownloadVideo,
            disabled: !project.output_video_path,
          },
          {
            label: (
              <>
                {isGeneratingDraft ? <Loader className="h-4 w-4 mr-2 animate-spin" /> : <Scissors className="h-4 w-4 mr-2" />}
                {isGeneratingDraft ? "生成草稿中..." : "生成剪映草稿"}
              </>
            ),
            onClick: handleGenerateDraft,
            disabled: !project.script || !project.video_path || isGeneratingDraft,
          },
        ]}
      />
      }
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

      {(isGeneratingDraft || (draftGenProgress > 0 && draftGenProgress < 100)) && (
        <div className="w-full mt-3">
          <div className="flex items-center justify-between text-xs text-gray-600 mb-1">
            <span>剪映草稿生成进度</span>
            <span>{Math.round(draftGenProgress)}%</span>
          </div>
          <div className="w-full h-2 bg-gray-200 rounded">
            <div
              className="h-2 bg-blue-600 rounded transition-all"
              style={{ width: `${Math.round(draftGenProgress)}%` }}
            />
          </div>
          {draftGenLogs.length > 0 && (
            <div className="mt-2 space-y-1">
              {draftGenLogs.slice(-1).map((log, idx) => (
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
                src={projectService.getMergedVideoUrl(project.id, outputVideoCacheBust)}
                controls
                className="w-full rounded-lg bg-black max-h-[70vh]"
                preload="metadata"
              />
            </div>
          </div>
        </div>
      )}
      {/* 生成脚本实时进度显示 */}
      {(isGeneratingScript || (scriptGenProgress > 0 && scriptGenProgress < 100)) && (
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
     
      {(draftPath || project.output_video_path) && (
        <div className="w-full mt-4 bg-gray-50 rounded-lg border border-gray-200 divide-y divide-gray-200 overflow-hidden">
          {/* 草稿目录 */}
          {draftPath && (
            <div className="px-4 py-3 flex items-center justify-between hover:bg-gray-100 transition-colors">
              <div className="flex items-center min-w-0 mr-4 overflow-hidden">
                <FolderOpen className="h-4 w-4 text-gray-500 mr-2 flex-shrink-0" />
                <span className="text-xs font-medium text-gray-500 mr-2 flex-shrink-0">草稿路径:</span>
                <span className="text-xs text-gray-700 truncate font-mono select-all" title={draftPath.toString()}>
                  {draftPath.toString()}
                </span>
              </div>
              <div className="flex items-center space-x-1 flex-shrink-0">
                <button
                  onClick={handleCopyDraftPath}
                  className={`p-1.5 rounded-md transition-all ${
                    copying 
                      ? "bg-green-100 text-green-600" 
                      : "text-gray-400 hover:text-gray-700 hover:bg-gray-200"
                  }`}
                  title="复制路径"
                >
                  {copying ? <Check className="h-3.5 w-3.5" /> : <Clipboard className="h-3.5 w-3.5" />}
                </button>
                <button
                  onClick={handleOpenDraftDir}
                  className="p-1.5 text-gray-400 hover:text-blue-600 hover:bg-blue-50 rounded-md transition-all"
                  title="打开文件管理器"
                >
                  {opening ? <Loader className="h-3.5 w-3.5 animate-spin" /> : <FolderOpen className="h-3.5 w-3.5" />}
                </button>
              </div>
            </div>
          )}

          {/* 输出视频 */}
          {project.output_video_path && (
            <div className="px-4 py-3 flex items-center justify-between hover:bg-gray-100 transition-colors">
              <div className="flex items-center min-w-0 overflow-hidden">
                <FileVideo className="h-4 w-4 text-blue-500 mr-2 flex-shrink-0" />
                <span className="text-xs font-medium text-gray-500 mr-2 flex-shrink-0">成品:</span>
                <button
                  onClick={() => setShowOutputPreview(true)}
                  className="text-xs text-blue-600 hover:text-blue-700 hover:underline truncate font-medium text-left"
                  title="点击预览"
                >
                  {project.output_video_path.split("/").pop()}
                </button>
              </div>
              <button
                onClick={() => setShowOutputPreview(true)}
                className="ml-2 text-xs px-2 py-1 bg-white border border-gray-200 text-gray-600 rounded hover:bg-blue-50 hover:text-blue-600 hover:border-blue-200 transition-all shadow-sm"
              >
                预览
              </button>
            </div>
          )}
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
                key={`${project.output_video_path}-${outputVideoCacheBust}`}
                src={projectService.getOutputVideoDownloadUrl(project.id, outputVideoCacheBust)}
                controls
                className="w-full rounded-lg bg-black max-h-[70vh]"
                preload="metadata"
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default ProjectOperations;

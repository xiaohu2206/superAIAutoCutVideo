import React from "react";
import {
  Loader,
  AlertCircle,
  FileVideo,
} from "lucide-react";
import { projectService } from "../../services/projectService";
import { Project } from "../../types/project";

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
  showMergedPreview,
  setShowMergedPreview,
  showOutputPreview,
  setShowOutputPreview,
}) => {
  return (
    <div className="pt-4 border-t border-gray-200 flex items-center space-x-3 flex-wrap">
      <button
        onClick={handleGenerateScript}
        disabled={!project.video_path || isGeneratingScript}
        className="bg-violet-600 mt-2 flex items-center px-6 py-3 bg-violet-300 text-white rounded-lg font-medium hover:bg-violet-800 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
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
  );
};

export default ProjectOperations;

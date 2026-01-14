import { Upload } from "lucide-react";
import React from "react";
import { message } from "../../services/message";
import { projectService } from "../../services/projectService";
import type { Project } from "../../types/project";

interface VideoSourcesManagerProps {
  project: Project;
  videoOrder: string[];
  dragIndex: number | null;
  isDraggingVideo: boolean;
  uploadingVideo: boolean;
  merging: boolean;
  mergeProgress: number;
  videoUploadProgress: number;
  videoInputRef: React.RefObject<HTMLInputElement>;
  onVideoDragOver: (e: React.DragEvent<HTMLDivElement>) => void;
  onVideoDragLeave: (e: React.DragEvent<HTMLDivElement>) => void;
  onVideoDrop: (e: React.DragEvent<HTMLDivElement>) => void;
  onVideoFileChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  onMergeClick: () => void;
  onItemDragStart: (index: number) => void;
  onItemDragOver: (
    e: React.DragEvent<HTMLDivElement>,
    overIndex: number
  ) => void;
  onItemDrop: (e: React.DragEvent<HTMLDivElement>) => void;
  onDeleteVideoItem: (path: string) => void;
}

const VideoSourcesManager: React.FC<VideoSourcesManagerProps> = ({
  project,
  videoOrder,
  dragIndex,
  isDraggingVideo,
  uploadingVideo,
  merging,
  mergeProgress,
  videoUploadProgress,
  videoInputRef,
  onVideoDragOver,
  onVideoDragLeave,
  onVideoDrop,
  onVideoFileChange,
  onMergeClick,
  onItemDragStart,
  onItemDragOver,
  onItemDrop,
  onDeleteVideoItem,
}) => {
  const handleOpenMergedVideoInExplorer = async () => {
    if (!project.merged_video_path) {
      message.error("尚未生成合并后的视频");
      return;
    }
    try {
      await projectService.openPathInExplorer(project.id, project.merged_video_path);
      message.success("已打开文件管理器");
    } catch (e: any) {
      message.error(e?.message || "打开文件管理器失败");
    }
  };

  return (
    <>
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
          <div
            onDragOver={onVideoDragOver}
            onDragLeave={onVideoDragLeave}
            onDrop={onVideoDrop}
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
              onChange={onVideoFileChange}
              className="hidden"
            />
          </div>

          <div className="flex-[2] flex flex-col space-y-3">
            <div className="flex items-center justify-between">
              <div className="text-base font-semibold text-gray-800">
                已上传视频 ({Array.isArray(videoOrder) ? videoOrder.length : (Array.isArray(project.video_paths) ? project.video_paths.length : 0)})
              </div>
              {Array.isArray(project.video_paths) && project.video_paths.length >= 2 && (
                <button
                  onClick={onMergeClick}
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
                    onDragStart={() => onItemDragStart(idx)}
                    onDragOver={(e) => onItemDragOver(e, idx)}
                    onDrop={onItemDrop}
                  >
                    <div className="flex items-center space-x-3">
                      <span className="text-gray-300 font-mono">::</span>
                      <span className="truncate max-w-xs text-gray-800" title={vp}>{project.video_names?.[vp] || vp.split("/").pop()}</span>
                      <span className="text-xs text-gray-400">#{idx+1}</span>
                    </div>
                    <button
                      onClick={(e) => { e.stopPropagation(); onDeleteVideoItem(vp); }}
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
              onClick={handleOpenMergedVideoInExplorer}
              className="ml-1 break-all text-blue-600 hover:underline"
              title="在文件管理器中定位"
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
    </>
  );
};

export default VideoSourcesManager;


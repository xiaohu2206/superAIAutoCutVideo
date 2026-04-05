import { ArrowRight, Loader } from "lucide-react";
import React from "react";
import type { Project, SubtitleMeta, SubtitleSegment } from "../../types/project";
import AdvancedConfigSection from "./AdvancedConfigSection";
import SubtitleEditor from "./SubtitleEditor";
import VideoSourcesManager from "./VideoSourcesManager";
import SubtitleAsrSelector from "./SubtitleAsrSelector";
import SceneListTable from "./SceneListTable";
import ScenePlayModal from "./ScenePlayModal";
import VisionAnalysisChoiceModal from "./VisionAnalysisChoiceModal";
import OverwriteConfirmModal from "./OverwriteConfirmModal";
import { projectService } from "../../services/projectService";
import { videoVisionAnalysisScopeLabel } from "@/features/visionModel/constants";
import { videoModelService } from "@/services/videoModelService";

interface ProjectEditUploadStepProps {
  projectId: string;
  project: Project;
  refreshProject: () => Promise<void>;

  showAdvancedConfig: boolean;
  setShowAdvancedConfig: React.Dispatch<React.SetStateAction<boolean>>;

  uploadingSubtitle: boolean;
  subtitleUploadProgress: number;
  isDraggingSubtitle: boolean;
  onSubtitleFileChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  onDeleteSubtitle: () => void;
  onSubtitleDragOver: (e: React.DragEvent<HTMLDivElement>) => void;
  onSubtitleDragLeave: (e: React.DragEvent<HTMLDivElement>) => void;
  onSubtitleDrop: (e: React.DragEvent<HTMLDivElement>) => void;

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
  onItemDragOver: (e: React.DragEvent<HTMLDivElement>, overIndex: number) => void;
  onItemDrop: (e: React.DragEvent<HTMLDivElement>) => void;
  onDeleteVideoItem: (path: string) => void;

  subtitleLoading: boolean;
  extractingSubtitle: boolean;
  subtitleExtractProgress: number;
  subtitleExtractLogs: { timestamp: string; message: string; phase?: string; type?: string }[];
  onExtractSubtitle: () => void;
  subtitleAsr: { provider: "bcut" | "fun_asr"; modelKey: string; language: string };
  onSubtitleAsrChange: (next: { provider: "bcut" | "fun_asr"; modelKey: string; language: string }) => void;

  subtitleDraft: SubtitleSegment[];
  subtitleMeta: SubtitleMeta | null;
  subtitleSaving: boolean;
  onReloadSubtitle: () => void;
  onSaveSubtitle: () => void;
  onSubtitleDraftChange: (next: SubtitleSegment[]) => void;
  onNextStep: () => void;
  
  onExtractScenes: (options?: { analyzeVision: boolean; visionMode: string; visionKeyFrames?: 1 | 3; visionAction?: "auto" | "continue" | "restart" }) => void;
  extractingScene: boolean;
  sceneExtractProgress: number;
  sceneResult: any | null;
  sceneExtractMessage: string;
  sceneExtractPhase: string | null;
  visionChoiceModalOpen: boolean;
  onVisionChoiceContinue: () => void;
  onVisionChoiceRestart: () => void;
  onVisionChoiceCancel: () => void;
  subtitleOverwriteModalOpen: boolean;
  onSubtitleOverwriteConfirm: () => void;
  onSubtitleOverwriteCancel: () => void;
}

const ProjectEditUploadStep: React.FC<ProjectEditUploadStepProps> = ({
  project,
  refreshProject,
  showAdvancedConfig,
  setShowAdvancedConfig,
  uploadingSubtitle,
  subtitleUploadProgress,
  isDraggingSubtitle,
  onSubtitleFileChange,
  onDeleteSubtitle,
  onSubtitleDragOver,
  onSubtitleDragLeave,
  onSubtitleDrop,
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
  subtitleLoading,
  extractingSubtitle,
  subtitleExtractProgress,
  subtitleExtractLogs,
  onExtractSubtitle,
  subtitleAsr,
  onSubtitleAsrChange,
  subtitleDraft,
  subtitleMeta,
  subtitleSaving,
  onReloadSubtitle,
  onSaveSubtitle,
  onSubtitleDraftChange,
  onNextStep,
  onExtractScenes,
  extractingScene,
  sceneExtractProgress,
  sceneResult,
  sceneExtractMessage,
  visionChoiceModalOpen,
  onVisionChoiceContinue,
  onVisionChoiceRestart,
  onVisionChoiceCancel,
  subtitleOverwriteModalOpen,
  onSubtitleOverwriteConfirm,
  onSubtitleOverwriteCancel,
}) => {
  const canReExtractSubtitle =
    project.subtitle_source === "extracted" &&
    Boolean(project.subtitle_path) &&
    project.subtitle_status === "ready";

  const [scenePlayState, setScenePlayState] = React.useState<{
    isOpen: boolean;
    startTime: number;
    endTime: number;
  }>({
    isOpen: false,
    startTime: 0,
    endTime: 0,
  });

  const [visionMode, setVisionMode] = React.useState<"no_subtitles" | "all">("all");
  const visionKeyFrames: 1 | 3 = 1;
  const analyzeVision = true;

  const [visionScopeLabel, setVisionScopeLabel] = React.useState("视觉分析");

  React.useEffect(() => {
    if (project.project_type !== "visual") return;
    let cancelled = false;
    (async () => {
      try {
        const res = await videoModelService.getConfigs();
        if (!res?.success || cancelled) return;
        const activeId = res.data?.active_config_id as string | undefined;
        const configs = res.data?.configs as Record<string, { provider?: string }> | undefined;
        const provider = activeId && configs ? configs[activeId]?.provider : undefined;
        setVisionScopeLabel(videoVisionAnalysisScopeLabel(provider));
      } catch {
        if (!cancelled) setVisionScopeLabel("视觉分析");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [project.project_type]);

  return (
    <>
      <div className="bg-white rounded-lg shadow-md p-6 space-y-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-gray-900">项目配置</h2>
          <p className="text-xs text-gray-500 mb-2">
            {subtitleAsr.provider === "bcut" ? "内置 API 识别字幕仅支持中文" : "FunASR 可选择语言（需先下载模型）"}
          </p>
        </div>

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
          onVideoDragOver={onVideoDragOver}
          onVideoDragLeave={onVideoDragLeave}
          onVideoDrop={onVideoDrop}
          onVideoFileChange={onVideoFileChange}
          onMergeClick={onMergeClick}
          onItemDragStart={onItemDragStart}
          onItemDragOver={onItemDragOver}
          onItemDrop={onItemDrop}
          onDeleteVideoItem={onDeleteVideoItem}
          onRefreshProject={refreshProject}
        />
      </div>

      <div className="bg-white rounded-lg shadow-md p-6 space-y-3">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-gray-900"></h2>
          <button
            onClick={() => setShowAdvancedConfig((v) => !v)}
            className="text-blue-600 hover:text-blue-800 text-sm"
          >
            <span className="text-xs text-gray-500">（可选-上传字幕）</span>
            高级配置
          </button>
        </div>
          {showAdvancedConfig && (
          <AdvancedConfigSection
            uploadingSubtitle={uploadingSubtitle}
            subtitleUploadProgress={subtitleUploadProgress}
            subtitlePath={project.subtitle_path}
            onSubtitleFileChange={onSubtitleFileChange}
            onDeleteSubtitle={onDeleteSubtitle}
            isDraggingSubtitle={isDraggingSubtitle}
            onSubtitleDragOver={onSubtitleDragOver}
            onSubtitleDragLeave={onSubtitleDragLeave}
            onSubtitleDrop={onSubtitleDrop}
          />
        )}

        <div className="flex items-center justify-between flex-wrap gap-2">
          <div className="flex items-center gap-2 flex-wrap">
            <h2 className="text-lg font-semibold text-gray-900">
                {project.project_type === "visual" ? "镜头与字幕提取" : "字幕提取"}
            </h2>
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
          
          {project.project_type === "visual" ? (
             <div className="flex flex-col gap-2 items-end">
               <div className="flex flex-col gap-1.5 items-end text-xs text-gray-700 bg-gray-50 px-2 py-1.5 rounded">
                  <div className="flex items-center gap-2 flex-wrap justify-end">
                    <span className="text-gray-600 select-none">{visionScopeLabel}</span>
                    <span className="text-gray-300 hidden sm:inline">|</span>
                    <label className="flex items-center gap-1 cursor-pointer select-none hover:text-blue-600">
                      <input
                        type="radio"
                        name="visionMode"
                        value="no_subtitles"
                        checked={visionMode === "no_subtitles"}
                        onChange={(e) => setVisionMode(e.target.value as "no_subtitles" | "all")}
                        disabled={extractingScene}
                        className="border-gray-300 text-blue-600 focus:ring-blue-500"
                      />
                      仅无字幕镜头
                    </label>
                    <label className="flex items-center gap-1 cursor-pointer select-none hover:text-blue-600">
                      <input
                        type="radio"
                        name="visionMode"
                        value="all"
                        checked={visionMode === "all"}
                        onChange={(e) => setVisionMode(e.target.value as "no_subtitles" | "all")}
                        disabled={extractingScene}
                        className="border-gray-300 text-blue-600 focus:ring-blue-500"
                      />
                      所有镜头
                    </label>
                  </div>
                  {/* <div className="flex items-center gap-2 flex-wrap justify-end border-t border-gray-200/80 pt-1.5 w-full">
                    <span className="text-gray-500 select-none shrink-0">每镜头抽帧</span>
                    <label className="flex items-center gap-1 cursor-pointer select-none hover:text-blue-600">
                      <input
                        type="radio"
                        name="visionKeyFrames"
                        checked={visionKeyFrames === 1}
                        onChange={() => setVisionKeyFrames(1)}
                        disabled={extractingScene}
                        className="border-gray-300 text-blue-600 focus:ring-blue-500"
                      />
                      1 帧
                    </label>
                    <label className="flex items-center gap-1 cursor-pointer select-none hover:text-blue-600">
                      <input
                        type="radio"
                        name="visionKeyFrames"
                        checked={visionKeyFrames === 3}
                        onChange={() => setVisionKeyFrames(3)}
                        disabled={extractingScene}
                        className="border-gray-300 text-blue-600 focus:ring-blue-500"
                      />
                      3 帧
                    </label>
                  </div> */}
               </div>
               <button
                onClick={() => onExtractScenes({ analyzeVision, visionMode, visionKeyFrames })}
                disabled={
                  subtitleLoading ||
                  extractingSubtitle ||
                  extractingScene ||
                  (!project.video_path && !project.merged_video_path)
                }
                className="flex items-center px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {extractingScene ? (
                  <>
                    <Loader className="h-4 w-4 mr-2 animate-spin" />
                    镜头提取中...
                  </>
                ) : (
                  "提取镜头"
                )}
              </button>
             </div>
          ) : (
              <button
                onClick={onExtractSubtitle}
                disabled={
                  subtitleLoading ||
                  extractingSubtitle ||
                  (!project.video_path &&
                  !project.merged_video_path) ||
                  (project.subtitle_source === "user" && (Boolean(project.subtitle_path))) 
                  // project.subtitle_status === "extracting"
                }
                className="flex items-center px-4 py-2 bg-violet-600 text-white rounded-lg hover:bg-violet-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {extractingSubtitle ? (
                  <>
                    <Loader className="h-4 w-4 mr-2 animate-spin" />
                    提取中...
                  </>
                ) : (
                  <>{canReExtractSubtitle ? "重新提取字幕" : "提取字幕"}</>
                )}
              </button>
          )}
        </div>

        <SubtitleAsrSelector
          value={subtitleAsr}
          disabled={subtitleLoading || extractingSubtitle}
          onChange={onSubtitleAsrChange}
        />

        {(extractingSubtitle ||
          (subtitleExtractProgress > 0 && subtitleExtractProgress < 100)) && (
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

        {(extractingScene || (sceneExtractProgress > 0 && sceneExtractProgress < 100)) && (
          <div className="w-full mt-4">
             <div className="flex items-center justify-between text-xs text-gray-600 mb-1">
              <span>镜头提取进度</span>
              <span>{Math.round(sceneExtractProgress)}%</span>
            </div>
            <div className="w-full h-2 bg-gray-200 rounded">
              <div
                className="h-2 bg-green-600 rounded transition-all"
                style={{ width: `${Math.round(sceneExtractProgress)}%` }}
              />
            </div>
            {sceneExtractMessage ? (
              <div className="mt-2 text-xs text-gray-700 break-all">
                {sceneExtractMessage}
              </div>
            ) : null}
          </div>
        )}
      </div>
      <div className="flex justify-end">
          <button
            onClick={onNextStep}
            disabled={
              project.project_type === "visual"
                ? !project.scenes_path
                : !project.subtitle_path
            }
            className={`
              group flex items-center px-4 py-2 mr-6 rounded-lg text-white font-medium shadow-md transition-all duration-300
              ${
                (project.project_type === "visual"
                  ? project.scenes_path
                  : project.subtitle_path)
                  ? "bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 hover:shadow-lg transform hover:-translate-y-0.5"
                  : "bg-gray-300 cursor-not-allowed opacity-60"
              }
            `}
          >
            <span>生成脚本</span>
            <ArrowRight
              className={`ml-2 h-5 w-5 transition-transform duration-300 ${
                (
                  project.project_type === "visual"
                    ? project.scenes_path
                    : project.subtitle_path
                )
                  ? "group-hover:translate-x-1"
                  : ""
              }`}
            />
          </button>
        </div>
        {project.project_type === "visual" && sceneResult && (
              <SceneListTable 
                 sceneResult={sceneResult} 
                 onPlayScene={(start, end) => {
                     setScenePlayState({ isOpen: true, startTime: start, endTime: end });
                 }}
              />
         )}
        {project.subtitle_source === "extracted" && (
          <SubtitleEditor
            segments={subtitleDraft}
            subtitleMeta={subtitleMeta}
            loading={subtitleLoading}
            saving={subtitleSaving}
            onReload={onReloadSubtitle}
            onSave={onSaveSubtitle}
            onChange={onSubtitleDraftChange}
          />
        )}
      <VisionAnalysisChoiceModal
        isOpen={visionChoiceModalOpen}
        onClose={onVisionChoiceCancel}
        onContinueIncomplete={onVisionChoiceContinue}
        onRestartAll={onVisionChoiceRestart}
      />
      <OverwriteConfirmModal
        isOpen={subtitleOverwriteModalOpen}
        title="重新提取字幕"
        message="字幕已被编辑，重新提取将覆盖修改内容，是否继续？"
        confirmLabel="继续提取"
        cancelLabel="取消"
        onConfirm={onSubtitleOverwriteConfirm}
        onCancel={onSubtitleOverwriteCancel}
      />
      <ScenePlayModal
        isOpen={scenePlayState.isOpen}
        onClose={() => setScenePlayState((prev) => ({ ...prev, isOpen: false }))}
        videoUrl={
            project.merged_video_path 
            ? projectService.getMergedVideoUrl(project.id)
            : (project.video_path ? projectService.getVideoStreamUrl(project.id) : "")
        }
        startTime={scenePlayState.startTime}
        endTime={scenePlayState.endTime}
      />
    </>
  );
};

export default ProjectEditUploadStep;

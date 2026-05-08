import React from "react";
import { useOmniFullNarrationPipeline } from "../../hooks/omni/useOmniFullNarrationPipeline";
import type { Project } from "../../types/project";
import VideoGenAdvancedConfig from "./advancedConfig/VideoGenAdvancedConfig";
import OmniFullNarrationPipelineControls from "./omni/OmniFullNarrationPipelineControls";
import OmniFullNarrationPipelineProgress from "./omni/OmniFullNarrationPipelineProgress";
import OmniFullNarrationScriptWorkspace from "./omni/OmniFullNarrationScriptWorkspace";
import ProjectOperations from "./ProjectOperations";
import ScriptJsonEditor from "./ScriptJsonEditor";

interface ProjectEditGenerateStepProps {
  project: Project;
  refreshProject: () => Promise<void>;
  onShowLogin?: () => void;
  onShowProfile?: () => void;

  isGeneratingCopywriting: boolean;
  handleGenerateCopywriting: () => void;
  handleStopGenerateCopywriting: () => void;
  isStoppingCopywriting: boolean;
  copywritingGenProgress: number;
  copywritingGenLogs: { timestamp: string; message: string; phase?: string; type?: string }[];

  isGeneratingScript: boolean;
  handleGenerateScript: () => void;
  generateScriptDisabled: boolean;
  generateScriptDisabledReason?: string;
  scriptGenProgress: number;
  scriptGenLogs: { timestamp: string; message: string; phase?: string; type?: string }[];

  isGeneratingVideo: boolean;
  handleGenerateVideo: () => void;
  handleStopGenerateVideo: () => void;
  isStoppingVideo: boolean;
  videoGenProgress: number;
  videoGenLogs: { timestamp: string; message: string; phase?: string; type?: string }[];

  isGeneratingDraft: boolean;
  handleGenerateDraft: () => void;
  handleStopGenerateDraft: () => void;
  isStoppingDraft: boolean;
  draftGenProgress: number;
  draftGenLogs: { timestamp: string; message: string; phase?: string; type?: string }[];

  showMergedPreview: boolean;
  setShowMergedPreview: React.Dispatch<React.SetStateAction<boolean>>;

  editedScript: string;
  setEditedScript: (script: string) => void;
  isSaving: boolean;
  handleSaveScript: () => void;
}

const ProjectEditGenerateStep: React.FC<ProjectEditGenerateStepProps> = ({
  project,
  refreshProject,
  onShowLogin,
  onShowProfile,
  isGeneratingCopywriting,
  handleGenerateCopywriting,
  handleStopGenerateCopywriting,
  isStoppingCopywriting,
  copywritingGenProgress,
  copywritingGenLogs,
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
  setEditedScript,
  isSaving,
  handleSaveScript,
}) => {
  const [showAdvancedConfig, setShowAdvancedConfig] = React.useState(false);

  const omniNarration = useOmniFullNarrationPipeline({
    project,
    refreshProject,
    onShowLogin,
    onShowProfile,
  });

  return (
    <>
      <div className="bg-white rounded-lg shadow-md p-6 space-y-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-gray-900">生成视频</h2>
          <button
            onClick={() => setShowAdvancedConfig((v) => !v)}
            className="text-blue-600 hover:text-blue-800 text-sm"
          >
             <span className="text-xs text-gray-500">（原片占比范围、生成语言）</span>
            高级配置
          </button>
        </div>

        {showAdvancedConfig && (
          <VideoGenAdvancedConfig projectId={project.id} />
        )}

        <ProjectOperations
          project={project}
          refreshProject={refreshProject}
          isGeneratingCopywriting={isGeneratingCopywriting}
          handleGenerateCopywriting={handleGenerateCopywriting}
          handleStopGenerateCopywriting={handleStopGenerateCopywriting}
          isStoppingCopywriting={isStoppingCopywriting}
          copywritingGenProgress={copywritingGenProgress}
          copywritingGenLogs={copywritingGenLogs}
          isGeneratingScript={isGeneratingScript}
          handleGenerateScript={handleGenerateScript}
          generateScriptDisabled={generateScriptDisabled}
          generateScriptDisabledReason={generateScriptDisabledReason}
          scriptGenProgress={scriptGenProgress}
          scriptGenLogs={scriptGenLogs}
          isGeneratingVideo={isGeneratingVideo}
          handleGenerateVideo={handleGenerateVideo}
          handleStopGenerateVideo={handleStopGenerateVideo}
          isStoppingVideo={isStoppingVideo}
          videoGenProgress={videoGenProgress}
          videoGenLogs={videoGenLogs}
          isGeneratingDraft={isGeneratingDraft}
          handleGenerateDraft={handleGenerateDraft}
          handleStopGenerateDraft={handleStopGenerateDraft}
          isStoppingDraft={isStoppingDraft}
          draftGenProgress={draftGenProgress}
          draftGenLogs={draftGenLogs}
          showMergedPreview={showMergedPreview}
          setShowMergedPreview={setShowMergedPreview}
          hideCopywritingOperations
          hideVisualGenerateScriptButton={project.project_type === "omni"}
          isOmniFullPipelineRunning={omniNarration.omniAnyPipelineBusy}
          omniScriptGenerateSlot={
            project.project_type === "omni" ? (
              <OmniFullNarrationPipelineControls
                busy={omniNarration.omniAnyPipelineBusy}
                disabled={omniNarration.omniPipelineDisabled}
                disabledReason={omniNarration.omniPipelineDisabledReason}
                omniPipelineBusy={omniNarration.omniPipelineBusy}
                omniStepTestPhase={omniNarration.omniStepTestPhase}
                onRun={omniNarration.handleRunOmniFullNarrationPipeline}
                onRunStepEmbed={omniNarration.handleRunOmniStepEmbed}
                onRunStepShotMatch={omniNarration.handleRunOmniStepShotMatch}
                onRunStepGenerateScript={omniNarration.handleRunOmniStepGenerateScript}
              />
            ) : undefined
          }
          omniScriptProgressSlot={
            project.project_type === "omni" ? (
              <OmniFullNarrationPipelineProgress
                busy={omniNarration.omniAnyPipelineBusy}
                progress={omniNarration.omniPipelineProgress}
                logs={omniNarration.omniPipelineLogs}
                title={
                  omniNarration.omniStepTestPhase === "embed"
                    ? "Omni 单步：文案结构化 + 向量"
                    : omniNarration.omniStepTestPhase === "shotMatch"
                      ? "Omni 单步：镜头匹配"
                      : omniNarration.omniStepTestPhase === "generateScript"
                        ? "Omni 单步：解说脚本生成"
                        : undefined
                }
              />
            ) : undefined
          }
        />
      </div>

      {/* 脚本编辑区 */}
      {project.project_type === "omni" ? (
        <div className="bg-white rounded-lg shadow-md p-6 space-y-8">
          <OmniFullNarrationScriptWorkspace
            editedScript={omniNarration.omniEditedScript}
            setEditedScript={omniNarration.setOmniEditedScript}
            isSaving={omniNarration.omniScriptSaving}
            onSave={omniNarration.handleSaveOmniScript}
          />
        </div>
      ) : (
        <div className="bg-white rounded-lg shadow-md p-6 space-y-8">
          <ScriptJsonEditor
            editedScript={editedScript}
            setEditedScript={setEditedScript}
            isSaving={isSaving}
            handleSaveScript={handleSaveScript}
          />
        </div>
      )}
    </>
  );
};

export default ProjectEditGenerateStep;

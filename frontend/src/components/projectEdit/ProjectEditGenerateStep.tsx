import React from "react";
import type { Project } from "../../types/project";
import GenerateAdvancedConfigSection from "./GenerateAdvancedConfigSection";
import ProjectOperations from "./ProjectOperations";
import ScriptEditor from "./ScriptEditor";

interface ProjectEditGenerateStepProps {
  project: Project;

  isGeneratingScript: boolean;
  handleGenerateScript: () => void;
  generateScriptDisabled: boolean;
  generateScriptDisabledReason?: string;
  scriptGenProgress: number;
  scriptGenLogs: { timestamp: string; message: string; phase?: string; type?: string }[];

  isGeneratingVideo: boolean;
  handleGenerateVideo: () => void;
  videoGenProgress: number;
  videoGenLogs: { timestamp: string; message: string; phase?: string; type?: string }[];

  isGeneratingDraft: boolean;
  handleGenerateDraft: () => void;
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
  setEditedScript,
  isSaving,
  handleSaveScript,
}) => {
  const [showAdvancedConfig, setShowAdvancedConfig] = React.useState(false);

  return (
    <>
      <div className="bg-white rounded-lg shadow-md p-6 space-y-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-gray-900">项目生成</h2>
          <button
            onClick={() => setShowAdvancedConfig((v) => !v)}
            className="text-blue-600 hover:text-blue-800 text-sm"
          >
             <span className="text-xs text-gray-500">（脚本条数、原片占比范围、提示词）</span>
            高级配置
          </button>
        </div>

        {showAdvancedConfig && (
          <GenerateAdvancedConfigSection
            projectId={project.id}
            narrationType={project.narration_type}
          />
        )}

        <ProjectOperations
          project={project}
          isGeneratingScript={isGeneratingScript}
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

      <ScriptEditor
        editedScript={editedScript}
        setEditedScript={setEditedScript}
        isSaving={isSaving}
        handleSaveScript={handleSaveScript}
      />
    </>
  );
};

export default ProjectEditGenerateStep;


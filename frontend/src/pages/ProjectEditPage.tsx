// 项目编辑页面（二级页面）

import { ArrowLeft, Loader } from "lucide-react";
import React, { useCallback, useEffect, useState } from "react";
import ProjectEditCopywritingStep from "../components/projectEdit/ProjectEditCopywritingStep";
import ProjectEditGenerateStep from "../components/projectEdit/ProjectEditGenerateStep";
import ProjectEditUploadStep from "../components/projectEdit/ProjectEditUploadStep";
import { useProjectEditGenerateStep } from "../hooks/useProjectEditGenerateStep";
import { useProjectEditUploadStep } from "../hooks/useProjectEditUploadStep";
import { useProjectDetail } from "../hooks/useProjects";
import { message } from "../services/message";

type StepKey = "upload" | "copywriting" | "generate";

interface ProjectEditPageProps {
  projectId: string;
  onBack: () => void;
  onShowLogin?: () => void;
  onShowProfile?: () => void;
}

const ProjectEditPage: React.FC<ProjectEditPageProps> = ({
  projectId,
  onBack,
  onShowLogin,
  onShowProfile,
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
    generateCopywriting,
    saveCopywriting,
    generateScript,
    saveScript,
    generateVideo,
    mergeVideos,
    mergeProgress,
    merging,
    refreshProject,
    extractScenes,
    cancelSceneExtraction,
    sceneResult,
    extractingScene,
    sceneExtractProgress,
    sceneExtractMessage,
    sceneExtractPhase,
    runOmniPipeline,
    runOmniPipelineWithSubtitle,
    cancelOmniPipeline,
    extractingOmniPipeline,
    omniPipelineProgress,
    omniPipelineMessage,
    omniPipelinePhase,
    omniPipelineShowProgressBar,
    omniPipelineCanStop,
    omniMultimodalResult,
  } = useProjectDetail(projectId);

  const [currentStep, setCurrentStep] = useState<StepKey>("upload");
  const [hasInitializedStep, setHasInitializedStep] = useState(false);

  // 判断上传步骤是否完成
  const isUploadReady = useCallback(() => {
    if (!project) return false;
    return project.project_type === "subtitle"
      ? project.subtitle_status === "ready"
      : project.project_type === "omni"
        ? Boolean(project.omni_multimodal_json_path)
        : Boolean(project.scenes_path);
  }, [project]);

  // 判断文案是否已生成
  const isCopywritingReady = useCallback(() => {
    if (!project) return false;
    return Boolean(project.narration_copywriting?.content);
  }, [project]);

  // 初始化步骤：根据项目状态定位到合适的步骤
  useEffect(() => {
    if (!loading && project && !hasInitializedStep) {
      if (isCopywritingReady()) {
        setCurrentStep("generate");
      } else if (isUploadReady()) {
        setCurrentStep("copywriting");
      }
      setHasInitializedStep(true);
    }
  }, [loading, project, hasInitializedStep, isUploadReady, isCopywritingReady]);

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
  }, [error, showErrorText]);

  const uploadStep = useProjectEditUploadStep({
    projectId,
    project,
    merging,
    mergeProgress,
    subtitleLoading,
    subtitleMeta,
    subtitleSegments: subtitleSegments || [],
    uploadVideos,
    uploadSubtitle,
    deleteSubtitle,
    extractSubtitle,
    fetchSubtitle,
    saveSubtitle,
    deleteVideoItem,
    reorderVideos,
    mergeVideos,
    refreshProject,
    extractScenes,
    cancelSceneExtraction,
    sceneResult,
    extractingScene,
    sceneExtractProgress,
    sceneExtractMessage,
    sceneExtractPhase,
    runOmniPipeline,
    runOmniPipelineWithSubtitle,
    cancelOmniPipeline,
    extractingOmniPipeline,
    omniPipelineProgress,
    omniPipelineMessage,
    omniPipelinePhase,
    omniPipelineShowProgressBar,
    omniPipelineCanStop,
    omniMultimodalResult,
    onShowLogin,
    onShowProfile,
    showSuccess,
    showErrorText,
    showError,
  });

  const generateStep = useProjectEditGenerateStep({
    project,
    extractingSubtitle: uploadStep.extractingSubtitle,
    generateCopywriting,
    saveCopywriting,
    generateScript,
    saveScript,
    generateVideo,
    refreshProject,
    showSuccess,
    showErrorText,
    showError,
  });

  // 从上传步骤跳转到文案步骤
  const handleUploadNext = useCallback(() => {
    if (isUploadReady()) {
      setCurrentStep("copywriting");
    } else {
      message.warning(
        project?.project_type === "visual"
          ? "请先提取镜头"
          : project?.project_type === "omni"
            ? "请先完成 Omni 管线"
            : "请先提取或上传字幕"
      );
    }
  }, [isUploadReady, project]);

  // 从文案步骤跳转到生成步骤
  const handleCopywritingNext = useCallback(() => {
    if (isCopywritingReady()) {
      setCurrentStep("generate");
    } else {
      message.warning("请先生成解说文案");
    }
  }, [isCopywritingReady]);

  // 点击步骤标签的处理
  const handleStepClick = useCallback((step: StepKey) => {
    if (step === "upload") {
      setCurrentStep("upload");
      return;
    }
    if (step === "copywriting") {
      if (!isUploadReady()) {
        message.warning(
          project?.project_type === "subtitle"
            ? "请先提取或上传字幕"
            : project?.project_type === "omni"
              ? "请先完成 Omni 管线（镜头拆分与多模态向量化）"
              : "请先提取镜头"
        );
        return;
      }
      setCurrentStep("copywriting");
      return;
    }
    if (step === "generate") {
      if (!isUploadReady()) {
        message.warning(
          project?.project_type === "subtitle"
            ? "请先提取或上传字幕"
            : project?.project_type === "omni"
              ? "请先完成 Omni 管线（镜头拆分与多模态向量化）"
              : "请先提取镜头"
        );
        return;
      }
      if (!isCopywritingReady()) {
        message.warning("请先生成解说文案");
        return;
      }
      setCurrentStep("generate");
      return;
    }
  }, [isUploadReady, isCopywritingReady, project]);

  // 步骤标签样式
  const stepButtonClass = (step: StepKey, isReady: boolean) => {
    const isActive = currentStep === step;
    if (isActive) return "bg-white text-gray-900 shadow-sm dark:bg-white/10 dark:text-zinc-100";
    if (!isReady) return "text-gray-400 cursor-not-allowed dark:text-zinc-500";
    return "text-gray-500 hover:text-gray-700 dark:text-zinc-400 dark:hover:text-zinc-100";
  };

  if (loading && !project) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader className="h-8 w-8 animate-spin text-blue-600" />
        <span className="ml-3 text-gray-600 dark:text-zinc-300">加载项目中...</span>
      </div>
    );
  }

  if (!project) {
    return (
      <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg dark:border-red-400/20 dark:bg-red-500/10 dark:text-red-300">
        项目不存在或加载失败
      </div>
    );
  }

  const uploadReady = isUploadReady();
  const copywritingReady = isCopywritingReady();

  return (
    <div className="space-y-6">
      <div className="bg-white rounded-lg shadow-md p-3 dark:border dark:border-[#2a2a2a] dark:bg-[#1f1f1f] dark:shadow-black/30">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-4">
            <button
              onClick={onBack}
              className="flex items-center justify-center w-10 h-10 bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors dark:bg-white/10 dark:hover:bg-white/15"
              title="返回"
            >
              <ArrowLeft className="h-5 w-5 text-gray-600 dark:text-zinc-300" />
            </button>
            <div>
              <h1 className="text-2xl font-bold text-gray-900 dark:text-zinc-100">{project.name}</h1>
              <p className="text-sm text-gray-600 mt-1 dark:text-zinc-400">{project.description}</p>
            </div>
          </div>

          <div className="flex bg-gray-100 rounded-lg p-1 dark:bg-[#242424]">
            <button
              onClick={() => handleStepClick("upload")}
              className={`px-4 py-1.5 rounded-md text-sm font-medium transition-all ${stepButtonClass("upload", true)}`}
            >
              1. 上传视频
            </button>
            <button
              onClick={() => handleStepClick("copywriting")}
              className={`px-4 py-1.5 rounded-md text-sm font-medium transition-all ${stepButtonClass("copywriting", uploadReady)}`}
            >
              2. 文案生成
            </button>
            <button
              onClick={() => handleStepClick("generate")}
              className={`px-4 py-1.5 rounded-md text-sm font-medium transition-all ${stepButtonClass("generate", uploadReady && copywritingReady)}`}
            >
              3. 生成视频
            </button>
          </div>
        </div>
      </div>

      {currentStep === "upload" && (
        <ProjectEditUploadStep
          projectId={projectId}
          project={project}
          refreshProject={refreshProject}
          merging={merging}
          mergeProgress={mergeProgress}
          subtitleLoading={subtitleLoading}
          subtitleMeta={subtitleMeta}
          onShowLogin={onShowLogin}
          onShowProfile={onShowProfile}
          onNextStep={handleUploadNext}
          {...uploadStep}
        />
      )}

      {currentStep === "copywriting" && (
        <ProjectEditCopywritingStep
          project={project}
          refreshProject={refreshProject}
          isGeneratingCopywriting={generateStep.isGeneratingCopywriting}
          handleGenerateCopywriting={generateStep.handleGenerateCopywriting}
          handleStopGenerateCopywriting={generateStep.handleStopGenerateCopywriting}
          isStoppingCopywriting={generateStep.isStoppingCopywriting}
          copywritingGenProgress={generateStep.copywritingGenProgress}
          copywritingGenLogs={generateStep.copywritingGenLogs}
          editedCopywriting={generateStep.editedCopywriting}
          setEditedCopywriting={generateStep.setEditedCopywriting}
          isSavingCopywriting={generateStep.isSavingCopywriting}
          handleSaveCopywriting={generateStep.handleSaveCopywriting}
          onGoToGenerateStep={handleCopywritingNext}
        />
      )}

      {currentStep === "generate" && (
        <ProjectEditGenerateStep
          project={project}
          refreshProject={refreshProject}
          onShowLogin={onShowLogin}
          onShowProfile={onShowProfile}
          {...generateStep}
        />
      )}

    </div>
  );
};

export default ProjectEditPage;

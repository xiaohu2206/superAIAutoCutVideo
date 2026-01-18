// 项目编辑页面（二级页面）

import { ArrowLeft, Loader } from "lucide-react";
import React, { useCallback, useEffect, useState } from "react";
import ProjectEditGenerateStep from "../components/projectEdit/ProjectEditGenerateStep";
import ProjectEditUploadStep from "../components/projectEdit/ProjectEditUploadStep";
import { useProjectEditGenerateStep } from "../hooks/useProjectEditGenerateStep";
import { useProjectEditUploadStep } from "../hooks/useProjectEditUploadStep";
import { useProjectDetail } from "../hooks/useProjects";
import { message } from "../services/message";

interface ProjectEditPageProps {
  projectId: string;
  onBack: () => void;
}

const ProjectEditPage: React.FC<ProjectEditPageProps> = ({ projectId, onBack }) => {
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
    generateScript,
    saveScript,
    generateVideo,
    mergeVideos,
    mergeProgress,
    merging,
    refreshProject,
  } = useProjectDetail(projectId);

  const [currentStep, setCurrentStep] = useState<"upload" | "generate">("upload");
  const [hasInitializedStep, setHasInitializedStep] = useState(false);

  useEffect(() => {
    if (!loading && project && !hasInitializedStep) {
      if (project.subtitle_status === "ready") {
        setCurrentStep("generate");
      }
      setHasInitializedStep(true);
    }
  }, [loading, project, hasInitializedStep]);

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
    showSuccess,
    showErrorText,
    showError,
  });

  const generateStep = useProjectEditGenerateStep({
    project,
    extractingSubtitle: uploadStep.extractingSubtitle,
    generateScript,
    saveScript,
    generateVideo,
    refreshProject,
    showSuccess,
    showErrorText,
    showError,
  });

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
  console.log("project---", project)
  return (
    <div className="space-y-6">
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
              <h1 className="text-2xl font-bold text-gray-900">{project.name}</h1>
              <p className="text-sm text-gray-600 mt-1">{project.description}</p>
            </div>
          </div>

          <div className="flex bg-gray-100 rounded-lg p-1">
            <button
              onClick={() => setCurrentStep("upload")}
              className={`px-4 py-1.5 rounded-md text-sm font-medium transition-all ${
                currentStep === "upload"
                  ? "bg-white text-gray-900 shadow-sm"
                  : "text-gray-500 hover:text-gray-700"
              }`}
            >
              1. 上传视频
            </button>
            <button
              onClick={() => {
                if (project?.subtitle_status === "ready") {
                  setCurrentStep("generate");
                } else {
                  message.warning("请先提取或上传字幕");
                }
              }}
              className={`px-4 py-1.5 rounded-md text-sm font-medium transition-all ${
                currentStep === "generate"
                  ? "bg-white text-gray-900 shadow-sm"
                  : project?.subtitle_status !== "ready"
                  ? "text-gray-400 cursor-not-allowed"
                  : "text-gray-500 hover:text-gray-700"
              }`}
            >
              2. 生成视频
            </button>
          </div>
        </div>
      </div>

      {currentStep === "upload" && (
        <ProjectEditUploadStep
          projectId={projectId}
          project={project}
          merging={merging}
          mergeProgress={mergeProgress}
          subtitleLoading={subtitleLoading}
          subtitleMeta={subtitleMeta}
          onNextStep={() => {
            if (project?.subtitle_status === "ready") {
              setCurrentStep("generate");
            } else {
              message.warning("请先提取或上传字幕");
            }
          }}
          {...uploadStep}
        />
      )}

      {currentStep === "generate" && (
        <ProjectEditGenerateStep
          project={project}
          {...generateStep}
        />
      )}
    </div>
  );
};

export default ProjectEditPage;


import React, { useCallback, useEffect, useState } from "react";
import CreateProjectModal from "../components/projectManagement/CreateProjectModal";
import DeleteConfirmModal from "../components/projectManagement/DeleteConfirmModal";
import NarrationTypePicker from "../components/projectManagement/NarrationTypePicker";
import ProjectList from "../components/projectManagement/ProjectList";
import { useProjects } from "../hooks/useProjects";
import { message } from "../services/message";
import {
  NarrationType,
  type CreateProjectRequest,
  type Project,
} from "../types/project";

interface ProjectManagementPageProps {
  onEditProject: (projectId: string) => void;
  onShowLogin?: () => void;
  onShowProfile?: () => void;
}

const ProjectManagementPage: React.FC<ProjectManagementPageProps> = ({
  onEditProject,
  onShowLogin,
  onShowProfile,
}) => {
  const {
    projects,
    loading,
    error,
    fetchProjects,
    createProject,
    deleteProject,
  } = useProjects();

  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [createInitialNarrationType, setCreateInitialNarrationType] =
    useState<NarrationType>(NarrationType.MOVIE);
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);
  const [selectedProject, setSelectedProject] = useState<Project | null>(null);

  const getErrorMessage = useCallback((err: unknown, fallback: string): string => {
    if (err && typeof err === "object") {
      const anyErr = err as any;
      if (typeof anyErr.message === "string" && anyErr.message) return anyErr.message;
      if (typeof anyErr.detail === "string" && anyErr.detail) return anyErr.detail;
    }
    if (typeof err === "string" && err) return err;
    return fallback;
  }, []);

  useEffect(() => {
    void fetchProjects().catch((e) => {
      const msg = getErrorMessage(e, "获取项目列表失败");
      message.error(msg, 3);
    });
  }, [fetchProjects, getErrorMessage]);

  useEffect(() => {
    if (error) {
      message.error(error, 3);
    }
  }, [error]);

  const showSuccess = (content: string) => {
    message.success(content);
  };

  const handleCreateProject = async (data: CreateProjectRequest) => {
    try {
      const newProject = await createProject(data);
      message.success("项目创建成功！");
      onEditProject(newProject.id);
    } catch (err) {
      throw err;
    }
  };

  const handleEditProject = (project: Project) => {
    onEditProject(project.id);
  };

  const handleDeleteProject = (project: Project) => {
    setSelectedProject(project);
    setIsDeleteModalOpen(true);
  };

  const handleConfirmDelete = async () => {
    if (!selectedProject) return;

    try {
      await deleteProject(selectedProject.id);
      setSelectedProject(null);
      showSuccess("项目已删除！");
    } catch (err) {
      const msg = getErrorMessage(err, "删除项目失败");
      message.error(msg, 3);
      throw err;
    }
  };

  return (
    <div className="flex h-full min-h-0 flex-col gap-4 dark:bg-[#121212]">
      <NarrationTypePicker
        onSelect={(narrationType) => {
          setCreateInitialNarrationType(narrationType);
          setIsCreateModalOpen(true);
        }}
      />

      <div className="flex min-h-0 flex-1 flex-col">
        <ProjectList
          projects={projects}
          loading={loading}
          onEdit={handleEditProject}
          onDelete={handleDeleteProject}
        />
      </div>

      <CreateProjectModal
        isOpen={isCreateModalOpen}
        onClose={() => setIsCreateModalOpen(false)}
        onCreate={handleCreateProject}
        onShowLogin={onShowLogin}
        onShowProfile={onShowProfile}
        initialNarrationType={createInitialNarrationType}
      />

      <DeleteConfirmModal
        isOpen={isDeleteModalOpen}
        projectName={selectedProject?.name || ""}
        onClose={() => {
          setIsDeleteModalOpen(false);
          setSelectedProject(null);
        }}
        onConfirm={handleConfirmDelete}
      />
    </div>
  );
};

export default ProjectManagementPage;

// 项目管理页面（一级页面）

import React, { useEffect, useState } from "react";
import { Plus, RefreshCw, Folder } from "lucide-react";
import ProjectList from "../components/projectManagement/ProjectList";
import CreateProjectModal from "../components/projectManagement/CreateProjectModal";
import DeleteConfirmModal from "../components/projectManagement/DeleteConfirmModal";
import { useProjects } from "../hooks/useProjects";
import type { Project, CreateProjectRequest } from "../types/project";

interface ProjectManagementPageProps {
  onEditProject: (projectId: string) => void;
}

/**
 * 项目管理页面
 */
const ProjectManagementPage: React.FC<ProjectManagementPageProps> = ({
  onEditProject,
}) => {
  const {
    projects,
    loading,
    error,
    fetchProjects,
    createProject,
    deleteProject,
    refreshProjects,
  } = useProjects();

  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);
  const [selectedProject, setSelectedProject] = useState<Project | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  // 初始加载项目列表
  useEffect(() => {
    fetchProjects();
  }, [fetchProjects]);

  /**
   * 处理创建项目
   */
  const handleCreateProject = async (data: CreateProjectRequest) => {
    await createProject(data);
  };

  /**
   * 处理编辑项目
   */
  const handleEditProject = (project: Project) => {
    onEditProject(project.id);
  };

  /**
   * 处理删除项目
   */
  const handleDeleteProject = (project: Project) => {
    setSelectedProject(project);
    setIsDeleteModalOpen(true);
  };

  /**
   * 确认删除项目
   */
  const handleConfirmDelete = async () => {
    if (selectedProject) {
      await deleteProject(selectedProject.id);
      setSelectedProject(null);
    }
  };

  /**
   * 处理刷新
   */
  const handleRefresh = async () => {
    setRefreshing(true);
    await refreshProjects();
    setRefreshing(false);
  };

  return (
    <div className="space-y-6">
      {/* 页面头部 */}
      <div className="bg-white rounded-lg shadow-md p-6">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-4">
            <div className="flex items-center justify-center w-12 h-12 bg-gradient-to-br from-blue-500 to-purple-600 rounded-lg">
              <Folder className="h-6 w-6 text-white" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-gray-900">项目管理</h1>
              <p className="text-sm text-gray-600 mt-1">
                创建和管理您的视频剪辑项目
              </p>
            </div>
          </div>

          <div className="flex items-center space-x-3">
            {/* 刷新按钮 */}
            <button
              onClick={handleRefresh}
              disabled={refreshing || loading}
              className="flex items-center px-4 py-2 text-gray-700 bg-white border border-gray-300 hover:bg-gray-50 rounded-lg font-medium transition-colors disabled:opacity-50"
            >
              <RefreshCw
                className={`h-4 w-4 mr-2 ${refreshing ? "animate-spin" : ""}`}
              />
              刷新
            </button>

            {/* 创建项目按钮 */}
            <button
              onClick={() => setIsCreateModalOpen(true)}
              className="flex items-center px-6 py-2 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 transition-colors"
            >
              <Plus className="h-4 w-4 mr-2" />
              创建项目
            </button>
          </div>
        </div>

        {/* 统计信息 */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mt-6 pt-6 border-t border-gray-200">
          <div className="text-center">
            <div className="text-2xl font-bold text-gray-900">
              {projects.length}
            </div>
            <div className="text-sm text-gray-600 mt-1">总项目数</div>
          </div>
          <div className="text-center">
            <div className="text-2xl font-bold text-gray-500">
              {projects.filter((p) => p.status === "draft").length}
            </div>
            <div className="text-sm text-gray-600 mt-1">草稿</div>
          </div>
          <div className="text-center">
            <div className="text-2xl font-bold text-blue-600">
              {projects.filter((p) => p.status === "processing").length}
            </div>
            <div className="text-sm text-gray-600 mt-1">处理中</div>
          </div>
          <div className="text-center">
            <div className="text-2xl font-bold text-green-600">
              {projects.filter((p) => p.status === "completed").length}
            </div>
            <div className="text-sm text-gray-600 mt-1">已完成</div>
          </div>
        </div>
      </div>

      {/* 错误提示 */}
      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg">
          {error}
        </div>
      )}

      {/* 项目列表 */}
      <ProjectList
        projects={projects}
        loading={loading}
        onEdit={handleEditProject}
        onDelete={handleDeleteProject}
      />

      {/* 创建项目模态框 */}
      <CreateProjectModal
        isOpen={isCreateModalOpen}
        onClose={() => setIsCreateModalOpen(false)}
        onCreate={handleCreateProject}
      />

      {/* 删除确认模态框 */}
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

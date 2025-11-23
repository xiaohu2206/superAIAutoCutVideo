// 项目管理页面（一级页面）

import React, { useEffect, useState } from "react";
import { Plus, RefreshCw } from "lucide-react";
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
  const [searchQuery, setSearchQuery] = useState("");

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
      <div className="bg-white rounded-lg shadow-md">
        {/* 统计信息 */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-6 ">
          <div className="bg-white rounded-xl p-6 shadow-sm">
            <p className="text-sm text-gray-600">总项目数</p>
            <p className="mt-2 text-3xl font-bold text-gray-900">{projects.length}</p>
          </div>
          <div className="bg-white rounded-xl p-6 shadow-sm">
            <p className="text-sm text-gray-600">草稿箱</p>
            <p className="mt-2 text-3xl font-bold text-gray-500">{projects.filter((p) => p.status === "draft").length}</p>
          </div>
          <div className="bg-white rounded-xl p-6 shadow-sm">
            <p className="text-sm text-gray-600">处理中</p>
            <p className="mt-2 text-3xl font-bold text-blue-600">{projects.filter((p) => p.status === "processing").length}</p>
          </div>
          <div className="bg-white rounded-xl p-6 shadow-sm">
            <p className="text-sm text-gray-600">已完成</p>
            <p className="mt-2 text-3xl font-bold text-green-600">{projects.filter((p) => p.status === "completed").length}</p>
          </div>
        </div>
      </div>

      {/* 区块标题：最近项目 + 搜索 + 创建按钮 */}
      <div className="flex items-center justify-between px-1">
        <h2 className="text-xl sm:text-2xl font-bold text-gray-900">最近项目</h2>
        <div className="flex items-center space-x-3">
          <input
            type="text"
            placeholder="搜索项目..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-44 sm:w-64 px-3 py-2 bg-white border border-gray-300 rounded-md text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none"
          />
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
          <button
            onClick={() => setIsCreateModalOpen(true)}
            className="flex items-center px-5 py-2 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 transition-colors"
          >
            <Plus className="h-4 w-4 mr-2" />
            创建项目
          </button>
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
        projects={projects.filter((p) =>
          p.name.toLowerCase().includes(searchQuery.trim().toLowerCase())
        )}
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

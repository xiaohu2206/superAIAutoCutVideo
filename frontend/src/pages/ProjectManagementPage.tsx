// 项目管理页面（一级页面）

import React, { useEffect, useState } from "react";
import { AlertCircle, CheckCircle, Clock, Edit, Folder, Plus, RefreshCw } from "lucide-react";
import ProjectList from "../components/projectManagement/ProjectList";
import CreateProjectModal from "../components/projectManagement/CreateProjectModal";
import DeleteConfirmModal from "../components/projectManagement/DeleteConfirmModal";
import { useProjects } from "../hooks/useProjects";
import { notifyError, notifySuccess } from "../services/notification";
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
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [actionErrorMessage, setActionErrorMessage] = useState<string | null>(null);

  // 初始加载项目列表
  useEffect(() => {
    void fetchProjects().catch((e) => {
      void notifyError("错误", e, "获取项目列表失败");
    });
  }, [fetchProjects]);

  const showSuccess = (message: string, timeoutMs: number = 2500) => {
    setSuccessMessage(message);
    setActionErrorMessage(null);
    void notifySuccess("成功", message);
    setTimeout(() => setSuccessMessage(null), timeoutMs);
  };

  const showError = async (err: unknown, fallback: string, timeoutMs: number = 4000) => {
    const msg = await notifyError("错误", err as any, fallback);
    setActionErrorMessage(msg);
    setTimeout(() => setActionErrorMessage(null), timeoutMs);
  };

  /**
   * 处理创建项目
   */
  const handleCreateProject = async (data: CreateProjectRequest) => {
    try {
      await createProject(data);
      showSuccess("项目创建成功！");
    } catch (err) {
      await showError(err, "创建项目失败");
      throw err;
    }
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
      try {
        await deleteProject(selectedProject.id);
        setSelectedProject(null);
        showSuccess("项目已删除！");
      } catch (err) {
        await showError(err, "删除项目失败");
        throw err;
      }
    }
  };

  /**
   * 处理刷新
   */
  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      await refreshProjects();
      showSuccess("列表已刷新！");
    } catch (err) {
      await showError(err, "刷新项目列表失败");
    } finally {
      setRefreshing(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* 统计信息 */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {/* 总项目数 */}
        <div className="bg-white rounded-lg py-3 px-4 shadow-sm border border-gray-100">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs font-medium text-gray-500">总项目数</p>
              <p className="text-xl font-bold text-gray-900">{projects.length}</p>
            </div>
            <div className="p-1.5 bg-gray-50 rounded-md">
              <Folder className="h-4 w-4 text-gray-400" />
            </div>
          </div>
        </div>

        {/* 草稿箱 */}
        <div className="bg-white rounded-lg py-3 px-4 shadow-sm border border-gray-100">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs font-medium text-gray-500">草稿箱</p>
              <p className="text-xl font-bold text-gray-500">
                {projects.filter((p) => p.status === "draft").length}
              </p>
            </div>
            <div className="p-1.5 bg-gray-50 rounded-md">
              <Edit className="h-4 w-4 text-gray-400" />
            </div>
          </div>
        </div>

        {/* 处理中 */}
        <div className="bg-white rounded-lg py-3 px-4 shadow-sm border border-gray-100">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs font-medium text-gray-500">处理中</p>
              <p className="text-xl font-bold text-blue-600">
                {projects.filter((p) => p.status === "processing").length}
              </p>
            </div>
            <div className="p-1.5 bg-blue-50 rounded-md">
              <Clock className="h-4 w-4 text-blue-500" />
            </div>
          </div>
        </div>

        {/* 已完成 */}
        <div className="bg-white rounded-lg py-3 px-4 shadow-sm border border-gray-100">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs font-medium text-gray-500">已完成</p>
              <p className="text-xl font-bold text-green-600">
                {projects.filter((p) => p.status === "completed").length}
              </p>
            </div>
            <div className="p-1.5 bg-green-50 rounded-md">
              <CheckCircle className="h-4 w-4 text-green-500" />
            </div>
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
      {successMessage && (
        <div className="bg-green-50 border border-green-200 text-green-700 px-4 py-3 rounded-lg flex items-center">
          <CheckCircle className="h-5 w-5 mr-2" />
          {successMessage}
        </div>
      )}
      {actionErrorMessage && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg flex items-center">
          <AlertCircle className="h-5 w-5 mr-2" />
          {actionErrorMessage}
        </div>
      )}
      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg flex items-center">
          <AlertCircle className="h-5 w-5 mr-2" />
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

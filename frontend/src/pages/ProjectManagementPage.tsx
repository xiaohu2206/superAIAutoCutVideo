// 项目管理页面（一级页面）

import { Plus, RefreshCw } from "lucide-react";
import React, { useCallback, useEffect, useRef, useState } from "react";
import CreateProjectModal from "../components/projectManagement/CreateProjectModal";
import DeleteConfirmModal from "../components/projectManagement/DeleteConfirmModal";
import ProjectList from "../components/projectManagement/ProjectList";
import BasicConfigCheckModal from "../components/projectManagement/BasicConfigCheckModal";
import { useProjects } from "../hooks/useProjects";
import type { CreateProjectRequest, Project } from "../types/project";
import { message } from "../services/message";

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
  const [isBasicConfigCheckOpen, setIsBasicConfigCheckOpen] = useState(false);
  const [selectedProject, setSelectedProject] = useState<Project | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [isListScrollbarVisible, setIsListScrollbarVisible] = useState(false);
  const listScrollHideTimerRef = useRef<number | null>(null);

  const getErrorMessage = useCallback((err: unknown, fallback: string): string => {
    if (err && typeof err === "object") {
      const anyErr = err as any;
      if (typeof anyErr.message === "string" && anyErr.message) return anyErr.message;
      if (typeof anyErr.detail === "string" && anyErr.detail) return anyErr.detail;
    }
    if (typeof err === "string" && err) return err;
    return fallback;
  }, []);

  // 初始加载项目列表
  useEffect(() => {
    void fetchProjects().catch((e) => {
      const msg = getErrorMessage(e, "获取项目列表失败");
      message.error(msg, 3);
    });
  }, [fetchProjects, getErrorMessage]);

  const showSuccess = (content: string) => {
    message.success(content);
  };

  const showError = async (err: unknown, fallback: string) => {
    const msg = getErrorMessage(err, fallback);
    message.error(msg, 3);
  };

  useEffect(() => {
    if (error) {
      message.error(error, 3);
    }
  }, [error]);

  useEffect(() => {
    return () => {
      if (listScrollHideTimerRef.current !== null) {
        window.clearTimeout(listScrollHideTimerRef.current);
      }
    };
  }, []);

  const handleListScroll = () => {
    setIsListScrollbarVisible(true);
    if (listScrollHideTimerRef.current !== null) {
      window.clearTimeout(listScrollHideTimerRef.current);
    }
    listScrollHideTimerRef.current = window.setTimeout(() => {
      setIsListScrollbarVisible(false);
      listScrollHideTimerRef.current = null;
    }, 900);
  };

  /**
   * 处理创建项目
   */
  const handleCreateProject = async (data: CreateProjectRequest) => {
    try {
      const newProject = await createProject(data);
      message.success("项目创建成功！");
      onEditProject(newProject.id);
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
    <div className="flex h-full min-h-0 flex-col gap-6">
      {/* 区块标题：最近项目 + 搜索 + 创建按钮 */}
      <div className="flex items-center justify-between px-1 shrink-0">
        <div className="flex items-baseline space-x-2">
          <h2 className="text-xl sm:text-2xl font-bold text-gray-900">项目</h2>
        </div>
        <div className="flex items-center space-x-3">
          <div className="flex items-center gap-0.5">
            
            <div className="group relative inline-flex shrink-0 items-center">
            <button
              type="button"
              onClick={() => setIsBasicConfigCheckOpen(true)}
              className="px-2 py-2 text-blue-600 hover:text-blue-700 font-medium transition-colors"
            >
              基础连通检测
            </button>
              <div
                id="basic-config-check-hint"
                role="tooltip"
                className="pointer-events-none absolute right-0 top-full z-20 pt-1 opacity-0 transition-opacity duration-150 group-hover:pointer-events-auto group-hover:opacity-100 group-focus-within:pointer-events-auto group-focus-within:opacity-100"
              >
                <div className="w-64 rounded-md border border-gray-200 bg-white px-3 py-2 text-left text-xs leading-relaxed text-gray-600 shadow-md">
                  一键检查当前配置（文案模型、视频模型、已启用的配音 TTS、内置字幕识别、剪映草稿路径等）是否能走通基础流程，便于在创建或编辑项目前发现问题。
                </div>
              </div>
            </div>
          </div>
          <input
            type="text"
            placeholder="搜索项目..."
            value={searchQuery}
            onChange={(e) => {
              setSearchQuery(e.target.value);
            }}
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
            onClick={() => {
              setIsCreateModalOpen(true);
            }}
            className="flex items-center px-5 py-2 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 transition-colors"
          >
            <Plus className="h-4 w-4 mr-2" />
            创建项目
          </button>
        </div>
      </div>

      <div className="flex min-h-0 flex-1 flex-col gap-4">
        {/* 项目列表 */}
        <div
          onScroll={handleListScroll}
          className={`project-list-scrollbar pt-2 min-h-0 flex-1 overflow-y-auto pr-2 ${isListScrollbarVisible ? "scrollbar-visible" : ""}`}
        >
          <ProjectList
            projects={projects.filter((p) =>
              p.name.toLowerCase().includes(searchQuery.trim().toLowerCase())
            )}
            loading={loading}
            onEdit={handleEditProject}
            onDelete={handleDeleteProject}
          />
        </div>
      </div>

      {/* 创建项目模态框 */}
      <CreateProjectModal
        isOpen={isCreateModalOpen}
        onClose={() => {
          setIsCreateModalOpen(false);
        }}
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

      <BasicConfigCheckModal
        isOpen={isBasicConfigCheckOpen}
        onClose={() => setIsBasicConfigCheckOpen(false)}
      />
    </div>
  );
};

export default ProjectManagementPage;

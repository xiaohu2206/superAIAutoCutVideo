// 项目管理自定义Hook

import { useState, useCallback, useEffect } from "react";
import { projectService } from "../services/projectService";
import type {
  Project,
  CreateProjectRequest,
  UpdateProjectRequest,
  GenerateScriptRequest,
  VideoScript,
} from "../types/project";

/**
 * 项目管理Hook返回类型
 */
export interface UseProjectsReturn {
  projects: Project[];
  loading: boolean;
  error: string | null;
  fetchProjects: () => Promise<void>;
  createProject: (data: CreateProjectRequest) => Promise<Project>;
  deleteProject: (projectId: string) => Promise<void>;
  refreshProjects: () => Promise<void>;
}

/**
 * 项目管理Hook
 */
export const useProjects = (): UseProjectsReturn => {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /**
   * 获取项目列表
   */
  const fetchProjects = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await projectService.getProjects();
      setProjects(data);
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : "获取项目列表失败";
      setError(errorMessage);
      console.error("获取项目列表失败:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  /**
   * 创建项目
   */
  const createProject = useCallback(
    async (data: CreateProjectRequest): Promise<Project> => {
      setError(null);
      try {
        const newProject = await projectService.createProject(data);
        setProjects((prev) => [newProject, ...prev]);
        return newProject;
      } catch (err) {
        const errorMessage = err instanceof Error ? err.message : "创建项目失败";
        setError(errorMessage);
        throw err;
      }
    },
    []
  );

  /**
   * 删除项目
   */
  const deleteProject = useCallback(async (projectId: string) => {
    setError(null);
    try {
      await projectService.deleteProject(projectId);
      setProjects((prev) => prev.filter((p) => p.id !== projectId));
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : "删除项目失败";
      setError(errorMessage);
      throw err;
    }
  }, []);

  /**
   * 刷新项目列表
   */
  const refreshProjects = useCallback(async () => {
    await fetchProjects();
  }, [fetchProjects]);

  return {
    projects,
    loading,
    error,
    fetchProjects,
    createProject,
    deleteProject,
    refreshProjects,
  };
};

/**
 * 单个项目详情Hook返回类型
 */
export interface UseProjectDetailReturn {
  project: Project | null;
  loading: boolean;
  error: string | null;
  fetchProject: (projectId: string) => Promise<void>;
  updateProject: (data: UpdateProjectRequest) => Promise<void>;
  uploadVideo: (file: File) => Promise<void>;
  uploadSubtitle: (file: File) => Promise<void>;
  generateScript: (data: GenerateScriptRequest) => Promise<void>;
  saveScript: (script: VideoScript) => Promise<void>;
  refreshProject: () => Promise<void>;
}

/**
 * 单个项目详情Hook
 */
export const useProjectDetail = (
  projectId?: string
): UseProjectDetailReturn => {
  const [project, setProject] = useState<Project | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /**
   * 获取项目详情
   */
  const fetchProject = useCallback(async (id: string) => {
    setLoading(true);
    setError(null);
    try {
      const data = await projectService.getProject(id);
      setProject(data);
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : "获取项目详情失败";
      setError(errorMessage);
      console.error("获取项目详情失败:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  /**
   * 更新项目
   */
  const updateProject = useCallback(
    async (data: UpdateProjectRequest) => {
      if (!project) return;
      setError(null);
      try {
        const updated = await projectService.updateProject(project.id, data);
        setProject(updated);
      } catch (err) {
        const errorMessage = err instanceof Error ? err.message : "更新项目失败";
        setError(errorMessage);
        throw err;
      }
    },
    [project]
  );

  /**
   * 上传视频
   */
  const uploadVideo = useCallback(
    async (file: File) => {
      if (!project) return;
      setError(null);
      setLoading(true);
      try {
        const response = await projectService.uploadVideo(project.id, file);
        // 更新项目视频路径
        await updateProject({ video_path: response.file_path });
      } catch (err) {
        const errorMessage = err instanceof Error ? err.message : "上传视频失败";
        setError(errorMessage);
        throw err;
      } finally {
        setLoading(false);
      }
    },
    [project, updateProject]
  );

  /**
   * 上传字幕
   */
  const uploadSubtitle = useCallback(
    async (file: File) => {
      if (!project) return;
      setError(null);
      setLoading(true);
      try {
        const response = await projectService.uploadSubtitle(project.id, file);
        // 更新项目字幕路径
        await updateProject({ subtitle_path: response.file_path });
      } catch (err) {
        const errorMessage = err instanceof Error ? err.message : "上传字幕失败";
        setError(errorMessage);
        throw err;
      } finally {
        setLoading(false);
      }
    },
    [project, updateProject]
  );

  /**
   * 生成解说脚本
   */
  const generateScript = useCallback(
    async (data: GenerateScriptRequest) => {
      if (!project) return;
      setError(null);
      setLoading(true);
      try {
        const script = await projectService.generateScript(data);
        setProject((prev) => (prev ? { ...prev, script } : null));
      } catch (err) {
        const errorMessage = err instanceof Error ? err.message : "生成解说脚本失败";
        setError(errorMessage);
        throw err;
      } finally {
        setLoading(false);
      }
    },
    [project]
  );

  /**
   * 保存脚本
   */
  const saveScript = useCallback(
    async (script: VideoScript) => {
      if (!project) return;
      setError(null);
      try {
        const savedScript = await projectService.saveScript(project.id, script);
        setProject((prev) => (prev ? { ...prev, script: savedScript } : null));
      } catch (err) {
        const errorMessage = err instanceof Error ? err.message : "保存脚本失败";
        setError(errorMessage);
        throw err;
      }
    },
    [project]
  );

  /**
   * 刷新项目
   */
  const refreshProject = useCallback(async () => {
    if (project) {
      await fetchProject(project.id);
    }
  }, [project, fetchProject]);

  // 初始加载项目
  useEffect(() => {
    if (projectId) {
      fetchProject(projectId);
    }
  }, [projectId, fetchProject]);

  return {
    project,
    loading,
    error,
    fetchProject,
    updateProject,
    uploadVideo,
    uploadSubtitle,
    generateScript,
    saveScript,
    refreshProject,
  };
};


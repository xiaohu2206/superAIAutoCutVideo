// 项目管理自定义Hook

import { useCallback, useEffect, useState } from "react";
import { projectService } from "../services/projectService";
import type {
  CreateProjectRequest,
  GenerateScriptRequest,
  Project,
  UpdateProjectRequest,
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
  uploadVideo: (file: File, onProgress?: (percent: number) => void) => Promise<void>;
  uploadVideos: (files: FileList | File[], onProgress?: (percent: number) => void) => Promise<void>;
  deleteVideo: () => Promise<void>;
  deleteVideoItem: (filePath: string) => Promise<void>;
  generateScript: (data: GenerateScriptRequest) => Promise<VideoScript>;
  saveScript: (script: VideoScript) => Promise<void>;
  generateVideo: () => Promise<string | null>;
  downloadVideo: () => void;
  mergeVideos: () => Promise<void>;
  refreshProject: () => Promise<void>;
  mergeProgress: number;
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
  const [mergeProgress, setMergeProgress] = useState<number>(0);

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
    async (file: File, onProgress?: (percent: number) => void) => {
      if (!project) return;
      setError(null);
      setLoading(true);
      try {
        const response = await projectService.uploadVideo(project.id, file, onProgress);
        setProject((prev) => {
          if (!prev) return null;
          const paths = Array.isArray(prev.video_paths) ? [...prev.video_paths] : [];
          if (!paths.includes(response.file_path)) paths.push(response.file_path);
          const merged = prev.merged_video_path;
          const effective = merged ? merged : (paths.length === 1 ? paths[0] : undefined);
          return { ...prev, video_paths: paths, video_path: effective };
        });
      } catch (err) {
        const errorMessage = err instanceof Error ? err.message : "上传视频失败";
        setError(errorMessage);
        throw err;
      } finally {
        setLoading(false);
      }
    },
    [project]
  );

  const uploadVideos = useCallback(
    async (files: FileList | File[], onProgress?: (percent: number) => void) => {
      const arr: File[] = Array.from(files as any);
      for (let i = 0; i < arr.length; i++) {
        await uploadVideo(arr[i], onProgress);
      }
    },
    [uploadVideo]
  );

  /**
   * 删除视频
   */
  const deleteVideo = useCallback(async () => {
    if (!project) return;
    setError(null);
    setLoading(true);
    try {
      await projectService.deleteVideo(project.id);
      // 本地状态清理视频路径
      setProject((prev) => (prev ? { ...prev, video_path: undefined, video_paths: [] } : null));
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : "删除视频失败";
      setError(errorMessage);
      throw err;
    } finally {
      setLoading(false);
    }
  }, [project]);

  const deleteVideoItem = useCallback(async (filePath: string) => {
    if (!project) return;
    setError(null);
    setLoading(true);
    try {
      await projectService.deleteVideoItem(project.id, filePath);
      setProject((prev) => {
        if (!prev) return null;
        const paths = (prev.video_paths || []).filter((p) => p !== filePath);
        const merged = prev.merged_video_path;
        const effective = merged ? merged : (paths.length === 1 ? paths[0] : undefined);
        return { ...prev, video_paths: paths, video_path: effective };
      });
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : "删除视频失败";
      setError(errorMessage);
      throw err;
    } finally {
      setLoading(false);
    }
  }, [project]);

  /**
   * 生成解说脚本
   */
  const generateScript = useCallback(
    async (data: GenerateScriptRequest): Promise<VideoScript> => {
      if (!project) {
        throw new Error("项目不存在或未加载");
      }
      setError(null);
      setLoading(true);
      try {
        const script = await projectService.generateScript(data);
        setProject((prev) => (prev ? { ...prev, script } : null));
        return script;
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
   * 根据脚本生成视频
   */
  const generateVideo = useCallback(async (): Promise<string | null> => {
    if (!project) return null;
    setError(null);
    setLoading(true);
    try {
      const result = await projectService.generateVideo(project.id);
      const outputPath = result?.output_path ?? null;
      if (outputPath) {
        setProject((prev) => (prev ? { ...prev, output_video_path: outputPath, status: "completed" as any } : null));
      }
      return outputPath;
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : "生成视频失败";
      setError(errorMessage);
      throw err;
    } finally {
      setLoading(false);
    }
  }, [project]);

  /**
   * 下载生成的视频
   */
  const downloadVideo = useCallback(() => {
    if (!project) return;
    if (!project.output_video_path) {
      alert("尚未生成输出视频");
      return;
    }
    const url = projectService.getOutputVideoDownloadUrl(project.id);
    window.open(url, "_blank");
  }, [project]);

  const mergeVideos = useCallback(async () => {
    if (!project) return;
    setError(null);
    setLoading(true);
    try {
      setMergeProgress(0);
      const start = await projectService.startMergeVideos(project.id);
      const taskId = start.task_id;
      let done = false;
      while (!done) {
        const st = await projectService.getMergeStatus(project.id, taskId);
        console.log("st", st)
        setMergeProgress(Math.round(st.progress));
        if (st.status === "completed") {
          if (st.file_path) {
            setProject((prev) => (prev ? { ...prev, merged_video_path: st.file_path, video_path: st.file_path } : null));
          }
          done = true;
        } else if (st.status === "failed") {
          throw new Error(st.message || "合并失败");
        } else {
          await new Promise((r) => setTimeout(r, 500));
        }
      }
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : "合并视频失败";
      setError(errorMessage);
      throw err;
    } finally {
      setLoading(false);
      setTimeout(() => setMergeProgress(0), 800);
    }
  }, [project]);

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
    uploadVideos,
    deleteVideo,
    deleteVideoItem,
    generateScript,
    saveScript,
    generateVideo,
    downloadVideo,
    mergeVideos,
    mergeProgress,
    refreshProject,
  };
};


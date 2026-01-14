// 项目管理自定义Hook

import { useCallback, useEffect, useState } from "react";
import { projectService } from "../services/projectService";
import { apiClient, wsClient, type WebSocketMessage } from "../services/clients";
import type {
  CreateProjectRequest,
  GenerateScriptRequest,
  Project,
  UpdateProjectRequest,
  VideoScript,
} from "../types/project";

// 统一提取错误信息，优先使用后端提供的 detail/message
const getErrorMessage = (err: unknown, fallback: string): string => {
  if (err && typeof err === "object") {
    const anyErr = err as any;
    if (typeof anyErr.message === "string" && anyErr.message) {
      return anyErr.message;
    }
    if (typeof anyErr.detail === "string" && anyErr.detail) {
      return anyErr.detail;
    }
  }
  if (typeof err === "string" && err) {
    return err;
  }
  return fallback;
};

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

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
    const maxAttempts = 20;
    let attempts = 0;
    try {
      while (attempts < maxAttempts) {
        const ready = await apiClient.testConnection();
        if (ready) break;
        attempts += 1;
        setError(`后端未就绪，正在重试(${attempts}/${maxAttempts})...`);
        await sleep(Math.min(800 + attempts * 200, 3000));
      }
      if (attempts >= maxAttempts) {
        const msg = "后端未就绪，请稍后重试";
        setError(msg);
        throw new Error(msg);
      }
      const data = await projectService.getProjects();
      setProjects(data);
      setError(null);
    } catch (err) {
      const msg = getErrorMessage(err, "获取项目列表失败");
      setError(msg);
      throw err instanceof Error ? err : new Error(msg);
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
        setError(getErrorMessage(err, "创建项目失败"));
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
      setError(getErrorMessage(err, "删除项目失败"));
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
  uploadSubtitle: (file: File, onProgress?: (percent: number) => void) => Promise<void>;
  deleteSubtitle: () => Promise<void>;
  deleteVideo: () => Promise<void>;
  deleteVideoItem: (filePath: string) => Promise<void>;
  reorderVideos: (orderedPaths: string[]) => Promise<void>;
  generateScript: (data: GenerateScriptRequest) => Promise<VideoScript>;
  saveScript: (script: VideoScript) => Promise<void>;
  generateVideo: () => Promise<string | null>;
  downloadVideo: () => void;
  mergeVideos: () => Promise<void>;
  refreshProject: () => Promise<void>;
  mergeProgress: number;
  merging: boolean;
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
  const [merging, setMerging] = useState(false);

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
      setError(getErrorMessage(err, "获取项目详情失败"));
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
        setError(getErrorMessage(err, "更新项目失败"));
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
          const names = { ...(prev.video_names || {}) };
          if (response.file_name) {
            names[response.file_path] = response.file_name;
          }
          const merged = prev.merged_video_path;
          const effective = merged ? merged : (paths.length === 1 ? paths[0] : undefined);
          const currentName = effective ? (names[effective] || effective.split("/").pop()) : undefined;
          return { ...prev, video_paths: paths, video_path: effective, video_names: names, video_current_name: currentName };
        });
      } catch (err) {
        setError(getErrorMessage(err, "上传视频失败"));
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

  const uploadSubtitle = useCallback(
    async (file: File, onProgress?: (percent: number) => void) => {
      if (!project) return;
      setError(null);
      setLoading(true);
      try {
        const response = await projectService.uploadSubtitle(project.id, file, onProgress);
        setProject((prev) => (prev ? { ...prev, subtitle_path: response.file_path } : null));
      } catch (err) {
        setError(getErrorMessage(err, "上传字幕失败"));
        throw err;
      } finally {
        setLoading(false);
      }
    },
    [project]
  );

  const deleteSubtitle = useCallback(async () => {
    if (!project) return;
    setError(null);
    setLoading(true);
    try {
      await projectService.deleteSubtitle(project.id);
      setProject((prev) => (prev ? { ...prev, subtitle_path: undefined } : null));
    } catch (err) {
      setError(getErrorMessage(err, "删除字幕失败"));
      throw err;
    } finally {
      setLoading(false);
    }
  }, [project]);

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
      setError(getErrorMessage(err, "删除视频失败"));
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
        const names = { ...(prev.video_names || {}) };
        if (names[filePath]) {
          delete names[filePath];
        }
        const merged = prev.merged_video_path;
        const effective = merged ? merged : (paths.length === 1 ? paths[0] : undefined);
        const currentName = effective ? (names[effective] || effective.split("/").pop()) : undefined;
        return { ...prev, video_paths: paths, video_path: effective, video_names: names, video_current_name: currentName };
      });
    } catch (err) {
      setError(getErrorMessage(err, "删除视频失败"));
      throw err;
    } finally {
      setLoading(false);
    }
  }, [project]);

  /**
   * 重排视频顺序（持久化）
   */
  const reorderVideos = useCallback(async (orderedPaths: string[]) => {
    if (!project) return;
    setError(null);
    setLoading(true);
    try {
      const updated = await projectService.updateVideoOrder(project.id, orderedPaths);
      setProject(updated);
    } catch (err) {
      setError(getErrorMessage(err, "更新排序失败"));
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
        setError(getErrorMessage(err, "生成解说脚本失败"));
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
        setError(getErrorMessage(err, "保存脚本失败"));
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
      setError(getErrorMessage(err, "生成视频失败"));
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
      setMerging(true);
      const start = await projectService.startMergeVideos(project.id);
      const taskId = start.task_id;

      // 通过 WebSocket 监听该任务的进度与完成事件
      await new Promise<void>((resolve, reject) => {
        const handler = (message: WebSocketMessage & { [key: string]: any }) => {
          if (
            message &&
            (message.type === "progress" || message.type === "completed" || message.type === "error") &&
            (message as any).scope === "merge_videos" &&
            (message as any).project_id === project.id &&
            (message as any).task_id === taskId
          ) {
            if (typeof message.progress === "number") {
              setMergeProgress(Math.max(0, Math.min(100, Math.round(message.progress))));
              setMerging(true);
            }
            if (message.type === "completed") {
              const fp = (message as any).file_path as string | undefined;
              if (fp) {
                const fileName = fp.split("/").pop();
                setProject((prev) => (prev ? { ...prev, merged_video_path: fp, video_path: fp, video_current_name: fileName } : null));
              }
              setMerging(false);
              wsClient.off("*", handler);
              resolve();
            }
            if (message.type === "error") {
              const msg = message.message || "合并失败";
              setMerging(false);
              wsClient.off("*", handler);
              reject(new Error(msg));
            }
          }
        };
        wsClient.on("*", handler);
      });
    } catch (err) {
      setError(getErrorMessage(err, "合并视频失败"));
      throw err;
    } finally {
      setLoading(false);
      setMerging(false);
      setTimeout(() => setMergeProgress(0), 800);
    }
  }, [project]);

  // 订阅 WebSocket 消息以更新合并进度（页面存在时持续监听）
  useEffect(() => {
    const handler = (message: WebSocketMessage & { [key: string]: any }) => {
      if (
        message &&
        (message.type === "progress" || message.type === "completed" || message.type === "error") &&
        (message as any).scope === "merge_videos" &&
        (message as any).project_id === project?.id
      ) {
        if (typeof message.progress === "number") {
          setMergeProgress(Math.max(0, Math.min(100, Math.round(message.progress))));
          setMerging(true);
        }
        if (message.type === "completed") {
          const fp = (message as any).file_path as string | undefined;
          if (fp) {
            const fileName = fp.split("/").pop();
            setProject((prev) => (prev ? { ...prev, merged_video_path: fp, video_path: fp, video_current_name: fileName } : null));
          }
          setMerging(false);
        }
        if (message.type === "error") {
          setMerging(false);
        }
      }
    };
    wsClient.on("*", handler);
    return () => {
      wsClient.off("*", handler);
    };
  }, [project?.id]);

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
    uploadSubtitle,
    deleteSubtitle,
    deleteVideo,
    deleteVideoItem,
    reorderVideos,
    generateScript,
    saveScript,
    generateVideo,
    downloadVideo,
    mergeVideos,
    mergeProgress,
    refreshProject,
    merging,
  };
};

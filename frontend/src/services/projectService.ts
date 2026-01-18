import type {
  CreateProjectRequest,
  FileUploadResponse,
  GenerateScriptRequest,
  Project,
  SubtitleResult,
  SubtitleSegment,
  UpdateProjectRequest,
  VideoScript,
} from "../types/project";
import { apiClient, type ApiResponse } from "./clients";

/**
 * 项目管理服务类
 */
export class ProjectService {
  /**
   * 获取项目列表
   */
  async getProjects(): Promise<Project[]> {
    const response = await apiClient.get<{ data: Project[] }>(
      "/api/projects"
    );
    return response.data;
  }

  /**
   * 获取单个项目详情
   */
  async getProject(projectId: string): Promise<Project> {
    const response = await apiClient.get<{ data: Project }>(
      `/api/projects/${projectId}`
    );
    return response.data;
  }

  /**
   * 创建项目
   */
  async createProject(data: CreateProjectRequest): Promise<Project> {
    const response = await apiClient.post<{ data: Project }>(
      "/api/projects",
      data
    );
    return response.data;
  }

  /**
   * 更新项目
   */
  async updateProject(
    projectId: string,
    data: UpdateProjectRequest
  ): Promise<Project> {
    const response = await apiClient.post<{ data: Project }>(
      `/api/projects/${projectId}`,
      data
    );
    return response.data;
  }

  /**
   * 删除项目
   */
  async deleteProject(projectId: string): Promise<boolean> {
    const response = await apiClient.post<{ success: boolean }>(
      `/api/projects/${projectId}/delete`
    );
    return response.success;
  }

  /**
   * 删除项目视频文件
   */
  async deleteVideo(projectId: string): Promise<boolean> {
    const response = await apiClient.post<{ data?: { removed?: boolean } }>(
      `/api/projects/${projectId}/delete/video`
    );
    return response?.data?.removed ?? true;
  }

  /**
   * 删除指定视频项
   */
  async deleteVideoItem(projectId: string, filePath: string): Promise<boolean> {
    const response = await apiClient.post<{ data?: { removed?: boolean } }>(
      `/api/projects/${projectId}/delete/video`,
      { file_path: filePath }
    );
    return response?.data?.removed ?? true;
  }

  async deleteSubtitle(projectId: string): Promise<boolean> {
    const response = await apiClient.post<{ data?: { removed?: boolean } }>(
      `/api/projects/${projectId}/delete/subtitle`
    );
    return response?.data?.removed ?? true;
  }

  

  /**
   * 上传视频文件
   */
  async uploadVideo(
    projectId: string,
    file: File,
    onProgress?: (percent: number) => void
  ): Promise<FileUploadResponse> {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("project_id", projectId);

    // 使用 XMLHttpRequest 以支持上传进度回调
    return new Promise<FileUploadResponse>((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open(
        "POST",
        `${apiClient.getBaseUrl()}/api/projects/${projectId}/upload/video`
      );

      xhr.upload.onprogress = (event) => {
        if (event.lengthComputable && onProgress) {
          const percent = Math.round((event.loaded / event.total) * 100);
          onProgress(percent);
        }
      };

      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          try {
            const result = JSON.parse(xhr.responseText);
            resolve(result.data as FileUploadResponse);
          } catch (e) {
            reject(new Error("解析响应失败"));
          }
        } else {
          // 尝试解析错误响应中的具体提示信息（detail 或 message）
          let msg = `上传视频失败: ${xhr.statusText || xhr.status}`;
          try {
            if (xhr.responseText) {
              const errJson = JSON.parse(xhr.responseText);
              if (typeof errJson === "string") {
                msg = errJson;
              } else if (errJson?.detail) {
                msg = errJson.detail;
              } else if (errJson?.message) {
                msg = errJson.message;
              }
            }
          } catch {
            // 忽略解析错误，保留默认错误信息
          }
          reject(new Error(msg));
        }
      };

      xhr.onerror = () => {
        reject(new Error("网络错误，上传视频失败"));
      };

      xhr.send(formData);
    });
  }

  async uploadSubtitle(
    projectId: string,
    file: File,
    onProgress?: (percent: number) => void
  ): Promise<FileUploadResponse> {
    const formData = new FormData()
    formData.append("file", file)

    return new Promise<FileUploadResponse>((resolve, reject) => {
      const xhr = new XMLHttpRequest()
      xhr.open(
        "POST",
        `${apiClient.getBaseUrl()}/api/projects/${projectId}/upload/subtitle`
      )

      xhr.upload.onprogress = (event) => {
        if (event.lengthComputable && onProgress) {
          const percent = Math.round((event.loaded / event.total) * 100)
          onProgress(percent)
        }
      }

      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          try {
            const result = JSON.parse(xhr.responseText)
            resolve(result.data as FileUploadResponse)
          } catch (e) {
            reject(new Error("解析响应失败"))
          }
        } else {
          let msg = `上传字幕失败: ${xhr.statusText || xhr.status}`
          try {
            if (xhr.responseText) {
              const errJson = JSON.parse(xhr.responseText)
              if (typeof errJson === "string") {
                msg = errJson
              } else if (errJson?.detail) {
                msg = errJson.detail
              } else if (errJson?.message) {
                msg = errJson.message
              }
            }
          } catch (e) {
            console.error(e)
          }
          reject(new Error(msg))
        }
      }

      xhr.onerror = () => {
        reject(new Error("网络错误，上传字幕失败"))
      }

      xhr.send(formData)
    })
  }

  /**
   * 合并多个视频
   */
  async startMergeVideos(projectId: string): Promise<{ task_id: string }> {
    const response = await apiClient.post<{ data: { task_id: string } }>(
      `/api/projects/${projectId}/merge/videos`
    );
    return response.data;
  }

  async getMergeStatus(projectId: string, taskId: string): Promise<{
    task_id: string;
    status: string;
    progress: number;
    message: string;
    file_path?: string;
  }> {
    const response = await apiClient.get<{ data: any }>(
      `/api/projects/${projectId}/merge/videos/status/${taskId}`
    );
    console.log("getMergeStatus: ", response)
    return response.data;
  }

  /**
   * 更新视频排序（按照用户提供的顺序）
   */
  async updateVideoOrder(projectId: string, orderedPaths: string[]): Promise<Project> {
    const response = await apiClient.post<{ data: Project }>(
      `/api/projects/${projectId}/videos/order`,
      { ordered_paths: orderedPaths }
    );
    return response.data;
  }

  

  /**
   * 生成解说脚本
   */
  async generateScript(data: GenerateScriptRequest): Promise<VideoScript> {
    const response = await apiClient.post<
      ApiResponse<{ script: VideoScript; plot_analysis: string }>
    >("/api/projects/generate-script", data);
    // 后端返回形如 { message, data: { script, plot_analysis }, timestamp }
    // 这里只提取脚本对象返回
    return response.data?.script as VideoScript;
  }

  async extractSubtitle(projectId: string, force?: boolean): Promise<SubtitleResult> {
    const response = await apiClient.post<ApiResponse<SubtitleResult>>(
      `/api/projects/${projectId}/extract-subtitle`,
      force ? { force: true } : undefined
    );
    if (!response.data) {
      throw new Error("字幕提取失败：响应为空");
    }
    return response.data;
  }

  async getSubtitle(projectId: string): Promise<SubtitleResult> {
    const response = await apiClient.get<ApiResponse<SubtitleResult>>(
      `/api/projects/${projectId}/subtitle`
    );
    if (!response.data) {
      throw new Error("获取字幕失败：响应为空");
    }
    return response.data;
  }

  async saveSubtitle(
    projectId: string,
    payload: { segments?: SubtitleSegment[]; content?: string }
  ): Promise<SubtitleResult> {
    const response = await apiClient.post<ApiResponse<SubtitleResult>>(
      `/api/projects/${projectId}/subtitle`,
      payload
    );
    if (!response.data) {
      throw new Error("保存字幕失败：响应为空");
    }
    return response.data;
  }

  /**
   * 保存脚本
   */
  async saveScript(
    projectId: string,
    script: VideoScript
  ): Promise<VideoScript> {
    const response = await apiClient.post<{ data: VideoScript }>(
      `/api/projects/${projectId}/script`,
      { script }
    );
    return response.data;
  }

  /**
   * 根据脚本生成输出视频
   */
  async generateVideo(projectId: string): Promise<{ output_path: string; segments_count: number } | null> {
    const response = await apiClient.post<
      ApiResponse<{ output_path: string; segments_count: number }>
    >(`/api/projects/${projectId}/generate-video`);
    return response.data ?? null;
  }

  /**
   * 生成剪映草稿（后台任务 + WebSocket 进度）
   */
  async startGenerateJianyingDraft(projectId: string): Promise<{ task_id: string; scope?: string } | null> {
    const response = await apiClient.post<ApiResponse<{ task_id: string; scope?: string }>>(
      `/api/projects/${projectId}/generate-jianying-draft`
    );
    return response.data ?? null;
  }

  /**
   * 在系统文件管理器中打开路径（目录或选中文件）
   */
  async openPathInExplorer(projectId: string, path?: string): Promise<void> {
    const base = `${apiClient.getBaseUrl()}/api/projects/${projectId}/open-in-explorer`;
    const url = path ? `${base}?path=${encodeURIComponent(path)}` : base;
    const res = await fetch(url);
    if (!res.ok) {
      let msg = `打开文件管理器失败: ${res.statusText}`;
      try {
        const ct = res.headers.get("content-type") || "";
        if (ct.includes("application/json")) {
          const j = await res.json();
          if (typeof j === "string") msg = j;
          else if (j?.detail) msg = j.detail;
          else if (j?.message) msg = j.message;
        } else {
          const t = await res.text();
          if (t) msg = t;
        }
      } catch (e) {
        void e;
      }
      throw new Error(msg);
    }
  }

  /**
   * 获取输出视频下载链接（后端直接返回文件）
   */
  getOutputVideoDownloadUrl(projectId: string, cacheBust?: string | number): string {
    const base = `${apiClient.getBaseUrl()}/api/projects/${projectId}/output-video/download`;
    return cacheBust !== undefined && cacheBust !== null
      ? `${base}?v=${encodeURIComponent(String(cacheBust))}`
      : base;
  }

  /**
   * 将 /uploads/... 等Web路径转换为完整URL，用于video预览
   */
  getWebFileUrl(webPath: string, cacheBust?: string | number): string {
    const base = `${apiClient.getBaseUrl()}${webPath}`;
    return cacheBust !== undefined && cacheBust !== null
      ? `${base}?v=${encodeURIComponent(String(cacheBust))}`
      : base;
  }

  /**
   * 获取已合并视频播放链接（后端直接返回文件）
   */
  getMergedVideoUrl(projectId: string, cacheBust?: string | number): string {
    const base = `${apiClient.getBaseUrl()}/api/projects/${projectId}/merged-video`;
    return cacheBust !== undefined && cacheBust !== null
      ? `${base}?v=${encodeURIComponent(String(cacheBust))}`
      : base;
  }

  /**
   * 下载输出视频为 Blob（可选）
   */
  async downloadOutputVideoBlob(projectId: string): Promise<Blob> {
    const url = this.getOutputVideoDownloadUrl(projectId);
    const res = await fetch(url);
    if (!res.ok) {
      // 尝试解析错误响应中的具体提示信息（detail 或 message）
      let msg = `下载视频失败: ${res.statusText}`;
      try {
        const contentType = res.headers.get("content-type") || "";
        if (contentType.includes("application/json")) {
          const errJson = await res.json();
          if (typeof errJson === "string") {
            msg = errJson;
          } else if (errJson?.detail) {
            msg = errJson.detail;
          } else if (errJson?.message) {
            msg = errJson.message;
          }
        } else {
          const text = await res.text();
          if (text) msg = text;
        }
      } catch {
        // 忽略解析错误，保留默认错误信息
      }
      throw new Error(msg);
    }
    return await res.blob();
  }
}

// 导出单例实例
export const projectService = new ProjectService();

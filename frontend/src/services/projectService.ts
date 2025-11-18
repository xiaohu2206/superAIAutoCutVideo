import type {
  CreateProjectRequest,
  FileUploadResponse,
  GenerateScriptRequest,
  Project,
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

  /**
   * 删除项目字幕文件
   */
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
          reject(new Error(`上传视频失败: ${xhr.statusText || xhr.status}`));
        }
      };

      xhr.onerror = () => {
        reject(new Error("网络错误，上传视频失败"));
      };

      xhr.send(formData);
    });
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
   * 上传字幕文件
   */
  async uploadSubtitle(
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
        `${apiClient.getBaseUrl()}/api/projects/${projectId}/upload/subtitle`
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
          reject(new Error(`上传字幕失败: ${xhr.statusText || xhr.status}`));
        }
      };

      xhr.onerror = () => {
        reject(new Error("网络错误，上传字幕失败"));
      };

      xhr.send(formData);
    });
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
   * 获取输出视频下载链接（后端直接返回文件）
   */
  getOutputVideoDownloadUrl(projectId: string): string {
    return `${apiClient.getBaseUrl()}/api/projects/${projectId}/output-video`;
  }

  /**
   * 下载输出视频为 Blob（可选）
   */
  async downloadOutputVideoBlob(projectId: string): Promise<Blob> {
    const url = this.getOutputVideoDownloadUrl(projectId);
    const res = await fetch(url);
    if (!res.ok) {
      throw new Error(`下载视频失败: ${res.statusText}`);
    }
    return await res.blob();
  }
}

// 导出单例实例
export const projectService = new ProjectService();


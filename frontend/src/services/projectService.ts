// 项目管理API服务层

import { apiClient } from "../api/client";
import type {
  Project,
  CreateProjectRequest,
  UpdateProjectRequest,
  GenerateScriptRequest,
  FileUploadResponse,
  VideoScript,
} from "../types/project";

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
   * 上传视频文件
   */
  async uploadVideo(
    projectId: string,
    file: File
  ): Promise<FileUploadResponse> {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("project_id", projectId);

    const response = await fetch(
      `${apiClient.getBaseUrl()}/api/projects/${projectId}/upload/video`,
      {
        method: "POST",
        body: formData,
      }
    );

    if (!response.ok) {
      throw new Error(`上传视频失败: ${response.statusText}`);
    }

    const result = await response.json();
    return result.data;
  }

  /**
   * 上传字幕文件
   */
  async uploadSubtitle(
    projectId: string,
    file: File
  ): Promise<FileUploadResponse> {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("project_id", projectId);

    const response = await fetch(
      `${apiClient.getBaseUrl()}/api/projects/${projectId}/upload/subtitle`,
      {
        method: "POST",
        body: formData,
      }
    );

    if (!response.ok) {
      throw new Error(`上传字幕失败: ${response.statusText}`);
    }

    const result = await response.json();
    return result.data;
  }

  /**
   * 生成解说脚本
   */
  async generateScript(data: GenerateScriptRequest): Promise<VideoScript> {
    const response = await apiClient.post<{ data: VideoScript }>(
      "/api/projects/generate-script",
      data
    );
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
}

// 导出单例实例
export const projectService = new ProjectService();


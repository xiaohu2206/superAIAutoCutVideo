// 项目管理相关的类型定义

/**
 * 解说类型枚举
 */
export enum NarrationType {
  SHORT_DRAMA = "短剧解说",
}

/**
 * 项目状态枚举
 */
export enum ProjectStatus {
  DRAFT = "draft", // 草稿
  PROCESSING = "processing", // 处理中
  COMPLETED = "completed", // 已完成
  FAILED = "failed", // 失败
}

/**
 * 脚本段落接口
 */
export interface ScriptSegment {
  id: string;
  start_time: number; // 开始时间（秒）
  end_time: number; // 结束时间（秒）
  text: string; // 解说文本
  subtitle?: string; // 对应字幕
}

/**
 * 视频脚本接口
 */
export interface VideoScript {
  version: string; // 脚本版本
  total_duration: number; // 总时长（秒）
  segments: ScriptSegment[]; // 脚本段落列表
  metadata?: {
    video_name?: string;
    created_at?: string;
    updated_at?: string;
    [key: string]: any;
  };
}

/**
 * 项目接口
 */
export interface Project {
  id: string; // 项目ID
  name: string; // 项目名称
  description?: string; // 项目描述
  narration_type: NarrationType; // 解说类型
  status: ProjectStatus; // 项目状态
  video_path?: string; // 视频文件路径
  subtitle_path?: string; // 字幕文件路径
  output_video_path?: string; // 输出视频文件路径
  script?: VideoScript; // 视频脚本
  created_at: string; // 创建时间
  updated_at: string; // 更新时间
}

/**
 * 创建项目请求接口
 */
export interface CreateProjectRequest {
  name: string;
  description?: string;
  narration_type?: NarrationType;
}

/**
 * 更新项目请求接口
 */
export interface UpdateProjectRequest {
  name?: string;
  description?: string;
  narration_type?: NarrationType;
  status?: ProjectStatus;
  video_path?: string;
  subtitle_path?: string;
  output_video_path?: string;
  script?: VideoScript;
}

/**
 * 生成解说脚本请求接口
 */
export interface GenerateScriptRequest {
  project_id: string;
  video_path: string;
  subtitle_path?: string;
  narration_type: NarrationType;
}

/**
 * 文件上传响应接口
 */
export interface FileUploadResponse {
  file_path: string;
  file_name: string;
  file_size: number;
  upload_time: string;
}


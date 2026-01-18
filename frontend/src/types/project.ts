// 项目管理相关的类型定义

/**
 * 解说类型枚举
 */
export enum NarrationType {
  SHORT_DRAMA = "短剧解说",
  MOVIE = "电影解说",
}

export type ScriptLengthOption = "短篇" | "中偏" | "长偏";

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

export type SubtitleSource = null | "user" | "extracted";
export type SubtitleStatus = null | "none" | "extracting" | "ready" | "failed";

export interface SubtitleSegment {
  id?: string;
  start_time: number;
  end_time: number;
  text: string;
}

export interface SubtitleMeta {
  file_path?: string | null;
  source?: SubtitleSource;
  status?: SubtitleStatus;
  updated_by_user?: boolean;
  updated_at?: string | null;
  format?: string | null;
}

export interface SubtitleResult {
  segments: SubtitleSegment[];
  subtitle_meta: SubtitleMeta;
}

/**
 * 项目接口
 */
export interface Project {
  id: string; // 项目ID
  name: string; // 项目名称
  description?: string; // 项目描述
  narration_type: NarrationType; // 解说类型
  script_length?: ScriptLengthOption; // 电影脚本长度（仅电影解说生效）
  status: ProjectStatus; // 项目状态
  video_path?: string; // 视频文件路径
  video_paths?: string[]; // 多个原始视频文件路径
  merged_video_path?: string; // 合并后视频文件路径
  // 新增：映射每个视频路径到原始文件名，以及当前生效视频的文件名
  video_names?: Record<string, string>;
  video_current_name?: string;
  subtitle_path?: string; // 字幕文件路径
  subtitle_source?: SubtitleSource;
  subtitle_status?: SubtitleStatus;
  subtitle_updated_by_user?: boolean;
  subtitle_updated_at?: string | null;
  subtitle_format?: string | null;
  output_video_path?: string; // 输出视频文件路径
  // 剪映草稿相关
  jianying_draft_last_dir?: string; // 最新草稿目录绝对路径或Web路径
  jianying_draft_last_dir_web?: string; // 最新草稿目录Web路径
  jianying_draft_dirs?: string[]; // 草稿目录Web路径列表
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
  script_length?: ScriptLengthOption;
  status?: ProjectStatus;
  video_path?: string;
  video_paths?: string[];
  merged_video_path?: string;
  subtitle_path?: string;
  subtitle_source?: SubtitleSource;
  subtitle_status?: SubtitleStatus;
  subtitle_updated_by_user?: boolean;
  subtitle_updated_at?: string | null;
  subtitle_format?: string | null;
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

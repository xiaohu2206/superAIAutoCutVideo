/**
 * 视频生成模型配置接口
 */
export interface VideoModelConfig {
  provider: string;
  api_key: string;
  base_url: string;
  model_name: string;
  extra_params: Record<string, any>;
  description?: string;
  enabled?: boolean;
}

/**
 * 文案生成模型配置接口
 */
export interface ContentModelConfig {
  provider: string;
  api_key: string;
  base_url: string;
  model_name: string;
  extra_params: Record<string, any>;
  description?: string;
  enabled?: boolean;
}

/**
 * 应用设置接口
 */
export interface AppSettings {
  // 后端设置
  backend: {
    autoStart: boolean;
    port: number;
    timeout: number;
    maxRetries: number;
  };

  // 文件路径设置
  paths: {
    defaultInputDir: string;
    defaultOutputDir: string;
    tempDir: string;
  };
}

/**
 * 测试结果接口
 */
export interface TestResult {
  success: boolean;
  message: string;
}

/**
 * 设置页面栏目接口
 */
export interface SettingsSection {
  id: string;
  label: string;
  icon: any;
}


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

/**
 * TTS 引擎元信息
 */
export interface TtsEngineMeta {
  provider: string;
  display_name: string;
  description?: string;
  required_fields?: string[];
  optional_fields?: string[];
}

/**
 * TTS 音色信息
 */
export interface TtsVoice {
  id: string;
  name: string;
  description?: string;
  sample_wav_url?: string;
  language?: string;
  gender?: string;
  tags?: string[];
}

/**
 * TTS 引擎配置
 */
export interface TtsEngineConfig {
  provider: string;
  secret_id?: string | null;
  secret_key?: string | null;
  region?: string | null;
  description?: string | null;
  enabled: boolean;
  active_voice_id?: string | null;
  speed_ratio: number;
  extra_params?: Record<string, any>;
}

export interface TtsConfigsData {
  configs: Record<string, TtsEngineConfig>;
  active_config_id?: string | null;
}

export interface TtsTestResult {
  success: boolean;
  config_id: string;
  provider: string;
  message: string;
}


/**
 * 视频生成模型相关工具函数
 */

/**
 * 根据提供商获取配置ID
 */
export const getConfigIdByProvider = (provider: string): string => {
  return `${provider}_video_analysis`;
};

/**
 * 获取默认的接口地址
 */
export const getDefaultBaseUrl = (provider: string): string => {
  const defaults: Record<string, string> = {
    qwen: "https://dashscope.aliyuncs.com/api/v1/chat/completions",
    doubao: "https://ark.cn-beijing.volces.com/api/v3/chat/completions",
    deepseek: "https://api.deepseek.com/chat/completions",
    openrouter: "https://openrouter.ai/api/v1/chat/completions",
  };
  return defaults[provider] || "";
};

/**
 * 获取默认的模型名称
 */
export const getDefaultModelName = (provider: string): string => {
  const defaults: Record<string, string> = {
    qwen: "qwen-vl-plus",
    doubao: "doubao-vision-pro",
    deepseek: "deepseek-vl-chat",
    openrouter: "openai/gpt-4o-mini",
  };
  return defaults[provider] || "";
};

/**
 * 获取默认的描述
 */
export const getDefaultDescription = (provider: string): string => {
  const defaults: Record<string, string> = {
    qwen: "通义千问视频生成模型",
    doubao: "豆包视频生成模型",
    deepseek: "DeepSeek视频生成模型",
    openrouter: "OpenRouter视频生成模型",
  };
  return defaults[provider] || "";
};

/**
 * 文案生成模型相关工具函数
 */

/**
 * 根据提供商获取文案生成模型配置ID
 */
export const getContentConfigIdByProvider = (provider: string): string => {
  return `${provider}_content_generation`;
};

/**
 * 获取文案生成模型默认的接口地址
 */
export const getContentDefaultBaseUrl = (provider: string): string => {
  const defaults: Record<string, string> = {
    qwen: "https://dashscope.aliyuncs.com/api/v1/chat/completions",
    doubao: "https://ark.cn-beijing.volces.com/api/v3/chat/completions",
    deepseek: "https://api.deepseek.com/chat/completions",
    openrouter: "https://openrouter.ai/api/v1/chat/completions",
  };
  return defaults[provider] || "";
};

/**
 * 获取文案生成模型默认的模型名称
 */
export const getContentDefaultModelName = (provider: string): string => {
  const defaults: Record<string, string> = {
    qwen: "qwen3-max",
    doubao: "doubao-seed-1-6-251015",
    deepseek: "deepseek-chat",
    openrouter: "openai/gpt-4o-mini",
  };
  return defaults[provider] || "";
};

/**
 * 获取文案生成模型默认的描述
 */
export const getContentDefaultDescription = (provider: string): string => {
  const defaults: Record<string, string> = {
    qwen: "通义千问文案生成模型",
    doubao: "豆包文案生成模型",
    deepseek: "DeepSeek文案生成模型",
    openrouter: "OpenRouter文案生成模型（支持结构化输出）",
  };
  return defaults[provider] || "";
};

/**
 * TTS（音色设置）相关工具函数
 */

// 根据提供商获取TTS配置ID（后端默认示例为 tencent_tts_default）
export const getTtsConfigIdByProvider = (provider: string): string => {
  if (provider === "tencent_tts") return "tencent_tts_default";
  return `${provider}_default`;
};

// 语速标签映射
export const getSpeedLabel = (speed: number): string => {
  if (speed < 0.8) return "较慢";
  if (speed <= 1.2) return "正常";
  return "较快";
};


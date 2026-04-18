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
    yunwu: "https://yunwu.ai/v1/chat/completions",
    "302ai": "https://api.302ai.cn/v1/chat/completions",
    qwen: "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
    doubao: "https://ark.cn-beijing.volces.com/api/v3/chat/completions",
    deepseek: "https://api.deepseek.com/chat/completions",
    openrouter: "https://openrouter.ai/api/v1/chat/completions",
    custom_openai_vision: "https://api.openai.com/v1/chat/completions",
    moondream: "",
  };
  return defaults[provider] || "";
};

/** 视频视觉分析：各提供商可选模型（第一项为默认） */
export const VIDEO_VISION_MODEL_OPTIONS: Record<
  string,
  { value: string; label: string }[]
> = {
  yunwu: [
    { value: "gemini-2.5-flash-lite", label: "gemini-2.5-flash-lite" },
    {
      value: "gemini-3.1-flash-lite-preview",
      label: "gemini-3.1-flash-lite-preview",
    },
  ],
  qwen: [{ value: "qwen3-vl-flash", label: "qwen3-vl-flash" }],
  "302ai": [
    { value: "qwen3-vl-flash", label: "qwen3-vl-flash" },
    { value: "gemini-2.0-flash-lite", label: "gemini-2.0-flash-lite" },
    {
      value: "gemini-2.5-flash-lite-preview-09-2025",
      label: "gemini-2.5-flash-lite-preview-09-2025",
    },
  ],
  doubao: [
    {
      value: "doubao-seed-1-6-flash-250828",
      label: "doubao-seed-1-6-flash-250828",
    },
  ],
  custom_openai_vision: [],
  moondream: [{ value: "moondream2", label: "moondream2" }],
};

export const getVideoVisionModelOptions = (
  provider: string,
): { value: string; label: string }[] => {
  return VIDEO_VISION_MODEL_OPTIONS[provider] ?? [];
};

/**
 * 获取默认的模型名称
 */
export const getDefaultModelName = (provider: string): string => {
  const fromPresets = VIDEO_VISION_MODEL_OPTIONS[provider]?.[0]?.value;
  if (fromPresets) return fromPresets;
  const defaults: Record<string, string> = {
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
    yunwu: "云雾API平台视频分析模型（支持视觉）",
    "302ai": "302AI平台视频分析模型（支持视觉）",
    qwen: "通义千问视频生成模型",
    doubao: "豆包视频生成模型",
    deepseek: "DeepSeek视频生成模型",
    openrouter: "OpenRouter视频生成模型",
    custom_openai_vision: "自定义视觉模型（OpenAI 兼容 Chat Completions，支持图片）",
    moondream: "Moondream2 本地视觉分析",
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
    yunwu: "https://yunwu.ai/v1/chat/completions",
    "302ai": "https://api.302ai.cn/v1/chat/completions",
    qwen: "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
    doubao: "https://ark.cn-beijing.volces.com/api/v3/chat/completions",
    deepseek: "https://api.deepseek.com/chat/completions",
    openrouter: "https://openrouter.ai/api/v1/chat/completions",
    custom_openai: "https://api.openai.com/v1/chat/completions",
  };
  return defaults[provider] || "";
};

/**
 * 获取文案生成模型默认的模型名称
 */
export const getContentDefaultModelName = (provider: string): string => {
  const defaults: Record<string, string> = {
    yunwu: "gemini-3.1-pro-preview",
    "302ai": "gemini-3.1-pro-preview",
    qwen: "qwen3-max",
    doubao: "doubao-seed-1-8-251228",
    deepseek: "deepseek-chat",
    openrouter: "openai/gpt-4o-mini",
    custom_openai: "gpt-4o-mini",
  };
  return defaults[provider] || "";
};

/**
 * 获取文案生成模型默认的描述
 */
export const getContentDefaultDescription = (provider: string): string => {
  const defaults: Record<string, string> = {
    yunwu: "云雾API平台文案生成模型（支持结构化输出）",
    "302ai": "302AI平台文案生成模型（支持结构化输出）",
    qwen: "通义千问文案生成模型",
    doubao: "豆包文案生成模型",
    deepseek: "DeepSeek文案生成模型",
    openrouter: "OpenRouter文案生成模型（支持结构化输出）",
    custom_openai: "自定义 OpenAI 兼容接口（与通义等相同 HTTP 调用）",
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

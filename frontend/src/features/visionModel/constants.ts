export const VISION_MODEL_OPTIONS = [
  {
    id: "moondream2_gguf",
    label: "Moondream2 (GGUF)",
    description: "轻量级视觉语言模型，支持图像描述与问答",
  },
];

/** 与后端 extract_scene 在线视觉分支一致 */
export const ONLINE_VIDEO_VISION_PROVIDERS = [
  "yunwu",
  "302ai",
  "qwen",
  "doubao",
  "custom_openai_vision",
] as const;

export function isOnlineVideoVisionProvider(
  provider: string | undefined | null,
): boolean {
  if (!provider) return false;
  const p = provider.toLowerCase();
  return (ONLINE_VIDEO_VISION_PROVIDERS as readonly string[]).includes(p);
}

/** 项目页等：镜头提取时视觉分析方式说明 */
export function videoVisionAnalysisScopeLabel(
  provider: string | undefined | null,
): string {
  if (!provider) return "视觉分析";
  if (isOnlineVideoVisionProvider(provider)) return "在线视觉分析";
  if (provider.toLowerCase() === "moondream") return "本地视觉分析 (Moondream2)";
  return "本地视觉分析";
}

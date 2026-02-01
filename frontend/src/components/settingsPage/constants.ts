import { Activity, FileText, Info, Mic, FolderOpen, HardDrive } from "lucide-react";
import type { AppSettings, SettingsSection } from "./types";

/**
 * 默认应用设置
 */
export const defaultSettings: AppSettings = {
  backend: {
    autoStart: true,
    port: 8000,
    timeout: 30,
    maxRetries: 3,
  },
  paths: {
    defaultInputDir: "",
    defaultOutputDir: "",
    tempDir: "",
  },
};

/**
 * 设置页面栏目配置
 */
export const sections: SettingsSection[] = [
  // { id: "videoModel", label: "视频生成模型", icon: Cpu },
  { id: "contentModel", label: "文案生成模型", icon: FileText },
  { id: "tts", label: "音色设置（TTS）", icon: Mic },
  { id: "jianyingDraftPath", label: "剪映草稿路径", icon: FolderOpen },
  { id: "storage", label: "存储设置", icon: HardDrive },
  { id: "monitor", label: "状态监控", icon: Activity },
  { id: "about", label: "关于", icon: Info },
];

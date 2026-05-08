import { Info, Mic, FolderOpen, HardDrive, Subtitles, Layers } from "lucide-react";
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
  { id: "integratedModel", label: "整合模型", icon: Layers },
  { id: "tts", label: "音色设置（TTS）", icon: Mic },
  { id: "subtitleAsr", label: "字幕识别", icon: Subtitles },
  { id: "jianyingDraftPath", label: "剪映草稿路径", icon: FolderOpen },
  { id: "storage", label: "存储设置", icon: HardDrive },
  { id: "about", label: "关于", icon: Info },
];

import { Cpu, FileText, Folder, Server } from "lucide-react";
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
  { id: "backend", label: "后端设置", icon: Server },
  { id: "videoModel", label: "视频生成模型", icon: Cpu },
  { id: "contentModel", label: "文案生成模型", icon: FileText },
  { id: "paths", label: "路径设置", icon: Folder },
];


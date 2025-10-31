import { useEffect, useState } from "react";
import { TauriCommands } from "../../../api/client";
import { defaultSettings } from "../constants";
import type { AppSettings } from "../types";

/**
 * 应用设置管理 Hook
 */
export const useSettings = () => {
  const [settings, setSettings] = useState<AppSettings>(defaultSettings);
  const [hasChanges, setHasChanges] = useState(false);
  const [isSaving, setIsSaving] = useState(false);

  // 加载设置
  useEffect(() => {
    loadSettings();
  }, []);

  const loadSettings = async () => {
    try {
      // 从本地存储或配置文件加载设置
      const savedSettings = localStorage.getItem("app-settings");
      if (savedSettings) {
        setSettings({ ...defaultSettings, ...JSON.parse(savedSettings) });
      }
    } catch (error) {
      console.error("加载设置失败:", error);
    }
  };

  const saveSettings = async () => {
    try {
      setIsSaving(true);

      // 保存到本地存储
      localStorage.setItem("app-settings", JSON.stringify(settings));

      // 显示成功通知
      await TauriCommands.showNotification("成功", "设置已保存");
      setHasChanges(false);
    } catch (error) {
      console.error("保存设置失败:", error);
      await TauriCommands.showNotification("错误", "保存设置失败");
    } finally {
      setIsSaving(false);
    }
  };

  const resetSettings = async () => {
    if (confirm("确定要重置所有设置吗？此操作不可撤销。")) {
      setSettings(defaultSettings);
      setHasChanges(true);
      await TauriCommands.showNotification("信息", "设置已重置");
    }
  };

  const updateSetting = (path: string, value: any) => {
    setSettings((prev) => {
      const newSettings = { ...prev };
      const keys = path.split(".");
      let current: any = newSettings;

      for (let i = 0; i < keys.length - 1; i++) {
        current = current[keys[i]];
      }

      current[keys[keys.length - 1]] = value;
      return newSettings;
    });
    setHasChanges(true);
  };

  const selectDirectory = async (settingPath: string) => {
    try {
      // 检查是否在Tauri环境中
      if (typeof (window as any).__TAURI_IPC__ === "function") {
        const result = await TauriCommands.selectOutputDirectory();
        if (!result.cancelled && result.path) {
          updateSetting(settingPath, result.path);
        }
      } else {
        // 在浏览器环境中，使用默认路径
        updateSetting(settingPath, "/default/path");
      }
    } catch (error) {
      console.error("选择目录失败:", error);
    }
  };

  return {
    settings,
    hasChanges,
    isSaving,
    saveSettings,
    resetSettings,
    updateSetting,
    selectDirectory,
  };
};


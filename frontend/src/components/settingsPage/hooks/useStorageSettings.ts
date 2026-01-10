import { useEffect, useMemo, useState } from "react";
 
import { TauriCommands } from "../../../services/tauriService";
import storageService from "../../../services/storageService";
import { notifyError, notifySuccess } from "../../../services/notification";
import type { DiskInfo, StorageSettingsData, StorageUpdateResponse } from "../types";

export function useStorageSettings() {
  const [current, setCurrent] = useState<StorageSettingsData | null>(null);
  const [selectedDir, setSelectedDirRaw] = useState<string>("");
  const [dirDirty, setDirDirty] = useState<boolean>(false);
  function setSelectedDir(v: string) {
    setSelectedDirRaw(v);
    setDirDirty(true);
  }
  const [migrate, setMigrate] = useState<boolean>(false);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const percentUsed = useMemo(() => {
    const d = current?.disk;
    if (!d || !d.total_bytes) return 0;
    if (typeof d.percent_used === "number") return Math.max(0, Math.min(100, d.percent_used));
    return Math.round(((d.used_bytes || 0) / d.total_bytes) * 100);
  }, [current]);

  useEffect(() => {
    init();
  }, []);

  async function init() {
    setError(null);
    try {
      const res = await storageService.getSettings();
      if (res?.success) {
        const data: StorageSettingsData = res.data || { uploads_root: "" };
        setCurrent(data);
        if (!dirDirty) {
          setSelectedDirRaw(data.uploads_root || "");
        }
      } else {
        setError(res?.message || "加载存储设置失败");
      }
    } catch (e: any) {
      const msg = await notifyError("错误", e, "加载存储设置失败");
      setError(msg);
    }
  }

  function isProtectedDirectory(p: string): boolean {
    const path = (p || "").trim();
    if (!path) return true;
    const lower = path.toLowerCase();
    if (lower === "/" || lower === "c:\\" || lower === "d:\\" || lower === "e:\\") return true;
    if (lower.includes("program files") || lower.includes("windows") || lower.includes("/system") || lower.includes("/applications")) return true;
    return false;
  }

  async function pickDirectory() {
    setError(null);
    try {
      const res = await TauriCommands.selectOutputDirectory();
      if (!res.cancelled && res.path) {
        const p = res.path;
        if (isProtectedDirectory(p)) {
          await notifyError("路径不可用", "选择的目录为系统保护目录");
          return;
        }
        setSelectedDir(p);
      }
    } catch (e: any) {
      const msg = await notifyError("错误", e, "选择目录失败");
      setError(msg);
    }
  }

  async function applySettings(target?: string, doMigrate?: boolean) {
    const uploadsRoot = (target || selectedDir || current?.uploads_root || "").trim();
    const migrateFlag = typeof doMigrate === "boolean" ? doMigrate : migrate;
    if (!uploadsRoot) {
      await notifyError("错误", "请输入或选择有效目录");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res: StorageUpdateResponse = await storageService.updateSettings(uploadsRoot, migrateFlag);
      if (res?.success) {
        setCurrent({
          uploads_root: res?.data?.uploads_root || uploadsRoot,
          disk: res?.data?.disk as DiskInfo | undefined,
        });
        await notifySuccess("成功", "已保存");
        if (typeof res?.data?.failed_count === "number" && res.data.failed_count > 0) {
          await notifyError("迁移未完成", `失败 ${res.data.failed_count} 项，建议手动处理`);
        }
      } else {
        const msg = await notifyError("错误", res?.message || "保存失败");
        setError(msg);
      }
    } catch (e: any) {
      const msg = await notifyError("错误", e, "保存失败");
      setError(msg);
    } finally {
      setLoading(false);
    }
  }

  return {
    current,
    selectedDir,
    setSelectedDir,
    migrate,
    setMigrate,
    loading,
    error,
    percentUsed,
    pickDirectory,
    applySettings,
  };
}

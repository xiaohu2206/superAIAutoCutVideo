import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  applyLocalRuntimeUpdate,
  checkLocalRuntimeUpdate,
  getRuntimeInstalledState,
  onRuntimeUpdateProgress,
  type DownloadProgress,
  type InstalledState,
  type RuntimeUpdateInfo,
} from "../services/runtimeUpdaterService";

interface RuntimeUpdateState {
  checking: boolean;
  installing: boolean;
  updateInfo: RuntimeUpdateInfo | null;
  installedState: InstalledState | null;
  localManifestPath: string | null;
  progress: DownloadProgress | null;
  error: string;
}

const initial: RuntimeUpdateState = {
  checking: false,
  installing: false,
  updateInfo: null,
  installedState: null,
  localManifestPath: null,
  progress: null,
  error: "",
};

export function useRuntimeUpdater() {
  const [state, setState] = useState<RuntimeUpdateState>(initial);
  const unlistenRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    let mounted = true;

    const setup = async () => {
      const unlisten = await onRuntimeUpdateProgress((progress) => {
        if (!mounted) return;
        setState((prev) => ({ ...prev, progress }));
      });
      if (mounted) {
        unlistenRef.current = unlisten;
      } else {
        unlisten();
      }
    };

    void setup();

    return () => {
      mounted = false;
      unlistenRef.current?.();
      unlistenRef.current = null;
    };
  }, []);

  useEffect(() => {
    void loadInstalledState();
  }, []);

  const loadInstalledState = useCallback(async () => {
    const installed = await getRuntimeInstalledState();
    setState((prev) => ({ ...prev, installedState: installed }));
  }, []);

  /** 选择清单后预览：需传入 runtime-manifest.json 的绝对路径 */
  const checkLocal = useCallback(async (manifestPath: string) => {
    setState((prev) => ({
      ...prev,
      checking: true,
      error: "",
      localManifestPath: manifestPath,
    }));
    try {
      const info = await checkLocalRuntimeUpdate(manifestPath);
      setState((prev) => ({
        ...prev,
        checking: false,
        updateInfo: info,
      }));
      return info;
    } catch (error) {
      const msg = error instanceof Error ? error.message : "读取本地清单失败";
      setState((prev) => ({
        ...prev,
        checking: false,
        error: msg,
        updateInfo: null,
      }));
      return null;
    }
  }, []);

  const applyLocal = useCallback(async (manifestPath: string) => {
    setState((prev) => ({
      ...prev,
      installing: true,
      error: "",
      progress: null,
    }));
    try {
      const info = await applyLocalRuntimeUpdate(manifestPath);
      setState((prev) => ({ ...prev, installing: false, updateInfo: info }));
      await loadInstalledState();
      return info;
    } catch (error) {
      const msg = error instanceof Error ? error.message : "安装本地运行时失败";
      setState((prev) => ({ ...prev, installing: false, error: msg }));
      return null;
    }
  }, [loadInstalledState]);

  const clearLocalSelection = useCallback(() => {
    setState((prev) => ({
      ...prev,
      localManifestPath: null,
      updateInfo: null,
      error: "",
    }));
  }, []);

  return useMemo(
    () => ({
      ...state,
      checkLocal,
      applyLocal,
      loadInstalledState,
      clearLocalSelection,
    }),
    [state, checkLocal, applyLocal, loadInstalledState, clearLocalSelection]
  );
}

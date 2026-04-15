import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  checkRuntimeUpdate,
  downloadRuntimeUpdate,
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
  progress: DownloadProgress | null;
  error: string;
}

const initial: RuntimeUpdateState = {
  checking: false,
  installing: false,
  updateInfo: null,
  installedState: null,
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

  const checkNow = useCallback(async () => {
    setState((prev) => ({ ...prev, checking: true, error: "" }));
    try {
      const info = await checkRuntimeUpdate();
      setState((prev) => ({ ...prev, checking: false, updateInfo: info }));
      return info;
    } catch (error) {
      const msg = error instanceof Error ? error.message : "检查运行时更新失败";
      setState((prev) => ({ ...prev, checking: false, error: msg }));
      return null;
    }
  }, []);

  const installNow = useCallback(async () => {
    setState((prev) => ({
      ...prev,
      installing: true,
      error: "",
      progress: null,
    }));
    try {
      const info = await downloadRuntimeUpdate();
      setState((prev) => ({ ...prev, installing: false, updateInfo: info }));
      await loadInstalledState();
      return info;
    } catch (error) {
      const msg = error instanceof Error ? error.message : "安装运行时更新失败";
      setState((prev) => ({ ...prev, installing: false, error: msg }));
      return null;
    }
  }, [loadInstalledState]);

  return useMemo(
    () => ({
      ...state,
      checkNow,
      installNow,
      loadInstalledState,
    }),
    [state, checkNow, installNow, loadInstalledState]
  );
}

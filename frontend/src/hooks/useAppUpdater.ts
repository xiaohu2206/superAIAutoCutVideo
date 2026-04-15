import { useCallback, useEffect, useMemo, useState } from "react";
import {
  checkForAppUpdate,
  downloadAndInstallAppUpdate,
  type UpdateSummary,
} from "../services/updaterService";

interface UpdateState {
  checking: boolean;
  installing: boolean;
  updateInfo: UpdateSummary | null;
  downloadedBytes: number;
  totalBytes?: number;
  error: string;
}

const initialState: UpdateState = {
  checking: false,
  installing: false,
  updateInfo: null,
  downloadedBytes: 0,
  totalBytes: undefined,
  error: "",
};

export function useAppUpdater(autoCheck = false) {
  const [state, setState] = useState<UpdateState>(initialState);

  const checkNow = useCallback(async () => {
    setState((prev) => ({ ...prev, checking: true, error: "" }));
    try {
      const updateInfo = await checkForAppUpdate();
      setState((prev) => ({
        ...prev,
        checking: false,
        updateInfo,
      }));
      return updateInfo;
    } catch (error) {
      const message = error instanceof Error ? error.message : "检查更新失败";
      setState((prev) => ({ ...prev, checking: false, error: message }));
      return null;
    }
  }, []);

  const installNow = useCallback(async () => {
    setState((prev) => ({
      ...prev,
      installing: true,
      error: "",
      downloadedBytes: 0,
      totalBytes: undefined,
    }));

    try {
      const updateInfo = await downloadAndInstallAppUpdate((progress) => {
        setState((prev) => ({
          ...prev,
          downloadedBytes: prev.downloadedBytes + progress.chunkLength,
          totalBytes: progress.contentLength ?? prev.totalBytes,
        }));
      });

      setState((prev) => ({
        ...prev,
        installing: false,
        updateInfo,
      }));

      return updateInfo;
    } catch (error) {
      const message = error instanceof Error ? error.message : "安装更新失败";
      setState((prev) => ({ ...prev, installing: false, error: message }));
      return null;
    }
  }, []);

  useEffect(() => {
    if (!autoCheck) return;
    void checkNow();
  }, [autoCheck, checkNow]);

  return useMemo(
    () => ({
      ...state,
      checkNow,
      installNow,
    }),
    [state, checkNow, installNow]
  );
}

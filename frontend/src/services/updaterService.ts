import { check } from "@tauri-apps/plugin-updater";

export interface UpdateSummary {
  available: boolean;
  currentVersion?: string;
  version?: string;
  body?: string;
  date?: string;
}

const isTauriRuntime = (): boolean => {
  const w = typeof window !== "undefined" ? (window as any) : undefined;
  if (!w) return false;
  return (
    !!w.__TAURI__ ||
    typeof w.__TAURI_IPC__ === "function" ||
    !!w.__TAURI_METADATA__ ||
    !!w.__TAURI_INTERNALS__
  );
};

export async function checkForAppUpdate(): Promise<UpdateSummary | null> {
  if (!isTauriRuntime()) {
    return null;
  }

  try {
    const update = await check();
    if (!update) {
      return { available: false };
    }

    return {
      available: true,
      currentVersion: update.currentVersion,
      version: update.version,
      body: update.body,
      date: update.date,
    };
  } catch (error) {
    console.warn("检查更新失败", error);
    return null;
  }
}

export async function downloadAndInstallAppUpdate(
  onProgress?: (progress: { chunkLength: number; contentLength?: number }) => void
): Promise<UpdateSummary | null> {
  if (!isTauriRuntime()) {
    return null;
  }

  const update = await check();
  if (!update) {
    return { available: false };
  }

  await update.downloadAndInstall((event) => {
    if (event.event === "Progress") {
      onProgress?.({
        chunkLength: event.data.chunkLength,
        contentLength: event.data.contentLength,
      });
    }
  });

  return {
    available: true,
    currentVersion: update.currentVersion,
    version: update.version,
    body: update.body,
    date: update.date,
  };
}

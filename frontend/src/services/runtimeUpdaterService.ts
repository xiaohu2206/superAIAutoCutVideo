import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";

export interface RuntimeChunk {
  name: string;
  version: string;
  sha256: string;
  size: number;
  url: string;
  description?: string;
}

export interface RuntimeUpdateInfo {
  available: boolean;
  current_version: string;
  remote_version: string;
  chunks_to_update: RuntimeChunk[];
  total_download_size: number;
  skip_chunks: string[];
}

export interface InstalledChunkInfo {
  version: string;
  sha256: string;
}

export interface InstalledState {
  schema_version: number;
  installed_at: string;
  runtime_version: string;
  variant: string;
  chunks: Record<string, InstalledChunkInfo>;
}

export interface DownloadProgress {
  chunk_name: string;
  downloaded: number;
  total: number;
  phase: "downloading" | "extracting" | "done";
}

const isTauriRuntime = (): boolean => {
  const w = typeof window !== "undefined" ? (window as any) : undefined;
  return !!w?.__TAURI__ || typeof w?.__TAURI_IPC__ === "function";
};

export async function checkRuntimeUpdate(): Promise<RuntimeUpdateInfo | null> {
  if (!isTauriRuntime()) return null;
  try {
    return await invoke<RuntimeUpdateInfo>("check_runtime_update");
  } catch (error) {
    console.warn("检查运行时更新失败", error);
    return null;
  }
}

export async function downloadRuntimeUpdate(): Promise<RuntimeUpdateInfo | null> {
  if (!isTauriRuntime()) return null;
  return await invoke<RuntimeUpdateInfo>("download_runtime_update");
}

export async function getRuntimeInstalledState(): Promise<InstalledState | null> {
  if (!isTauriRuntime()) return null;
  try {
    return await invoke<InstalledState>("get_runtime_installed_state");
  } catch (error) {
    console.warn("获取运行时安装状态失败", error);
    return null;
  }
}

export function onRuntimeUpdateProgress(
  callback: (progress: DownloadProgress) => void
): Promise<UnlistenFn> {
  return listen<DownloadProgress>("runtime-update-progress", (event) => {
    callback(event.payload);
  });
}

export function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let value = bytes;
  let index = 0;
  while (value >= 1024 && index < units.length - 1) {
    value /= 1024;
    index += 1;
  }
  return `${value.toFixed(value >= 100 || index === 0 ? 0 : 1)} ${units[index]}`;
}

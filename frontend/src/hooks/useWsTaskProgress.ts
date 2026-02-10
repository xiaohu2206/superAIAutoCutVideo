import { useEffect } from "react";
import type { WebSocketMessage } from "../services/clients";
import { wsClient } from "../services/clients";

export type WsProgressLog = {
  timestamp: string;
  message: string;
  phase?: string;
  type?: string;
};

export interface UseWsTaskProgressOptions {
  scope: string;
  projectId?: string;
  taskId?: string | null;
  onProgress?: (progress: number) => void;
  onLog?: (log: WsProgressLog) => void;
  onCompleted?: (message: WebSocketMessage) => void;
  onCancelled?: (message: WebSocketMessage) => void;
  onError?: (message: WebSocketMessage) => void;
}

const clampPercent = (v: number) => Math.max(0, Math.min(100, v));

export function useWsTaskProgress(options: UseWsTaskProgressOptions) {
  const scope = options.scope;
  const projectId = options.projectId;
  const taskId = options.taskId ?? null;
  const onProgress = options.onProgress;
  const onLog = options.onLog;
  const onCompleted = options.onCompleted;
  const onCancelled = options.onCancelled;
  const onError = options.onError;

  useEffect(() => {
    if (!projectId) return;

    const handler = (message: WebSocketMessage) => {
      if (
        !message ||
        (message.type !== "progress" && message.type !== "completed" && message.type !== "error" && message.type !== "cancelled")
      ) {
        return;
      }

      const msgScope = (message as any).scope as string | undefined;
      const msgProjectId = (message as any).project_id as string | undefined;
      if (msgScope !== scope || msgProjectId !== projectId) return;

      const msgTaskId = (message as any).task_id as string | undefined;
      if (taskId && msgTaskId && msgTaskId !== taskId) return;

      if (typeof message.progress === "number") {
        onProgress?.(clampPercent(message.progress));
      }

      const msgText = message.message || "";
      onLog?.({
        timestamp: message.timestamp,
        message: msgText,
        phase: (message as any).phase,
        type: message.type,
      });

      if (message.type === "completed") {
        onCompleted?.(message);
      }
      if (message.type === "cancelled") {
        onCancelled?.(message);
      }
      if (message.type === "error") {
        onError?.(message);
      }
    };

    wsClient.on("*", handler);
    return () => {
      wsClient.off("*", handler);
    };
  }, [
    projectId,
    scope,
    taskId,
    onProgress,
    onLog,
    onCompleted,
    onCancelled,
    onError,
  ]);
}

import { useEffect, useRef } from "react";
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
  const onProgressRef = useRef<UseWsTaskProgressOptions["onProgress"]>(undefined);
  const onLogRef = useRef<UseWsTaskProgressOptions["onLog"]>(undefined);
  const onCompletedRef = useRef<UseWsTaskProgressOptions["onCompleted"]>(undefined);
  const onCancelledRef = useRef<UseWsTaskProgressOptions["onCancelled"]>(undefined);
  const onErrorRef = useRef<UseWsTaskProgressOptions["onError"]>(undefined);
  const maxProgressRef = useRef<number>(0);
  const doneRef = useRef<boolean>(false);

  onProgressRef.current = options.onProgress;
  onLogRef.current = options.onLog;
  onCompletedRef.current = options.onCompleted;
  onCancelledRef.current = options.onCancelled;
  onErrorRef.current = options.onError;

  useEffect(() => {
    if (!projectId) return;
    maxProgressRef.current = 0;
    doneRef.current = false;

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
      if (taskId) {
        if (!msgTaskId) return;
        if (msgTaskId !== taskId) return;
      }

      if (doneRef.current && message.type === "progress") return;

      if (typeof message.progress === "number") {
        const next = clampPercent(message.progress);
        if (next >= maxProgressRef.current) {
          maxProgressRef.current = next;
          onProgressRef.current?.(next);
        }
      }

      const msgText = message.message || "";
      onLogRef.current?.({
        timestamp: message.timestamp,
        message: msgText,
        phase: (message as any).phase,
        type: message.type,
      });

      if (message.type === "completed") {
        doneRef.current = true;
        maxProgressRef.current = 100;
        onProgressRef.current?.(100);
        onCompletedRef.current?.(message);
      }
      if (message.type === "cancelled") {
        doneRef.current = true;
        onCancelledRef.current?.(message);
      }
      if (message.type === "error") {
        doneRef.current = true;
        onErrorRef.current?.(message);
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
  ]);
}

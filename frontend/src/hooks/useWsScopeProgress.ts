import { useEffect } from "react";
import type { WebSocketMessage } from "../services/clients";
import { wsClient } from "../services/clients";

export type WsScopeProgressLog = {
  timestamp: string;
  message: string;
  phase?: string;
  type?: string;
};

export interface UseWsScopeProgressOptions {
  scope: string;
  match?: (message: WebSocketMessage) => boolean;
  onMessage?: (message: WebSocketMessage) => void;
  onProgress?: (progress: number) => void;
  onLog?: (log: WsScopeProgressLog) => void;
  onCompleted?: (message: WebSocketMessage) => void;
  onError?: (message: WebSocketMessage) => void;
}

const clampPercent = (v: number) => Math.max(0, Math.min(100, v));

export function useWsScopeProgress(options: UseWsScopeProgressOptions) {
  const scope = options.scope;
  const match = options.match;
  const onMessage = options.onMessage;
  const onProgress = options.onProgress;
  const onLog = options.onLog;
  const onCompleted = options.onCompleted;
  const onError = options.onError;

  useEffect(() => {
    const handler = (message: WebSocketMessage) => {
      if (
        !message ||
        (message.type !== "progress" &&
          message.type !== "completed" &&
          message.type !== "error" &&
          message.type !== "cancelled")
      ) {
        return;
      }
      const msgScope = (message as any).scope as string | undefined;
      if (msgScope !== scope) return;
      if (match && !match(message)) return;

      onMessage?.(message);

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

      if (message.type === "completed") onCompleted?.(message);
      if (message.type === "error") onError?.(message);
    };

    wsClient.on("*", handler);
    return () => wsClient.off("*", handler);
  }, [scope, match, onMessage, onProgress, onLog, onCompleted, onError]);
}

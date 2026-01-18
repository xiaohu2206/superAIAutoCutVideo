import { useEffect, useRef } from "react";
import { listen } from "@tauri-apps/api/event";

export interface UseTauriFileDropOptions {
  onHovered?: () => void;
  onCancelled?: () => void;
  onDropped?: (paths: string[]) => void | Promise<void>;
  preventWindowDrop?: boolean;
}

export function useTauriFileDrop(options?: UseTauriFileDropOptions) {
  const preventWindowDrop = options?.preventWindowDrop ?? true;
  const isTauri = typeof (window as any).__TAURI_IPC__ === "function";
  const hoveredRef = useRef(options?.onHovered);
  const cancelledRef = useRef(options?.onCancelled);
  const droppedRef = useRef(options?.onDropped);

  useEffect(() => {
    hoveredRef.current = options?.onHovered;
    cancelledRef.current = options?.onCancelled;
    droppedRef.current = options?.onDropped;
  }, [options?.onCancelled, options?.onDropped, options?.onHovered]);

  useEffect(() => {
    const onGlobalDragOver = (ev: DragEvent) => {
      ev.preventDefault();
      try {
        if (ev.dataTransfer) {
          ev.dataTransfer.dropEffect = "copy";
        }
      } catch {
        void 0;
      }
    };

    const onGlobalDrop = (ev: DragEvent) => {
      if (preventWindowDrop) {
        ev.preventDefault();
      }
    };

    window.addEventListener("dragover", onGlobalDragOver);
    window.addEventListener("drop", onGlobalDrop);

    let unlistenDrop: (() => void) | undefined;
    let unlistenHover: (() => void) | undefined;
    let unlistenCancel: (() => void) | undefined;

    const setup = async () => {
      try {
        if (!isTauri) {
          return;
        }
        unlistenHover = await listen<string[]>("tauri://file-drop-hovered", () => {
          hoveredRef.current?.();
        });
        unlistenCancel = await listen<string[]>("tauri://file-drop-cancelled", () => {
          cancelledRef.current?.();
        });
        unlistenDrop = await listen<string[]>("tauri://file-drop", async (event) => {
          const payload = Array.isArray(event.payload) ? (event.payload as string[]) : [];
          await droppedRef.current?.(payload);
        });
      } catch (e) {
        console.error(e);
      }
    };

    setup();

    return () => {
      window.removeEventListener("dragover", onGlobalDragOver);
      window.removeEventListener("drop", onGlobalDrop);
      try {
        unlistenDrop?.();
        unlistenHover?.();
        unlistenCancel?.();
      } catch (e) {
        console.error(e);
      }
    };
  }, [preventWindowDrop, isTauri]);
}

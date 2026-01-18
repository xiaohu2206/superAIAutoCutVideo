import { useCallback, useEffect, useState, type Dispatch, type DragEvent, type SetStateAction } from "react";

export interface UseVideoOrderDragOptions {
  projectVideoPaths?: string[] | null;
  reorderVideos: (videoPaths: string[]) => Promise<void>;
  showSuccess: (text: string, durationSec?: number) => void;
  showError: (err: unknown, fallback: string) => void | Promise<void>;
}

export interface UseVideoOrderDragReturn {
  videoOrder: string[];
  dragIndex: number | null;
  setVideoOrder: Dispatch<SetStateAction<string[]>>;
  handleItemDragStart: (index: number) => void;
  handleItemDragOver: (e: DragEvent<HTMLDivElement>, overIndex: number) => void;
  handleItemDrop: (e: DragEvent<HTMLDivElement>) => Promise<void>;
}

export function useVideoOrderDrag(options: UseVideoOrderDragOptions): UseVideoOrderDragReturn {
  const [videoOrder, setVideoOrder] = useState<string[]>([]);
  const [dragIndex, setDragIndex] = useState<number | null>(null);

  useEffect(() => {
    if (Array.isArray(options.projectVideoPaths)) {
      setVideoOrder(options.projectVideoPaths);
    } else {
      setVideoOrder([]);
    }
  }, [options.projectVideoPaths]);

  const handleItemDragStart = useCallback((index: number) => {
    setDragIndex(index);
  }, []);

  const handleItemDragOver = useCallback(
    (e: DragEvent<HTMLDivElement>, overIndex: number) => {
      e.preventDefault();
      try {
        if (e.dataTransfer) {
          e.dataTransfer.dropEffect = "move";
        }
      } catch {
        void 0;
      }
      e.stopPropagation();
      if (dragIndex === null || dragIndex === overIndex) return;
      setVideoOrder((prev) => {
        const next = [...prev];
        const [moved] = next.splice(dragIndex, 1);
        next.splice(overIndex, 0, moved);
        return next;
      });
      setDragIndex(overIndex);
    },
    [dragIndex]
  );

  const handleItemDrop = useCallback(
    async (e: DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      e.stopPropagation();
      setDragIndex(null);
      try {
        if (Array.isArray(options.projectVideoPaths)) {
          const before = options.projectVideoPaths.join("|");
          const after = videoOrder.join("|");
          if (before !== after) {
            await options.reorderVideos(videoOrder);
            options.showSuccess("排序已保存！", 2000);
          }
        }
      } catch (err) {
        await options.showError(err, "保存排序失败");
      }
    },
    [options, videoOrder]
  );

  return {
    videoOrder,
    dragIndex,
    setVideoOrder,
    handleItemDragStart,
    handleItemDragOver,
    handleItemDrop,
  };
}

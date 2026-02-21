import React, { useRef, useEffect } from "react";
import { X } from "lucide-react";

interface ScenePlayModalProps {
  isOpen: boolean;
  onClose: () => void;
  videoUrl: string;
  startTime: number;
  endTime: number;
}

const ScenePlayModal: React.FC<ScenePlayModalProps> = ({
  isOpen,
  onClose,
  videoUrl,
  startTime,
  endTime,
}) => {
  const videoRef = useRef<HTMLVideoElement>(null);

  const normalizeTime = (value: number) => {
    if (!Number.isFinite(value)) return 0;
    return Math.max(0, value);
  };

  const ensureMetadata = (video: HTMLVideoElement) =>
    new Promise<void>((resolve) => {
      if (video.readyState >= 1) {
        resolve();
        return;
      }
      const handleLoadedMetadata = () => {
        video.removeEventListener("loadedmetadata", handleLoadedMetadata);
        resolve();
      };
      video.addEventListener("loadedmetadata", handleLoadedMetadata, { once: true });
    });

  const seekToTime = (video: HTMLVideoElement, targetTime: number) =>
    new Promise<void>((resolve) => {
      const safeTarget = normalizeTime(targetTime);
      if (Math.abs(video.currentTime - safeTarget) < 0.01) {
        resolve();
        return;
      }
      const handleSeeked = () => {
        video.removeEventListener("seeked", handleSeeked);
        resolve();
      };
      video.addEventListener("seeked", handleSeeked, { once: true });
      video.currentTime = safeTarget;
    });

  const startSegmentPlayback = async (video: HTMLVideoElement, segmentStart: number) => {
    await ensureMetadata(video);
    await seekToTime(video, segmentStart);
    await video.play().catch(() => {});
  };

  const attachSegmentLoop = (
    video: HTMLVideoElement,
    segmentStart: number,
    segmentEnd: number,
  ) => {
    const safeStart = normalizeTime(segmentStart);
    const safeEnd = normalizeTime(segmentEnd);

    const epsilon = 0.05;
    let finished = false;

    const handleTimeUpdate = () => {
      if (!finished && video.currentTime >= Math.max(safeStart, safeEnd - epsilon)) {
        finished = true;
        const d = Number.isFinite(video.duration) ? video.duration : undefined;
        if (typeof d === "number" && d > 0) {
          const clamp = Math.min(safeEnd, Math.max(0, d - 0.001));
          video.currentTime = clamp;
        } else {
          video.currentTime = safeEnd;
        }
        video.pause();
        video.removeEventListener("timeupdate", handleTimeUpdate);
        video.removeEventListener("play", handlePlayGuard);
      }
    };

    const handlePlayGuard = () => {
      if (video.currentTime + epsilon < safeStart) {
        const d = Number.isFinite(video.duration) ? video.duration : undefined;
        if (typeof d === "number" && d > 0) {
          const clamp = Math.min(safeStart, Math.max(0, d - 0.001));
          video.currentTime = clamp;
        } else {
          video.currentTime = safeStart;
        }
      }
    };

    void startSegmentPlayback(video, safeStart);
    video.addEventListener("timeupdate", handleTimeUpdate);
    video.addEventListener("play", handlePlayGuard);

    return () => {
      video.removeEventListener("timeupdate", handleTimeUpdate);
      video.removeEventListener("play", handlePlayGuard);
      video.pause();
    };
  };

  useEffect(() => {
    if (isOpen && videoRef.current) {
      const video = videoRef.current;
      return attachSegmentLoop(video, startTime, endTime);
    }
    return undefined;
  }, [isOpen, videoUrl, startTime, endTime]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-75" onClick={onClose}>
      <div className="relative bg-black rounded-lg overflow-hidden max-w-4xl w-full mx-4 shadow-2xl" onClick={e => e.stopPropagation()}>
        <button
          onClick={onClose}
          className="absolute top-4 right-4 text-white hover:text-gray-300 z-10 bg-black bg-opacity-50 rounded-full p-1"
        >
          <X className="w-6 h-6" />
        </button>
        <div className="aspect-video w-full bg-black flex items-center justify-center">
            <video
                ref={videoRef}
                src={videoUrl}
                controls
                className="w-full h-full object-contain"
            />
        </div>
        <div className="p-4 bg-gray-900 text-white flex justify-between items-center">
            <span className="font-mono text-sm">
                {startTime.toFixed(2)}s - {endTime.toFixed(2)}s
            </span>
            <span className="text-xs text-gray-400">片段预览</span>
        </div>
      </div>
    </div>
  );
};

export default ScenePlayModal;

import React, { useMemo } from "react";
import { Loader, Pause, Play } from "lucide-react";
import { TrimTimeline, type TrimRange } from "./TrimTimeline";
import { formatMs } from "../../utils/timecode";

export type TrimPlayerPanelProps = {
  videoRef: React.RefObject<HTMLVideoElement>;
  srcUrl: string;
  durationMs: number;
  currentMs: number;
  ranges: TrimRange[];
  activeRangeId: string | null;
  isPlaying: boolean;
  isVideoLoading: boolean;
  loopRange: boolean;
  disabled?: boolean;
  onLoadedMetadata: () => void;
  onLoadStart: () => void;
  onLoadedData: () => void;
  onCanPlay: () => void;
  onWaiting: () => void;
  onStalled: () => void;
  onPlaying: () => void;
  onEnded: () => void;
  onError: () => void;
  onTimeUpdate: () => void;
  onPlay: () => void;
  onPause: () => void;
  onSeek: (ms: number) => void;
  onTogglePlay: () => void;
  onRangesChange: (next: TrimRange[]) => void;
  onActiveRangeChange: (id: string | null) => void;
  onLoopRangeChange: (next: boolean) => void;
};

export const TrimPlayerPanel: React.FC<TrimPlayerPanelProps> = ({
  videoRef,
  srcUrl,
  durationMs,
  currentMs,
  ranges,
  activeRangeId,
  isPlaying,
  isVideoLoading,
  loopRange,
  disabled,
  onLoadedMetadata,
  onLoadStart,
  onLoadedData,
  onCanPlay,
  onWaiting,
  onStalled,
  onPlaying,
  onEnded,
  onError,
  onTimeUpdate,
  onPlay,
  onPause,
  onSeek,
  onTogglePlay,
  onRangesChange,
  onActiveRangeChange,
  onLoopRangeChange,
}) => {
  const timeText = useMemo(() => {
    return `${formatMs(currentMs)} / ${formatMs(durationMs)}`;
  }, [currentMs, durationMs]);

  return (
    <div className="lg:col-span-2 space-y-3">
      <div className="bg-black rounded-lg overflow-hidden aspect-video relative">
        <video
          ref={videoRef}
          src={srcUrl}
          className="w-full h-full"
          controls={false}
          preload="metadata"
          onLoadedMetadata={onLoadedMetadata}
          onLoadStart={onLoadStart}
          onLoadedData={onLoadedData}
          onCanPlay={onCanPlay}
          onWaiting={onWaiting}
          onStalled={onStalled}
          onPlaying={onPlaying}
          onEnded={onEnded}
          onError={onError}
          onTimeUpdate={onTimeUpdate}
          onPlay={onPlay}
          onPause={onPause}
        />
        {isVideoLoading && (
          <div className="absolute inset-0 bg-black/60 flex items-center justify-center">
            <div className="flex items-center gap-2 text-white text-sm">
              <Loader className="h-4 w-4 animate-spin" />
              视频加载中
            </div>
          </div>
        )}
      </div>

      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={onTogglePlay}
            disabled={durationMs <= 0 || isVideoLoading}
            className="inline-flex items-center gap-2 px-3 py-2 rounded-lg bg-gray-900 text-white hover:bg-gray-800 disabled:opacity-50"
          >
            {isPlaying ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
            <span className="text-sm">{isPlaying ? "暂停" : "播放"}</span>
          </button>
          <label className="inline-flex items-center gap-2 text-sm text-gray-700">
            <input
              type="checkbox"
              className="accent-violet-600"
              checked={loopRange}
              onChange={(e) => onLoopRangeChange(e.target.checked)}
              disabled={!activeRangeId}
            />
            循环当前段
          </label>
        </div>
        <div className="text-xs text-gray-600 font-mono">{timeText}</div>
      </div>

      <TrimTimeline
        durationMs={durationMs}
        currentMs={currentMs}
        ranges={ranges}
        activeRangeId={activeRangeId}
        disabled={Boolean(disabled) || durationMs <= 0}
        onSeek={onSeek}
        onRangesChange={onRangesChange}
        onActiveRangeChange={onActiveRangeChange}
      />
    </div>
  );
};

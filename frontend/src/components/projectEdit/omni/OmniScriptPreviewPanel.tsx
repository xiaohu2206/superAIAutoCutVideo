import { Play, SkipBack, SkipForward, Square, Volume2 } from "lucide-react";
import React from "react";
import type { ScriptSegment } from "../../../types/project";
import SegmentDurationControl from "./SegmentDurationControl";
import {
  durationLabel,
  isOriginalAudio,
  isValidSegmentTts,
  PLAYBACK_RATES,
  ttsStatusLabel,
} from "./omniScriptWorkspaceUtils";

export interface OmniScriptPreviewPanelProps {
  videoRef: React.Ref<HTMLVideoElement>;
  ttsAudioRef: React.Ref<HTMLAudioElement>;
  videoUrl: string;
  selectedSegment: ScriptSegment | undefined;
  selectedIndex: number;
  segmentsCount: number;
  selectedTextHash?: string;
  isSequencePlaying: boolean;
  playbackRate: number;
  onPlaybackRateChange: (rate: number) => void;
  onPlayAdjacent: (direction: -1 | 1) => void;
  onToggleSequencePlayback: () => void;
  onPlaySegmentTts?: () => void;
  videoDuration?: number;
  onRangeChange?: (range: { start_time: number; end_time: number }) => void;
}

const OmniScriptPreviewPanel: React.FC<OmniScriptPreviewPanelProps> = ({
  videoRef,
  ttsAudioRef,
  videoUrl,
  selectedSegment,
  selectedIndex,
  segmentsCount,
  selectedTextHash,
  isSequencePlaying,
  playbackRate,
  onPlaybackRateChange,
  onPlayAdjacent,
  onToggleSequencePlayback,
  onPlaySegmentTts,
  videoDuration,
  onRangeChange,
}) => {
  const canPlayTts =
    selectedSegment &&
    !isOriginalAudio(selectedSegment) &&
    isValidSegmentTts(selectedSegment, selectedTextHash);
  const playbackUsesTts = Boolean(
    selectedSegment && !isOriginalAudio(selectedSegment) && canPlayTts
  );

  return (
  <aside className="space-y-4">
    <audio ref={ttsAudioRef} className="hidden" preload="auto" />
    <div className="aspect-video bg-black rounded-lg overflow-hidden">
      {videoUrl ? (
        <video ref={videoRef} src={videoUrl} controls className="w-full h-full object-contain" />
      ) : (
        <div className="h-full flex items-center justify-center text-sm text-gray-300">暂无可预览视频</div>
      )}
    </div>
    {selectedSegment ? (
      <div className="rounded-lg bg-gray-900/95 px-4 py-3 min-h-[56px] flex items-center justify-center text-center">
        {selectedSegment.text ? (
          <p className="text-base text-white leading-relaxed whitespace-pre-wrap break-words">
            {selectedSegment.text}
          </p>
        ) : (
          <span className="text-sm text-gray-400">
            {isOriginalAudio(selectedSegment) ? "原片播放段，无解说文案" : "暂无解说文案"}
          </span>
        )}
      </div>
    ) : null}
    {selectedSegment ? (
      <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-4 space-y-3">
        <div className="flex items-center justify-between text-sm">
          <span className="font-medium text-gray-900 dark:text-gray-100">第 {selectedIndex + 1} 条片段</span>
          <div className="flex items-center gap-3">
            {canPlayTts && onPlaySegmentTts ? (
              <button
                type="button"
                onClick={onPlaySegmentTts}
                title="播放配音"
                className="inline-flex items-center gap-1 text-xs text-gray-500 dark:text-gray-400 hover:text-violet-600 dark:hover:text-violet-300 transition-colors"
              >
                <Volume2 className="h-3.5 w-3.5" />
                配音
              </button>
            ) : null}
            <span className="font-mono text-xs text-gray-500 dark:text-gray-400">
              {durationLabel(selectedSegment.start_time, selectedSegment.end_time)}
            </span>
          </div>
        </div>
        <div className="space-y-2 pt-1">
          
          <div className="flex items-center gap-2 min-w-0">
            <div className="flex flex-1 items-center justify-center gap-1 min-w-0 shrink">
              <button
                type="button"
                onClick={() => onPlayAdjacent(-1)}
                disabled={!videoUrl || !segmentsCount || selectedIndex <= 0}
                title="播放上一个镜头"
                className="inline-flex shrink-0 items-center justify-center p-2 rounded-lg border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              >
                <SkipBack className="h-4 w-4" />
              </button>
              <button
                type="button"
                onClick={onToggleSequencePlayback}
                disabled={!videoUrl || !segmentsCount}
                className={`inline-flex shrink-0 items-center justify-center min-w-[7.25rem] px-3 py-2 rounded-lg text-sm transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${
                  isSequencePlaying
                    ? "bg-red-600 text-white hover:bg-red-700"
                    : "bg-blue-600 text-white hover:bg-blue-700"
                }`}
              >
                {isSequencePlaying ? (
                  <Square className="h-4 w-4 mr-2 fill-current" />
                ) : (
                  <Play className="h-4 w-4 mr-2" />
                )}
                {isSequencePlaying ? "停止连播" : "镜头连播"}
              </button>
              <button
                type="button"
                onClick={() => onPlayAdjacent(1)}
                disabled={!videoUrl || !segmentsCount || selectedIndex >= segmentsCount - 1}
                title="播放下一个镜头"
                className="inline-flex shrink-0 items-center justify-center p-2 rounded-lg border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              >
                <SkipForward className="h-4 w-4" />
              </button>
            </div>
            <label className="inline-flex shrink-0 items-center gap-1.5 text-sm text-gray-700 dark:text-gray-300 whitespace-nowrap">
              倍速
              <select
                value={playbackRate}
                onChange={(e) => onPlaybackRateChange(Number(e.target.value) || 1)}
                className="border border-gray-300 dark:border-gray-600 rounded-lg px-2 py-1.5 text-sm text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-800 focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none"
              >
                {PLAYBACK_RATES.map((rate) => (
                  <option key={rate} value={rate}>
                    {rate}x
                  </option>
                ))}
              </select>
            </label>
          </div>
        </div>
        {onRangeChange ? (
          <SegmentDurationControl
            startTime={selectedSegment.start_time}
            endTime={selectedSegment.end_time}
            videoDuration={videoDuration}
            playbackUsesTts={playbackUsesTts}
            onRangeChange={onRangeChange}
          />
        ) : null}
        
      </div>
    ) : null}
  </aside>
  );
};

export default OmniScriptPreviewPanel;

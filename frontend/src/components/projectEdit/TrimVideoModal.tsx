import React, { useRef } from "react";
import { createPortal } from "react-dom";
import { Check, Loader, Scissors, X } from "lucide-react";
import { useTrimVideoModal } from "../../hooks/useTrimVideoModal";
import { TrimPlayerPanel } from "./TrimPlayerPanel";
import { TrimRangesPanel } from "./TrimRangesPanel";

export type TrimVideoModalProps = {
  isOpen: boolean;
  projectId: string;
  videoPath: string;
  videoLabel?: string;
  onClose: () => void;
};

export const TrimVideoModal: React.FC<TrimVideoModalProps> = ({ isOpen, projectId, videoPath, videoLabel, onClose }) => {
  const videoRef = useRef<HTMLVideoElement>(null);
  const vm = useTrimVideoModal({
    isOpen,
    projectId,
    videoPath,
    onClose,
    getVideoEl: () => videoRef.current,
  });

  if (!isOpen) return null;

  return createPortal(
    <div className="fixed inset-0 z-50 overflow-y-auto">
      <div className="fixed inset-0 bg-black/60 backdrop-blur-sm" onClick={vm.close} />
      <div className="flex items-center justify-center min-h-screen p-4">
        <div className="relative bg-white rounded-xl shadow-2xl w-full max-w-5xl">
          <div className="flex items-center justify-between px-6 py-3 border-b border-gray-100">
            <div className="flex items-center gap-3">
              <div className="p-1.5 bg-violet-50 rounded-lg">
                <Scissors className="h-5 w-5 text-violet-600" />
              </div>
              <div>
                <h3 className="text-base font-bold text-gray-900">逐段修剪</h3>
                <p className="text-xs text-gray-500">{videoLabel || videoPath.split("/").pop()}</p>
              </div>
            </div>
            <button
              onClick={vm.close}
              disabled={vm.submitting}
              className="p-1 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-full transition-colors disabled:opacity-50"
            >
              <X className="h-5 w-5" />
            </button>
          </div>

          <div className="p-5 space-y-4">
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
              <TrimPlayerPanel
                videoRef={videoRef}
                srcUrl={vm.srcUrl}
                durationMs={vm.durationMs}
                currentMs={vm.currentMs}
                ranges={vm.ranges}
                activeRangeId={vm.activeRangeId}
                isPlaying={vm.isPlaying}
                isVideoLoading={vm.isVideoLoading}
                loopRange={vm.loopRange}
                disabled={vm.submitting}
                onLoadedMetadata={vm.onLoadedMetadata}
                onLoadStart={vm.onLoadStart}
                onLoadedData={vm.onLoadedData}
                onCanPlay={vm.onCanPlay}
                onWaiting={vm.onWaiting}
                onStalled={vm.onStalled}
                onPlaying={vm.onPlaying}
                onEnded={vm.onEnded}
                onError={vm.onError}
                onTimeUpdate={vm.onTimeUpdate}
                onPlay={vm.onPlay}
                onPause={vm.onPause}
                onSeeking={vm.onSeeking}
                onSeeked={vm.onSeeked}
                onSeek={vm.seekTo}
                onTogglePlay={vm.togglePlay}
                onRangesChange={vm.setRanges}
                onActiveRangeChange={(id) => {
                  vm.setActiveRangeId(id);
                  const r = vm.ranges.find((x) => x.id === id);
                  if (r) vm.seekTo(r.startMs);
                }}
                onLoopRangeChange={vm.setLoopRange}
              />

              <TrimRangesPanel
                mode={vm.mode}
                durationMs={vm.durationMs}
                ranges={vm.ranges}
                activeRangeId={vm.activeRangeId}
                submitting={vm.submitting}
                progress={vm.progress}
                statusText={vm.statusText}
                errorText={vm.errorText}
                onSwitchMode={vm.switchMode}
                onAddRange={vm.addRangeFromCurrent}
                onActiveRangeChange={(id) => {
                  vm.setActiveRangeId(id);
                  const r = vm.ranges.find((x) => x.id === id);
                  if (r) vm.seekTo(r.startMs);
                }}
                onSeek={vm.seekTo}
                onRangesChange={vm.setRanges}
              />
            </div>
          </div>

          <div className="px-6 py-4 border-t border-gray-100 flex items-center justify-between">
            <div className="text-xs text-gray-500">确认后会不可逆替换原视频文件</div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={vm.close}
                disabled={vm.submitting}
                className="px-4 py-2 rounded-lg border border-gray-200 text-gray-700 hover:bg-gray-50 disabled:opacity-50"
              >
                取消
              </button>
              <button
                type="button"
                onClick={vm.confirm}
                disabled={!vm.canSubmit}
                className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-violet-600 text-white hover:bg-violet-700 disabled:opacity-50"
              >
                {vm.submitting ? <Loader className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
                确认修剪
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>,
    document.body
  );
};

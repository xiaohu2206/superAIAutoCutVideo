import { Minus, Plus } from "lucide-react";
import React from "react";
import {
  clampSegmentTimes,
  DURATION_ADJUST_STEPS,
  DURATION_SLIDER_STEP,
  durationLabel,
  getEndTimeBounds,
  getStartTimeBounds,
  roundSegmentTime,
  secondsToTime,
} from "./omniScriptWorkspaceUtils";

export interface SegmentTimeRange {
  start_time: number;
  end_time: number;
}

export interface SegmentDurationControlProps {
  startTime: number;
  endTime: number;
  videoDuration?: number;
  playbackUsesTts?: boolean;
  onRangeChange: (range: SegmentTimeRange) => void;
}

const formatStepAbs = (step: number) => {
  const abs = Math.abs(step);
  return Number.isInteger(abs) ? String(abs) : abs.toFixed(1);
};

interface TimePointRowProps {
  label: string;
  value: number;
  min: number;
  max: number;
  onChange: (next: number) => void;
}

const TimePointRow: React.FC<TimePointRowProps> = ({ label, value, min, max, onChange }) => {
  const clamped = Math.min(max, Math.max(min, roundSegmentTime(value)));
  const negativeSteps = DURATION_ADJUST_STEPS.filter((s) => s < 0);
  const positiveSteps = DURATION_ADJUST_STEPS.filter((s) => s > 0);

  const apply = (next: number) => {
    onChange(Math.min(max, Math.max(min, roundSegmentTime(next))));
  };

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-medium text-gray-700 dark:text-gray-300">{label}</span>
        <span className="font-mono text-xs tabular-nums text-gray-600 dark:text-gray-400">{secondsToTime(clamped)}</span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={DURATION_SLIDER_STEP}
        value={clamped}
        onChange={(e) => apply(parseFloat(e.target.value))}
        className="w-full h-2 accent-blue-600 cursor-pointer"
        aria-label={`${label}滑块`}
      />
      <div className="flex flex-wrap items-center justify-between gap-1">
        <div className="flex flex-wrap items-center gap-1">
          {negativeSteps.map((step) => (
            <button
              key={step}
              type="button"
              onClick={() => apply(clamped + step)}
              disabled={clamped + step < min - 1e-6}
              title={`${label} 提前 ${Math.abs(step)} 秒`}
              className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[11px] border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-800 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <Minus className="h-2.5 w-2.5" />
              {formatStepAbs(step)}s
            </button>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-1">
          {positiveSteps.map((step) => (
            <button
              key={step}
              type="button"
              onClick={() => apply(clamped + step)}
              disabled={clamped + step > max + 1e-6}
              title={`${label} 延后 ${step} 秒`}
              className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[11px] border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-800 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <Plus className="h-2.5 w-2.5" />
              {formatStepAbs(step)}s
            </button>
          ))}
        </div>
      </div>
    </div>
  );
};

const SegmentDurationControl: React.FC<SegmentDurationControlProps> = ({
  startTime,
  endTime,
  videoDuration,
  playbackUsesTts,
  onRangeChange,
}) => {
  const startBounds = getStartTimeBounds(endTime, videoDuration);
  const endBounds = getEndTimeBounds(startTime, videoDuration);

  const emit = (start: number, end: number) => {
    onRangeChange(clampSegmentTimes(start, end, videoDuration));
  };

  return (
    <div className="space-y-3 pt-1 border-t border-gray-100 dark:border-gray-700/80">
      <div className="flex items-center justify-between gap-2">
        <span className="text-sm font-medium text-gray-900 dark:text-gray-100">时间段</span>
        <span className="font-mono text-sm tabular-nums text-blue-600 dark:text-blue-400">
          时长 {durationLabel(startTime, endTime)}
        </span>
      </div>
      <TimePointRow
        label="镜头开始"
        value={startTime}
        min={startBounds.min}
        max={startBounds.max}
        onChange={(start) => emit(start, endTime)}
      />
      <TimePointRow
        label="镜头结束"
        value={endTime}
        min={endBounds.min}
        max={endBounds.max}
        onChange={(end) => emit(startTime, end)}
      />
      {playbackUsesTts ? (
        <p className="text-[11px] text-amber-600 dark:text-amber-400 leading-snug">
          预览播放以配音时长为准；入点/出点仍写入脚本，供导出与无配音场景使用。
        </p>
      ) : (
        <p className="text-[11px] text-gray-500 dark:text-gray-400 leading-snug">
          拖动滑块或点按步进按钮调整入点与出点，修改后自动保存。
        </p>
      )}
    </div>
  );
};

export default SegmentDurationControl;

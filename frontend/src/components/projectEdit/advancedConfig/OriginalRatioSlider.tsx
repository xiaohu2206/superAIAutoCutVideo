import React from "react";
import type { InterleaveMode } from "../../../types/project";
import { DEFAULT_ORIGINAL_RATIO, ORIGINAL_RATIO_MIN, ORIGINAL_RATIO_MAX } from "./utils";
import { useThemeMode } from "../../../hooks/useThemeMode";

interface Props {
  interleaveMode: InterleaveMode;
  interleaveModeLoading: boolean;
  interleaveModeSaving: boolean;
  setInterleaveModeAndPersist: (value: InterleaveMode) => Promise<void>;
  originalRatio: number | null;
  loading: boolean;
  saving: boolean;
  setOriginalRatioAndPersist: (value: number | null) => Promise<void>;
}

const OriginalRatioSlider: React.FC<Props> = ({
  interleaveMode,
  interleaveModeLoading,
  interleaveModeSaving,
  setInterleaveModeAndPersist,
  originalRatio,
  loading,
  saving,
  setOriginalRatioAndPersist,
}) => {
  const isDark = useThemeMode() === "dark";
  const isAuto = originalRatio === null || originalRatio === undefined;
  const displayedRatio = originalRatio ?? DEFAULT_ORIGINAL_RATIO;
  const isSmart = interleaveMode === "smart_interleave";
  const selectedButtonClass = isDark
    ? "bg-violet-500/10 text-violet-300"
    : "bg-violet-50 text-violet-700";
  const idleButtonClass = isDark
    ? "bg-[#242424] text-zinc-300 hover:bg-[#2d2d2d]"
    : "bg-white text-gray-700 hover:bg-gray-50";
  const groupBorderClass = isDark ? "border-[#2a2a2a]" : "border-gray-200";

  return (
    <div className="border-t border-gray-200 dark:border-gray-700 pt-4">
      <div className="flex items-center justify-between mb-2">
        <label className="block text-sm font-medium text-gray-700 dark:text-gray-200">穿插模式</label>
        {interleaveModeSaving ? (
          <span className="text-xs text-gray-500 dark:text-gray-400">保存中</span>
        ) : null}
      </div>
      <div className="flex items-center gap-2 mb-3">
        <div className={`inline-flex overflow-hidden rounded-md border ${groupBorderClass}`}>
          <button
            type="button"
            className={`px-3 py-1 text-xs ${
              isSmart ? selectedButtonClass : idleButtonClass
            }`}
            onClick={() => void setInterleaveModeAndPersist("smart_interleave")}
            disabled={interleaveModeLoading || interleaveModeSaving}
          >
            智能穿插
          </button>
          <button
            type="button"
            className={`border-l px-3 py-1 text-xs ${groupBorderClass} ${
              !isSmart ? selectedButtonClass : idleButtonClass
            }`}
            onClick={() => void setInterleaveModeAndPersist("original_interleave")}
            disabled={interleaveModeLoading || interleaveModeSaving}
          >
            原片交替穿插
          </button>
        </div>
      </div>

      {isSmart && (
        <>
          <div className="flex items-center justify-between mt-4 mb-2">
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-200">原片占比</label>
            {loading ? (
              <span className="text-xs text-gray-500 dark:text-gray-400">加载中</span>
            ) : saving ? (
              <span className="text-xs text-gray-500 dark:text-gray-400">保存中</span>
            ) : (
              <span className="text-xs text-gray-500 dark:text-gray-400">{isAuto ? "自动" : "0% - 100%"}</span>
            )}
          </div>
          <div className="flex items-center gap-3">
            <div className={`inline-flex overflow-hidden rounded-md border ${groupBorderClass}`}>
              <button
                type="button"
                className={`px-3 py-1 text-xs ${
                  isAuto ? selectedButtonClass : idleButtonClass
                }`}
                onClick={() => void setOriginalRatioAndPersist(null)}
                disabled={loading || saving}
              >
                自动
              </button>
              <button
                type="button"
                className={`border-l px-3 py-1 text-xs ${groupBorderClass} ${
                  !isAuto ? selectedButtonClass : idleButtonClass
                }`}
                onClick={() => void setOriginalRatioAndPersist(isAuto ? DEFAULT_ORIGINAL_RATIO : displayedRatio)}
                disabled={loading || saving}
              >
                自定义
              </button>
            </div>
            <input
              type="range"
              min={ORIGINAL_RATIO_MIN}
              max={ORIGINAL_RATIO_MAX}
              step={1}
              value={displayedRatio}
              onChange={(e) => void setOriginalRatioAndPersist(Number(e.target.value))}
              className="flex-1"
              disabled={isAuto || loading}
            />
            <div className="text-sm text-gray-800 dark:text-gray-200 w-28">
              {isAuto ? (
                <>
                  <div>自动</div>
                  <div className="text-gray-500 dark:text-gray-400">系统决定</div>
                </>
              ) : (
                <>
                  <div>{displayedRatio}%</div>
                  <div className="text-gray-500 dark:text-gray-400">{`解说 ${100 - displayedRatio}%`}</div>
                </>
              )}
            </div>
          </div>
          <div className="text-xs text-gray-500 dark:text-gray-400 mt-2">滑动时自动保存</div>
        </>
      )}
    </div>
  );
};

export default OriginalRatioSlider;

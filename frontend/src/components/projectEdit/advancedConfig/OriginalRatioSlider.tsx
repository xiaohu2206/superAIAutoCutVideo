import React from "react";
import { DEFAULT_ORIGINAL_RATIO, ORIGINAL_RATIO_MIN, ORIGINAL_RATIO_MAX } from "./utils";

interface Props {
  originalRatio: number | null;
  loading: boolean;
  saving: boolean;
  setOriginalRatioAndPersist: (value: number | null) => Promise<void>;
}

const OriginalRatioSlider: React.FC<Props> = ({
  originalRatio,
  loading,
  saving,
  setOriginalRatioAndPersist,
}) => {
  const isAuto = originalRatio === null || originalRatio === undefined;
  const displayedRatio = originalRatio ?? DEFAULT_ORIGINAL_RATIO;

  return (
    <div className="border-t border-gray-200 pt-4">
      <div className="flex items-center justify-between">
        <label className="block text-sm font-medium text-gray-700 mb-2">原片占比</label>
        {loading ? (
          <span className="text-xs text-gray-500">加载中</span>
        ) : saving ? (
          <span className="text-xs text-gray-500">保存中</span>
        ) : (
          <span className="text-xs text-gray-500">{isAuto ? "自动" : "0% - 100%"}</span>
        )}
      </div>
      <div className="flex items-center gap-3">
        <div className="inline-flex rounded-md border border-gray-200 overflow-hidden">
          <button
            type="button"
            className={`px-3 py-1 text-xs ${
              isAuto ? "bg-violet-50 text-violet-700" : "bg-white text-gray-700 hover:bg-gray-50"
            }`}
            onClick={() => void setOriginalRatioAndPersist(null)}
            disabled={loading || saving}
          >
            自动
          </button>
          <button
            type="button"
            className={`px-3 py-1 text-xs border-l border-gray-200 ${
              !isAuto ? "bg-violet-50 text-violet-700" : "bg-white text-gray-700 hover:bg-gray-50"
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
        <div className="text-sm text-gray-800 w-28">
          {isAuto ? (
            <>
              <div>自动</div>
              <div className="text-gray-500">系统决定</div>
            </>
          ) : (
            <>
              <div>{displayedRatio}%</div>
              <div className="text-gray-500">{`解说 ${100 - displayedRatio}%`}</div>
            </>
          )}
        </div>
      </div>
      <div className="text-xs text-gray-500 mt-2">滑动时自动保存</div>
    </div>
  );
};

export default OriginalRatioSlider;

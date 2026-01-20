import React from "react";
import { ORIGINAL_RATIO_MIN, ORIGINAL_RATIO_MAX } from "./utils";

interface Props {
  originalRatio: number;
  loading: boolean;
  saving: boolean;
  setOriginalRatioAndPersist: (value: number) => Promise<void>;
}

const OriginalRatioSlider: React.FC<Props> = ({
  originalRatio,
  loading,
  saving,
  setOriginalRatioAndPersist,
}) => {
  return (
    <div className="border-t border-gray-200 pt-4">
      <div className="flex items-center justify-between">
        <label className="block text-sm font-medium text-gray-700 mb-2">原片占比</label>
        {loading ? (
          <span className="text-xs text-gray-500">加载中</span>
        ) : saving ? (
          <span className="text-xs text-gray-500">保存中</span>
        ) : (
          <span className="text-xs text-gray-500">10% - 90%</span>
        )}
      </div>
      <div className="flex items-center gap-4">
        <input
          type="range"
          min={ORIGINAL_RATIO_MIN}
          max={ORIGINAL_RATIO_MAX}
          step={1}
          value={originalRatio}
          onChange={(e) => void setOriginalRatioAndPersist(Number(e.target.value))}
          className="flex-1"
        />
        <div className="text-sm text-gray-800 w-28">
          <div>{originalRatio}%</div>
          <div className="text-gray-500">{`解说 ${100 - originalRatio}%`}</div>
        </div>
      </div>
      <div className="text-xs text-gray-500 mt-2">滑动时自动保存</div>
    </div>
  );
};

export default OriginalRatioSlider;


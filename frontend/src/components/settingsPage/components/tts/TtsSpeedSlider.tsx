import React from "react";
import { Loader } from "lucide-react";

interface Props {
  speedRatio: number;
  onChange: (value: number) => void;
  label: string;
  savingState: "idle" | "saving" | "saved" | "failed";
}

export const TtsSpeedSlider: React.FC<Props> = ({ speedRatio, onChange, label, savingState }) => {
  return (
    <div>
      <h4 className="text-md font-semibold text-gray-900 mb-2">语速</h4>
      <div className="flex items-center gap-4">
        <input
          type="range"
          min={0.5}
          max={2.0}
          step={0.1}
          value={Number(speedRatio.toFixed(1))}
          onChange={(e) => onChange(parseFloat(e.target.value))}
          className="flex-1"
        />
        <div className="text-sm text-gray-800 w-28">
          <div>×{Number(speedRatio.toFixed(1))}</div>
          <div className="text-gray-500">{label}</div>
        </div>
      </div>
      <div className="text-xs text-gray-600 mt-2">
        {savingState === "saving" ? (
          <span className="inline-flex items-center"><Loader className="h-3 w-3 mr-1 animate-spin" /> 保存中…</span>
        ) : savingState === "saved" ? (
          <span className="text-green-600">已保存</span>
        ) : savingState === "failed" ? (
          <span className="text-red-600">保存失败，请重试</span>
        ) : (
          <span className="text-gray-500">滑动时自动保存</span>
        )}
      </div>
    </div>
  );
};

export default TtsSpeedSlider;
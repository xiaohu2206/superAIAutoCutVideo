import { Check, Plus } from "lucide-react";
import React from "react";
import type { ScriptLengthOption } from "../../../types/project";
import {
  SCRIPT_LENGTH_OPTIONS,
  parseRangeFromString,
  formatRangeTitle,
  formatRangeValue,
} from "./utils";

interface Props {
  scriptLength: ScriptLengthOption;
  loading: boolean;
  saving: boolean;
  setScriptLengthAndPersist: (value: ScriptLengthOption) => Promise<void>;
  onOpenCustomModal: () => void;
}

const ScriptLengthSelector: React.FC<Props> = ({
  scriptLength,
  loading,
  saving,
  setScriptLengthAndPersist,
  onOpenCustomModal,
}) => {
  const presetValues = SCRIPT_LENGTH_OPTIONS.map((opt) => opt.value);
  const isPresetSelected = presetValues.includes(scriptLength);
  const customSelectedRange = !isPresetSelected ? parseRangeFromString(scriptLength) : null;
  const customCardSubtitle = customSelectedRange
    ? `预计约 ${Math.max(2, Math.ceil(customSelectedRange.max / 20)) + (customSelectedRange.max > 100 ? Math.ceil((customSelectedRange.max - 100) / 20) : Math.max(0, Math.ceil(customSelectedRange.max / 20) - 5))} 次模型调用`
    : "点击设置条数";

  return (
    <div className="border-t border-gray-200 pt-4">
      <div className="flex items-center justify-between">
        <label className="block text-sm font-medium text-gray-700 mb-2">解说脚本条数</label>
        {loading ? (
          <span className="text-xs text-gray-500">加载中</span>
        ) : saving ? (
          <span className="text-xs text-gray-500">保存中</span>
        ) : (
          <span className="text-xs text-gray-500">条数越多，生成更慢且消耗更高</span>
        )}
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
        {SCRIPT_LENGTH_OPTIONS.map((opt) => {
          const isSelected = scriptLength === opt.value;
          return (
            <div
              key={opt.value}
              className={`
                relative flex flex-col justify-between p-3 rounded-lg border cursor-pointer transition-all duration-200
                ${
                  isSelected
                    ? "border-violet-600 bg-violet-50 ring-1 ring-violet-600 shadow-sm"
                    : "border-gray-200 bg-white hover:border-violet-300 hover:shadow-sm"
                }
              `}
              onClick={() => void setScriptLengthAndPersist(opt.value)}
            >
              <div className="flex items-center justify-between mb-1">
                <span className={`text-sm font-medium ${isSelected ? "text-violet-900" : "text-gray-900"}`}>
                  {opt.title}
                </span>
                {isSelected && (
                  <div className="h-4 w-4 rounded-full bg-violet-600 flex items-center justify-center">
                    <Check className="h-3 w-3 text-white" />
                  </div>
                )}
              </div>
              <span className={`text-xs ${isSelected ? "text-violet-700" : "text-gray-500"}`}>{opt.subtitle}</span>
            </div>
          );
        })}
        {customSelectedRange ? (
          <div
            className={`
                relative flex flex-col justify-between p-3 rounded-lg border cursor-pointer transition-all duration-200
                ${
                  !isPresetSelected
                    ? "border-violet-600 bg-violet-50 ring-1 ring-violet-600 shadow-sm"
                    : "border-gray-200 bg-white hover:border-violet-300 hover:shadow-sm"
                }
              `}
            onClick={() => void setScriptLengthAndPersist(formatRangeValue(customSelectedRange))}
          >
            <div className="flex items-center justify-between mb-1">
              <span className={`text-sm font-medium ${!isPresetSelected ? "text-violet-900" : "text-gray-900"}`}>
                {formatRangeTitle(customSelectedRange)}
              </span>
              {!isPresetSelected ? (
                <div className="h-4 w-4 rounded-full bg-violet-600 flex items-center justify-center">
                  <Check className="h-3 w-3 text-white" />
                </div>
              ) : null}
            </div>
            <span className={`text-xs ${!isPresetSelected ? "text-violet-700" : "text-gray-500"}`}>
              {customCardSubtitle}
            </span>
          </div>
        ) : null}
        <button
          type="button"
          onClick={onOpenCustomModal}
          className="relative flex flex-col items-center justify-center p-3 rounded-lg border border-dashed border-violet-300 text-violet-600 bg-white hover:border-violet-500 hover:bg-violet-50 transition-all duration-200"
        >
          <Plus className="h-5 w-5 mb-1" />
          <span className="text-sm font-medium">自定义条数</span>
        </button>
      </div>
    </div>
  );
};

export default ScriptLengthSelector;


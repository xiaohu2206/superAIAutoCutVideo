import { X } from "lucide-react";
import React, { useState } from "react";
import type { ScriptLengthOption } from "../../../types/project";
import {
  CUSTOM_SCRIPT_LENGTH_MIN,
  CUSTOM_SCRIPT_LENGTH_MAX,
  computeCustomRange,
  formatRangeTitle,
  estimateCallsForDisplay,
  formatRangeValue,
} from "./utils";

interface Props {
  isOpen: boolean;
  onClose: () => void;
  initialRange: { min: number; max: number } | null;
  onSave: (value: ScriptLengthOption) => Promise<void> | void;
}

const CustomScriptLengthModal: React.FC<Props> = ({ isOpen, onClose, initialRange, onSave }) => {
  const [customInput, setCustomInput] = useState<string>(() => {
    if (initialRange) {
      const avg = Math.round((initialRange.min + initialRange.max) / 2);
      return String(avg);
    }
    return "40";
  });
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  const customNumber = Number.parseInt(customInput, 10);
  const customRange = Number.isFinite(customNumber) ? computeCustomRange(customNumber) : null;
  const customRangeText = customRange ? formatRangeTitle(customRange) : "";
  const customCallsText = customRange ? `预计约 ${estimateCallsForDisplay(customRange.max)} 次模型调用` : "";
  const canSaveCustom = Boolean(customRange);

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      <div className="fixed inset-0 bg-black bg-opacity-50 transition-opacity" onClick={onClose} />
      <div className="flex items-center justify-center min-h-screen p-4">
        <div className="relative bg-white rounded-lg shadow-xl max-w-md w-full">
          <div className="flex items-center justify-between p-6 border-b border-gray-200">
            <h3 className="text-lg font-semibold text-gray-900">自定义条数范围</h3>
            <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
              <X className="h-5 w-5" />
            </button>
          </div>
          <div className="p-6 space-y-3">
            <div className="text-sm text-gray-600">输入目标条数，系统会自动生成一个合理范围</div>
            <input
              type="number"
              min={CUSTOM_SCRIPT_LENGTH_MIN}
              max={CUSTOM_SCRIPT_LENGTH_MAX}
              value={customInput}
              onChange={(e) => {
                setCustomInput(e.target.value);
                setError(null);
              }}
              placeholder={`建议 ${CUSTOM_SCRIPT_LENGTH_MIN}-${CUSTOM_SCRIPT_LENGTH_MAX}`}
              className="w-full border border-gray-300 rounded px-3 py-2 text-sm"
            />
            {error ? <div className="text-xs text-red-600">{error}</div> : null}
            {customRange ? (
              <div className="rounded-lg border border-gray-200 bg-gray-50 p-3 text-sm text-gray-700 space-y-1">
                <div>默认范围：{customRangeText}</div>
                <div>{customCallsText}</div>
              </div>
            ) : (
              <div className="text-xs text-gray-500">请输入 {CUSTOM_SCRIPT_LENGTH_MIN}-{CUSTOM_SCRIPT_LENGTH_MAX} 的数字</div>
            )}
            <div className="flex items-center justify-end space-x-3 pt-2">
              <button onClick={onClose} className="px-3 py-1 text-gray-700 bg-gray-100 rounded text-sm">
                取消
              </button>
              <button
                onClick={async () => {
                  if (!customRange) {
                    setError(`请输入 ${CUSTOM_SCRIPT_LENGTH_MIN}-${CUSTOM_SCRIPT_LENGTH_MAX} 的数字`);
                    return;
                  }
                  await onSave(formatRangeValue(customRange));
                  onClose();
                }}
                disabled={!canSaveCustom}
                className="px-3 py-1 bg-violet-600 text-white rounded text-sm disabled:opacity-50 disabled:cursor-not-allowed"
              >
                保存并使用
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default CustomScriptLengthModal;


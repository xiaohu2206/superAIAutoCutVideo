import { Mic, X } from "lucide-react";
import React from "react";
import { useThemeMode } from "../../../hooks/useThemeMode";

export interface BulkTtsChoiceModalProps {
  isOpen: boolean;
  /** 可配音的解说段总数 */
  dubbableCount: number;
  /** 已存在有效配音的段落数 */
  validDubbedCount: number;
  onClose: () => void;
  /** 仅为未完成段补全配音 */
  onContinueIncomplete: () => void;
  /** 全部重新配音（覆盖已有手动/自动配音） */
  onRestartAll: () => void;
}

/**
 * 批量配音冲突选择弹框：
 * 当已存在条目配过音时，让用户选择"补全未完成"或"全部重新配音"。
 */
const BulkTtsChoiceModal: React.FC<BulkTtsChoiceModalProps> = ({
  isOpen,
  dubbableCount,
  validDubbedCount,
  onClose,
  onContinueIncomplete,
  onRestartAll,
}) => {
  const isDark = useThemeMode() === "dark";

  if (!isOpen) return null;

  const remaining = Math.max(0, dubbableCount - validDubbedCount);
  const allDubbed = dubbableCount > 0 && validDubbedCount >= dubbableCount;

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      <div
        className={`fixed inset-0 transition-opacity ${isDark ? "bg-black/70" : "bg-black/50"}`}
        onClick={onClose}
        aria-hidden
      />
      <div className="flex min-h-screen items-center justify-center p-4">
        <div
          className={`relative w-full max-w-md rounded-lg border shadow-xl ${
            isDark ? "border-[#2a2a2a] bg-[#1f1f1f]" : "border-gray-200 bg-white"
          }`}
          role="dialog"
          aria-modal="true"
          aria-labelledby="bulk-tts-choice-title"
          onClick={(e) => e.stopPropagation()}
        >
          <div
            className={`flex items-center justify-between border-b p-5 ${
              isDark ? "border-[#2a2a2a]" : "border-gray-200"
            }`}
          >
            <div className="flex items-center gap-3">
              <div
                className={`flex h-10 w-10 items-center justify-center rounded-lg ${
                  isDark ? "bg-violet-900/40" : "bg-violet-100"
                }`}
              >
                <Mic className={`h-5 w-5 ${isDark ? "text-violet-300" : "text-violet-700"}`} />
              </div>
              <h3
                id="bulk-tts-choice-title"
                className={`text-lg font-semibold ${isDark ? "text-gray-100" : "text-gray-900"}`}
              >
                批量配音
              </h3>
            </div>
            <button
              type="button"
              onClick={onClose}
              className={`transition-colors ${
                isDark
                  ? "text-gray-500 hover:text-gray-300"
                  : "text-gray-400 hover:text-gray-600"
              }`}
              aria-label="关闭"
            >
              <X className="h-6 w-6" />
            </button>
          </div>

          <div
            className={`space-y-3 p-5 text-sm ${isDark ? "text-gray-300" : "text-gray-700"}`}
          >
            <p>
              已存在{" "}
              <span
                className={`font-semibold ${isDark ? "text-violet-300" : "text-violet-700"}`}
              >
                {validDubbedCount}
              </span>{" "}
              / {dubbableCount} 段有效配音。请选择如何继续：
            </p>
            <ul
              className={`list-inside list-disc space-y-1 ${
                isDark ? "text-gray-400" : "text-gray-600"
              }`}
            >
              <li>
                补全未完成：仅为剩余 <span className="font-semibold">{remaining}</span> 段未配音的解说生成配音，已有手动配音保持不变
              </li>
              <li>全部重新：对所有解说段重新生成配音（已有手动配音也会被覆盖）</li>
            </ul>
            {allDubbed ? (
              <p
                className={`rounded-md border px-3 py-2 ${
                  isDark
                    ? "border-amber-700/40 bg-amber-900/15 text-amber-200"
                    : "border-amber-200 bg-amber-50 text-amber-900"
                }`}
              >
                所有解说段均已完成配音，"补全未完成"无可处理项。
              </p>
            ) : null}
          </div>

          <div
            className={`flex flex-col gap-2 border-t px-5 py-4 sm:flex-row sm:justify-end sm:gap-3 ${
              isDark ? "border-[#2a2a2a] bg-[#181818]" : "border-gray-200 bg-gray-50"
            }`}
          >
            <button
              type="button"
              onClick={onClose}
              className={`order-last rounded-lg border px-4 py-2 text-sm font-medium transition-colors sm:order-first ${
                isDark
                  ? "border-[#2a2a2a] bg-[#242424] text-gray-200 hover:bg-[#2d2d2d]"
                  : "border-gray-300 bg-white text-gray-700 hover:bg-gray-50"
              }`}
            >
              取消
            </button>
            <button
              type="button"
              onClick={onRestartAll}
              className={`rounded-lg border px-4 py-2 text-sm font-medium transition-colors ${
                isDark
                  ? "border-amber-700/40 bg-amber-900/20 text-amber-200 hover:bg-amber-900/30"
                  : "border-amber-200 bg-amber-50 text-amber-900 hover:bg-amber-100"
              }`}
            >
              全部重新配音
            </button>
            <button
              type="button"
              onClick={onContinueIncomplete}
              disabled={allDubbed}
              className={`rounded-lg px-4 py-2 text-sm font-medium text-white transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
                isDark ? "bg-violet-600 hover:bg-violet-500" : "bg-violet-700 hover:bg-violet-800"
              }`}
            >
              补全未完成
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default BulkTtsChoiceModal;

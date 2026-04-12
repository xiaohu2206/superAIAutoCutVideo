import { Eye, X } from "lucide-react";
import React from "react";

interface VisionAnalysisChoiceModalProps {
  isOpen: boolean;
  onClose: () => void;
  onContinueIncomplete: () => void;
  onRestartAll: () => void;
}

/**
 * 已有镜头分析结果时，选择继续补全视觉分析或全部重跑
 */
const VisionAnalysisChoiceModal: React.FC<VisionAnalysisChoiceModalProps> = ({
  isOpen,
  onClose,
  onContinueIncomplete,
  onRestartAll,
}) => {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      <div className="fixed inset-0 bg-black/50 transition-opacity" onClick={onClose} aria-hidden />
      <div className="flex min-h-screen items-center justify-center p-4">
        <div
          className="relative w-full max-w-md rounded-lg border border-gray-200 bg-white shadow-xl"
          role="dialog"
          aria-modal="true"
          aria-labelledby="vision-choice-title"
          onClick={(e) => e.stopPropagation()}
        >
          <div className="flex items-center justify-between border-b border-gray-200 p-5">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-blue-100">
                <Eye className="h-5 w-5 text-blue-600" />
              </div>
              <h3 id="vision-choice-title" className="text-lg font-semibold text-gray-900">
                视觉分析
              </h3>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="text-gray-400 transition-colors hover:text-gray-600"
              aria-label="关闭"
            >
              <X className="h-6 w-6" />
            </button>
          </div>

          <div className="space-y-3 p-5 text-sm text-gray-700">
            <p>已存在镜头分析结果（uploads/analyses 下的 scenes 数据）。请选择如何继续：</p>
            <ul className="list-inside list-disc space-y-1 text-gray-600">
              <li>继续补全：仅对尚未完成视觉分析的镜头调用大模型</li>
              <li>全部重新：保留镜头切分，重新对所有镜头做视觉分析</li>
            </ul>
          </div>

          <div className="flex flex-col gap-2 border-t border-gray-200 bg-gray-50 px-5 py-4 sm:flex-row sm:justify-end sm:gap-3">
            <button
              type="button"
              onClick={onClose}
              className="order-last rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50 sm:order-first"
            >
              取消
            </button>
            <button
              type="button"
              onClick={onRestartAll}
              className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-2 text-sm font-medium text-amber-900 transition-colors hover:bg-amber-100"
            >
              全部重新视觉分析
            </button>
            <button
              type="button"
              onClick={onContinueIncomplete}
              className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700"
            >
              继续补全未分析镜头
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default VisionAnalysisChoiceModal;

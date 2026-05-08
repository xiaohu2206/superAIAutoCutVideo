import { Boxes, X } from "lucide-react";
import React from "react";

export interface OmniMultimodalChoiceModalProps {
  isOpen: boolean;
  onClose: () => void;
  onContinueIncomplete: () => void;
  onRestartAll: () => void;
  /** 未登录或无 token 时为 false，禁用继续/重新按钮 */
  actionsEnabled?: boolean;
}

const OmniMultimodalChoiceModal: React.FC<OmniMultimodalChoiceModalProps> = ({
  isOpen,
  onClose,
  onContinueIncomplete,
  onRestartAll,
  actionsEnabled = true,
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
          aria-labelledby="omni-multimodal-choice-title"
          onClick={(e) => e.stopPropagation()}
        >
          <div className="flex items-center justify-between border-b border-gray-200 p-5">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-fuchsia-100">
                <Boxes className="h-5 w-5 text-fuchsia-700" />
              </div>
              <h3 id="omni-multimodal-choice-title" className="text-lg font-semibold text-gray-900">
                Omni 多模态管线
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
            <p>已存在 Omni 多模态结果（镜头拆分后的语义段 + 向量）。请选择如何继续：</p>
            <ul className="list-inside list-disc space-y-1 text-gray-600">
              <li>继续补全：仅对尚未完成多模态/向量化的语义段调用模型</li>
              <li>全部重新：保留本次镜头拆分，重新对所有语义段做视觉与向量化</li>
            </ul>
            {!actionsEnabled ? (
              <p className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-amber-900">
                请先登录账号，并在个人中心绑定处于生效中的 License，再运行 Omni 管线。
              </p>
            ) : null}
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
              disabled={!actionsEnabled}
              className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-2 text-sm font-medium text-amber-900 transition-colors hover:bg-amber-100 disabled:cursor-not-allowed disabled:opacity-50"
            >
              全部重新分析
            </button>
            <button
              type="button"
              onClick={onContinueIncomplete}
              disabled={!actionsEnabled}
              className="rounded-lg bg-fuchsia-700 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-fuchsia-800 disabled:cursor-not-allowed disabled:opacity-50"
            >
              补全未完成段落
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default OmniMultimodalChoiceModal;

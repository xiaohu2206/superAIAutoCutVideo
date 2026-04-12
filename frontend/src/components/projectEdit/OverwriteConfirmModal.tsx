import { AlertTriangle, X } from "lucide-react";
import React from "react";

interface OverwriteConfirmModalProps {
  isOpen: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  onConfirm: () => void;
  onCancel: () => void;
}

/**
 * 通用确认弹框（替代 window.confirm）
 */
const OverwriteConfirmModal: React.FC<OverwriteConfirmModalProps> = ({
  isOpen,
  title,
  message,
  confirmLabel = "继续",
  cancelLabel = "取消",
  onConfirm,
  onCancel,
}) => {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      <div className="fixed inset-0 bg-black/50 transition-opacity" onClick={onCancel} aria-hidden />
      <div className="flex min-h-screen items-center justify-center p-4">
        <div
          className="relative w-full max-w-md rounded-lg border border-gray-200 bg-white shadow-xl"
          role="dialog"
          aria-modal="true"
          aria-labelledby="overwrite-confirm-title"
          onClick={(e) => e.stopPropagation()}
        >
          <div className="flex items-center justify-between border-b border-gray-200 p-5">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-amber-100">
                <AlertTriangle className="h-5 w-5 text-amber-600" />
              </div>
              <h3 id="overwrite-confirm-title" className="text-lg font-semibold text-gray-900">
                {title}
              </h3>
            </div>
            <button
              type="button"
              onClick={onCancel}
              className="text-gray-400 transition-colors hover:text-gray-600"
              aria-label="关闭"
            >
              <X className="h-6 w-6" />
            </button>
          </div>

          <div className="p-5">
            <p className="text-sm text-gray-700 whitespace-pre-wrap">{message}</p>
          </div>

          <div className="flex justify-end gap-3 border-t border-gray-200 bg-gray-50 px-5 py-4">
            <button
              type="button"
              onClick={onCancel}
              className="rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50"
            >
              {cancelLabel}
            </button>
            <button
              type="button"
              onClick={onConfirm}
              className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700"
            >
              {confirmLabel}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default OverwriteConfirmModal;

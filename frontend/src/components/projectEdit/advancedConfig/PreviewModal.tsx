import { Check, Copy, X } from "lucide-react";
import React from "react";

interface Props {
  isOpen: boolean;
  text: string | null;
  copied: boolean;
  onCopy: () => void;
  onClose: () => void;
}

const PreviewModal: React.FC<Props> = ({ isOpen, text, copied, onCopy, onClose }) => {
  if (!isOpen) return null;
  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      <div className="fixed inset-0 bg-black bg-opacity-50 transition-opacity" onClick={onClose} />
      <div className="flex items-center justify-center min-h-screen p-4">
        <div className="relative bg-white rounded-lg shadow-xl w-[70%]">
          <div className="flex items-center justify-between p-4 border-b border-gray-200">
            <h3 className="text-lg font-semibold text-gray-900">预览</h3>
            <div className="flex items-center space-x-2">
              <button
                onClick={onCopy}
                disabled={!text}
                className="flex items-center px-2 py-1 text-xs bg-gray-100 text-gray-700 rounded hover:bg-gray-200 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {copied ? (
                  <>
                    <Check className="h-4 w-4 mr-1" />
                    已复制
                  </>
                ) : (
                  <>
                    <Copy className="h-4 w-4 mr-1" />
                    复制
                  </>
                )}
              </button>
              <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
                <X className="h-5 w-5" />
              </button>
            </div>
          </div>
          <div className="p-4">
            <div className="max-h-[70vh] overflow-auto">
              <pre className="text-xs bg-white border rounded p-2 whitespace-pre-wrap">{text || "加载中..."}</pre>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default PreviewModal;


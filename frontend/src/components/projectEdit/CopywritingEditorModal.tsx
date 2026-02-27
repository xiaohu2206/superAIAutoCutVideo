import React, { useState, useEffect } from "react";
import { X, Save, Loader } from "lucide-react";

interface CopywritingEditorModalProps {
  isOpen: boolean;
  onClose: () => void;
  value: string;
  onSave: (newValue: string) => void;
  isSaving: boolean;
}

const CopywritingEditorModal: React.FC<CopywritingEditorModalProps> = ({
  isOpen,
  onClose,
  value,
  onSave,
  isSaving,
}) => {
  const [internalValue, setInternalValue] = useState(value);

  useEffect(() => {
    if (isOpen) {
      setInternalValue(value);
    }
  }, [value, isOpen]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      {/* Overlay */}
      <div 
        className="fixed inset-0 bg-black bg-opacity-50 transition-opacity" 
        onClick={onClose} 
      />

      {/* Modal */}
      <div className="flex items-center justify-center min-h-screen p-4">
        <div className="relative bg-white rounded-lg shadow-xl max-w-4xl w-full flex flex-col max-h-[90vh]">
          {/* Header */}
          <div className="flex items-center justify-between p-6 border-b border-gray-200">
            <h3 className="text-xl font-semibold text-gray-900">编辑解说文案</h3>
            <button 
              onClick={onClose} 
              className="text-gray-400 hover:text-gray-500 p-1 rounded-full hover:bg-gray-100 transition-colors"
            >
              <X className="h-6 w-6" />
            </button>
          </div>

          {/* Body */}
          <div className="p-6 flex-1 overflow-y-auto">
            <textarea
              className="w-full h-[60vh] p-4 border border-gray-300 rounded-lg font-mono text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none resize-none"
              value={internalValue}
              onChange={(e) => setInternalValue(e.target.value)}
              placeholder="请输入解说文案..."
              autoFocus
            />
            <div className="mt-2 text-right text-sm text-gray-500">
              字数：{internalValue.length}
            </div>
          </div>

          {/* Footer */}
          <div className="flex justify-end gap-3 p-6 border-t border-gray-200 bg-gray-50 rounded-b-lg">
            <button
              onClick={onClose}
              className="px-4 py-2 text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
            >
              取消
            </button>
            <button
              onClick={() => onSave(internalValue)}
              disabled={isSaving || !internalValue.trim()}
              className="flex items-center px-4 py-2 text-white bg-blue-600 rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isSaving ? (
                <>
                  <Loader className="w-4 h-4 mr-2 animate-spin" />
                  保存中...
                </>
              ) : (
                <>
                  <Save className="w-4 h-4 mr-2" />
                  保存
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default CopywritingEditorModal;

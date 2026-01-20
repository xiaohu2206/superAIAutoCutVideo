import { X } from "lucide-react";
import React from "react";

interface Props {
  isOpen: boolean;
  mode: "create" | "edit";
  name: string;
  template: string;
  onChangeName: (v: string) => void;
  onChangeTemplate: (v: string) => void;
  onSave: () => Promise<void> | void;
  onClose: () => void;
}

const TemplateModal: React.FC<Props> = ({
  isOpen,
  mode,
  name,
  template,
  onChangeName,
  onChangeTemplate,
  onSave,
  onClose,
}) => {
  if (!isOpen) return null;
  const canSave = Boolean(name.trim()) && Boolean(template.trim());
  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      <div className="fixed inset-0 bg-black bg-opacity-50 transition-opacity" onClick={onClose} />
      <div className="flex items-center justify-center min-h-screen p-4">
        <div className="relative bg-white rounded-lg shadow-xl w-[70%]">
          <div className="flex items-center justify-between p-6 border-b border-gray-200">
            <h3 className="text-lg font-semibold text-gray-900">{mode === "edit" ? "编辑自定义模板" : "新建自定义模板"}</h3>
            <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
              <X className="h-5 w-5" />
            </button>
          </div>
          <div className="p-6 space-y-2">
            <input
              type="text"
              placeholder="模板名称"
              value={name}
              onChange={(e) => onChangeName(e.target.value)}
              className="w-full border border-gray-300 rounded px-3 py-2 text-sm"
            />
            <textarea
              placeholder={`模版需要要求大模型输出包含这些字段，不然无法合并：_id, timestamp, picture, narration, OST`}
              value={template}
              onChange={(e) => onChangeTemplate(e.target.value)}
              className="w-full h-[60vh] border border-gray-300 rounded px-3 py-2 text-sm"
            />
            <div className="flex items-center justify-end space-x-3 pt-2">
              <button onClick={onClose} className="px-3 py-1 text-gray-700 bg-gray-100 rounded text-sm">
                取消
              </button>
              <button
                onClick={onSave}
                disabled={!canSave}
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

export default TemplateModal;


import React, { useState } from "react";
import { Edit3 } from "lucide-react";
import CopywritingEditorModal from "./CopywritingEditorModal";

interface CopywritingSectionProps {
  editedCopywriting: string;
  setEditedCopywriting: (copywriting: string) => void;
  isSavingCopywriting: boolean;
  handleSaveCopywriting: (content?: string) => void;
}

const CopywritingSection: React.FC<CopywritingSectionProps> = ({
  editedCopywriting,
  setEditedCopywriting,
  isSavingCopywriting,
  handleSaveCopywriting,
}) => {
  const [isModalOpen, setIsModalOpen] = useState(false);

  const handleModalSave = (content: string) => {
    setEditedCopywriting(content);
    handleSaveCopywriting(content);
    setIsModalOpen(false);
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-gray-900">解说文案</h2>
      </div>

      <p className="text-sm text-gray-600">
        点击下方区域可编辑解说文案。
      </p>

      <div 
        className="relative group cursor-pointer"
        onClick={() => setIsModalOpen(true)}
      >
        <div className="w-full h-10 px-4 py-3 font-mono text-sm border border-gray-300 rounded-lg bg-gray-50 overflow-hidden text-gray-700 hover:border-blue-400 hover:ring-1 hover:ring-blue-400 transition-all whitespace-pre-wrap">
          {editedCopywriting || <span className="text-gray-400">暂无文案内容，请点击“生成解说文案”...</span>}
        </div>
        
        <div className="absolute inset-0 bg-black bg-opacity-0 group-hover:bg-opacity-5 flex items-center justify-center transition-all rounded-lg pointer-events-none">
           <div className="opacity-0 group-hover:opacity-100 bg-white shadow-sm border border-gray-200 px-3 py-1.5 rounded-full text-sm font-medium text-gray-700 flex items-center">
             <Edit3 className="w-3 h-3 mr-1.5" />
             点击编辑
           </div>
        </div>

        {editedCopywriting && (
          <div className="absolute top-2 right-2 bg-gray-100 px-2 py-1 rounded text-xs text-gray-600">
            文本内容
          </div>
        )}
      </div>

      <CopywritingEditorModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        value={editedCopywriting}
        onSave={handleModalSave}
        isSaving={isSavingCopywriting}
      />
    </div>
  );
};

export default CopywritingSection;

import React from "react";
import { SubtitleUploader } from "./SubtitleUploader";

interface AdvancedConfigSectionProps {
  uploadingSubtitle: boolean;
  subtitleUploadProgress: number;
  subtitlePath?: string;
  onSubtitleFileChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  onDeleteSubtitle: () => void;
  isDraggingSubtitle: boolean;
  onSubtitleDragOver: (e: React.DragEvent<HTMLDivElement>) => void;
  onSubtitleDragLeave: (e: React.DragEvent<HTMLDivElement>) => void;
  onSubtitleDrop: (e: React.DragEvent<HTMLDivElement>) => void;
}

const AdvancedConfigSection: React.FC<AdvancedConfigSectionProps> = ({
  uploadingSubtitle,
  subtitleUploadProgress,
  subtitlePath,
  onSubtitleFileChange,
  onDeleteSubtitle,
  isDraggingSubtitle,
  onSubtitleDragOver,
  onSubtitleDragLeave,
  onSubtitleDrop,
}) => {
  return (
    <div className="border-t border-gray-200 pt-4 space-y-3">
      <SubtitleUploader
        uploading={uploadingSubtitle}
        progress={subtitleUploadProgress}
        path={subtitlePath}
        onFileChange={onSubtitleFileChange}
        onDelete={onDeleteSubtitle}
        isDragging={isDraggingSubtitle}
        onDragOver={onSubtitleDragOver}
        onDragLeave={onSubtitleDragLeave}
        onDrop={onSubtitleDrop}
      />
    </div>
  );
};

export default AdvancedConfigSection;

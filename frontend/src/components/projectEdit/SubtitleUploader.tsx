import React, { useRef } from 'react';
import { Upload, FileText, Trash2, Loader2 } from 'lucide-react';

interface SubtitleUploaderProps {
  uploading: boolean;
  progress: number;
  path?: string;
  onFileChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  onDelete: () => void;
  isDragging?: boolean;
  onDragOver?: (e: React.DragEvent<HTMLDivElement>) => void;
  onDragLeave?: (e: React.DragEvent<HTMLDivElement>) => void;
  onDrop?: (e: React.DragEvent<HTMLDivElement>) => void;
}

export const SubtitleUploader: React.FC<SubtitleUploaderProps> = ({
  uploading,
  progress,
  path,
  onFileChange,
  onDelete,
  isDragging,
  onDragOver,
  onDragLeave,
  onDrop,
}) => {
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleClick = () => {
    if (!uploading) {
      fileInputRef.current?.click();
    }
  };

  return (
    <div className="bg-white p-4 rounded-xl border border-gray-100 shadow-sm hover:shadow-md transition-shadow duration-200">
      <div className="flex items-center justify-between mb-4">
        <label className="text-sm font-semibold text-gray-800 flex items-center gap-2">
          <div className="p-1.5 bg-violet-100 rounded-lg">
            <FileText className="w-4 h-4 text-violet-600" />
          </div>
          字幕配置
        </label>
        {path && (
          <span className="text-xs px-2.5 py-1 bg-green-50 text-green-600 font-medium rounded-full border border-green-100">
            已配置
          </span>
        )}
      </div>

      {!path ? (
        <div 
          onClick={handleClick}
          onDragOver={onDragOver}
          onDragLeave={onDragLeave}
          onDrop={onDrop}
          className={`
            relative group cursor-pointer
            border-2 border-dashed border-gray-200 hover:border-violet-400
            rounded-xl p-2 transition-all duration-300
            flex items-center justify-center gap-2
            bg-gray-50/50 hover:bg-violet-50/30 flex-row
            ${isDragging ? 'border-violet-400 bg-violet-50/40' : ''}
            ${uploading ? 'pointer-events-none opacity-80' : ''}
          `}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept=".srt"
            onChange={onFileChange}
            disabled={uploading}
            className="hidden"
          />
          
          {uploading ? (
             <div className="flex flex-col items-center w-full max-w-[200px]">
                <div className="relative mb-3">
                  <div className="absolute inset-0 bg-violet-100 rounded-full animate-ping opacity-75"></div>
                  <Loader2 className="relative w-8 h-8 text-violet-600 animate-spin" />
                </div>
                <div className="w-full h-1.5 bg-gray-100 rounded-full overflow-hidden mb-2">
                  <div 
                    className="h-full bg-violet-600 transition-all duration-300 ease-out rounded-full"
                    style={{ width: `${Math.round(progress)}%` }}
                  />
                </div>
                <span className="text-xs font-medium text-gray-500">正在上传... {Math.round(progress)}%</span>
             </div>
          ) : (
            <> 
              <div className="p-2.5 bg-white rounded-full shadow-sm border border-gray-100 group-hover:scale-110 group-hover:border-violet-100 group-hover:shadow-md transition-all duration-300">
                <Upload className="w-5 h-5 text-gray-400 group-hover:text-violet-600 transition-colors" />
              </div>
              <div className="text-center space-y-1">
                <p className="text-sm font-medium text-gray-600 group-hover:text-violet-700 transition-colors">点击上传 SRT 字幕</p>
                <p className="text-xs text-gray-400">支持 .srt 格式文件</p>
              </div>
            </>
          )}
        </div>
      ) : (
        <div className="group relative overflow-hidden bg-gray-50 rounded-xl border border-gray-200 transition-all duration-200 hover:border-violet-200 hover:bg-violet-50/10">
            <div className="flex items-center justify-between p-4">
                <div className="flex items-center gap-4 overflow-hidden">
                    <div className="flex-shrink-0 p-2.5 bg-white rounded-lg border border-gray-200 shadow-sm">
                        <FileText className="w-6 h-6 text-violet-500" />
                    </div>
                    <div className="flex flex-col overflow-hidden min-w-0">
                        <span className="text-sm font-medium text-gray-900 truncate pr-4" title={path.split('/').pop()}>
                            {path.split('/').pop()}
                        </span>
                        <span className="text-xs text-gray-500 flex items-center gap-1">
                          <span className="w-1.5 h-1.5 rounded-full bg-green-500"></span>
                          SRT 字幕文件
                        </span>
                    </div>
                </div>
                <button
                    onClick={(e) => {
                      e.stopPropagation();
                      onDelete();
                    }}
                    className="flex-shrink-0 p-2 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-red-500/20"
                    title="删除字幕"
                >
                    <Trash2 className="w-5 h-5" />
                </button>
            </div>
            <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-gradient-to-r from-violet-500/0 via-violet-500/20 to-violet-500/0 opacity-0 group-hover:opacity-100 transition-opacity" />
        </div>
      )}
    </div>
  );
};

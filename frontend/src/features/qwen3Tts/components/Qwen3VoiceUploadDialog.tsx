import React, { useEffect, useMemo, useState, useRef, useCallback } from "react";
import { Loader, Upload, X, FileAudio, AlertCircle, Check } from "lucide-react";
import type { Qwen3TtsUploadVoiceInput } from "../types";
import { createPortal } from "react-dom";
import { LANGUAGE_OPTIONS } from "../constants";

// --- Types ---

export type Qwen3VoiceUploadDialogResult = {
  input: Qwen3TtsUploadVoiceInput;
  autoStartClone: boolean;
};

export type Qwen3VoiceUploadDialogProps = {
  isOpen: boolean;
  modelKeys: string[];
  onClose: () => void;
  onSubmit: (result: Qwen3VoiceUploadDialogResult) => Promise<void>;
};

// --- Logic Hook ---

const useQwen3VoiceUploadForm = ({ isOpen, modelKeys, onClose, onSubmit }: Qwen3VoiceUploadDialogProps) => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  const defaultModelKey = useMemo(() => modelKeys[0] || "base_0_6b", [modelKeys]);

  const [file, setFile] = useState<File | null>(null);
  const [name, setName] = useState<string>("");
  const [modelKey, setModelKey] = useState<string>(defaultModelKey);
  const [language, setLanguage] = useState<string>("Auto");
  const [refText, setRefText] = useState<string>("");
  const [instruct, setInstruct] = useState<string>("");
  const [xVectorOnlyMode, setXVectorOnlyMode] = useState<boolean>(true);
  const [autoStartClone, setAutoStartClone] = useState<boolean>(true);

  // Reset state when dialog opens
  useEffect(() => {
    if (isOpen) {
      setError(null);
      setLoading(false);
      setFile(null);
      setName("");
      setModelKey(defaultModelKey);
      setLanguage("Auto");
      setRefText("");
      setInstruct("");
      setXVectorOnlyMode(true);
      setAutoStartClone(true);
    }
  }, [isOpen, defaultModelKey]);

  const validateAndSetFile = useCallback((newFile: File) => {
    // Simple check, can be more robust
    if (!newFile.type.startsWith("audio/") && !newFile.name.match(/\.(wav|mp3|m4a|flac|ogg|aac)$/i)) {
      setError("不支持的文件格式，请上传音频文件");
      return;
    }
    setFile(newFile);
    setError(null);
    
    // Auto-fill name if empty
    if (!name) {
      const fileNameWithoutExt = newFile.name.replace(/\.[^/.]+$/, "");
      setName(fileNameWithoutExt);
    }
  }, [name]);

  const handleSubmit = async () => {
    if (!file) {
      setError("请选择音频文件");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      await onSubmit({
        input: {
          file,
          name: name.trim() || undefined,
          model_key: (modelKey || defaultModelKey).trim() || defaultModelKey,
          language: (language || "Auto").trim() || "Auto",
          ref_text: refText.trim() || undefined,
          instruct: instruct.trim() || undefined,
          x_vector_only_mode: Boolean(xVectorOnlyMode),
        },
        autoStartClone: Boolean(autoStartClone),
      });
      onClose();
    } catch (e: any) {
      setError(e?.message || "上传失败");
    } finally {
      setLoading(false);
    }
  };

  const canSubmit = Boolean(file) && !loading;

  return {
    state: {
      loading, error, file, name, modelKey, language, refText, instruct, xVectorOnlyMode, autoStartClone, canSubmit, defaultModelKey
    },
    actions: {
      setFile: validateAndSetFile,
      setName,
      setModelKey,
      setLanguage,
      setRefText,
      setInstruct,
      setXVectorOnlyMode,
      setAutoStartClone,
      handleSubmit,
      setError
    }
  };
};

// --- Sub-components ---

const Label: React.FC<{ children: React.ReactNode; required?: boolean }> = ({ children, required }) => (
  <label className="block text-sm font-medium text-gray-700 mb-1.5">
    {children}
    {required && <span className="text-red-500 ml-1">*</span>}
  </label>
);

// --- Main Component ---

export const Qwen3VoiceUploadDialog: React.FC<Qwen3VoiceUploadDialogProps> = (props) => {
  const { isOpen, modelKeys, onClose } = props;
  const { state, actions } = useQwen3VoiceUploadForm(props);
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const droppedFiles = e.dataTransfer.files;
    if (droppedFiles && droppedFiles.length > 0) {
      actions.setFile(droppedFiles[0]);
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      actions.setFile(e.target.files[0]);
    }
  };

  if (!isOpen) return null;

  return createPortal(
    <div className="fixed inset-0 z-50 overflow-y-auto">
      <div 
        className="fixed inset-0 bg-black/60 backdrop-blur-sm transition-opacity" 
        onClick={state.loading ? undefined : onClose} 
      />
      <div className="flex items-center justify-center min-h-screen p-4">
        <div className="relative bg-white rounded-xl shadow-2xl max-w-2xl w-full transform transition-all">
          {/* Header */}
          <div className="flex items-center justify-between px-6 py-3 border-b border-gray-100">
            <div className="flex items-center gap-3">
              <div className="p-1.5 bg-blue-50 rounded-lg">
                <Upload className="h-5 w-5 text-blue-600" />
              </div>
              <div>
                <h3 className="text-base font-bold text-gray-900">上传参考音频</h3>
                <p className="text-xs text-gray-500">上传一段音频用于声音克隆</p>
              </div>
            </div>
            <button
              onClick={onClose}
              disabled={state.loading}
              className="p-1 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-full transition-colors disabled:opacity-50"
            >
              <X className="h-5 w-5" />
            </button>
          </div>

          <div className="p-5 space-y-4">
            {state.error && (
              <div className="flex items-start gap-3 bg-red-50 text-red-700 px-4 py-3 rounded-lg text-sm border border-red-100">
                <AlertCircle className="h-5 w-5 shrink-0" />
                <span>{state.error}</span>
              </div>
            )}

            {/* File Upload Area */}
            <div>
              <Label required>音频文件</Label>
              <div
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
                onClick={() => !state.loading && fileInputRef.current?.click()}
                className={`
                  relative border-2 border-dashed rounded-xl p-4 text-center cursor-pointer transition-all duration-200 group
                  ${isDragging ? "border-blue-500 bg-blue-50" : "border-gray-300 hover:border-blue-400 hover:bg-gray-50"}
                  ${state.file ? "bg-blue-50/50 border-blue-200" : ""}
                `}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".wav,.mp3,.m4a,.flac,.ogg,.aac,audio/*"
                  disabled={state.loading}
                  onChange={handleFileSelect}
                  className="hidden"
                />
                
                {state.file ? (
                  <div className="flex flex-row items-center justify-between px-2">
                    <div className="flex items-center gap-3">
                      <div className="h-10 w-10 bg-blue-100 text-blue-600 rounded-full flex items-center justify-center shrink-0">
                        <FileAudio className="h-5 w-5" />
                      </div>
                      <div className="text-left">
                        <p className="text-sm font-medium text-gray-900 truncate max-w-[200px]">{state.file.name}</p>
                        <p className="text-xs text-gray-500">
                          {(state.file.size / 1024 / 1024).toFixed(2)} MB
                        </p>
                      </div>
                    </div>
                    <button 
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        actions.setFile(null as any); // Force null
                      }}
                      className="text-xs text-gray-500 hover:text-red-600 font-medium px-2 py-1 hover:bg-red-50 rounded"
                    >
                      更换
                    </button>
                  </div>
                ) : (
                  <div className="flex flex-col items-center text-gray-500 py-1">
                    <div className={`
                      h-10 w-10 rounded-full flex items-center justify-center mb-2 transition-colors
                      ${isDragging ? "bg-blue-100 text-blue-600" : "bg-gray-100 text-gray-400 group-hover:bg-blue-50 group-hover:text-blue-500"}
                    `}>
                      <Upload className="h-5 w-5" />
                    </div>
                    <p className="text-sm font-medium text-gray-700">
                      点击或拖拽音频文件到此处
                    </p>
                    <p className="text-xs text-gray-400 mt-0.5">
                      支持 WAV, MP3, M4A, FLAC, OGG, AAC
                    </p>
                  </div>
                )}
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* Name */}
              <div>
                <Label>名称 (可选)</Label>
                <input
                  type="text"
                  value={state.name}
                  disabled={state.loading}
                  onChange={(e) => actions.setName(e.target.value)}
                  placeholder="给这个声音起个名字"
                  className="w-full px-3 py-2 bg-gray-50 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all"
                />
              </div>

              {/* Model Selection */}
              <div>
                <Label required>模型</Label>
                <div className="relative">
                  <select
                    value={state.modelKey}
                    disabled={state.loading}
                    onChange={(e) => actions.setModelKey(e.target.value)}
                    className="w-full px-3 py-2 bg-gray-50 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all appearance-none"
                  >
                    {(modelKeys.length ? modelKeys : [state.defaultModelKey]).map((k) => (
                      <option key={k} value={k}>
                        {k}
                      </option>
                    ))}
                  </select>
                  <div className="absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none text-gray-400">
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7"></path></svg>
                  </div>
                </div>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* Language */}
              <div>
                <Label>语言</Label>
                <div className="relative">
                  <select
                    value={state.language}
                    disabled={state.loading}
                    onChange={(e) => actions.setLanguage(e.target.value)}
                    className="w-full px-3 py-2 bg-gray-50 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all appearance-none"
                  >
                    {LANGUAGE_OPTIONS.map((opt) => (
                      <option key={opt.value} value={opt.value}>
                        {opt.label}
                      </option>
                    ))}
                  </select>
                  <div className="absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none text-gray-400">
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7"></path></svg>
                  </div>
                </div>
              </div>

              {/* Options */}
              <div className="flex flex-col gap-3 pt-6">
                 <label className="flex items-center gap-2 p-2 border border-gray-200 rounded-lg cursor-pointer hover:bg-gray-50 transition-colors h-[38px]">
                  <input
                    type="checkbox"
                    checked={state.xVectorOnlyMode}
                    disabled={state.loading}
                    onChange={(e) => actions.setXVectorOnlyMode(e.target.checked)}
                    className="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
                  />
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-gray-700">仅使用 x-vector 模式</span>
                    <span className="text-xs text-gray-400 hidden sm:inline">(仅提取音色)</span>
                  </div>
                </label>
              </div>
            </div>

            <div className="space-y-3">
              {/* Ref Text */}
              <div>
                <Label>参考文本 (可选)</Label>
                <textarea
                  value={state.refText}
                  disabled={state.loading}
                  onChange={(e) => actions.setRefText(e.target.value)}
                  placeholder="如果音频包含清晰的语音，输入对应的文本可以提高克隆效果"
                  className="w-full px-3 py-2 bg-gray-50 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all min-h-[60px] resize-y"
                />
              </div>

              {/* Instruct */}
              <div>
                <Label>指令 (可选)</Label>
                <textarea
                  value={state.instruct}
                  disabled={state.loading}
                  onChange={(e) => actions.setInstruct(e.target.value)}
                  placeholder="输入合成时的默认风格指令，例如：用开心的语气说话"
                  className="w-full px-3 py-2 bg-gray-50 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all min-h-[60px] resize-y"
                />
              </div>
            </div>

            {/* Footer Options */}
            <div className="flex items-center gap-2 pt-2">
              <label className="flex items-center gap-2 cursor-pointer select-none">
                <div className={`w-5 h-5 rounded border flex items-center justify-center transition-colors ${state.autoStartClone ? 'bg-blue-600 border-blue-600' : 'border-gray-300 bg-white'}`}>
                  {state.autoStartClone && <Check className="w-3.5 h-3.5 text-white" />}
                  <input
                    type="checkbox"
                    checked={state.autoStartClone}
                    disabled={state.loading}
                    onChange={(e) => actions.setAutoStartClone(e.target.checked)}
                    className="hidden"
                  />
                </div>
                <span className="text-sm text-gray-700">上传成功后自动开始克隆（预处理）</span>
              </label>
            </div>
          </div>

          {/* Footer Actions */}
          <div className="bg-gray-50 px-6 py-3 flex items-center justify-end gap-3 border-t border-gray-200 rounded-b-xl">
            <button
              type="button"
              onClick={onClose}
              disabled={state.loading}
              className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 hover:bg-gray-50 hover:text-gray-900 rounded-lg transition-all shadow-sm disabled:opacity-50"
            >
              取消
            </button>
            <button
              type="button"
              onClick={actions.handleSubmit}
              disabled={!state.canSubmit}
              className={`
                relative px-5 py-2 text-sm font-medium rounded-lg text-white shadow-sm transition-all
                ${state.canSubmit 
                  ? "bg-blue-600 hover:bg-blue-700 hover:shadow-md active:transform active:scale-95" 
                  : "bg-gray-300 cursor-not-allowed"
                }
              `}
            >
              <span className={`flex items-center gap-2 ${state.loading ? 'opacity-0' : 'opacity-100'}`}>
                <Upload className="h-4 w-4" />
                开始上传
              </span>
              {state.loading && (
                <div className="absolute inset-0 flex items-center justify-center">
                  <Loader className="h-4 w-4 animate-spin" />
                </div>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>,
    document.body
  );
};

export default Qwen3VoiceUploadDialog;

import React, { useEffect, useMemo, useState } from "react";
import { Loader, Upload, X } from "lucide-react";
import type { Qwen3TtsUploadVoiceInput } from "../types";

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

export const Qwen3VoiceUploadDialog: React.FC<Qwen3VoiceUploadDialogProps> = ({ isOpen, modelKeys, onClose, onSubmit }) => {
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

  useEffect(() => {
    if (!isOpen) return;
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
  }, [isOpen, defaultModelKey]);

  const canSubmit = Boolean(file) && !loading;

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

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      <div className="fixed inset-0 bg-black bg-opacity-50 transition-opacity" onClick={loading ? undefined : onClose} />
      <div className="flex items-center justify-center min-h-screen p-4">
        <div className="relative bg-white rounded-lg shadow-xl max-w-lg w-full">
          <div className="flex items-center justify-between p-5 border-b border-gray-200">
            <div className="flex items-center gap-2">
              <Upload className="h-5 w-5 text-gray-700" />
              <h3 className="text-lg font-semibold text-gray-900">上传参考音频</h3>
            </div>
            <button
              onClick={onClose}
              disabled={loading}
              className="text-gray-400 hover:text-gray-600 transition-colors disabled:opacity-50"
            >
              <X className="h-6 w-6" />
            </button>
          </div>

          <div className="p-5 space-y-4">
            {error ? <div className="bg-red-50 text-red-600 px-4 py-3 rounded-lg text-sm">{error}</div> : null}

            <div>
              <label className="block text-sm text-gray-700 mb-1">音频文件</label>
              <input
                type="file"
                accept=".wav,.mp3,.m4a,.flac,.ogg,.aac,audio/*"
                disabled={loading}
                onChange={(e) => setFile(e.target.files?.[0] || null)}
                className="w-full text-sm"
              />
              {file ? <div className="text-xs text-gray-500 mt-1 truncate">已选择: {file.name}</div> : null}
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div>
                <label className="block text-sm text-gray-700 mb-1">名称（可选）</label>
                <input
                  type="text"
                  value={name}
                  disabled={loading}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="展示名称"
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-200"
                />
              </div>
              <div>
                <label className="block text-sm text-gray-700 mb-1">模型</label>
                <select
                  value={modelKey}
                  disabled={loading}
                  onChange={(e) => setModelKey(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md bg-white"
                >
                  {(modelKeys.length ? modelKeys : [defaultModelKey]).map((k) => (
                    <option key={k} value={k}>
                      {k}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div>
                <label className="block text-sm text-gray-700 mb-1">语言</label>
                <input
                  type="text"
                  value={language}
                  disabled={loading}
                  onChange={(e) => setLanguage(e.target.value)}
                  placeholder="Auto/zh/en"
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-200"
                />
              </div>
              <div className="flex items-center gap-2 mt-6">
                <input
                  type="checkbox"
                  checked={xVectorOnlyMode}
                  disabled={loading}
                  onChange={(e) => setXVectorOnlyMode(e.target.checked)}
                />
                <span className="text-sm text-gray-700">仅使用 x-vector 模式</span>
              </div>
            </div>

            <div>
              <label className="block text-sm text-gray-700 mb-1">参考文本（可选）</label>
              <textarea
                value={refText}
                disabled={loading}
                onChange={(e) => setRefText(e.target.value)}
                placeholder="用于克隆/合成对齐的参考文本"
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-200 min-h-[72px]"
              />
            </div>

            <div>
              <label className="block text-sm text-gray-700 mb-1">指令（可选）</label>
              <textarea
                value={instruct}
                disabled={loading}
                onChange={(e) => setInstruct(e.target.value)}
                placeholder="可选的合成指令"
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-200 min-h-[72px]"
              />
            </div>

            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={autoStartClone}
                disabled={loading}
                onChange={(e) => setAutoStartClone(e.target.checked)}
              />
              <span className="text-sm text-gray-700">上传成功后自动开始克隆（预处理）</span>
            </div>
          </div>

          <div className="bg-gray-50 px-5 py-4 flex items-center justify-end gap-3 border-t border-gray-200">
            <button
              type="button"
              onClick={onClose}
              disabled={loading}
              className="px-4 py-2 text-gray-700 bg-white border border-gray-300 hover:bg-gray-50 rounded-lg font-medium transition-colors disabled:opacity-50"
            >
              取消
            </button>
            <button
              type="button"
              onClick={handleSubmit}
              disabled={!canSubmit}
              className={`px-5 py-2 rounded-lg font-medium transition-colors ${
                canSubmit ? "bg-blue-600 text-white hover:bg-blue-700" : "bg-gray-300 text-gray-500 cursor-not-allowed"
              }`}
            >
              <span className="inline-flex items-center gap-2">
                {loading ? <Loader className="h-4 w-4 animate-spin" /> : null}
                上传
              </span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Qwen3VoiceUploadDialog;


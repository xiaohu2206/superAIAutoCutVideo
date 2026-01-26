import React, { useEffect, useMemo, useState } from "react";
import { Loader, Save, X } from "lucide-react";
import type { Qwen3TtsPatchVoiceInput, Qwen3TtsVoice } from "../types";

export type Qwen3VoiceEditDialogProps = {
  isOpen: boolean;
  voice: Qwen3TtsVoice | null;
  modelKeys: string[];
  onClose: () => void;
  onSubmit: (voiceId: string, patch: Qwen3TtsPatchVoiceInput) => Promise<void>;
};

export const Qwen3VoiceEditDialog: React.FC<Qwen3VoiceEditDialogProps> = ({ isOpen, voice, modelKeys, onClose, onSubmit }) => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const defaultModelKey = useMemo(() => modelKeys[0] || "base_0_6b", [modelKeys]);

  const [name, setName] = useState<string>("");
  const [modelKey, setModelKey] = useState<string>(defaultModelKey);
  const [language, setLanguage] = useState<string>("Auto");
  const [refText, setRefText] = useState<string>("");
  const [instruct, setInstruct] = useState<string>("");
  const [xVectorOnlyMode, setXVectorOnlyMode] = useState<boolean>(true);

  useEffect(() => {
    if (!isOpen) return;
    setError(null);
    setLoading(false);
    setName(voice?.name || "");
    setModelKey(voice?.model_key || defaultModelKey);
    setLanguage(voice?.language || "Auto");
    setRefText(voice?.ref_text || "");
    setInstruct(voice?.instruct || "");
    setXVectorOnlyMode(Boolean(voice?.x_vector_only_mode));
  }, [isOpen, voice, defaultModelKey]);

  const canSubmit = Boolean(voice?.id) && !loading;

  const handleSubmit = async () => {
    if (!voice?.id) return;
    setLoading(true);
    setError(null);
    try {
      await onSubmit(voice.id, {
        name: name.trim() || undefined,
        model_key: (modelKey || defaultModelKey).trim() || defaultModelKey,
        language: (language || "Auto").trim() || "Auto",
        ref_text: refText.trim() || undefined,
        instruct: instruct.trim() || undefined,
        x_vector_only_mode: Boolean(xVectorOnlyMode),
      });
      onClose();
    } catch (e: any) {
      setError(e?.message || "保存失败");
    } finally {
      setLoading(false);
    }
  };

  if (!isOpen || !voice) return null;

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      <div className="fixed inset-0 bg-black bg-opacity-50 transition-opacity" onClick={loading ? undefined : onClose} />
      <div className="flex items-center justify-center min-h-screen p-4">
        <div className="relative bg-white rounded-lg shadow-xl max-w-lg w-full">
          <div className="flex items-center justify-between p-5 border-b border-gray-200">
            <h3 className="text-lg font-semibold text-gray-900">编辑音色</h3>
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

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div>
                <label className="block text-sm text-gray-700 mb-1">名称</label>
                <input
                  type="text"
                  value={name}
                  disabled={loading}
                  onChange={(e) => setName(e.target.value)}
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
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-200 min-h-[72px]"
              />
            </div>

            <div>
              <label className="block text-sm text-gray-700 mb-1">指令（可选）</label>
              <textarea
                value={instruct}
                disabled={loading}
                onChange={(e) => setInstruct(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-200 min-h-[72px]"
              />
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
                {loading ? <Loader className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                保存
              </span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Qwen3VoiceEditDialog;


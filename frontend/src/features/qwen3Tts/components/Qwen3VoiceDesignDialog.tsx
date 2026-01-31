import React, { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { Loader, Palette, X, Save } from "lucide-react";
import type { Qwen3TtsDesignCloneCreateInput, Qwen3TtsVoice, Qwen3TtsPatchVoiceInput } from "../types";
import { LANGUAGE_OPTIONS } from "../constants";

export type Qwen3VoiceDesignDialogResult = {
  input: Qwen3TtsDesignCloneCreateInput;
};

export type Qwen3VoiceDesignDialogEditResult = {
  edit: true;
  voiceId: string;
  patch: Qwen3TtsPatchVoiceInput;
};

export type Qwen3VoiceDesignDialogProps = {
  isOpen: boolean;
  voiceDesignModelKeys: string[];
  baseModelKeys: string[];
  isModelAvailable?: (key: string) => boolean;
  voice?: Qwen3TtsVoice | null;
  onClose: () => void;
  onSubmit: (result: Qwen3VoiceDesignDialogResult | Qwen3VoiceDesignDialogEditResult) => Promise<void>;
};

export const Qwen3VoiceDesignDialog: React.FC<Qwen3VoiceDesignDialogProps> = ({
  isOpen,
  voiceDesignModelKeys,
  baseModelKeys,
  isModelAvailable,
  voice,
  onClose,
  onSubmit,
}) => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const defaultDesignModelKey = useMemo(() => {
    const keys = voiceDesignModelKeys.length ? voiceDesignModelKeys : ["voice_design_1_7b"];
    if (isModelAvailable) {
      const usable = keys.find((k) => isModelAvailable(k));
      if (usable) return usable;
    }
    return keys[0] || "voice_design_1_7b";
  }, [voiceDesignModelKeys, isModelAvailable]);

  const defaultBaseModelKey = useMemo(() => {
    const keys = baseModelKeys.length ? baseModelKeys : ["base_0_6b"];
    if (isModelAvailable) {
      const usable = keys.find((k) => isModelAvailable(k));
      if (usable) return usable;
    }
    return keys[0] || "base_0_6b";
  }, [baseModelKeys, isModelAvailable]);

  const [name, setName] = useState<string>("");
  const [designModelKey, setDesignModelKey] = useState<string>(defaultDesignModelKey);
  const [baseModelKey, setBaseModelKey] = useState<string>(defaultBaseModelKey);
  const [language, setLanguage] = useState<string>("Auto");
  const [text, setText] = useState<string>("");
  const [instruct, setInstruct] = useState<string>("");

  useEffect(() => {
    if (!isOpen) return;
    setError(null);
    setLoading(false);

    if (voice) {
      setName(voice.name || "");
      const designKey = voice.meta?.voice_design_model_key;
      const initialDesignKey =
        designKey && (!isModelAvailable || isModelAvailable(designKey))
          ? designKey
          : defaultDesignModelKey;
      const baseKey = voice.model_key;
      const initialBaseKey =
        baseKey && (!isModelAvailable || isModelAvailable(baseKey))
          ? baseKey
          : defaultBaseModelKey;
      setDesignModelKey(initialDesignKey);
      setBaseModelKey(initialBaseKey);
      setLanguage(voice.language || "Auto");
      setText(voice.ref_text || "");
      setInstruct(voice.instruct || "");
    } else {
      setName("");
      setDesignModelKey(defaultDesignModelKey);
      setBaseModelKey(defaultBaseModelKey);
      setLanguage("Auto");
      setText("");
      setInstruct("");
    }
  }, [isOpen, voice, defaultDesignModelKey, defaultBaseModelKey, isModelAvailable]);

  const canSubmit = Boolean(name) && Boolean(text) && Boolean(instruct) && !loading;

  const handleSubmit = async () => {
    if (!name || !text || !instruct) {
      setError("请填写所有必填项");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      if (voice) {
        // Edit submit
        const patch: Qwen3TtsPatchVoiceInput = {
          name: name.trim() || undefined,
          model_key: baseModelKey,
          language: (language || "Auto").trim() || "Auto",
          ref_text: text.trim() || undefined,
          instruct: instruct.trim() || undefined,
        };
        await onSubmit({
          edit: true,
          voiceId: voice.id,
          patch,
        });
      } else {
        // Create submit
        await onSubmit({
          input: {
            name: name.trim(),
            model_key: baseModelKey, // The final voice uses the Base model for cloning
            voice_design_model_key: designModelKey, // Used for generating the reference audio
            language: language.trim() || "Auto",
            text: text.trim(),
            instruct: instruct.trim(),
          },
        });
      }
      onClose();
    } catch (e: any) {
      setError(e?.message || (voice ? "保存失败" : "创建失败"));
    } finally {
      setLoading(false);
    }
  };

  if (!isOpen) return null;

  return createPortal(
    <div className="fixed inset-0 z-50 overflow-y-auto">
      <div className="fixed inset-0 bg-black bg-opacity-50 transition-opacity" onClick={loading ? undefined : onClose} />
      <div className="flex items-center justify-center min-h-screen p-4">
        <div className="relative bg-white rounded-lg shadow-xl max-w-lg w-full">
          <div className="flex items-center justify-between p-5 border-b border-gray-200">
            <div className="flex items-center gap-2">
              <Palette className="h-5 w-5 text-indigo-700" />
              <h3 className="text-lg font-semibold text-gray-900">{voice ? "编辑设计音色" : "设计新音色"}</h3>
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
              <label className="block text-sm text-gray-700 mb-1">名称</label>
              <input
                type="text"
                value={name}
                disabled={loading}
                onChange={(e) => setName(e.target.value)}
                placeholder="给新音色起个名"
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-200"
              />
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div>
                <label className="block text-sm text-gray-700 mb-1">设计模型</label>
                <select
                  value={designModelKey}
                  disabled={loading || !!voice} // Disable design model selection during edit if we can't update it
                  onChange={(e) => setDesignModelKey(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md bg-white disabled:bg-gray-100 disabled:text-gray-500"
                >
                  {(voiceDesignModelKeys.length ? voiceDesignModelKeys : [defaultDesignModelKey]).map((k) => (
                    <option key={k} value={k} disabled={isModelAvailable ? !isModelAvailable(k) : false}>
                      {k}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm text-gray-700 mb-1">基底模型</label>
                <select
                  value={baseModelKey}
                  disabled={loading}
                  onChange={(e) => setBaseModelKey(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md bg-white"
                >
                  {(baseModelKeys.length ? baseModelKeys : [defaultBaseModelKey]).map((k) => (
                    <option key={k} value={k} disabled={isModelAvailable ? !isModelAvailable(k) : false}>
                      {k}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div>
              <label className="block text-sm text-gray-700 mb-1">语言</label>
              <select
                value={language}
                disabled={loading}
                onChange={(e) => setLanguage(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-200 bg-white"
              >
                {LANGUAGE_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-sm text-gray-700 mb-1">目标文本</label>
              <textarea
                value={text}
                disabled={loading}
                onChange={(e) => setText(e.target.value)}
                placeholder="输入一段文本，模型将尝试用设计的声音朗读它（生成参考音频）"
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-200 min-h-[72px]"
              />
            </div>

            <div>
              <label className="block text-sm text-gray-700 mb-1">设计指令</label>
              <textarea
                value={instruct}
                disabled={loading}
                onChange={(e) => setInstruct(e.target.value)}
                placeholder="描述想要的声音特征，例如：一个年轻的女性声音，语气欢快，语速稍快..."
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-200 min-h-[72px]"
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
                canSubmit ? "bg-indigo-600 text-white hover:bg-indigo-700" : "bg-gray-300 text-gray-500 cursor-not-allowed"
              }`}
            >
              <span className="inline-flex items-center gap-2">
                {loading ? <Loader className="h-4 w-4 animate-spin" /> : (voice ? <Save className="h-4 w-4" /> : null)}
                {voice ? "保存" : "生成并创建"}
              </span>
            </button>
          </div>
        </div>
      </div>
    </div>,
    document.body
  );
};

export default Qwen3VoiceDesignDialog;

import React, { useEffect, useMemo, useState, useRef } from "react";
import { createPortal } from "react-dom";
import { Loader, Mic2, X, ChevronDown, Check, Save } from "lucide-react";
import { useQwen3Voices } from "../hooks/useQwen3Voices";
import { LANGUAGE_OPTIONS } from "../constants";
import type { Qwen3TtsCustomRoleCreateInput, Qwen3TtsVoice, Qwen3TtsPatchVoiceInput } from "../types";

const SPEAKER_METADATA: Record<string, { name: string; desc: string; lang: string }> = {
  vivian: { name: "Vivian", desc: "明亮、略带锐利感的年轻女声", lang: "中文" },
  serena: { name: "Serena", desc: "温暖柔和的年轻女声", lang: "中文" },
  uncle_fu: { name: "Uncle_Fu", desc: "音色低沉醇厚的成熟男声", lang: "中文" },
  dylan: { name: "Dylan", desc: "清晰自然的北京青年男声", lang: "中文（北京方言）" },
  eric: { name: "Eric", desc: "活泼、略带沙哑明亮感的成都男声", lang: "中文（四川方言）" },
  ryan: { name: "Ryan", desc: "富有节奏感的动态男声", lang: "英语" },
  aiden: { name: "Aiden", desc: "清晰中频、阳光的美式男声", lang: "英语" },
  ono_anna: { name: "Ono_Anna", desc: "轻快灵巧的俏皮日语女声", lang: "日语" },
  sohee: { name: "Sohee", desc: "情感丰富的温暖韩语女声", lang: "韩语" },
};

export type Qwen3CustomRoleDialogResult = {
  input: Qwen3TtsCustomRoleCreateInput;
};

export type Qwen3CustomRoleDialogEditResult = {
  edit: true;
  voiceId: string;
  patch: Qwen3TtsPatchVoiceInput;
};

export type Qwen3CustomRoleDialogProps = {
  isOpen: boolean;
  modelKeys: string[];
  voice?: Qwen3TtsVoice | null;
  onClose: () => void;
  onSubmit: (result: Qwen3CustomRoleDialogResult | Qwen3CustomRoleDialogEditResult) => Promise<void>;
};

export const Qwen3CustomRoleDialog: React.FC<Qwen3CustomRoleDialogProps> = ({ isOpen, modelKeys, voice, onClose, onSubmit }) => {
  const { getCapabilities } = useQwen3Voices();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const defaultModelKey = useMemo(() => modelKeys[0] || "custom_0_6b", [modelKeys]);

  const [name, setName] = useState<string>("");
  const [modelKey, setModelKey] = useState<string>(defaultModelKey);
  const [language, setLanguage] = useState<string>("Auto");
  const [speaker, setSpeaker] = useState<string>("");
  const [instruct, setInstruct] = useState<string>("");

  const [isSpeakerOpen, setIsSpeakerOpen] = useState(false);

  const [supportedSpeakers, setSupportedSpeakers] = useState<string[]>([]);
  const [capabilitiesLoading, setCapabilitiesLoading] = useState(false);

  useEffect(() => {
    if (!isOpen) return;
    setError(null);
    setLoading(false);
    
    if (voice) {
        setName(voice.name || "");
        setModelKey(voice.model_key || defaultModelKey);
        setLanguage(voice.language || "Auto");
        setSpeaker(voice.speaker || "");
        setInstruct(voice.instruct || "");
    } else {
        setName("");
        setModelKey(defaultModelKey);
        setLanguage("Auto");
        setSpeaker("");
        setInstruct("");
    }
  }, [isOpen, voice, defaultModelKey]);

  // Fetch capabilities when modelKey changes
  useEffect(() => {
    if (!isOpen || !modelKey) return;
    const fetchCap = async () => {
      setCapabilitiesLoading(true);
      try {
        const caps = await getCapabilities(modelKey);
        setSupportedSpeakers(caps.speakers || []);
        // Only auto-select if creating new, or if editing but speaker not set (unlikely)
        // If editing, we want to keep existing speaker.
        // If existing speaker is not in supported list (e.g. model changed), maybe we should warn or reset?
        // For now, if we are editing, we trust the state.speaker from useEffect above.
        // But if user changes modelKey manually in edit mode, we might want to reset speaker if invalid.
        if (caps.speakers?.length && !speaker && !voice) {
          setSpeaker(caps.speakers[0]);
        }
      } catch (e) {
        console.error(e);
      } finally {
        setCapabilitiesLoading(false);
      }
    };
    void fetchCap();
  }, [isOpen, modelKey, getCapabilities, voice]);

  const canSubmit = Boolean(name) && Boolean(speaker) && !loading && !capabilitiesLoading;

  const handleSubmit = async () => {
    if (!name || !speaker) {
      setError("请填写名称并选择角色");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      if (voice) {
        await onSubmit({
            edit: true,
            voiceId: voice.id,
            patch: {
                name: name.trim(),
                model_key: modelKey,
                language: language.trim() || "Auto",
                speaker: speaker.trim(),
                instruct: instruct.trim() || undefined,
            }
        });
      } else {
        await onSubmit({
            input: {
            name: name.trim(),
            model_key: modelKey,
            language: language.trim() || "Auto",
            speaker: speaker.trim(),
            instruct: instruct.trim() || undefined,
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
              <Mic2 className="h-5 w-5 text-purple-700" />
              <h3 className="text-lg font-semibold text-gray-900">{voice ? "编辑角色音色" : "创建角色音色"}</h3>
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

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div>
                <label className="block text-sm text-gray-700 mb-1">名称</label>
                <input
                  type="text"
                  value={name}
                  disabled={loading}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="给音色起个名"
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-purple-200"
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
                <select
                  value={language}
                  disabled={loading}
                  onChange={(e) => setLanguage(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-purple-200 bg-white"
                >
                  {LANGUAGE_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </div>
              <div className="relative">
                <label className="block text-sm text-gray-700 mb-1">
                  说话人 {capabilitiesLoading ? <span className="text-xs text-gray-400 font-normal">(加载中...)</span> : null}
                </label>
                <button
                  type="button"
                  disabled={loading || capabilitiesLoading}
                  onClick={() => setIsSpeakerOpen(!isSpeakerOpen)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md bg-white text-left flex items-center justify-between focus:outline-none focus:ring-2 focus:ring-purple-200"
                >
                  <span className={!speaker ? "text-gray-500" : "text-gray-900"}>
                    {speaker ? (
                      <span className="flex items-center gap-2">
                        <span>{SPEAKER_METADATA[speaker] ? SPEAKER_METADATA[speaker].name : speaker}</span>
                        {SPEAKER_METADATA[speaker] && (
                          <span className="text-xs text-gray-500 bg-gray-100 px-1.5 py-0.5 rounded">
                            {SPEAKER_METADATA[speaker].lang}
                          </span>
                        )}
                      </span>
                    ) : (
                      "请选择"
                    )}
                  </span>
                  <ChevronDown className="h-4 w-4 text-gray-400" />
                </button>

                {isSpeakerOpen && (
                  <>
                    <div className="fixed inset-0 z-10" onClick={() => setIsSpeakerOpen(false)} />
                    <div className="absolute z-20 w-full mt-1 bg-white border border-gray-200 rounded-md shadow-lg max-h-60 overflow-y-auto">
                      {supportedSpeakers.map((s) => {
                        const meta = SPEAKER_METADATA[s];
                        return (
                          <div
                            key={s}
                            onClick={() => {
                              setSpeaker(s);
                              setIsSpeakerOpen(false);
                            }}
                            className={`px-3 py-2 cursor-pointer hover:bg-purple-50 transition-colors border-b border-gray-50 last:border-0 ${
                              speaker === s ? "bg-purple-50" : ""
                            }`}
                          >
                            <div className="flex items-center justify-between">
                              <div className="font-medium text-gray-900 flex items-center gap-2">
                                {meta ? meta.name : s}
                                {meta && (
                                  <span className="text-xs text-gray-500 bg-gray-100 px-1.5 py-0.5 rounded font-normal">
                                    {meta.lang}
                                  </span>
                                )}
                              </div>
                              {speaker === s && <Check className="h-4 w-4 text-purple-600" />}
                            </div>
                            {meta && <div className="text-xs text-gray-500 mt-0.5">{meta.desc}</div>}
                          </div>
                        );
                      })}
                      {supportedSpeakers.length === 0 && (
                        <div className="px-3 py-2 text-gray-400 text-sm">暂无可用角色</div>
                      )}
                    </div>
                  </>
                )}
              </div>
            </div>

            <div>
              <label className="block text-sm text-gray-700 mb-1">指令（可选）</label>
              <textarea
                value={instruct}
                disabled={loading}
                onChange={(e) => setInstruct(e.target.value)}
                placeholder="可选的情感/风格指令"
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-purple-200 min-h-[72px]"
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
                canSubmit ? "bg-purple-600 text-white hover:bg-purple-700" : "bg-gray-300 text-gray-500 cursor-not-allowed"
              }`}
            >
              <span className="inline-flex items-center gap-2">
                {loading ? <Loader className="h-4 w-4 animate-spin" /> : (voice ? <Save className="h-4 w-4" /> : null)}
                {voice ? "保存" : "创建"}
              </span>
            </button>
          </div>
        </div>
      </div>
    </div>,
    document.body
  );
};

export default Qwen3CustomRoleDialog;

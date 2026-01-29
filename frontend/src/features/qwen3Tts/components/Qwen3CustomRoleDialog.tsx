import React, { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { Loader, Mic2, X } from "lucide-react";
import { useQwen3Voices } from "../hooks/useQwen3Voices";
import { LANGUAGE_OPTIONS } from "../constants";
import type { Qwen3TtsCustomRoleCreateInput } from "../types";

export type Qwen3CustomRoleDialogResult = {
  input: Qwen3TtsCustomRoleCreateInput;
};

export type Qwen3CustomRoleDialogProps = {
  isOpen: boolean;
  modelKeys: string[];
  onClose: () => void;
  onSubmit: (result: Qwen3CustomRoleDialogResult) => Promise<void>;
};

export const Qwen3CustomRoleDialog: React.FC<Qwen3CustomRoleDialogProps> = ({ isOpen, modelKeys, onClose, onSubmit }) => {
  const { getCapabilities } = useQwen3Voices();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const defaultModelKey = useMemo(() => modelKeys[0] || "custom_0_6b", [modelKeys]);

  const [name, setName] = useState<string>("");
  const [modelKey, setModelKey] = useState<string>(defaultModelKey);
  const [language, setLanguage] = useState<string>("Auto");
  const [speaker, setSpeaker] = useState<string>("");
  const [instruct, setInstruct] = useState<string>("");

  const [supportedSpeakers, setSupportedSpeakers] = useState<string[]>([]);
  const [capabilitiesLoading, setCapabilitiesLoading] = useState(false);

  useEffect(() => {
    if (!isOpen) return;
    setError(null);
    setLoading(false);
    setName("");
    setModelKey(defaultModelKey);
    setLanguage("Auto");
    setSpeaker("");
    setInstruct("");
  }, [isOpen, defaultModelKey]);

  // Fetch capabilities when modelKey changes
  useEffect(() => {
    if (!isOpen || !modelKey) return;
    const fetchCap = async () => {
      setCapabilitiesLoading(true);
      try {
        const caps = await getCapabilities(modelKey);
        setSupportedSpeakers(caps.speakers || []);
        if (caps.speakers?.length && !speaker) {
          setSpeaker(caps.speakers[0]);
        }
      } catch (e) {
        console.error(e);
      } finally {
        setCapabilitiesLoading(false);
      }
    };
    void fetchCap();
  }, [isOpen, modelKey, getCapabilities]);

  const canSubmit = Boolean(name) && Boolean(speaker) && !loading && !capabilitiesLoading;

  const handleSubmit = async () => {
    if (!name || !speaker) {
      setError("请填写名称并选择角色");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      await onSubmit({
        input: {
          name: name.trim(),
          model_key: modelKey,
          language: language.trim() || "Auto",
          speaker: speaker.trim(),
          instruct: instruct.trim() || undefined,
        },
      });
      onClose();
    } catch (e: any) {
      setError(e?.message || "创建失败");
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
              <h3 className="text-lg font-semibold text-gray-900">创建角色音色</h3>
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
              <div>
                <label className="block text-sm text-gray-700 mb-1">
                  说话人 {capabilitiesLoading ? <span className="text-xs text-gray-400 font-normal">(加载中...)</span> : null}
                </label>
                <select
                  value={speaker}
                  disabled={loading || capabilitiesLoading}
                  onChange={(e) => setSpeaker(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md bg-white"
                >
                  {!speaker && <option value="">请选择</option>}
                  {supportedSpeakers.map((s) => (
                    <option key={s} value={s}>
                      {s}
                    </option>
                  ))}
                </select>
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
                {loading ? <Loader className="h-4 w-4 animate-spin" /> : null}
                创建
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

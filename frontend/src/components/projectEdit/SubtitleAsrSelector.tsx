import React, { useEffect, useMemo, useRef } from "react";
import { FUN_ASR_MLT_LANGUAGES, FUN_ASR_NANO_LANGUAGES } from "@/features/subtitleAsr/constants";
import { useFunAsrModels } from "@/features/subtitleAsr/hooks/useFunAsrModels";
import { message } from "@/services/message";

export type SubtitleAsrProvider = "bcut" | "fun_asr";

export type SubtitleAsrSelectorValue = {
  provider: SubtitleAsrProvider;
  modelKey: string;
  language: string;
};

export type SubtitleAsrSelectorProps = {
  value: SubtitleAsrSelectorValue;
  disabled?: boolean;
  onChange: (next: SubtitleAsrSelectorValue) => void;
};

export const SubtitleAsrSelector: React.FC<SubtitleAsrSelectorProps> = ({ value, disabled, onChange }) => {
  const { models, loading } = useFunAsrModels();
  const lastWarnKeyRef = useRef<string>("");

  const provider = value.provider || "bcut";
  const isFun = provider === "fun_asr";

  const funModels = useMemo(() => {
    const order: Record<string, number> = {
      fun_asr_nano_2512: 1,
      fun_asr_mlt_nano_2512: 2,
    };
    return (models || [])
      .filter((m) => String(m?.key || "").startsWith("fun_asr_") && Boolean(m.exists) && Boolean(m.valid))
      .slice()
      .sort((a, b) => (order[a.key] ?? 999) - (order[b.key] ?? 999) || String(a.key).localeCompare(String(b.key)));
  }, [models]);

  const resolvedModelKey = useMemo(() => {
    const cur = String(value.modelKey || "").trim() || "fun_asr_nano_2512";
    if (!isFun) return cur;
    if (funModels.some((m) => m.key === cur)) return cur;
    if (funModels.length > 0) return funModels[0].key;
    return cur;
  }, [funModels, isFun, value.modelKey]);

  const languageOptions = useMemo(() => {
    if (!isFun) return ["中文"];
    const meta = funModels.find((m) => m.key === resolvedModelKey);
    const fromMeta = (meta?.languages || []).filter((x) => String(x || "").trim());
    if (fromMeta.length) return fromMeta;
    if (String(resolvedModelKey).includes("mlt")) return FUN_ASR_MLT_LANGUAGES.length ? FUN_ASR_MLT_LANGUAGES : ["中文"];
    return FUN_ASR_NANO_LANGUAGES;
  }, [funModels, isFun, resolvedModelKey]);

  const normalizedLanguage = languageOptions.includes(value.language) ? value.language : languageOptions[0] || "中文";

  const funAsrSelectable = !loading && funModels.length > 0;

  useEffect(() => {
    if (funModels.length > 0) lastWarnKeyRef.current = "";
  }, [funModels.length]);

  useEffect(() => {
    if (provider !== "fun_asr") return;
    if (loading) return;
    if (funModels.length > 0) return;
    if (lastWarnKeyRef.current === "no_fun_models") return;
    lastWarnKeyRef.current = "no_fun_models";
    message.warning("未检测到可用 FunASR 模型，已自动切换为内置 API（仅中文）");
    onChange({ provider: "bcut", modelKey: value.modelKey || "fun_asr_nano_2512", language: "中文" });
  }, [funModels.length, loading, onChange, provider, value.modelKey]);

  useEffect(() => {
    if (!isFun) return;
    if (!funModels.length) return;
    if (value.modelKey !== resolvedModelKey) {
      onChange({ provider, modelKey: resolvedModelKey, language: normalizedLanguage });
    }
  }, [funModels.length, isFun, normalizedLanguage, onChange, provider, resolvedModelKey, value.modelKey]);

  const setProvider = (p: SubtitleAsrProvider) => {
    const next: SubtitleAsrSelectorValue = {
      provider: p,
      modelKey: resolvedModelKey,
      language: p === "bcut" ? "中文" : normalizedLanguage,
    };
    onChange(next);
  };

  const setModelKey = (k: string) => {
    const meta = funModels.find((m) => m.key === k);
    const metaLangs = (meta?.languages || []).filter((x) => String(x || "").trim());
    const nextLangs = metaLangs.length
      ? metaLangs
      : String(k).includes("mlt")
        ? FUN_ASR_MLT_LANGUAGES.length
          ? FUN_ASR_MLT_LANGUAGES
          : ["中文"]
        : FUN_ASR_NANO_LANGUAGES;
    const next: SubtitleAsrSelectorValue = {
      provider,
      modelKey: k,
      language: nextLangs.includes(normalizedLanguage) ? normalizedLanguage : nextLangs[0] || "中文",
    };
    onChange(next);
  };

  const setLanguage = (lang: string) => {
    onChange({ provider, modelKey: resolvedModelKey, language: lang });
  };

  return (
    <div className="bg-gray-50 border border-gray-200 rounded-lg p-3">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <div>
          <label className="block text-xs text-gray-600 mb-1">识别引擎</label>
          <select
            value={provider}
            disabled={disabled}
            onChange={(e) => setProvider(e.target.value as SubtitleAsrProvider)}
            className="w-full px-3 py-2 border border-gray-300 rounded-md bg-white text-sm"
          >
            <option value="bcut">内置 API（仅中文）</option>
            <option value="fun_asr" disabled={!funAsrSelectable}>
              FunASR（本地模型）
            </option>
          </select>
        </div>

        {isFun && (
          <>
            <div>
              <label className="block text-xs text-gray-600 mb-1">模型</label>
              <select
                value={resolvedModelKey}
                disabled={disabled || loading || funModels.length === 0}
                onChange={(e) => setModelKey(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-md bg-white text-sm disabled:bg-gray-100 disabled:text-gray-500"
                title="选择 FunASR 模型"
              >
                {loading ? (
                  <option value={resolvedModelKey}>加载模型状态中…</option>
                ) : funModels.length === 0 ? (
                  <option value={resolvedModelKey}>暂无可用模型（请先在设置下载并校验）</option>
                ) : (
                  funModels.map((m) => (
                    <option key={m.key} value={m.key}>
                      {m.display_name || m.key}
                    </option>
                  ))
                )}
              </select>
            </div>

            <div>
              <label className="block text-xs text-gray-600 mb-1">语言</label>
              <select
                value={normalizedLanguage}
                disabled={disabled || loading || funModels.length === 0}
                onChange={(e) => setLanguage(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-md bg-white text-sm disabled:bg-gray-100 disabled:text-gray-500"
                title="选择识别语言"
              >
                {languageOptions.map((x) => (
                  <option key={x} value={x}>
                    {x}
                  </option>
                ))}
              </select>
            </div>
          </>
        )}
      </div>

      <div className="mt-2 text-[11px] text-gray-600">
        {provider === "bcut"
          ? "内置 API 识别字幕只支持中文。"
          : loading
            ? "正在加载本地模型状态…"
            : funModels.length === 0
              ? "未检测到可用 FunASR 模型：请先在「设置-字幕识别」下载并校验模型。"
              : "将使用已校验的本地 FunASR 模型进行识别。"}
      </div>
    </div>
  );
};

export default SubtitleAsrSelector;

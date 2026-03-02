import React, { useMemo } from "react";
import { FUN_ASR_MLT_LANGUAGES, FUN_ASR_NANO_LANGUAGES } from "@/features/subtitleAsr/constants";

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
  const provider = value.provider || "bcut";
  const modelKey = value.modelKey || "fun_asr_nano_2512";
  const isFun = provider === "fun_asr";

  const languageOptions = useMemo(() => {
    if (!isFun) return ["中文"];
    if (String(modelKey).includes("mlt")) return FUN_ASR_MLT_LANGUAGES.length ? FUN_ASR_MLT_LANGUAGES : ["中文"];
    return FUN_ASR_NANO_LANGUAGES;
  }, [isFun, modelKey]);

  const normalizedLanguage = languageOptions.includes(value.language) ? value.language : languageOptions[0] || "中文";

  const setProvider = (p: SubtitleAsrProvider) => {
    const next: SubtitleAsrSelectorValue = {
      provider: p,
      modelKey,
      language: p === "bcut" ? "中文" : normalizedLanguage,
    };
    onChange(next);
  };

  const setModelKey = (k: string) => {
    const nextLangs = String(k).includes("mlt") ? (FUN_ASR_MLT_LANGUAGES.length ? FUN_ASR_MLT_LANGUAGES : ["中文"]) : FUN_ASR_NANO_LANGUAGES;
    const next: SubtitleAsrSelectorValue = {
      provider,
      modelKey: k,
      language: nextLangs.includes(normalizedLanguage) ? normalizedLanguage : nextLangs[0] || "中文",
    };
    onChange(next);
  };

  const setLanguage = (lang: string) => {
    onChange({ provider, modelKey, language: lang });
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
            <option value="fun_asr">FunASR（本地模型）</option>
          </select>
        </div>

        {isFun && (
          <>
            <div>
              <label className="block text-xs text-gray-600 mb-1">模型</label>
              <select
                value={modelKey}
                disabled={disabled}
                onChange={(e) => setModelKey(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-md bg-white text-sm disabled:bg-gray-100 disabled:text-gray-500"
                title="选择 FunASR 模型"
              >
                <option value="fun_asr_nano_2512">Fun-ASR-Nano-2512</option>
                <option value="fun_asr_mlt_nano_2512">Fun-ASR-MLT-Nano-2512</option>
              </select>
            </div>

            <div>
              <label className="block text-xs text-gray-600 mb-1">语言</label>
              <select
                value={normalizedLanguage}
                disabled={disabled}
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
          : "使用 FunASR 需要先在「设置-字幕识别」下载并校验模型。"}
      </div>
    </div>
  );
};

export default SubtitleAsrSelector;


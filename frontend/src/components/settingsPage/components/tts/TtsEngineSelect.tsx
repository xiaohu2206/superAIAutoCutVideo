import React from "react";
import type { TtsEngineMeta } from "../../types";

interface Props {
  engines: TtsEngineMeta[];
  provider: string;
  onProviderChange: (provider: string) => void;
}

export const TtsEngineSelect: React.FC<Props> = ({ engines, provider, onProviderChange }) => {
  const handleChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    onProviderChange(e.target.value);
  };

  const current = engines.find((e) => e.provider === provider);

  return (
    <div>
      <h4 className="text-md font-semibold text-gray-900 mb-2">引擎选择</h4>
      <div className="flex items-center gap-3">
        <select
          className="px-3 py-2 border border-gray-300 rounded-md"
          value={provider}
          onChange={handleChange}
        >
          {engines.map((eng) => (
            <option key={eng.provider} value={eng.provider}>{eng.display_name}</option>
          ))}
          {engines.length === 0 && (
            <option value="tencent_tts">腾讯云 TTS</option>
          )}
        </select>
        {current && (
          <span className="text-gray-500 text-sm">{current.display_name}</span>
        )}
      </div>
      <p className="text-gray-700 text-sm mt-3">
        {current?.description || "请选择引擎；部分引擎需配置密钥。"}
      </p>
    </div>
  );
};

export default TtsEngineSelect;
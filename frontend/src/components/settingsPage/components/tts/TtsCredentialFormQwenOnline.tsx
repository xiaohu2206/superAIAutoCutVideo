import { KeyRound, Loader, ShieldAlert, ShieldCheck } from "lucide-react";
import React, { useEffect, useState } from "react";
import { TauriCommands } from "@/services/clients";
import type { TtsEngineConfig, TtsTestResult } from "../../types";

interface Props {
  configId: string | null;
  config?: TtsEngineConfig;
  hasCredentials: boolean;
  onUpdate: (partial: Partial<TtsEngineConfig>) => Promise<void> | void;
  onTest: () => Promise<void> | void;
  testing: boolean;
  testDurationMs: number | null;
  testResult: TtsTestResult | null;
}

export const TtsCredentialFormQwenOnline: React.FC<Props> = ({
  configId,
  config,
  hasCredentials,
  onUpdate,
  onTest,
  testing,
  testDurationMs,
  testResult,
}) => {
  const [apiKeyInput, setApiKeyInput] = useState<string>("");
  const [modelInput, setModelInput] = useState<string>("");
  const [languageInput, setLanguageInput] = useState<string>("");
  const [instructionsInput, setInstructionsInput] = useState<string>("");
  const [optimizeInstructionsInput, setOptimizeInstructionsInput] =
    useState<boolean>(false);
  const [baseUrlInput, setBaseUrlInput] = useState<string>("");

  useEffect(() => {
    setApiKeyInput(config?.secret_key === "***" ? "****" : "");
    const ep = config?.extra_params || {};
    setModelInput((ep.Model as string) || "");
    setLanguageInput((ep.LanguageType as string) || "");
    setInstructionsInput((ep.Instructions as string) || "");
    setOptimizeInstructionsInput(Boolean(ep.OptimizeInstructions));
    setBaseUrlInput((ep.BaseUrl as string) || "");
  }, [configId, config]);

  const handleBlurApiKey = async () => {
    const trimmed = apiKeyInput.trim();
    if (!trimmed) {
      if (config?.secret_key === "***") setApiKeyInput("****");
      return;
    }
    if (trimmed === "****") return;
    await onUpdate({ secret_key: trimmed });
    setApiKeyInput("****");
  };

  const handleBlurExtraParams = async () => {
    const ep: Record<string, any> = {};
    if (modelInput.trim()) ep.Model = modelInput.trim();
    if (languageInput.trim()) ep.LanguageType = languageInput.trim();
    if (instructionsInput.trim()) ep.Instructions = instructionsInput.trim();
    ep.OptimizeInstructions = optimizeInstructionsInput;
    if (baseUrlInput.trim()) ep.BaseUrl = baseUrlInput.trim();
    await onUpdate({ extra_params: ep });
  };

  return (
    <div>
      <h4 className="text-md font-semibold text-gray-900 mb-2">凭据设置</h4>
      <p className="text-gray-600 text-sm mb-4">
        为保障安全，API Key 仅展示设置状态，不显示明文。
      </p>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
        <div>
          <div className="flex items-center justify-between mb-1">
            <label className="block text-sm text-gray-700">
              DashScope API Key
            </label>
            <button
              type="button"
              onClick={() =>
                TauriCommands.openExternalLink(
                  "https://bailian.console.aliyun.com/cn-beijing/",
                )
              }
              className="text-sm text-blue-600 hover:text-blue-800 hover:underline cursor-pointer"
            >
              获取API Key
            </button>
          </div>
          <div className="flex items-center gap-2">
            <input
              type="password"
              value={apiKeyInput}
              placeholder={config?.secret_key === "***" ? "已设置" : "未设置"}
              onChange={(e) => setApiKeyInput(e.target.value)}
              onBlur={handleBlurApiKey}
              className="px-3 py-2 border border-gray-300 rounded-md w-full"
            />
            {config?.secret_key === "***" ? (
              <ShieldCheck className="h-5 w-5 text-green-600" />
            ) : (
              <ShieldAlert className="h-5 w-5 text-orange-600" />
            )}
          </div>
        </div>
              <div>
          <label className="block text-sm text-gray-700 mb-1">
            LanguageType（可选）
          </label>
          <select
            value={languageInput}
            onChange={(e) => setLanguageInput(e.target.value)}
            onBlur={handleBlurExtraParams}
            className="px-3 py-2 border border-gray-300 rounded-md w-full"
          >
            <option value="Auto">Auto（自动）</option>
            <option value="Chinese">Chinese（中文）</option>
            <option value="English">English（英语）</option>
            <option value="German">German（德语）</option>
            <option value="Italian">Italian（意大利语）</option>
            <option value="Portuguese">Portuguese（葡萄牙语）</option>
            <option value="Spanish">Spanish（西班牙语）</option>
            <option value="Japanese">Japanese（日语）</option>
            <option value="Korean">Korean（韩语）</option>
            <option value="French">French（法语）</option>
            <option value="Russian">Russian（俄语）</option>
          </select>
        </div>
        {/* <div>
          <label className="block text-sm text-gray-700 mb-1">
            Model（可选）
          </label>
          <select
            value={modelInput}
            onChange={(e) => setModelInput(e.target.value)}
            onBlur={handleBlurExtraParams}
            className="px-3 py-2 border border-gray-300 rounded-md w-full"
          >
            <option value="">默认</option>
            {QWEN_ONLINE_TTS_MODELS.map((m) => (
              <option key={m.value} value={m.value}>
                {m.label}
              </option>
            ))}
          </select>
        </div> */}
      </div>

     

      {/* <div className="mb-4">
        <label className="block text-sm text-gray-700 mb-1">
          Instructions（可选）
        </label>
        <textarea
          value={instructionsInput}
          placeholder="自定义音色指令"
          onChange={(e) => setInstructionsInput(e.target.value)}
          onBlur={handleBlurExtraParams}
          rows={2}
          className="px-3 py-2 border border-gray-300 rounded-md w-full"
        />
      </div> */}

      <div className="flex items-center gap-6 mb-4">
        <label className="flex items-center gap-2 text-sm text-gray-700">
          <input
            type="checkbox"
            checked={optimizeInstructionsInput}
            onChange={(e) => {
              setOptimizeInstructionsInput(e.target.checked);
              setTimeout(handleBlurExtraParams, 0);
            }}
            className="rounded border-gray-300"
          />
          OptimizeInstructions
        </label>

        {/* <div className="flex-1">
          <label className="block text-sm text-gray-700 mb-1">
            BaseUrl（可选，覆盖默认）
          </label>
          <input
            type="text"
            value={baseUrlInput}
            placeholder="如 https://dashscope.aliyuncs.com/api/v1"
            onChange={(e) => setBaseUrlInput(e.target.value)}
            onBlur={handleBlurExtraParams}
            className="px-3 py-2 border border-gray-300 rounded-md w-full"
          />
        </div> */}
      </div>

      <div className="flex items-center gap-3">
        {/* <button
          className={`inline-flex items-center px-3 py-2 rounded-md text-sm ${
            testing || !hasCredentials || !configId
              ? "bg-gray-200 text-gray-500 cursor-not-allowed"
              : "bg-gray-100 hover:bg-gray-200 text-gray-800"
          }`}
          onClick={() => onTest()}
          disabled={testing || !hasCredentials || !configId}
          title={hasCredentials ? "测试连通性" : "请先填写并保存 API Key"}
        >
          {testing ? (
            <Loader className="h-4 w-4 mr-1 animate-spin" />
          ) : (
            <KeyRound className="h-4 w-4 mr-1" />
          )}
          测试连通性
        </button> */}

        {testResult && (
          <div
            className={`inline-flex items-center text-sm ${
              testResult.success ? "text-green-600" : "text-red-600"
            }`}
          >
            {testResult.success ? (
              <ShieldCheck className="h-4 w-4 mr-1" />
            ) : (
              <ShieldAlert className="h-4 w-4 mr-1" />
            )}
            {testResult.success
              ? `已连接千问在线 TTS（响应 ${testDurationMs ?? "--"}ms）`
              : `${testResult.message || "鉴权失败，请检查 API Key"}`}
          </div>
        )}
      </div>
    </div>
  );
};

export default TtsCredentialFormQwenOnline;

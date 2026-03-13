const fs = require("fs");
const path = require("path");

const filePath = path.join(
  __dirname,
  "src/components/settingsPage/components/models/content/ContentModelSettings.tsx"
);

const content = `import { TauriCommands } from "@/services/clients";
import {
  AlertCircle,
  CheckCircle,
  ChevronDown,
  ChevronRight,
  ExternalLink,
  Eye,
  EyeOff,
} from "lucide-react";
import React from "react";
import type {
  ContentModelConfig,
  ProviderCapabilities,
  TestResult,
} from "../../../types";

interface ContentModelSettingsProps {
  contentSelectedProvider: string;
  currentContentConfig: ContentModelConfig;
  setCurrentContentConfig: React.Dispatch<
    React.SetStateAction<ContentModelConfig>
  >;
  testingContentConnection: boolean;
  contentTestResult: TestResult | null;
  contentTestStructured: string | null;
  showContentPassword: boolean;
  setShowContentPassword: React.Dispatch<React.SetStateAction<boolean>>;
  handleContentProviderChange: (provider: string) => void;
  updateCurrentContentConfig: (field: string, value: any) => void;
  testContentModelConnection: () => void;
  currentCapabilities: ProviderCapabilities | null;
  showAdvanced: boolean;
  setShowAdvanced: React.Dispatch<React.SetStateAction<boolean>>;
}

/**
 * 文案生成模型设置组件
 */
export const ContentModelSettings: React.FC<ContentModelSettingsProps> = ({
  contentSelectedProvider,
  currentContentConfig,
  setCurrentContentConfig,
  testingContentConnection,
  contentTestResult,
  contentTestStructured,
  showContentPassword,
  setShowContentPassword,
  handleContentProviderChange,
  updateCurrentContentConfig,
  testContentModelConnection,
  currentCapabilities,
  showAdvanced,
  setShowAdvanced,
}) => {
  const providerLinks: Record<string, string> = {
    "302ai": "https://302.ai/apis/list",
    qwen: "https://bailian.console.aliyun.com/cn-beijing/?spm=5176.28197619.console-base_search-panel.dvisited_sfm.20d53ae4f6I5R3&tab=model#/api-key",
    doubao:
      "https://console.volcengine.com/ark/region:ark+cn-beijing/apiKey?apikey=%7B%7D",
    openrouter: "https://openrouter.ai/settings/keys",
  };
  const providerLink = providerLinks[contentSelectedProvider];

  const extraParams = currentContentConfig.extra_params || {};

  const updateExtraParam = (key: string, value: any) => {
    const newExtra = { ...extraParams, [key]: value };
    setCurrentContentConfig((prev) => ({ ...prev, extra_params: newExtra }));
    updateCurrentContentConfig("extra_params", newExtra);
  };

  const removeExtraParam = (key: string) => {
    const newExtra = { ...extraParams };
    delete newExtra[key];
    setCurrentContentConfig((prev) => ({ ...prev, extra_params: newExtra }));
    updateCurrentContentConfig("extra_params", newExtra);
  };

  const thinkingValue = extraParams.thinking;
  const isThinkingEnabled =
    thinkingValue === true ||
    (typeof thinkingValue === "object" &&
      thinkingValue?.type &&
      ["enabled", "enable", "on", "true"].includes(
        String(thinkingValue.type).toLowerCase()
      ));

  const responseFormatValue = extraParams.response_format;
  const currentResponseFormat =
    typeof responseFormatValue === "object"
      ? responseFormatValue?.type || "none"
      : "none";

  return (
    <div className="space-y-6">
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">
          选择模型提供商
        </label>
        <select
          value={contentSelectedProvider}
          onChange={(e) => handleContentProviderChange(e.target.value)}
          className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <option value="302ai">302平台 (302.AI)</option>
          <option value="qwen">通义千问 (Qwen)</option>
          <option value="doubao">豆包 (Doubao)</option>
          <option value="deepseek">DeepSeek</option>
          <option value="openrouter">OpenRouter</option>
        </select>
        <p className="text-xs text-gray-500 mt-1">
          选择用于文案生成的AI模型提供商
        </p>
        {providerLink && (
          <button
            type="button"
            onClick={() => TauriCommands.openExternalLink(providerLink)}
            className="mt-2 inline-flex items-center text-xs text-blue-600 hover:text-blue-800 hover:underline"
          >
            <ExternalLink className="h-3 w-3 mr-1" />
            前往获取API密钥
          </button>
        )}
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">
          API密钥
        </label>
        <div className="relative">
          <input
            type={showContentPassword ? "text" : "password"}
            value={currentContentConfig.api_key}
            onChange={(e) =>
              setCurrentContentConfig((prev) => ({
                ...prev,
                api_key: e.target.value,
              }))
            }
            onBlur={(e) =>
              updateCurrentContentConfig("api_key", e.target.value)
            }
            placeholder="请输入API密钥"
            className="w-full px-3 py-2 pr-10 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <button
            type="button"
            onClick={() => setShowContentPassword(!showContentPassword)}
            className="absolute inset-y-0 right-0 pr-3 flex items-center text-gray-400 hover:text-gray-600 focus:outline-none"
          >
            {showContentPassword ? (
              <EyeOff className="h-4 w-4" />
            ) : (
              <Eye className="h-4 w-4" />
            )}
          </button>
        </div>
        <p className="text-xs text-gray-500 mt-1">
          从模型提供商获取的API密钥（需自己获取）
        </p>
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">
          接口地址
        </label>
        <input
          type="text"
          value={currentContentConfig.base_url}
          onChange={(e) =>
            setCurrentContentConfig((prev) => ({
              ...prev,
              base_url: e.target.value,
            }))
          }
          onBlur={(e) =>
            updateCurrentContentConfig("base_url", e.target.value)
          }
          placeholder="请输入接口地址"
          className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <p className="text-xs text-gray-500 mt-1">
          模型API的基础URL地址，切换提供商后自动填充默认值
        </p>
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">
          模型名称
        </label>
        <input
          type="text"
          value={currentContentConfig.model_name}
          onChange={(e) =>
            setCurrentContentConfig((prev) => ({
              ...prev,
              model_name: e.target.value,
            }))
          }
          onBlur={(e) =>
            updateCurrentContentConfig("model_name", e.target.value)
          }
          placeholder="请输入模型名称"
          className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <p className="text-xs text-gray-500 mt-1">具体的模型版本名称</p>
      </div>

      <div className="border rounded-lg">
        <button
          type="button"
          onClick={() => setShowAdvanced(!showAdvanced)}
          className="w-full flex items-center justify-between px-4 py-3 text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors rounded-lg"
        >
          <span>高级参数</span>
          {showAdvanced ? (
            <ChevronDown className="h-4 w-4 text-gray-400" />
          ) : (
            <ChevronRight className="h-4 w-4 text-gray-400" />
          )}
        </button>

        {showAdvanced && (
          <div className="px-4 pb-4 space-y-4 border-t">
            {currentCapabilities?.temperature !== false && (
              <div className="pt-4">
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  温度 (Temperature)
                  <span className="ml-2 text-xs font-normal text-gray-400">
                    {currentContentConfig.temperature ?? 0.7}
                  </span>
                </label>
                <input
                  type="range"
                  min="0"
                  max="2"
                  step="0.1"
                  value={currentContentConfig.temperature ?? 0.7}
                  onChange={(e) => {
                    const val = parseFloat(e.target.value);
                    setCurrentContentConfig((prev) => ({
                      ...prev,
                      temperature: val,
                    }));
                  }}
                  onMouseUp={(e) =>
                    updateCurrentContentConfig(
                      "temperature",
                      parseFloat((e.target as HTMLInputElement).value)
                    )
                  }
                  className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-blue-500"
                />
                <div className="flex justify-between text-xs text-gray-400 mt-1">
                  <span>精确</span>
                  <span>创意</span>
                </div>
              </div>
            )}

            {currentCapabilities?.max_tokens !== false && (
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  最大输出长度 (Max Tokens)
                </label>
                <input
                  type="number"
                  min="1"
                  max="128000"
                  value={currentContentConfig.max_tokens ?? ""}
                  onChange={(e) => {
                    const val = e.target.value
                      ? parseInt(e.target.value)
                      : undefined;
                    setCurrentContentConfig((prev) => ({
                      ...prev,
                      max_tokens: val,
                    }));
                  }}
                  onBlur={(e) => {
                    const val = e.target.value
                      ? parseInt(e.target.value)
                      : null;
                    updateCurrentContentConfig("max_tokens", val);
                  }}
                  placeholder="留空使用模型默认值"
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
                <p className="text-xs text-gray-500 mt-1">
                  限制模型单次回复的最大 token 数，留空则使用模型默认值
                </p>
              </div>
            )}

            {currentCapabilities?.thinking && (
              <div className="flex items-center justify-between">
                <div>
                  <span className="text-sm font-medium text-gray-700">
                    深度思考 (Thinking)
                  </span>
                  <p className="text-xs text-gray-500 mt-0.5">
                    启用后模型会进行更深入的推理，可能增加延迟和费用
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => {
                    if (isThinkingEnabled) {
                      removeExtraParam("thinking");
                    } else {
                      updateExtraParam("thinking", { type: "enabled" });
                    }
                  }}
                  className={\`relative inline-flex h-6 w-11 items-center rounded-full transition-colors \${isThinkingEnabled ? "bg-blue-500" : "bg-gray-300"}\`}
                >
                  <span
                    className={\`inline-block h-4 w-4 transform rounded-full bg-white transition-transform \${isThinkingEnabled ? "translate-x-6" : "translate-x-1"}\`}
                  />
                </button>
              </div>
            )}

            {(currentCapabilities?.json_object ||
              currentCapabilities?.json_schema) && (
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  结构化输出 (Response Format)
                </label>
                <select
                  value={currentResponseFormat}
                  onChange={(e) => {
                    const val = e.target.value;
                    if (val === "none") {
                      removeExtraParam("response_format");
                    } else {
                      updateExtraParam("response_format", { type: val });
                    }
                  }}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  <option value="none">不限制</option>
                  {currentCapabilities?.json_object && (
                    <option value="json_object">JSON Object</option>
                  )}
                  {currentCapabilities?.json_schema && (
                    <option value="json_schema">JSON Schema</option>
                  )}
                </select>
                <p className="text-xs text-gray-500 mt-1">
                  强制模型以指定格式输出，适用于需要结构化数据的场景
                </p>
              </div>
            )}

            {currentCapabilities && (
              <div className="pt-2">
                <p className="text-xs font-medium text-gray-500 mb-2">
                  当前提供商支持的能力
                </p>
                <div className="flex flex-wrap gap-2">
                  {Object.entries(currentCapabilities).map(([key, val]) => (
                    <span
                      key={key}
                      className={\`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium \${val ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-400"}\`}
                    >
                      {key}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      <div className="pt-4 border-t">
        <button
          onClick={testContentModelConnection}
          disabled={testingContentConnection || !currentContentConfig.api_key}
          className="w-full px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {testingContentConnection ? "测试中..." : "测试连接"}
        </button>

        {contentTestResult && (
          <div
            className={\`mt-3 p-3 rounded-lg flex items-center \${contentTestResult.success ? "bg-green-50 text-green-700" : "bg-red-50 text-red-700"}\`}
          >
            {contentTestResult.success ? (
              <CheckCircle className="h-5 w-5 mr-2 flex-shrink-0" />
            ) : (
              <AlertCircle className="h-5 w-5 mr-2 flex-shrink-0" />
            )}
            <span className="text-sm">{contentTestResult.message}</span>
          </div>
        )}

        {contentTestStructured && (
          <div className="mt-3 p-3 rounded-lg bg-gray-50 text-gray-800 border border-gray-200">
            <p className="text-xs font-medium text-gray-600 mb-2">
              结构化输出预览
            </p>
            <pre className="text-xs overflow-auto max-h-48 whitespace-pre-wrap break-words">
              {contentTestStructured}
            </pre>
          </div>
        )}
      </div>
    </div>
  );
};
`;

fs.writeFileSync(filePath, content, "utf8");
console.log("File written successfully, lines:", content.split("\\n").length);

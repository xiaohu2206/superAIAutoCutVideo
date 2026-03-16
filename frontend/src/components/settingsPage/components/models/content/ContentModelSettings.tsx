import { TauriCommands } from "@/services/clients";
import { message } from "@/services/message";
import { AlertCircle, CheckCircle, ExternalLink, Eye, EyeOff } from "lucide-react";
import React from "react";
import type { ContentModelConfig, TestResult } from "../../../types";

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
}) => {
  const apiKeyBeforeEditRef = React.useRef<string>(currentContentConfig.api_key);
  const modelNameBeforeEditRef = React.useRef<string>(
    currentContentConfig.model_name
  );
  const providerLinks: Record<string, string> = {
    yunwu: "https://yunwu.apifox.cn/api-232421924",
    "302ai": "https://302.ai/apis/list",
    qwen: "https://bailian.console.aliyun.com/cn-beijing/?spm=5176.28197619.console-base_search-panel.dvisited_sfm.20d53ae4f6I5R3&tab=model#/api-key",
    doubao: "https://console.volcengine.com/ark/region:ark+cn-beijing/apiKey?apikey=%7B%7D",
    openrouter: "https://openrouter.ai/settings/keys",
  };
  const providerLink = providerLinks[contentSelectedProvider];
  return (
    <div className="space-y-6">
      {/* 模型选择 */}
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
          <option value="yunwu">云雾API平台 (Yunwu.AI)</option>
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

      {/* API密钥 */}
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
            onFocus={(e) => {
              apiKeyBeforeEditRef.current = e.target.value;
            }}
            onBlur={(e) => {
              const trimmed = e.target.value.trim();
              if (!trimmed) {
                setCurrentContentConfig((prev) => ({
                  ...prev,
                  api_key: apiKeyBeforeEditRef.current,
                }));
                message.warning("API密钥不能为空");
                return;
              }
              if (trimmed === apiKeyBeforeEditRef.current) return;
              updateCurrentContentConfig("api_key", trimmed);
            }}
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
        <p className="text-xs text-gray-500 mt-1">从模型提供商获取的API密钥（需自己获取）</p>
      </div>

      {/* 接口地址 */}
      {/* <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">
          大模型接口地址
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
          onBlur={(e) => updateCurrentContentConfig("base_url", e.target.value)}
          placeholder="请输入接口地址"
          className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <p className="text-xs text-gray-500 mt-1">模型API的基础URL地址</p>
      </div> */}

      {/* 模型名称 */}
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">
          大模型名称
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
          onFocus={(e) => {
            modelNameBeforeEditRef.current = e.target.value;
          }}
          onBlur={(e) => {
            const trimmed = e.target.value.trim();
            if (!trimmed) {
              setCurrentContentConfig((prev) => ({
                ...prev,
                model_name: modelNameBeforeEditRef.current,
              }));
              message.warning("模型名称不能为空");
              return;
            }
            if (trimmed === modelNameBeforeEditRef.current) return;
            updateCurrentContentConfig("model_name", trimmed);
          }}
          placeholder="请输入模型名称"
          className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <p className="text-xs text-gray-500 mt-1">具体的模型版本名称</p>
      </div>

      {/* 测试连接 */}
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
            className={`mt-3 p-3 rounded-lg flex items-center ${
              contentTestResult.success
                ? "bg-green-50 text-green-700"
                : "bg-red-50 text-red-700"
            }`}
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

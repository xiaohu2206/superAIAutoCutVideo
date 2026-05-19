import {
  AlertCircle,
  Check,
  CheckCircle,
  ChevronDown,
} from "lucide-react";
import React, {
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import AppSelect from "@/components/ui/AppSelect";
import type { TestResult, VideoModelConfig } from "../../../types";
import { getVideoVisionModelOptions } from "../../../utils";
import { MoondreamLocalModelPanel } from "@/features/visionModel/components/MoondreamLocalModelPanel";

interface VideoModelSettingsProps {
  selectedProvider: string;
  currentConfig: VideoModelConfig;
  setCurrentConfig: React.Dispatch<React.SetStateAction<VideoModelConfig>>;
  testingConnection: boolean;
  testResult: TestResult | null;
  handleProviderChange: (provider: string) => void;
  updateCurrentConfig: (field: string, value: any) => void;
  testModelConnection: () => void;
}

type ModelType = "online" | "local";

const MODEL_PROVIDERS = [
  { id: "yunwu", label: "云雾API平台 (Yunwu.AI)", type: "online" as ModelType },
  { id: "302ai", label: "302平台 (302.AI)", type: "online" as ModelType },
  { id: "qwen", label: "阿里百炼", type: "online" as ModelType },
  { id: "doubao", label: "火山引擎（不建议用）", type: "online" as ModelType },
  {
    id: "custom_openai_vision",
    label: "自定义模型（OpenAI 兼容）",
    type: "online" as ModelType,
  },
  { id: "moondream", label: "Moondream2 (本地)", type: "local" as ModelType },
];

export const VideoModelSettings: React.FC<VideoModelSettingsProps> = ({
  selectedProvider,
  currentConfig,
  setCurrentConfig,
  testingConnection,
  testResult,
  handleProviderChange,
  updateCurrentConfig,
  testModelConnection,
}) => {
  const [modelNameDropdownOpen, setModelNameDropdownOpen] = useState(false);
  const modelNameDropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        modelNameDropdownRef.current &&
        !modelNameDropdownRef.current.contains(event.target as Node)
      ) {
        setModelNameDropdownOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const visionModelPresetOptions = useMemo(
    () => getVideoVisionModelOptions(selectedProvider),
    [selectedProvider],
  );

  const currentProvider = MODEL_PROVIDERS.find(
    (p) => p.id === selectedProvider,
  );
  const isLocalModel = currentProvider?.type === "local";

  return (
    <div className="space-y-6">
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">
          选择模型
        </label>
        <AppSelect
          value={selectedProvider}
          onChange={(e) => handleProviderChange(e.target.value)}
        >
          {MODEL_PROVIDERS.map((provider) => (
            <option key={provider.id} value={provider.id}>
              {provider.label}
            </option>
          ))}
        </AppSelect>
        <p className="text-xs text-gray-500 mt-1">
          {isLocalModel
            ? "选择本地视觉分析模型（不支持全感知推理）"
            : selectedProvider === "custom_openai_vision"
              ? "自定义端点需支持 OpenAI 格式图文消息（image_url + text），用于抽帧后的画面描述"
              : "选择用于视频生成的AI模型提供商 （视频模型可能消耗巨大，请谨慎使用）"}
             
        </p>
      </div>


      {isLocalModel ? (
        <MoondreamLocalModelPanel />
      ) : (
        <div className="space-y-6">
          {selectedProvider === "custom_openai_vision" && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                大模型接口地址
              </label>
              <input
                type="text"
                value={currentConfig.base_url}
                onChange={(e) =>
                  setCurrentConfig((prev) => ({
                    ...prev,
                    base_url: e.target.value,
                  }))
                }
                onBlur={(e) =>
                  updateCurrentConfig("base_url", e.target.value.trim())
                }
                placeholder="https://api.openai.com/v1/chat/completions"
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <p className="text-xs text-gray-500 mt-1">
                Chat Completions 完整 URL；未以 /chat/completions 结尾时会自动补全
              </p>
            </div>
          )}

          {selectedProvider === "custom_openai_vision" && (
            <div>
              <label className="flex items-center gap-3 text-sm font-medium text-gray-700">
                <input
                  type="checkbox"
                  checked={Boolean(currentConfig.stream_output)}
                  onChange={(e) =>
                    void updateCurrentConfig("stream_output", e.target.checked)
                  }
                  className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                />
                <span>开启流式输出（失败尝试勾选）</span>
              </label>
            </div>
          )}

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              API密钥
            </label>
            <input
              type="text"
              value={currentConfig.api_key}
              onChange={(e) =>
                setCurrentConfig((prev) => ({
                  ...prev,
                  api_key: e.target.value,
                }))
              }
              onBlur={(e) => updateCurrentConfig("api_key", e.target.value)}
              placeholder="请输入API密钥"
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <p className="text-xs text-gray-500 mt-1">
              从模型提供商获取的API密钥
            </p>
          </div>

          <div ref={modelNameDropdownRef} className="relative">
            <label className="block text-sm font-medium text-gray-700 mb-2">
              大模型名称
            </label>
            <div className="relative">
              <input
                type="text"
                value={currentConfig.model_name}
                onChange={(e) =>
                  setCurrentConfig((prev) => ({
                    ...prev,
                    model_name: e.target.value,
                  }))
                }
                onFocus={() => setModelNameDropdownOpen(true)}
                onBlur={(e) => updateCurrentConfig("model_name", e.target.value)}
                placeholder="输入或选择模型名称"
                className="w-full px-3 py-2 pr-8 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              {visionModelPresetOptions.length > 0 ? (
                <button
                  type="button"
                  onClick={() =>
                    setModelNameDropdownOpen(!modelNameDropdownOpen)
                  }
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 p-1 rounded-full hover:bg-gray-100 transition-colors"
                  aria-expanded={modelNameDropdownOpen}
                  aria-label="展开预设模型列表"
                >
                  <ChevronDown
                    className={`h-4 w-4 transition-transform duration-200 ${
                      modelNameDropdownOpen ? "rotate-180" : ""
                    }`}
                  />
                </button>
              ) : null}
            </div>

            {modelNameDropdownOpen && visionModelPresetOptions.length > 0 ? (
              <ul className="absolute z-10 w-full mt-1 bg-white border border-gray-200 rounded-md shadow-lg max-h-60 overflow-auto py-1">
                {visionModelPresetOptions.map((m) => {
                  const isSelected = currentConfig.model_name === m.value;
                  return (
                    <li
                      key={m.value}
                      onMouseDown={(e) => e.preventDefault()}
                      onClick={() => {
                        setCurrentConfig((prev) => ({
                          ...prev,
                          model_name: m.value,
                        }));
                        void updateCurrentConfig("model_name", m.value);
                        setModelNameDropdownOpen(false);
                      }}
                      className={`
                          px-3 py-2 text-sm cursor-pointer flex items-center justify-between transition-colors
                          ${
                            isSelected
                              ? "bg-blue-50 text-blue-600 font-medium"
                              : "text-gray-700 hover:bg-gray-50"
                          }
                        `}
                    >
                      <span>{m.label}</span>
                      {isSelected ? <Check className="h-4 w-4" /> : null}
                    </li>
                  );
                })}
              </ul>
            ) : null}
            <p className="text-xs text-gray-500 mt-1">
              {selectedProvider === "custom_openai_vision"
                ? "须填写支持视觉的多模态模型 ID（与接口文档一致）"
                : "可从列表选择常用模型，或直接输入其他模型名称"}
            </p>
          </div>

          <div className="pt-4 border-t">
            <button
              onClick={testModelConnection}
              disabled={
                testingConnection ||
                !currentConfig.api_key ||
                (selectedProvider === "custom_openai_vision" &&
                  !currentConfig.base_url?.trim())
              }
              className="w-full px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {testingConnection ? "测试中..." : "测试连接"}
            </button>

            {testResult && (
              <div
                className={`mt-3 p-3 rounded-lg flex items-center ${
                  testResult.success
                    ? "bg-green-50 text-green-700"
                    : "bg-red-50 text-red-700"
                }`}
              >
                {testResult.success ? (
                  <CheckCircle className="h-5 w-5 mr-2 flex-shrink-0" />
                ) : (
                  <AlertCircle className="h-5 w-5 mr-2 flex-shrink-0" />
                )}
                <span className="text-sm">{testResult.message}</span>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

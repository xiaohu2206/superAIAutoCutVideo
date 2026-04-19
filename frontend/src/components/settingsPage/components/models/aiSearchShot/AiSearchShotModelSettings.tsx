import { TauriCommands } from "@/services/clients";
import { message } from "@/services/message";
import { AlertCircle, CheckCircle, ExternalLink, Loader } from "lucide-react";
import React from "react";
import type { AiSearchShotModelConfig, TestResult } from "../../../types";

interface AiSearchShotModelSettingsProps {
  config: AiSearchShotModelConfig;
  setConfig: React.Dispatch<React.SetStateAction<AiSearchShotModelConfig>>;
  loading: boolean;
  saveConfig: (config: AiSearchShotModelConfig) => Promise<void>;
  testingEmbedding: boolean;
  testingRerank: boolean;
  embeddingTestResult: TestResult | null;
  rerankTestResult: TestResult | null;
  embeddingTestDetail: string | null;
  rerankTestDetail: string | null;
  testEmbedding: () => void;
  testRerank: () => void;
}

const providerLink = "https://yunwu.apifox.cn";

export const AiSearchShotModelSettings: React.FC<AiSearchShotModelSettingsProps> = ({
  config,
  setConfig,
  loading,
  saveConfig,
  testingEmbedding,
  testingRerank,
  embeddingTestResult,
  rerankTestResult,
  embeddingTestDetail,
  rerankTestDetail,
  testEmbedding,
  testRerank,
}) => {
  const apiKeyBeforeEditRef = React.useRef<string>(config.api_key);
  const embeddingModelBeforeEditRef = React.useRef<string>(config.embedding_model);
  const rerankModelBeforeEditRef = React.useRef<string>(config.rerank_model);

  const persistTrimmedField = async (
    field: keyof AiSearchShotModelConfig,
    value: string,
    fallbackValue: string,
    emptyMessage: string
  ) => {
    const trimmed = value.trim();
    if (!trimmed) {
      setConfig((prev) => ({
        ...prev,
        [field]: fallbackValue,
      }));
      message.warning(emptyMessage);
      return;
    }

    const nextConfig = {
      ...config,
      [field]: trimmed,
    };
    setConfig(nextConfig);
    await saveConfig(nextConfig);
  };

  const persistNumberField = async (
    field: keyof AiSearchShotModelConfig,
    value: number,
    minValue: number,
    emptyMessage: string
  ) => {
    if (!Number.isFinite(value) || value < minValue) {
      message.warning(emptyMessage);
      setConfig((prev) => ({
        ...prev,
        [field]: prev[field],
      }));
      return;
    }

    const nextConfig = {
      ...config,
      [field]: value,
    };
    setConfig(nextConfig);
    await saveConfig(nextConfig);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12 text-gray-500">
        <Loader className="mr-2 h-5 w-5 animate-spin" />
        加载中...
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <label className="mb-2 block text-sm font-medium text-gray-700">模型平台</label>
        <input
          type="text"
          value="云雾 API 平台 (Yunwu.AI)"
          disabled
          className="w-full cursor-not-allowed rounded-md border border-gray-200 bg-gray-50 px-3 py-2 text-gray-500"
        />
        <p className="mt-1 text-xs text-gray-500">当前版本仅开放云雾平台，不支持切换其他提供商。  <button
            type="button"
            onClick={() => TauriCommands.openExternalLink(providerLink)}
            className="inline-flex items-center text-xs text-blue-600 hover:text-blue-800 hover:underline"
          >
            <ExternalLink className="mr-1 h-3 w-3" />
            前往云雾平台
          </button></p>
      </div>

      <div>
        <label className="mb-2 block text-sm font-medium text-gray-700">API密钥</label>
        <input
          type="text"
          value={config.api_key}
          onChange={(e) =>
            setConfig((prev) => ({
              ...prev,
              api_key: e.target.value,
            }))
          }
          onFocus={(e) => {
            apiKeyBeforeEditRef.current = e.target.value;
          }}
          onBlur={(e) =>
            void persistTrimmedField(
              "api_key",
              e.target.value,
              apiKeyBeforeEditRef.current,
              "API密钥不能为空"
            )
          }
          placeholder="请输入云雾平台 API 密钥"
          className="w-full rounded-md border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <div className="space-y-4 rounded-xl border border-slate-200 p-4">
          <div>
            <h4 className="text-sm font-semibold text-slate-900">向量模型</h4>
            <p className="mt-1 text-xs text-slate-500">
              对应 `embed_text` 调用，使用云雾 `/v1/embeddings` 接口。
            </p>
          </div>

          <div>
            <label className="mb-2 block text-sm font-medium text-gray-700">向量接口地址</label>
            <input
              type="text"
              value={config.embedding_base_url}
              onChange={(e) =>
                setConfig((prev) => ({
                  ...prev,
                  embedding_base_url: e.target.value,
                }))
              }
              onBlur={(e) =>
                void persistTrimmedField(
                  "embedding_base_url",
                  e.target.value,
                  "https://yunwu.ai/v1/embeddings",
                  "向量接口地址不能为空"
                )
              }
              placeholder="https://yunwu.ai/v1/embeddings"
              className="w-full rounded-md border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          <div>
            <label className="mb-2 block text-sm font-medium text-gray-700">向量模型名称</label>
            <input
              type="text"
              value={config.embedding_model}
              onChange={(e) =>
                setConfig((prev) => ({
                  ...prev,
                  embedding_model: e.target.value,
                }))
              }
              onFocus={(e) => {
                embeddingModelBeforeEditRef.current = e.target.value;
              }}
              onBlur={(e) =>
                void persistTrimmedField(
                  "embedding_model",
                  e.target.value,
                  embeddingModelBeforeEditRef.current,
                  "向量模型名称不能为空"
                )
              }
              placeholder="例如 gemini-embedding-2-preview"
              className="w-full rounded-md border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          <div className="border-t pt-4">
            <button
              type="button"
              onClick={testEmbedding}
              disabled={testingEmbedding || !config.api_key}
              className="w-full rounded-lg bg-gray-100 px-4 py-2 text-sm text-gray-700 transition-colors hover:bg-gray-200 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {testingEmbedding ? "测试中..." : "测试向量模型"}
            </button>

            {embeddingTestResult && (
              <div
                className={`mt-3 flex items-center rounded-lg p-3 ${
                  embeddingTestResult.success
                    ? "bg-green-50 text-green-700"
                    : "bg-red-50 text-red-700"
                }`}
              >
                {embeddingTestResult.success ? (
                  <CheckCircle className="mr-2 h-5 w-5 flex-shrink-0" />
                ) : (
                  <AlertCircle className="mr-2 h-5 w-5 flex-shrink-0" />
                )}
                <span className="text-sm">{embeddingTestResult.message}</span>
              </div>
            )}

            {embeddingTestDetail && (
              <div className="mt-3 rounded-lg border border-gray-200 bg-gray-50 p-3 text-gray-800">
                <p className="mb-2 text-xs font-medium text-gray-600">向量测试结果</p>
                <pre className="max-h-48 overflow-auto whitespace-pre-wrap break-words text-xs">
                  {embeddingTestDetail}
                </pre>
              </div>
            )}
          </div>
        </div>

        <div className="space-y-4 rounded-xl border border-slate-200 p-4">
          <div>
            <h4 className="text-sm font-semibold text-slate-900">召回模型</h4>
            <p className="mt-1 text-xs text-slate-500">
              对应 `rerank` 调用，使用云雾 `/v1/rerank` 接口。
            </p>
          </div>

          <div>
            <label className="mb-2 block text-sm font-medium text-gray-700">召回接口地址</label>
            <input
              type="text"
              value={config.rerank_base_url}
              onChange={(e) =>
                setConfig((prev) => ({
                  ...prev,
                  rerank_base_url: e.target.value,
                }))
              }
              onBlur={(e) =>
                void persistTrimmedField(
                  "rerank_base_url",
                  e.target.value,
                  "https://yunwu.ai/v1/rerank",
                  "召回接口地址不能为空"
                )
              }
              placeholder="https://yunwu.ai/v1/rerank"
              className="w-full rounded-md border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          <div>
            <label className="mb-2 block text-sm font-medium text-gray-700">召回模型名称</label>
            <input
              type="text"
              value={config.rerank_model}
              onChange={(e) =>
                setConfig((prev) => ({
                  ...prev,
                  rerank_model: e.target.value,
                }))
              }
              onFocus={(e) => {
                rerankModelBeforeEditRef.current = e.target.value;
              }}
              onBlur={(e) =>
                void persistTrimmedField(
                  "rerank_model",
                  e.target.value,
                  rerankModelBeforeEditRef.current,
                  "召回模型名称不能为空"
                )
              }
              placeholder="例如 qwen3-rerank"
              className="w-full rounded-md border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          <div className="border-t pt-4">
            <button
              type="button"
              onClick={testRerank}
              disabled={testingRerank || !config.api_key}
              className="w-full rounded-lg bg-gray-100 px-4 py-2 text-sm text-gray-700 transition-colors hover:bg-gray-200 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {testingRerank ? "测试中..." : "测试召回模型"}
            </button>

            {rerankTestResult && (
              <div
                className={`mt-3 flex items-center rounded-lg p-3 ${
                  rerankTestResult.success
                    ? "bg-green-50 text-green-700"
                    : "bg-red-50 text-red-700"
                }`}
              >
                {rerankTestResult.success ? (
                  <CheckCircle className="mr-2 h-5 w-5 flex-shrink-0" />
                ) : (
                  <AlertCircle className="mr-2 h-5 w-5 flex-shrink-0" />
                )}
                <span className="text-sm">{rerankTestResult.message}</span>
              </div>
            )}

            {rerankTestDetail && (
              <div className="mt-3 rounded-lg border border-gray-200 bg-gray-50 p-3 text-gray-800">
                <p className="mb-2 text-xs font-medium text-gray-600">召回测试结果</p>
                <pre className="max-h-48 overflow-auto whitespace-pre-wrap break-words text-xs">
                  {rerankTestDetail}
                </pre>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* <div className="grid gap-4 md:grid-cols-3">
        <div>
          <label className="mb-2 block text-sm font-medium text-gray-700">超时时间（秒）</label>
          <input
            type="number"
            min={1}
            value={config.timeout_seconds ?? 300}
            onChange={(e) =>
              setConfig((prev) => ({
                ...prev,
                timeout_seconds: Number(e.target.value),
              }))
            }
            onBlur={(e) =>
              void persistNumberField(
                "timeout_seconds",
                Number(e.target.value),
                1,
                "超时时间必须大于 0"
              )
            }
            className="w-full rounded-md border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>

        <div>
          <label className="mb-2 block text-sm font-medium text-gray-700">最大重试次数</label>
          <input
            type="number"
            min={3}
            value={config.max_retries ?? 5}
            onChange={(e) =>
              setConfig((prev) => ({
                ...prev,
                max_retries: Number(e.target.value),
              }))
            }
            onBlur={(e) =>
              void persistNumberField(
                "max_retries",
                Number(e.target.value),
                3,
                "重试次数至少为 3"
              )
            }
            className="w-full rounded-md border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>

        <div>
          <label className="mb-2 block text-sm font-medium text-gray-700">重试间隔（秒）</label>
          <input
            type="number"
            min={0.1}
            step={0.1}
            value={config.retry_sleep_seconds ?? 2}
            onChange={(e) =>
              setConfig((prev) => ({
                ...prev,
                retry_sleep_seconds: Number(e.target.value),
              }))
            }
            onBlur={(e) =>
              void persistNumberField(
                "retry_sleep_seconds",
                Number(e.target.value),
                0.1,
                "重试间隔必须大于 0"
              )
            }
            className="w-full rounded-md border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
      </div> */}
    </div>
  );
};

export default AiSearchShotModelSettings;

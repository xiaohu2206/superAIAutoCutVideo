import React, { useEffect, useState } from "react";
import { ExternalLink, Loader2 } from "lucide-react";
import { TauriCommands } from "@/services/clients";
import { ContentModelSettings } from "../content/ContentModelSettings";
import { VideoModelSettings } from "../video/VideoModelSettings";
import { useUnifiedYunwuModelConfig } from "../../../hooks/useUnifiedYunwuModelConfig";
import type { ContentModelConfig, TestResult, VideoModelConfig, YunwuTierConfig } from "../../../types";

type IntegratedSubTab = "yunwu" | "content" | "video";
type TierKey = "low" | "medium" | "high";

interface IntegratedModelSettingsProps {
  contentSelectedProvider: string;
  currentContentConfig: ContentModelConfig;
  setCurrentContentConfig: React.Dispatch<React.SetStateAction<ContentModelConfig>>;
  testingContentConnection: boolean;
  contentTestResult: TestResult | null;
  contentTestStructured: string | null;
  handleContentProviderChange: (provider: string) => void;
  updateCurrentContentConfig: (field: string, value: unknown) => void;
  testContentModelConnection: () => void;
  selectedProvider: string;
  currentConfig: VideoModelConfig;
  setCurrentConfig: React.Dispatch<React.SetStateAction<VideoModelConfig>>;
  testingConnection: boolean;
  testResult: TestResult | null;
  handleProviderChange: (provider: string) => void;
  updateCurrentConfig: (field: string, value: unknown) => void;
  testModelConnection: () => void;
}

const tabBtn =
  "rounded-lg px-4 py-2 text-sm font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-400/60";

const tierLabel: Record<TierKey, { name: string; desc: string }> = {
  low: { name: "低消耗", desc: "低效果" },
  medium: { name: "中消耗", desc: "均衡" },
  high: { name: "高消耗", desc: "高效果" },
};

const tierTabBtn = (active: boolean) =>
  `rounded-lg px-3 py-1.5 text-xs font-medium transition-colors focus:outline-none ${
    active
      ? "border-b-2 border-blue-600 text-blue-800"
      : "text-slate-600 hover:bg-slate-100/80"
  }`;

/**
 * 整合模型：默认云雾一键配置（三档）；开启「自定义模型」后横向切换文案 / 视频分析。
 */
export const IntegratedModelSettings: React.FC<IntegratedModelSettingsProps> = ({
  contentSelectedProvider,
  currentContentConfig,
  setCurrentContentConfig,
  testingContentConnection,
  contentTestResult,
  contentTestStructured,
  handleContentProviderChange,
  updateCurrentContentConfig,
  testContentModelConnection,
  selectedProvider,
  currentConfig,
  setCurrentConfig,
  testingConnection,
  testResult,
  handleProviderChange,
  updateCurrentConfig,
  testModelConnection,
}) => {
  const {
    root,
    loading,
    saving,
    testing,
    testMessage,
    load,
    setUseCustomModelsPersist,
    togglingCustom,
    setYunwuTierField,
    testConnection,
  } = useUnifiedYunwuModelConfig();

  const [subTab, setSubTab] = useState<IntegratedSubTab>("yunwu");
  const [activeTier, setActiveTier] = useState<TierKey>("high");

  useEffect(() => {
    if (root.use_custom_models) {
      setSubTab((t) => (t === "yunwu" ? "content" : t));
    } else {
      setSubTab("yunwu");
    }
  }, [root.use_custom_models]);

  const useCustom = root.use_custom_models;

  const curTier: YunwuTierConfig = root.yunwu[activeTier];

  return (
    <div className="space-y-6">
      <div className="flex items-start gap-3">
        <input
          type="checkbox"
          className="mt-0.5 h-4 w-4 shrink-0 rounded border-slate-300 text-blue-600 focus:ring-blue-500"
          checked={useCustom}
          disabled={togglingCustom}
          onChange={(e) => void setUseCustomModelsPersist(e.target.checked)}
        />
        <div className="min-w-0">
          <div className="text-sm font-medium text-slate-900">使用自定义模型</div>
          <p className="mt-1 text-xs text-slate-500">
            (小白不建议开启) 开启后将显示「文案模型」「视频分析模型」配置页，并隐藏云雾整合默认项；关闭后仅保留云雾整合。
          </p>
        </div>
      </div>

      {/* 横向子 Tab（自定义模式） */}
      {useCustom && (
        <div
          role="tablist"
          aria-label="整合模型子页"
          className="flex flex-wrap gap-1 border-b border-slate-200 pb-0.5"
        >
          <>
            <button
              type="button"
              role="tab"
              aria-selected={subTab === "content"}
              className={`${tabBtn} ${
                subTab === "content"
                  ? "border-b-2 border-blue-600 text-blue-800"
                  : "text-slate-600 hover:bg-slate-100/80"
              }`}
              onClick={() => setSubTab("content")}
            >
              文案模型
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={subTab === "video"}
              className={`${tabBtn} ${
                subTab === "video"
                  ? "border-b-2 border-blue-600 text-blue-800"
                  : "text-slate-600 hover:bg-slate-100/80"
              }`}
              onClick={() => setSubTab("video")}
            >
              视频分析模型
            </button>
          </>
        </div>
      )}

      <div className="pt-2" role="tabpanel">
        {loading ? (
          <div className="flex items-center gap-2 text-sm text-slate-500">
            <Loader2 className="h-4 w-4 animate-spin" />
            加载整合模型配置…
          </div>
        ) : !useCustom ? (
          <div className="space-y-5">
            {/* 档位切换 Tab */}
            <div>
              <label className="mb-2 block text-sm font-medium text-gray-700">
                全感知生成效果档位
              </label>
              <div
                role="tablist"
                aria-label="云雾档位"
                className="flex flex-wrap gap-2 border-b border-slate-200 pb-0.5"
              >
                {(["low", "medium", "high"] as const).map((tk) => (
                  <button
                    key={tk}
                    type="button"
                    role="tab"
                    aria-selected={activeTier === tk}
                    className={tierTabBtn(activeTier === tk)}
                    onClick={() => setActiveTier(tk)}
                  >
                    {tierLabel[tk].name}（{tierLabel[tk].desc}）
                  </button>
                ))}
              </div>
            </div>

            {/* 当前档位配置表单 */}
            <div className="space-y-4">
              <div>
                <label className="mb-2 block text-sm font-medium text-gray-700">
                  云雾 API 密钥
                </label>
                <input
                  type="password"
                  autoComplete="off"
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                  placeholder="请输入云雾平台 API Key"
                  value={curTier.api_key}
                  onChange={(e) => setYunwuTierField(activeTier, "api_key", e.target.value)}
                />
                <button
                  type="button"
                  onClick={() => TauriCommands.openExternalLink("https://yunwu.apifox.cn")}
                  className="mt-2 inline-flex items-center text-xs text-blue-600 hover:text-blue-800 hover:underline"
                >
                  <ExternalLink className="mr-1 h-3 w-3" />
                  前往云雾平台
                </button>
                <span className="mt-2 text-xs text-slate-500">
                  （与平台没有任何合作，保险使用，建议充值2元即可）
                </span>
              </div>

              <div>
                <label className="mb-2 block text-sm font-medium text-gray-700">
                  API 地址
                </label>
                <input
                  type="text"
                  autoComplete="off"
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                  placeholder="Chat Completions 地址"
                  value={curTier.base_url}
                  onChange={(e) => setYunwuTierField(activeTier, "base_url", e.target.value)}
                />
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="mb-1 block text-xs font-medium text-gray-600">
                    文案生成模型
                  </label>
                  <input
                    type="text"
                    autoComplete="off"
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                    value={curTier.copywriting_model_name}
                    onChange={(e) => setYunwuTierField(activeTier, "copywriting_model_name", e.target.value)}
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-gray-600">
                    视频分析模型
                  </label>
                  <input
                    type="text"
                    autoComplete="off"
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                    value={curTier.video_analysis_model_name}
                    onChange={(e) => setYunwuTierField(activeTier, "video_analysis_model_name", e.target.value)}
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-gray-600">
                    LLM 精排模型
                  </label>
                  <input
                    type="text"
                    autoComplete="off"
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                    value={curTier.llm_rerank_model_name}
                    onChange={(e) => setYunwuTierField(activeTier, "llm_rerank_model_name", e.target.value)}
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-gray-600">
                    脚本生成模型
                  </label>
                  <input
                    type="text"
                    autoComplete="off"
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                    value={curTier.script_generation_model_name}
                    onChange={(e) => setYunwuTierField(activeTier, "script_generation_model_name", e.target.value)}
                  />
                </div>
              </div>
            </div>

            {testMessage && (
              <p
                className={`text-sm ${
                  testMessage.includes("成功") ? "text-emerald-700" : "text-amber-800"
                }`}
              >
                {testMessage}
              </p>
            )}

            <div className="flex flex-wrap items-center gap-3">
              {saving && (
                <span className="inline-flex items-center text-sm text-slate-500">
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  正在保存…
                </span>
              )}
              <button
                type="button"
                disabled={testing}
                onClick={() => void testConnection()}
                className="inline-flex items-center rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 shadow-sm hover:bg-slate-50 disabled:opacity-50"
              >
                {testing && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                测试连接
              </button>
            </div>
          </div>
        ) : subTab === "content" ? (
          <ContentModelSettings
            contentSelectedProvider={contentSelectedProvider}
            currentContentConfig={currentContentConfig}
            setCurrentContentConfig={setCurrentContentConfig}
            testingContentConnection={testingContentConnection}
            contentTestResult={contentTestResult}
            contentTestStructured={contentTestStructured}
            handleContentProviderChange={handleContentProviderChange}
            updateCurrentContentConfig={updateCurrentContentConfig}
            testContentModelConnection={testContentModelConnection}
          />
        ) : (
          <VideoModelSettings
            selectedProvider={selectedProvider}
            currentConfig={currentConfig}
            setCurrentConfig={setCurrentConfig}
            testingConnection={testingConnection}
            testResult={testResult}
            handleProviderChange={handleProviderChange}
            updateCurrentConfig={updateCurrentConfig}
            testModelConnection={testModelConnection}
          />
        )}
      </div>

      {useCustom && (
        <p className="text-xs text-slate-500">
          自定义模式下请分别在「文案模型」「视频分析模型」标签内保存各自配置；与云雾整合配置相互独立。
        </p>
      )}
    </div>
  );
};

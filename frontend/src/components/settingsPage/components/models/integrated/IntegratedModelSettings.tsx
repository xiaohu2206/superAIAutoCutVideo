import React, { useEffect, useState } from "react";
import { ExternalLink, Loader2 } from "lucide-react";
import { TauriCommands } from "@/services/clients";
import { ContentModelSettings } from "../content/ContentModelSettings";
import { VideoModelSettings } from "../video/VideoModelSettings";
import { useUnifiedYunwuModelConfig } from "../../../hooks/useUnifiedYunwuModelConfig";
import type { ContentModelConfig, TestResult, VideoModelConfig } from "../../../types";

type IntegratedSubTab = "yunwu" | "content" | "video";

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

/**
 * 整合模型：选择聚合平台 + API Key + 测试；开启「自定义模型」后横向切换文案 / 视频分析。
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
    activePlatform,
    loading,
    saving,
    testing,
    testMessage,
    setUseCustomModelsPersist,
    togglingCustom,
    setActivePlatform,
    setPlatformApiKey,
    testConnection,
    forceSync,
    syncing,
  } = useUnifiedYunwuModelConfig();

  const [subTab, setSubTab] = useState<IntegratedSubTab>("yunwu");

  useEffect(() => {
    if (root.use_custom_models) {
      setSubTab((t) => (t === "yunwu" ? "content" : t));
    } else {
      setSubTab("yunwu");
    }
  }, [root.use_custom_models]);

  const useCustom = root.use_custom_models;

  // 当前激活平台的 API Key（三档共用）
  const currentApiKey = activePlatform?.tiers?.high?.api_key ?? "";
  const platformOptions = Object.entries(root.platforms).map(([key, platform]) => ({
    key,
    display_name: platform.display_name || key,
  }));

  return (
    <div className="space-y-6">
      <div
        className={`flex items-start gap-3 ${togglingCustom ? "opacity-90" : ""}`}
        aria-busy={togglingCustom}
      >
        <input
          type="checkbox"
          className="mt-0.5 h-4 w-4 shrink-0 rounded border-slate-300 text-blue-600 focus:ring-blue-500 disabled:cursor-wait"
          checked={useCustom}
          disabled={togglingCustom}
          onChange={(e) => void setUseCustomModelsPersist(e.target.checked)}
          aria-describedby="integrated-custom-models-hint"
        />
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-medium text-slate-900 dark:text-gray-100">
              使用自定义模型
            </span>
            {togglingCustom && (
              <span className="inline-flex items-center gap-1.5 text-xs text-slate-500 dark:text-gray-400">
                <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
                切换中…
              </span>
            )}
          </div>
          <p
            id="integrated-custom-models-hint"
            className="mt-1 text-xs text-slate-500 dark:text-gray-400"
          >
            (小白不建议开启)
            开启后将显示「文案模型」「视频分析模型」配置页，并隐藏聚合整合默认项；关闭后仅保留聚合整合。
          </p>
        </div>
      </div>

      {useCustom && (
        <div
          role="tablist"
          aria-label="整合模型子页"
          className="inline-flex rounded-xl bg-slate-100 p-1 dark:bg-gray-800"
        >
          <button
            type="button"
            role="tab"
            aria-selected={subTab === "content"}
            className={`rounded-lg px-4 py-2 text-sm font-medium transition-all duration-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-400/60 ${
              subTab === "content"
                ? "bg-white text-blue-700 shadow-sm ring-1 ring-slate-200/60 dark:bg-gray-700 dark:text-blue-400 dark:ring-gray-600"
                : "text-slate-500 hover:text-slate-800 dark:text-gray-400 dark:hover:text-gray-200"
            }`}
            onClick={() => setSubTab("content")}
          >
            文案模型
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={subTab === "video"}
            className={`rounded-lg px-4 py-2 text-sm font-medium transition-all duration-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-400/60 ${
              subTab === "video"
                ? "bg-white text-blue-700 shadow-sm ring-1 ring-slate-200/60 dark:bg-gray-700 dark:text-blue-400 dark:ring-gray-600"
                : "text-slate-500 hover:text-slate-800 dark:text-gray-400 dark:hover:text-gray-200"
            }`}
            onClick={() => setSubTab("video")}
          >
            视频分析模型
          </button>
        </div>
      )}

      <div className="pt-2" role="tabpanel">
        {loading && !useCustom ? (
          <div className="flex items-center gap-2 text-sm text-slate-500">
            <Loader2 className="h-4 w-4 animate-spin" />
            加载整合模型配置…
          </div>
        ) : !useCustom ? (
          <div className="space-y-5">
            {/* 平台选择器 */}
            <div>
              <label className="mb-2 block text-sm font-medium text-gray-700">
                选择聚合平台
              </label>
              <select
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                value={root.active_platform}
                onChange={(e) => setActivePlatform(e.target.value)}
              >
                {platformOptions.map((p) => (
                  <option key={p.key} value={p.key}>
                    {p.display_name || p.key}
                  </option>
                ))}
              </select>
              {/* 平台官网链接 */}
              <div className="mt-2 flex flex-wrap items-center gap-3">
                {activePlatform?.office_web && (
                  <button
                    type="button"
                    onClick={() =>
                      TauriCommands.openExternalLink(activePlatform.office_web)
                    }
                    className="inline-flex items-center text-xs text-blue-600 hover:text-blue-800 hover:underline"
                  >
                    <ExternalLink className="mr-1 h-3 w-3" />
                    前往{activePlatform.display_name || root.active_platform}
                    官网
                  </button>
                )}
              </div>
              <span className="mt-1 text-xs text-slate-500">
                建议少量充值，中转平台容易跑路
              </span>
              <button
                type="button"
                disabled={syncing}
                onClick={() => void forceSync()}
                className="inline-flex items-center text-xs text-slate-500 hover:text-slate-700 disabled:opacity-50"
                title="强制从远程同步最新模型平台配置"
              >
                {syncing && <Loader2 className="mr-1 h-3 w-3 animate-spin text-sm" />}
                {syncing ? "（同步中…）" : "（强制同步）"}
              </button>
            </div>

            {/* API Key 输入 */}
            <div>
              <label className="mb-2 block text-sm font-medium text-gray-700">
                API 密钥
              </label>
              <input
                type="password"
                autoComplete="off"
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                placeholder={`请输入${activePlatform?.display_name || root.active_platform}平台 API Key`}
                value={currentApiKey}
                onChange={(e) =>
                  setPlatformApiKey(root.active_platform, e.target.value)
                }
              />
            </div>

            {/* 模型信息展示（只读） */}
            {activePlatform && (
              <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 dark:border-slate-700 dark:bg-gray-900/60">
                <h4 className="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-gray-400">
                  当前平台模型配置（high 档）
                </h4>
                <div className="grid grid-cols-1 gap-2 text-sm sm:grid-cols-2">
                  <div>
                    <span className="text-slate-500 dark:text-gray-400">模型1：</span>
                    <span className="font-medium text-slate-800 dark:text-gray-200">
                      {activePlatform.tiers.high.copywriting_model_name}
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-500 dark:text-gray-400">模型2：</span>
                    <span className="font-medium text-slate-800 dark:text-gray-200">
                      {activePlatform.tiers.high.video_analysis_model_name}
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-500 dark:text-gray-400">模型3：</span>
                    <span className="font-medium text-slate-800 dark:text-gray-200">
                      {activePlatform.tiers.high.llm_rerank_model_name}
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-500 dark:text-gray-400">模型4：</span>
                    <span className="font-medium text-slate-800 dark:text-gray-200">
                      {activePlatform.tiers.high.script_generation_model_name}
                    </span>
                  </div>
                </div>
              </div>
            )}

            {testMessage && (
              <p
                className={`text-sm ${
                  testMessage.includes("成功")
                    ? "text-emerald-700"
                    : "text-amber-800"
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
          自定义模式下请分别在「文案模型」「视频分析模型」标签内保存各自配置；与聚合整合配置相互独立。
        </p>
      )}
    </div>
  );
};

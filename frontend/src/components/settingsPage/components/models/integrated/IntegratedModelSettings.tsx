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

const tabBtn =
  "rounded-lg px-4 py-2 text-sm font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-400/60";

/**
 * 整合模型：云雾 API Key + 测试；开启「自定义模型」后横向切换文案 / 视频分析。
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
    setUseCustomModelsPersist,
    togglingCustom,
    setYunwuApiKeyForAllTiers,
    testConnection,
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
            <div>
              <label className="mb-2 block text-sm font-medium text-gray-700">
                云雾 API 密钥
              </label>
              <input
                type="password"
                autoComplete="off"
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                placeholder="请输入云雾平台 API Key"
                value={root.yunwu.high.api_key}
                onChange={(e) => setYunwuApiKeyForAllTiers(e.target.value)}
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

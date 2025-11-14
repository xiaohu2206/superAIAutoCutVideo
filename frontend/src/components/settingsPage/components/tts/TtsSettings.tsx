import { TauriCommands } from "@/services/tauriService";
import { ttsService } from "@/services/ttsService";
import { AlertCircle, CheckCircle, Clock, Loader, Mic, RefreshCw } from "lucide-react";
import React, { useEffect, useMemo, useRef, useState } from "react";
import { TtsCredentialForm } from "../../components/tts/TtsCredentialForm";
import { TtsEngineSelect } from "../../components/tts/TtsEngineSelect";
import { TtsPreviewPlayer } from "../../components/tts/TtsPreviewPlayer";
import { TtsSpeedSlider } from "../../components/tts/TtsSpeedSlider";
import { TtsVoiceGallery } from "../../components/tts/TtsVoiceGallery";
import type { TtsEngineConfig, TtsEngineMeta, TtsTestResult, TtsVoice } from "../../types";
import { getSpeedLabel, getTtsConfigIdByProvider } from "../../utils";
import { TtsActivationSwitch } from "./TtsActivationSwitch";

type SaveState = "idle" | "saving" | "saved" | "failed";

export const TtsSettings: React.FC = () => {
  // 引擎与配置
  const [engines, setEngines] = useState<TtsEngineMeta[]>([]);
  const [provider, setProvider] = useState<string>("tencent_tts");
  const [configs, setConfigs] = useState<Record<string, TtsEngineConfig>>({});
  const [activeConfigId, setActiveConfigId] = useState<string | null>(null);
  const currentConfigId = useMemo(() => getTtsConfigIdByProvider(provider), [provider]);
  const currentConfig = configs[currentConfigId];

  // 音色与试听
  const [voices, setVoices] = useState<TtsVoice[]>([]);
  const [search, setSearch] = useState<string>("");

  // 保存状态
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const [lastSavedAt, setLastSavedAt] = useState<string>("");
  const latestPatchSeq = useRef<number>(0);

  // 连通性状态
  const [testing, setTesting] = useState<boolean>(false);
  const [testResult, setTestResult] = useState<TtsTestResult | null>(null);
  const [testDurationMs, setTestDurationMs] = useState<number | null>(null);

  const hasCredentials = Boolean(
    currentConfig?.secret_id === "***" && currentConfig?.secret_key === "***"
  );

  // 初始化：并发加载引擎与配置
  useEffect(() => {
    const init = async () => {
      try {
        const [engRes, cfgRes] = await Promise.all([
          ttsService.getEngines(),
          ttsService.getConfigs(),
        ]);

        if (engRes?.success) setEngines(engRes.data || []);
        if (cfgRes?.success) {
          setConfigs(cfgRes.data?.configs || {});
          setActiveConfigId(cfgRes.data?.active_config_id || null);
          // 推断提供商
          const activeId = cfgRes.data?.active_config_id;
          if (activeId && cfgRes.data?.configs?.[activeId]) {
            setProvider(cfgRes.data.configs[activeId].provider);
          } else {
            setProvider("tencent_tts");
          }
        }

        // 若不存在当前配置，则创建默认配置
        const cid = getTtsConfigIdByProvider(provider);
        if (!cfgRes?.data?.configs?.[cid]) {
          await createOrUpdateDefaultConfig(cid, provider);
        }

        // 加载音色
        await loadVoices(provider);
      } catch (error) {
        console.error("初始化TTS设置失败:", error);
        await TauriCommands.showNotification("错误", "初始化TTS设置失败");
      }
    };
    init();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const loadVoices = async (prov: string) => {
    try {
      const res = await ttsService.getVoices(prov);
      if (res?.success) setVoices(res.data || []);
    } catch (error) {
      console.error("加载音色列表失败:", error);
    }
  };

  const createOrUpdateDefaultConfig = async (configId: string, prov: string) => {
    try {
      setSaveState("saving");
      const res = await ttsService.patchConfig(configId, {
        provider: prov,
        enabled: false,
      });
      if (res?.success) {
        await refreshConfigs();
        markSaved();
      } else {
        markFailed();
      }
    } catch (error) {
      console.error("创建默认配置失败:", error);
      markFailed();
    }
  };

  const refreshConfigs = async () => {
    try {
      const cfgRes = await ttsService.getConfigs();
      if (cfgRes?.success) {
        setConfigs(cfgRes.data?.configs || {});
        setActiveConfigId(cfgRes.data?.active_config_id || null);
      }
    } catch (error) {
      console.error("刷新配置失败:", error);
    }
  };

  const markSaved = () => {
    setSaveState("saved");
    setLastSavedAt(new Date().toLocaleTimeString());
    setTimeout(() => setSaveState("idle"), 800);
  };

  const markFailed = () => {
    setSaveState("failed");
    setTimeout(() => setSaveState("idle"), 2000);
  };

  // 事件：提供商切换
  const handleProviderChange = async (prov: string) => {
    setProvider(prov);
    const cid = getTtsConfigIdByProvider(prov);
    if (!configs[cid]) {
      await createOrUpdateDefaultConfig(cid, prov);
    }
    await loadVoices(prov);
  };

  // 事件：更新凭据（onBlur实时保存）
  const handleCredentialUpdate = async (partial: Partial<TtsEngineConfig>) => {
    try {
      setSaveState("saving");
      latestPatchSeq.current += 1;
      const seq = latestPatchSeq.current;
      const res = await ttsService.patchConfig(currentConfigId!, partial);
      if (seq !== latestPatchSeq.current) {
        // 过期响应，忽略
        return;
      }
      if (res?.success) {
        await refreshConfigs();
        markSaved();
      } else {
        markFailed();
      }
    } catch (error) {
      console.error("更新凭据失败:", error);
      markFailed();
    }
  };

  // 事件：设为当前音色并激活配置
  const handleSetActiveVoice = async (voiceId: string) => {
    try {
      setSaveState("saving");
      // 更新音色
      const r1 = await ttsService.patchConfig(currentConfigId!, {
        active_voice_id: voiceId,
      });
      // 激活配置（保证唯一）
      const r2 = await ttsService.activateConfig(currentConfigId!);
      if (r1?.success && r2?.success) {
        await refreshConfigs();
        markSaved();
      } else {
        markFailed();
      }
    } catch (error) {
      console.error("设为当前音色失败:", error);
      markFailed();
    }
  };

  // 事件：语速更新（防抖）
  const debouncedSaveRef = useRef<number | null>(null);
  const handleSpeedChangeDebounced = (speed: number) => {
    if (debouncedSaveRef.current) {
      window.clearTimeout(debouncedSaveRef.current);
    }
    setSaveState("saving");
    debouncedSaveRef.current = window.setTimeout(async () => {
      try {
        latestPatchSeq.current += 1;
        const seq = latestPatchSeq.current;
        const res = await ttsService.patchConfig(currentConfigId!, {
          speed_ratio: speed,
        });
        if (seq !== latestPatchSeq.current) return;
        if (res?.success) {
          await refreshConfigs();
          markSaved();
        } else {
          markFailed();
        }
      } catch (error) {
        console.error("更新语速失败:", error);
        markFailed();
      }
    }, 300);
  };

  // 事件：激活开关
  const handleActivate = async () => {
    try {
      setSaveState("saving");
      const res = await ttsService.activateConfig(currentConfigId!);
      if (res?.success) {
        await refreshConfigs();
        markSaved();
      } else {
        markFailed();
      }
    } catch (error) {
      console.error("激活配置失败:", error);
      markFailed();
    }
  };

  // 事件：测试连通性
  const handleTestConnection = async () => {
    try {
      if (!hasCredentials || !currentConfigId) {
        setTestResult({
          success: false,
          config_id: currentConfigId || "",
          provider,
          message: "缺少SecretId或SecretKey，请先填写并保存",
        });
        return;
      }
      setTesting(true);
      setTestResult(null);
      setTestDurationMs(null);
      const t0 = performance.now();
      const res = await ttsService.testConnection(currentConfigId!);
      const t1 = performance.now();
      setTestDurationMs(Math.round(t1 - t0));
      if (res?.success || res?.data?.success) {
        const data = res.data || res;
        setTestResult({
          success: true,
          config_id: data.config_id,
          provider: data.provider,
          message: data.message || "凭据有效",
        });
      } else {
        const data = res.data || res;
        setTestResult({
          success: false,
          config_id: data.config_id || currentConfigId,
          provider: data.provider || provider,
          message: data.message || data.error || "鉴权失败",
        });
      }
    } catch (error) {
      setTestResult({
        success: false,
        config_id: currentConfigId,
        provider,
        message: (error as Error).message,
      });
    } finally {
      setTesting(false);
    }
  };

  // 右侧状态文案
  const statusText = hasCredentials
    ? testResult?.success === false
      ? "异常"
      : "健康"
    : "降级";

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
      {/* 左侧主内容 */}
      <div className="lg:col-span-2 space-y-8">
        {/* 引擎选择 */}
        <section className="bg-white border rounded-lg p-4">
          <TtsEngineSelect
            engines={engines}
            provider={provider}
            onProviderChange={handleProviderChange}
          />
        </section>

        {/* 凭据设置 */}
        <section className="bg-white border rounded-lg p-4">
          <TtsCredentialForm
            configId={currentConfigId}
            config={currentConfig}
            hasCredentials={hasCredentials}
            onUpdate={handleCredentialUpdate}
            onTest={handleTestConnection}
            testing={testing}
            testDurationMs={testDurationMs}
            testResult={testResult}
          />
        </section>

        {/* 音色库 */}
        <section className="bg-white border rounded-lg p-4">
          <div className="flex items-center justify-between mb-3">
            <h4 className="text-md font-semibold text-gray-900">音色库</h4>
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="搜索音色..."
              className="px-3 py-2 border border-gray-300 rounded-md w-56"
            />
          </div>
          <TtsVoiceGallery
            voices={voices.filter((v) =>
              (v.name + v.id + (v.description || "")).toLowerCase().includes(search.toLowerCase())
            )}
            activeVoiceId={currentConfig?.active_voice_id || ""}
            configId={currentConfigId}
            hasCredentials={hasCredentials}
            onSetActive={handleSetActiveVoice}
          />
        </section>

        {/* 语速 */}
        <section className="bg-white border rounded-lg p-4">
          <TtsSpeedSlider
            speedRatio={currentConfig?.speed_ratio ?? 1.0}
            onChange={handleSpeedChangeDebounced}
            label={getSpeedLabel(currentConfig?.speed_ratio ?? 1.0)}
            savingState={saveState}
          />
        </section>

        {/* 预览 */}
        <section className="bg-white border rounded-lg p-4">
          <TtsPreviewPlayer
            provider={provider}
            configId={currentConfigId}
            voices={voices}
            activeVoiceId={currentConfig?.active_voice_id || ""}
            hasCredentials={hasCredentials}
          />
        </section>

        {/* 底部状态 */}
        <section className="flex items-center justify-between text-sm">
          <div className="flex items-center gap-2">
            {saveState === "saving" && (
              <span className="flex items-center text-gray-600">
                <Loader className="h-4 w-4 mr-1 animate-spin" /> 保存中…
              </span>
            )}
            {saveState === "saved" && (
              <span className="flex items-center text-green-600">
                <CheckCircle className="h-4 w-4 mr-1" /> 已保存
              </span>
            )}
            {saveState === "failed" && (
              <span className="flex items-center text-red-600">
                <AlertCircle className="h-4 w-4 mr-1" /> 保存失败，请重试
              </span>
            )}
          </div>
          <div className="text-gray-500 flex items-center">
            <Clock className="h-4 w-4 mr-1" /> 最近保存时间：{lastSavedAt || "--"}
          </div>
        </section>
      </div>

      {/* 右侧状态面板 */}
      <aside className="space-y-4">
        <div className="bg-white border rounded-lg p-4">
          <div className="flex items-center gap-2 mb-2">
            <Mic className="h-5 w-5 text-gray-700" />
            <span className="text-sm font-medium text-gray-900">TTS状态</span>
          </div>
          <div className="space-y-2 text-sm text-gray-700">
            <div>当前配置ID：<span className="font-mono">{currentConfigId}</span></div>
            <div>激活配置：<span className="font-mono">{activeConfigId || "无"}</span></div>
            <div>
              连通性：
              <span className={
                statusText === "健康"
                  ? "text-green-600"
                  : statusText === "降级"
                  ? "text-orange-600"
                  : "text-red-600"
              }>
                {statusText}
              </span>
              {testDurationMs != null && (
                <span className="text-gray-500 ml-2">响应 {testDurationMs}ms</span>
              )}
            </div>
          </div>

          <div className="mt-4">
            <TtsActivationSwitch
              enabled={Boolean(currentConfig?.enabled)}
              onActivate={handleActivate}
            />
          </div>

          <div className="mt-2">
            <button
              className="inline-flex items-center px-3 py-2 text-xs bg-gray-100 hover:bg-gray-200 rounded-md text-gray-700"
              onClick={() => handleTestConnection()}
              disabled={testing}
            >
              {testing ? <Loader className="h-4 w-4 mr-1 animate-spin" /> : <RefreshCw className="h-4 w-4 mr-1" />}
              重新测试
            </button>
          </div>
        </div>
      </aside>
    </div>
  );
};

export default TtsSettings;
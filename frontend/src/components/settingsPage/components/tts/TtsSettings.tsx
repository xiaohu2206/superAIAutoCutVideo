import { TauriCommands } from "@/services/tauriService";
import { ttsService } from "@/services/ttsService";
import { AlertCircle, CheckCircle, Loader } from "lucide-react";
import React, { useEffect, useMemo, useRef, useState } from "react";
import { TtsCredentialForm } from "../../components/tts/TtsCredentialForm";
import { TtsEngineSelect } from "../../components/tts/TtsEngineSelect";
import { TtsSpeedSlider } from "../../components/tts/TtsSpeedSlider";
import { TtsVoiceGallery } from "../../components/tts/TtsVoiceGallery";
import type { TtsEngineConfig, TtsEngineMeta, TtsTestResult, TtsVoice } from "../../types";
import { getSpeedLabel, getTtsConfigIdByProvider } from "../../utils";
 
import { LabeledChip } from "./LabeledGroup";
import { getGenderLabel } from "./utils";

type SaveState = "idle" | "saving" | "saved" | "failed";

export const TtsSettings: React.FC = () => {
  // 引擎与配置
  const [engines, setEngines] = useState<TtsEngineMeta[]>([]);
  const [provider, setProvider] = useState<string>("edge_tts");
  const [configs, setConfigs] = useState<Record<string, TtsEngineConfig>>({});
  const [activeConfigId, setActiveConfigId] = useState<string | null>(null);
  const currentConfigId = useMemo(() => getTtsConfigIdByProvider(provider), [provider]);
  const currentConfig = configs[currentConfigId];

  // 音色与试听
  const [voices, setVoices] = useState<TtsVoice[]>([]);
  const [search, setSearch] = useState<string>("");

  // 保存状态
  const [saveState, setSaveState] = useState<SaveState>("idle");
 
  const latestPatchSeq = useRef<number>(0);

  // 连通性状态
  const [testing, setTesting] = useState<boolean>(false);
  const [testResult, setTestResult] = useState<TtsTestResult | null>(null);
  const [testDurationMs, setTestDurationMs] = useState<number | null>(null);

  const hasCredentials = useMemo(() => {
    // Edge TTS 免凭据：只要当前提供商为 edge_tts，则视为具备“连通性测试许可”
    if (provider === "edge_tts") return true;
    // 腾讯云：后端返回时会将已设置的敏感值脱敏为“***”，以此判断是否已配置
    return Boolean(currentConfig?.secret_id === "***" && currentConfig?.secret_key === "***");
  }, [provider, currentConfig]);

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
          // 推断提供商（优先使用后端激活配置；否则默认 edge_tts）
          const activeId = cfgRes.data?.active_config_id;
          let resolvedProvider = "edge_tts";
          if (activeId && cfgRes.data?.configs?.[activeId]) {
            resolvedProvider = cfgRes.data.configs[activeId].provider;
          }
          setProvider(resolvedProvider);
        }

        // 若不存在当前配置，则创建默认配置（使用已解析的提供商）
        const initProvider = (cfgRes?.success && cfgRes?.data)
          ? (cfgRes.data?.active_config_id && cfgRes.data?.configs?.[cfgRes.data.active_config_id]
              ? cfgRes.data.configs[cfgRes.data.active_config_id].provider
              : "edge_tts")
          : "edge_tts";
        const cid = getTtsConfigIdByProvider(initProvider);
        if (!cfgRes?.data?.configs?.[cid]) {
          await createOrUpdateDefaultConfig(cid, initProvider);
        }

        // 加载音色（使用已解析的提供商）
        await loadVoices(initProvider);
      } catch (error) {
        console.error("初始化TTS设置失败:", error);
        await TauriCommands.showNotification("错误", "初始化TTS设置失败");
      }
    };
    init();
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

  const activeVoiceDetail = React.useMemo(() => {
    const ep = currentConfig?.extra_params || {};
    const aid = currentConfig?.active_voice_id || "";
    const match = voices.find(v => v.id === aid);
    const name = ep?.VoiceName ?? match?.name ?? "";
    const desc = ep?.VoiceDesc ?? match?.description ?? "";
    const quality = ep?.VoiceQuality ?? match?.voice_quality ?? "";
    const typeTag = ep?.VoiceTypeTag ?? match?.voice_type_tag ?? "";
    const style = ep?.VoiceHumanStyle ?? match?.voice_human_style ?? "";
    const gender = ep?.VoiceGender ?? match?.gender ?? "";
    return { name, desc, quality, typeTag, style, gender, id: aid };
  }, [currentConfig, voices]);

  const markSaved = () => {
    setSaveState("saved");
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
  

  

  // 事件：测试连通性
  const handleTestConnection = async () => {
    try {
      // Edge TTS 无需凭据；腾讯云需要凭据且需要存在配置ID
      if (provider !== "edge_tts" && (!hasCredentials || !currentConfigId)) {
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

  return (
    <div className="grid grid-cols-1 gap-6">
      <div className="space-y-8">
        {/* 引擎选择 */}
        <section className="bg-white/80 backdrop-blur border rounded-xl p-5 shadow-sm">
          <TtsEngineSelect
            engines={engines}
            provider={provider}
            onProviderChange={handleProviderChange}
          />
        </section>

        {/* 凭据设置 */}
        <section className="bg-white/80 backdrop-blur border rounded-xl p-5 shadow-sm">
          <TtsCredentialForm
            configId={currentConfigId}
            config={currentConfig}
            hasCredentials={hasCredentials}
            onUpdate={handleCredentialUpdate}
            onTest={handleTestConnection}
            testing={testing}
            testDurationMs={testDurationMs}
            testResult={testResult}
            activeConfigId={activeConfigId}
          />
        </section>

        {/* 音色库 */}
        <section className="bg-white/80 backdrop-blur border rounded-xl p-5 shadow-sm">
          <div className="flex items-center justify-between mb-3">
            <h4 className="text-md font-semibold text-gray-900">音色库</h4>
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="搜索音色..."
              className="px-3 py-2 border border-gray-300 rounded-lg w-56 focus:outline-none focus:ring-2 focus:ring-blue-200"
            />
          </div>
          {activeVoiceDetail.id && (
            <div className="mb-3 border border-blue-100 bg-blue-50 rounded-lg p-3 text-xs text-gray-800">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium">当前激活：</span>
                {activeVoiceDetail.name && (
                  <LabeledChip label="名称" value={activeVoiceDetail.name} variant="blue" />
                )}
                {activeVoiceDetail.gender && (
                  <LabeledChip label="性别" value={getGenderLabel(activeVoiceDetail.gender)} variant="white" />
                )}
                {activeVoiceDetail.typeTag && (
                  <LabeledChip label="类型标签" value={activeVoiceDetail.typeTag} variant="white" />
                )}
                {activeVoiceDetail.style && (
                  <LabeledChip label="风格" value={activeVoiceDetail.style} variant="white" />
                )}
                {(() => {
                  const statusText = hasCredentials
                    ? (testResult?.success === false ? "异常" : "健康")
                    : "降级";
                  const cls = statusText === "健康" ? "text-green-600" : statusText === "降级" ? "text-orange-600" : "text-red-600";
                  return (
                    <>
                      <LabeledChip label="连通性" value={<span className={cls}>{statusText}</span>} variant="white" />
                      {typeof testDurationMs === "number" && (
                        <span className="text-[11px] text-gray-500">响应 {testDurationMs}ms</span>
                      )}
                    </>
                  );
                })()}
              </div>
            </div>
          )}
          <div className="h-80 overflow-y-auto pr-1">
          <TtsVoiceGallery
            voices={voices.filter((v) =>
              (v.name + v.id + (v.description || "")).toLowerCase().includes(search.toLowerCase())
            )}
            activeVoiceId={currentConfig?.active_voice_id || ""}
            configId={currentConfigId}
            provider={provider}
            hasCredentials={hasCredentials}
            testResult={testResult}
            testDurationMs={testDurationMs}
            onSetActive={handleSetActiveVoice}
          />
          </div>
        </section>

        {/* 语速 */}
        <section className="bg-white/80 backdrop-blur border rounded-xl p-5 shadow-sm">
          <TtsSpeedSlider
            speedRatio={currentConfig?.speed_ratio ?? 1.0}
            onChange={handleSpeedChangeDebounced}
            label={getSpeedLabel(currentConfig?.speed_ratio ?? 1.0)}
            savingState={saveState}
          />
        </section>

        {/* 底部状态 */}
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
      </div>
    </div>
  );
};

export default TtsSettings;
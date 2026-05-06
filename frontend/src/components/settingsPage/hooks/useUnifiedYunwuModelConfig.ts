import { useCallback, useEffect, useRef, useState } from "react";
import { message } from "@/services/message";
import unifiedYunwuModelService from "@/services/unifiedYunwuModelService";
import type {
  PlatformConfig,
  PlatformListItem,
  UnifiedYunwuModelsPayload,
  YunwuTierConfig,
} from "../types";

const DEFAULT_TIER: YunwuTierConfig = {
  api_key: "",
  base_url: "https://yunwu.ai/v1/chat/completions",
  copywriting_model_name: "gemini-3.1-pro-preview",
  video_analysis_model_name: "gemini-2.5-flash-lite",
  llm_rerank_model_name: "gemini-3.1-pro-preview",
  script_generation_model_name: "gemini-3.1-pro-preview",
};

const DEFAULT_TIERS: PlatformConfig["tiers"] = {
  low: { ...DEFAULT_TIER },
  medium: { ...DEFAULT_TIER },
  high: { ...DEFAULT_TIER },
};

function normalizeTiers(raw: unknown): PlatformConfig["tiers"] {
  if (!raw || typeof raw !== "object") return { ...DEFAULT_TIERS };
  const y = raw as Record<string, unknown>;
  if ("low" in y || "medium" in y || "high" in y) {
    const keys = ["low", "medium", "high"] as const;
    const result: Record<string, YunwuTierConfig> = {};
    for (const tk of keys) {
      const tier = y[tk];
      result[tk] =
        tier && typeof tier === "object"
          ? { ...DEFAULT_TIER, ...(tier as Partial<YunwuTierConfig>) }
          : { ...DEFAULT_TIER };
    }
    return result as PlatformConfig["tiers"];
  }
  return { ...DEFAULT_TIERS };
}

function normalizePlatform(raw: unknown): PlatformConfig {
  if (!raw || typeof raw !== "object") {
    return { display_name: "", office_web: "", tiers: { ...DEFAULT_TIERS } };
  }
  const p = raw as Record<string, unknown>;
  return {
    display_name: String(p.display_name ?? ""),
    office_web: String(p.office_web ?? ""),
    tiers: normalizeTiers(p.tiers),
  };
}

function normalizePayload(data: Record<string, unknown>): UnifiedYunwuModelsPayload {
  const platformsRaw = data.platforms as Record<string, unknown> | undefined;
  const platforms: Record<string, PlatformConfig> = {};
  if (platformsRaw && typeof platformsRaw === "object") {
    for (const [k, v] of Object.entries(platformsRaw)) {
      platforms[k] = normalizePlatform(v);
    }
  }
  return {
    use_custom_models: Boolean(data.use_custom_models),
    active_platform: String(data.active_platform ?? "yunwu"),
    platforms,
  };
}

const emptyRoot = (): UnifiedYunwuModelsPayload => ({
  use_custom_models: false,
  active_platform: "yunwu",
  platforms: {},
});

const AUTOSAVE_DEBOUNCE_MS = 600;

function isMaskedYunwuApiKey(ak: string): boolean {
  const s = String(ak ?? "");
  if (s.length <= 8) return false;
  const mid = s.slice(4, -4);
  return mid.length > 0 && /^\*+$/.test(mid);
}

export const useUnifiedYunwuModelConfig = () => {
  const [root, setRoot] = useState<UnifiedYunwuModelsPayload>(emptyRoot);
  const [platformList, setPlatformList] = useState<PlatformListItem[]>([]);
  const rootRef = useRef(root);
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testMessage, setTestMessage] = useState<string | null>(null);
  const [togglingCustom, setTogglingCustom] = useState(false);
  const [syncing, setSyncing] = useState(false);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const res = await unifiedYunwuModelService.get();
      const data = res?.data;
      let nextRoot = rootRef.current;
      if (res?.success && data && typeof data === "object") {
        nextRoot = normalizePayload(data as Record<string, unknown>);
        setRoot(nextRoot);
      }
      // 非自定义模型模式才加载平台列表
      if (!nextRoot.use_custom_models) {
        try {
          const platRes = await unifiedYunwuModelService.getPlatforms();
          const platData = platRes?.data;
          if (platRes?.success && platData?.platforms) {
            setPlatformList(platData.platforms as PlatformListItem[]);
          }
        } catch {
          // 平台列表加载失败不影响主流程
        }
      }
    } catch (e) {
      console.error("加载聚合模型配置失败:", e);
      message.error("加载整合模型配置失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    rootRef.current = root;
  }, [root]);

  useEffect(() => {
    return () => {
      if (saveTimerRef.current) {
        clearTimeout(saveTimerRef.current);
      }
    };
  }, []);

  const setUseCustomModels = useCallback((value: boolean) => {
    setRoot((prev) => ({ ...prev, use_custom_models: value }));
  }, []);

  const setUseCustomModelsPersist = useCallback(
    async (value: boolean) => {
      try {
        setTogglingCustom(true);
        const res = await unifiedYunwuModelService.update({
          use_custom_models: value,
        });
        const data = res?.data;
        if (res?.success && data && typeof data === "object") {
          setRoot(normalizePayload(data as Record<string, unknown>));
          message.success(
            value ? "已开启自定义模型（文案 / 视频分析）" : "已使用聚合整合模型"
          );
        } else {
          message.error("切换失败");
        }
      } catch (e: unknown) {
        const msg = e instanceof Error ? e.message : "切换失败";
        message.error(msg);
        await load();
      } finally {
        setTogglingCustom(false);
      }
    },
    [load]
  );

  const persistRoot = useCallback(
    async (payload: UnifiedYunwuModelsPayload, options?: { toastOnSuccess?: boolean }) => {
      const toastOnSuccess = options?.toastOnSuccess ?? false;
      try {
        setSaving(true);
        // 构建 platforms 更新体
        const platforms: Record<string, unknown> = {};
        for (const [platKey, platVal] of Object.entries(payload.platforms)) {
          const tiers: Record<string, unknown> = {};
          for (const [tierKey, tierVal] of Object.entries(platVal.tiers)) {
            const tierCopy: Record<string, unknown> = { ...tierVal };
            const ak = String(tierCopy.api_key ?? "");
            if (isMaskedYunwuApiKey(ak)) {
              delete tierCopy.api_key;
            }
            tiers[tierKey] = tierCopy;
          }
          platforms[platKey] = { tiers };
        }
        const body: Record<string, unknown> = {
          use_custom_models: payload.use_custom_models,
          active_platform: payload.active_platform,
          platforms,
        };
        const res = await unifiedYunwuModelService.update(body);
        const data = res?.data;
        if (res?.success && data && typeof data === "object") {
          setRoot((prev) => ({
            ...prev,
            use_custom_models: Boolean((data as Record<string, unknown>).use_custom_models),
            active_platform: String((data as Record<string, unknown>).active_platform ?? prev.active_platform),
          }));
          if (toastOnSuccess) {
            message.success("整合模型配置已保存");
          }
        } else {
          message.error("保存失败");
        }
      } catch (e: any) {
        console.error("保存聚合模型配置失败:", e);
        message.error(e?.message || "保存整合模型配置失败");
        throw e;
      } finally {
        setSaving(false);
      }
    },
    []
  );

  const scheduleAutosave = useCallback(() => {
    if (saveTimerRef.current) {
      clearTimeout(saveTimerRef.current);
    }
    saveTimerRef.current = setTimeout(() => {
      saveTimerRef.current = null;
      void persistRoot(rootRef.current);
    }, AUTOSAVE_DEBOUNCE_MS);
  }, [persistRoot]);

  /** 切换激活平台 */
  const setActivePlatform = useCallback(
    (platformKey: string) => {
      setRoot((prev) => ({ ...prev, active_platform: platformKey }));
      scheduleAutosave();
    },
    [scheduleAutosave]
  );

  /** 更新指定平台的 API Key（三档共用同一把 Key） */
  const setPlatformApiKey = useCallback(
    (platformKey: string, value: string) => {
      setRoot((prev) => {
        const plat = prev.platforms[platformKey];
        if (!plat) return prev;
        return {
          ...prev,
          platforms: {
            ...prev.platforms,
            [platformKey]: {
              ...plat,
              tiers: {
                low: { ...plat.tiers.low, api_key: value },
                medium: { ...plat.tiers.medium, api_key: value },
                high: { ...plat.tiers.high, api_key: value },
              },
            },
          },
        };
      });
      scheduleAutosave();
    },
    [scheduleAutosave]
  );

  /** 获取当前激活平台配置 */
  const activePlatform = root.platforms[root.active_platform];

  /** 兼容旧调用：设置当前激活平台的 API Key */
  const setYunwuApiKeyForAllTiers = useCallback(
    (value: string) => {
      setPlatformApiKey(rootRef.current.active_platform, value);
    },
    [setPlatformApiKey]
  );

  /** 更新指定平台的指定档位的指定字段 */
  const setPlatformTierField = useCallback(
    <K extends keyof YunwuTierConfig>(
      platformKey: string,
      tier: "low" | "medium" | "high",
      field: K,
      value: YunwuTierConfig[K]
    ) => {
      setRoot((prev) => {
        const plat = prev.platforms[platformKey];
        if (!plat) return prev;
        return {
          ...prev,
          platforms: {
            ...prev.platforms,
            [platformKey]: {
              ...plat,
              tiers: {
                ...plat.tiers,
                [tier]: { ...plat.tiers[tier], [field]: value },
              },
            },
          },
        };
      });
      scheduleAutosave();
    },
    [scheduleAutosave]
  );

  /** 兼容旧调用：更新当前激活平台的指定档位字段 */
  const setYunwuTierField = useCallback(
    <K extends keyof YunwuTierConfig>(
      tier: "low" | "medium" | "high",
      field: K,
      value: YunwuTierConfig[K]
    ) => {
      setPlatformTierField(rootRef.current.active_platform, tier, field, value);
    },
    [setPlatformTierField]
  );

  /** 兼容旧调用：更新当前激活平台 high 档位字段 */
  const setYunwuField = useCallback(
    <K extends keyof YunwuTierConfig>(field: K, value: YunwuTierConfig[K]) => {
      setYunwuTierField("high", field, value);
    },
    [setYunwuTierField]
  );

  const save = useCallback(async () => {
    await persistRoot(root, { toastOnSuccess: true });
  }, [persistRoot, root]);

  const testConnection = useCallback(async () => {
    try {
      setTesting(true);
      setTestMessage(null);
      const res = await unifiedYunwuModelService.test();
      const data = res?.data;
      if (res?.success && data?.success) {
        setTestMessage(data?.message || "连接成功");
        message.success("连接测试成功");
      } else {
        const err = data?.error || data?.message || "连接测试失败";
        setTestMessage(String(err));
        message.error(String(err));
      }
    } catch (e: any) {
      const err = e?.message || "连接测试失败";
      setTestMessage(err);
      message.error(err);
    } finally {
      setTesting(false);
    }
  }, []);

  const forceSync = useCallback(async () => {
    try {
      setSyncing(true);
      const res = await unifiedYunwuModelService.forceSync();
      const data = res?.data;
      if (res?.success && data && typeof data === "object") {
        setRoot(normalizePayload(data as Record<string, unknown>));
        message.success("远程模型平台配置已同步");
      } else {
        message.error(res?.data?.error || "同步失败");
      }
    } catch (e: any) {
      message.error(e?.message || "同步失败");
    } finally {
      setSyncing(false);
    }
  }, []);

  return {
    root,
    platformList,
    activePlatform,
    loading,
    saving,
    testing,
    testMessage,
    togglingCustom,
    syncing,
    load,
    setUseCustomModels,
    setUseCustomModelsPersist,
    setActivePlatform,
    setPlatformApiKey,
    setPlatformTierField,
    setYunwuField,
    setYunwuApiKeyForAllTiers,
    setYunwuTierField,
    save,
    testConnection,
    forceSync,
  };
};

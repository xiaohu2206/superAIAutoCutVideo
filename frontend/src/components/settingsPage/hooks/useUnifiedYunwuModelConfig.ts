import { useCallback, useEffect, useRef, useState } from "react";
import { message } from "@/services/message";
import unifiedYunwuModelService from "@/services/unifiedYunwuModelService";
import type { UnifiedYunwuModelsPayload } from "../types";

const YUNWU_DEFAULTS: UnifiedYunwuModelsPayload["yunwu"] = {
  api_key: "",
  base_url: "https://yunwu.ai/v1/chat/completions",
  copywriting_model_name: "gemini-3.1-pro-preview",
  video_analysis_model_name: "gemini-2.5-flash-lite",
  llm_rerank_model_name: "gemini-3.1-pro-preview",
  script_generation_model_name: "gemini-3.1-pro-preview",
};

const emptyRoot = (): UnifiedYunwuModelsPayload => ({
  use_custom_models: true,
  yunwu: { ...YUNWU_DEFAULTS },
});

const AUTOSAVE_DEBOUNCE_MS = 600;

export const useUnifiedYunwuModelConfig = () => {
  const [root, setRoot] = useState<UnifiedYunwuModelsPayload>(emptyRoot);
  const rootRef = useRef(root);
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testMessage, setTestMessage] = useState<string | null>(null);
  const [togglingCustom, setTogglingCustom] = useState(false);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const res = await unifiedYunwuModelService.get();
      const data = res?.data;
      if (res?.success && data && typeof data === "object") {
        setRoot({
          use_custom_models: Boolean(data.use_custom_models),
          yunwu: {
            ...YUNWU_DEFAULTS,
            ...(typeof data.yunwu === "object" && data.yunwu ? data.yunwu : {}),
          },
        });
      }
    } catch (e) {
      console.error("加载云雾整合模型配置失败:", e);
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

  /** 立即同步「是否自定义」到后端，避免仅切换 UI 与后端不一致 */
  const setUseCustomModelsPersist = useCallback(
    async (value: boolean) => {
      try {
        setTogglingCustom(true);
        const res = await unifiedYunwuModelService.update({
          use_custom_models: value,
        });
        const data = res?.data;
        if (res?.success && data && typeof data === "object") {
          setRoot({
            use_custom_models: Boolean(data.use_custom_models),
            yunwu: {
              ...YUNWU_DEFAULTS,
              ...(typeof data.yunwu === "object" && data.yunwu ? data.yunwu : {}),
            },
          });
          message.success(
            value ? "已开启自定义模型（文案 / 视频分析）" : "已使用云雾整合模型"
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
        const yunwu: Record<string, unknown> = { ...payload.yunwu };
        const ak = String(yunwu.api_key ?? "");
        if (ak.includes("*") && ak.length > 8) {
          delete yunwu.api_key;
        }
        const body: Record<string, unknown> = {
          use_custom_models: payload.use_custom_models,
          yunwu,
        };
        const res = await unifiedYunwuModelService.update(body);
        const data = res?.data;
        if (res?.success && data && typeof data === "object") {
          setRoot({
            use_custom_models: Boolean(data.use_custom_models),
            yunwu: {
              ...YUNWU_DEFAULTS,
              ...(typeof data.yunwu === "object" && data.yunwu ? data.yunwu : {}),
            },
          });
          if (toastOnSuccess) {
            message.success("整合模型配置已保存");
          }
        } else {
          message.error("保存失败");
        }
      } catch (e: any) {
        console.error("保存云雾整合模型配置失败:", e);
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

  const setYunwuField = useCallback(
    <K extends keyof UnifiedYunwuModelsPayload["yunwu"]>(
      field: K,
      value: UnifiedYunwuModelsPayload["yunwu"][K]
    ) => {
      setRoot((prev) => ({
        ...prev,
        yunwu: { ...prev.yunwu, [field]: value },
      }));
      scheduleAutosave();
    },
    [scheduleAutosave]
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

  return {
    root,
    loading,
    saving,
    testing,
    testMessage,
    togglingCustom,
    load,
    setUseCustomModels,
    setUseCustomModelsPersist,
    setYunwuField,
    save,
    testConnection,
  };
};

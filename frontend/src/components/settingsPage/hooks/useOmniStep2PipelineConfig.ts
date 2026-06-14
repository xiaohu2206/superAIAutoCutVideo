import { useCallback, useEffect, useRef, useState } from "react";
import { message } from "@/services/message";
import omniStep2PipelineService from "@/services/omniStep2PipelineService";
import type { OmniStep2LocalSettings, OmniStep2PipelinePayload } from "../types";

const DEFAULT_LOCAL: OmniStep2LocalSettings = {
  vl_batch_size: 1,
  infer_wall_sec: 1200,
  vision_api_concurrency: 1,
  text_api_concurrency: 1,
};

function normalizePayload(data: Record<string, unknown>): OmniStep2PipelinePayload {
  const localRaw = data.local;
  const localData =
    localRaw && typeof localRaw === "object"
      ? (localRaw as Partial<OmniStep2LocalSettings> & { api_concurrency?: number })
      : {};
  const legacyConcurrency = Number(localData.api_concurrency) || 1;
  const local: OmniStep2LocalSettings = {
    vl_batch_size: localData.vl_batch_size ?? DEFAULT_LOCAL.vl_batch_size,
    infer_wall_sec: localData.infer_wall_sec ?? DEFAULT_LOCAL.infer_wall_sec,
    vision_api_concurrency:
      localData.vision_api_concurrency ?? legacyConcurrency,
    text_api_concurrency: localData.text_api_concurrency ?? legacyConcurrency,
  };
  const effective =
    data.effective && typeof data.effective === "object"
      ? (data.effective as OmniStep2PipelinePayload["effective"])
      : undefined;
  const legacyEnabled = Boolean(data.use_local_model_pipeline);
  return {
    use_local_vision_model:
      typeof data.use_local_vision_model === "boolean"
        ? data.use_local_vision_model
        : legacyEnabled,
    use_local_text_model:
      typeof data.use_local_text_model === "boolean"
        ? data.use_local_text_model
        : legacyEnabled,
    local,
    effective,
  };
}

const emptyRoot = (): OmniStep2PipelinePayload => ({
  use_local_vision_model: false,
  use_local_text_model: false,
  local: { ...DEFAULT_LOCAL },
});

const AUTOSAVE_DEBOUNCE_MS = 600;

export const useOmniStep2PipelineConfig = () => {
  const [root, setRoot] = useState<OmniStep2PipelinePayload>(emptyRoot);
  const rootRef = useRef(root);
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [togglingModel, setTogglingModel] = useState<"vision" | "text" | null>(null);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const res = await omniStep2PipelineService.get();
      const data = res?.data;
      if (res?.success && data && typeof data === "object") {
        setRoot(normalizePayload(data as Record<string, unknown>));
      }
    } catch (e) {
      console.error("加载 Omni Step2 管线配置失败:", e);
      message.error("加载本地模型管线配置失败");
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

  const persist = useCallback(async (payload: OmniStep2PipelinePayload) => {
    try {
      setSaving(true);
      const res = await omniStep2PipelineService.update({
        use_local_vision_model: payload.use_local_vision_model,
        use_local_text_model: payload.use_local_text_model,
        local: payload.local,
      });
      const data = res?.data;
      if (res?.success && data && typeof data === "object") {
        setRoot(normalizePayload(data as Record<string, unknown>));
      } else {
        message.error("保存失败");
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "保存失败";
      message.error(msg);
      throw e;
    } finally {
      setSaving(false);
    }
  }, []);

  const scheduleAutosave = useCallback(() => {
    if (saveTimerRef.current) {
      clearTimeout(saveTimerRef.current);
    }
    saveTimerRef.current = setTimeout(() => {
      saveTimerRef.current = null;
      void persist(rootRef.current);
    }, AUTOSAVE_DEBOUNCE_MS);
  }, [persist]);

  const setUseLocalModel = useCallback(
    async (model: "vision" | "text", value: boolean) => {
      try {
        setTogglingModel(model);
        const field =
          model === "vision" ? "use_local_vision_model" : "use_local_text_model";
        const res = await omniStep2PipelineService.update({
          [field]: value,
        });
        const data = res?.data;
        if (res?.success && data && typeof data === "object") {
          setRoot(normalizePayload(data as Record<string, unknown>));
          const label = model === "vision" ? "视觉模型" : "文案模型";
          message.success(value ? `已开启本地${label}模式` : `已关闭本地${label}模式`);
        } else {
          message.error("切换失败");
        }
      } catch (e: unknown) {
        const msg = e instanceof Error ? e.message : "切换失败";
        message.error(msg);
        await load();
      } finally {
        setTogglingModel(null);
      }
    },
    [load]
  );

  const setLocalField = useCallback(
    <K extends keyof OmniStep2LocalSettings>(field: K, value: OmniStep2LocalSettings[K]) => {
      setRoot((prev) => ({
        ...prev,
        local: { ...prev.local, [field]: value },
      }));
      scheduleAutosave();
    },
    [scheduleAutosave]
  );

  return {
    root,
    loading,
    saving,
    toggling: togglingModel !== null,
    togglingVision: togglingModel === "vision",
    togglingText: togglingModel === "text",
    load,
    setUseLocalModel,
    setLocalField,
  };
};

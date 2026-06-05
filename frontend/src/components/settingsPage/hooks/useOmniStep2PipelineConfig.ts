import { useCallback, useEffect, useRef, useState } from "react";
import { message } from "@/services/message";
import omniStep2PipelineService from "@/services/omniStep2PipelineService";
import type { OmniStep2LocalSettings, OmniStep2PipelinePayload } from "../types";

const DEFAULT_LOCAL: OmniStep2LocalSettings = {
  vl_batch_size: 1,
  infer_wall_sec: 1200,
  api_concurrency: 1,
};

function normalizePayload(data: Record<string, unknown>): OmniStep2PipelinePayload {
  const localRaw = data.local;
  const local =
    localRaw && typeof localRaw === "object"
      ? { ...DEFAULT_LOCAL, ...(localRaw as Partial<OmniStep2LocalSettings>) }
      : { ...DEFAULT_LOCAL };
  const effective =
    data.effective && typeof data.effective === "object"
      ? (data.effective as OmniStep2PipelinePayload["effective"])
      : undefined;
  return {
    use_local_model_pipeline: Boolean(data.use_local_model_pipeline),
    local,
    effective,
  };
}

const emptyRoot = (): OmniStep2PipelinePayload => ({
  use_local_model_pipeline: false,
  local: { ...DEFAULT_LOCAL },
});

const AUTOSAVE_DEBOUNCE_MS = 600;

export const useOmniStep2PipelineConfig = () => {
  const [root, setRoot] = useState<OmniStep2PipelinePayload>(emptyRoot);
  const rootRef = useRef(root);
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [toggling, setToggling] = useState(false);

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
        use_local_model_pipeline: payload.use_local_model_pipeline,
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

  const setUseLocalModelPipeline = useCallback(
    async (value: boolean) => {
      try {
        setToggling(true);
        const res = await omniStep2PipelineService.update({
          use_local_model_pipeline: value,
        });
        const data = res?.data;
        if (res?.success && data && typeof data === "object") {
          setRoot(normalizePayload(data as Record<string, unknown>));
          message.success(value ? "已开启本地模型低并发模式" : "已恢复云端默认参数");
        } else {
          message.error("切换失败");
        }
      } catch (e: unknown) {
        const msg = e instanceof Error ? e.message : "切换失败";
        message.error(msg);
        await load();
      } finally {
        setToggling(false);
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
    toggling,
    load,
    setUseLocalModelPipeline,
    setLocalField,
  };
};

import { useCallback, useEffect, useMemo, useState } from "react";
import { qwenOnlineTtsService } from "../services/qwenOnlineTtsService";
import type {
  QwenOnlineTtsPatchVoiceInput,
  QwenOnlineTtsUploadVoiceInput,
  QwenOnlineTtsVoice,
} from "../types";

export function useQwenOnlineVoices() {
  const [voices, setVoices] = useState<QwenOnlineTtsVoice[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res: any = await qwenOnlineTtsService.listVoices();
      if (res?.success) {
        setVoices(res.data || []);
      } else {
        setError(res?.message || "加载音色失败");
      }
    } catch (e: any) {
      setError(e?.message || "加载音色失败");
    } finally {
      setLoading(false);
    }
  }, []);

  const upload = useCallback(
    async (input: QwenOnlineTtsUploadVoiceInput, configId?: string) => {
      const res: any = await qwenOnlineTtsService.uploadVoice(input, configId);
      if (!res?.success || !res.data) {
        throw new Error(res?.message || "上传失败");
      }
      await refresh();
      return res.data;
    },
    [refresh]
  );

  const patch = useCallback(
    async (id: string, partial: QwenOnlineTtsPatchVoiceInput) => {
      const res: any = await qwenOnlineTtsService.patchVoice(id, partial);
      if (!res?.success || !res.data) {
        throw new Error(res?.message || "更新失败");
      }
      setVoices((prev) => prev.map((v) => (v.id === id ? res.data! : v)));
      return res.data;
    },
    []
  );

  const remove = useCallback(async (id: string, removeFiles: boolean) => {
    const res: any = await qwenOnlineTtsService.deleteVoice(id, removeFiles);
    if (!res?.success) {
      throw new Error(res?.message || "删除失败");
    }
    setVoices((prev) => prev.filter((v) => v.id !== id));
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const byId = useMemo(() => {
    const m = new Map<string, QwenOnlineTtsVoice>();
    voices.forEach((v) => m.set(v.id, v));
    return m;
  }, [voices]);

  return {
    voices,
    byId,
    loading,
    error,
    refresh,
    upload,
    patch,
    remove,
  };
}

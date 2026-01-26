import { useCallback, useEffect, useMemo, useState } from "react";
import { useWsScopeProgress } from "@/hooks/useWsScopeProgress";
import { message } from "@/services/message";
import { qwen3TtsService } from "../services/qwen3TtsService";
import type { Qwen3TtsPatchVoiceInput, Qwen3TtsUploadVoiceInput, Qwen3TtsVoice } from "../types";

export type Qwen3CloneEvent = {
  voice_id: string;
  job_id?: string;
  phase?: string;
  progress?: number;
  message?: string;
  type?: string;
  timestamp?: string;
};

export function useQwen3Voices() {
  const [voices, setVoices] = useState<Qwen3TtsVoice[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [cloneEventByVoiceId, setCloneEventByVoiceId] = useState<Record<string, Qwen3CloneEvent>>({});

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await qwen3TtsService.listVoices();
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

  const upload = useCallback(async (input: Qwen3TtsUploadVoiceInput) => {
    const res = await qwen3TtsService.uploadVoice(input);
    if (!res?.success || !res.data) {
      throw new Error(res?.message || "上传失败");
    }
    await refresh();
    return res.data;
  }, [refresh]);

  const patch = useCallback(async (id: string, partial: Qwen3TtsPatchVoiceInput) => {
    const res = await qwen3TtsService.patchVoice(id, partial);
    if (!res?.success || !res.data) {
      throw new Error(res?.message || "更新失败");
    }
    setVoices((prev) => prev.map((v) => (v.id === id ? res.data! : v)));
    return res.data;
  }, []);

  const remove = useCallback(async (id: string, removeFiles: boolean) => {
    const res = await qwen3TtsService.deleteVoice(id, removeFiles);
    if (!res?.success) {
      throw new Error(res?.message || "删除失败");
    }
    setVoices((prev) => prev.filter((v) => v.id !== id));
    setCloneEventByVoiceId((prev) => {
      if (!prev[id]) return prev;
      const next = { ...prev };
      delete next[id];
      return next;
    });
  }, []);

  const startClone = useCallback(async (id: string) => {
    setVoices((prev) =>
      prev.map((v) =>
        v.id === id
          ? { ...v, status: "cloning", progress: Math.max(1, Number(v.progress || 0)), last_error: null }
          : v
      )
    );
    const res = await qwen3TtsService.startClone(id);
    if (!res?.success) {
      throw new Error(res?.message || "启动克隆失败");
    }
    message.info("已开始克隆（预处理）");
    return res.data?.job_id || "";
  }, []);

  const syncCloneStatus = useCallback(async (id: string) => {
    try {
      const res = await qwen3TtsService.getCloneStatus(id);
      if (!res?.success || !res.data) return;
      const st = res.data;
      setVoices((prev) =>
        prev.map((v) =>
          v.id !== id
            ? v
            : {
                ...v,
                status: st.status || v.status,
                progress: typeof st.progress === "number" ? st.progress : v.progress,
                last_error: st.last_error ?? v.last_error,
                ref_audio_url: st.ref_audio_url ?? v.ref_audio_url,
                ref_audio_path: st.ref_audio_path ?? v.ref_audio_path,
              }
        )
      );
    } catch (e) {
      void e;
    }
  }, []);

  useWsScopeProgress({
    scope: "qwen3_tts_voice_clone",
    match: (msg) => Boolean((msg as any).voice_id),
    onMessage: (wsMsg) => {
      const vid = (wsMsg as any).voice_id as string | undefined;
      if (!vid) return;
      setCloneEventByVoiceId((prev) => ({
        ...prev,
        [vid]: {
          voice_id: vid,
          job_id: (wsMsg as any).job_id,
          phase: (wsMsg as any).phase,
          progress: typeof wsMsg.progress === "number" ? wsMsg.progress : undefined,
          message: wsMsg.message,
          type: wsMsg.type,
          timestamp: wsMsg.timestamp,
        },
      }));

      if (wsMsg.type === "progress") {
        setVoices((prev) =>
          prev.map((v) =>
            v.id !== vid
              ? v
              : {
                  ...v,
                  status: "cloning",
                  progress: typeof wsMsg.progress === "number" ? wsMsg.progress : v.progress,
                  last_error: null,
                }
          )
        );
      }

      if (wsMsg.type === "completed") {
        setVoices((prev) =>
          prev.map((v) => (v.id !== vid ? v : { ...v, status: "ready", progress: 100, last_error: null }))
        );
        void syncCloneStatus(vid);
      }

      if (wsMsg.type === "error") {
        const errText = String(wsMsg.message || "");
        setVoices((prev) =>
          prev.map((v) => (v.id !== vid ? v : { ...v, status: "failed", progress: 0, last_error: errText || v.last_error }))
        );
        void syncCloneStatus(vid);
      }
    },
  });

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const byId = useMemo(() => {
    const m = new Map<string, Qwen3TtsVoice>();
    voices.forEach((v) => m.set(v.id, v));
    return m;
  }, [voices]);

  return {
    voices,
    byId,
    loading,
    error,
    cloneEventByVoiceId,
    refresh,
    upload,
    patch,
    remove,
    startClone,
    syncCloneStatus,
  };
}

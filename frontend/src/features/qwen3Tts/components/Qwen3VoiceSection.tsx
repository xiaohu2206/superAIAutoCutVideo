import React, { useMemo, useState } from "react";
import { Plus, RefreshCw } from "lucide-react";
import { message } from "@/services/message";
import { useQwen3Voices } from "../hooks/useQwen3Voices";
import Qwen3ModelSection from "./Qwen3ModelSection";
import Qwen3VoiceEditDialog from "./Qwen3VoiceEditDialog";
import Qwen3VoiceList from "./Qwen3VoiceList";
import Qwen3VoiceUploadDialog, { type Qwen3VoiceUploadDialogResult } from "./Qwen3VoiceUploadDialog";
import type { Qwen3TtsVoice } from "../types";

export type Qwen3VoiceSectionProps = {
  configId: string | null;
  activeVoiceId: string;
  onSetActive: (voiceId: string) => Promise<void> | void;
};

export const Qwen3VoiceSection: React.FC<Qwen3VoiceSectionProps> = ({ configId, activeVoiceId, onSetActive }) => {
  const { voices, loading, error, cloneEventByVoiceId, refresh, upload, patch, remove, startClone } = useQwen3Voices();
  const [uploadOpen, setUploadOpen] = useState<boolean>(false);
  const [editVoice, setEditVoice] = useState<Qwen3TtsVoice | null>(null);

  const modelKeys = useMemo(() => {
    const keys = Array.from(new Set((voices || []).map((v) => String(v.model_key || "").trim()).filter(Boolean)));
    const base = "base_0_6b";
    if (!keys.includes(base)) keys.unshift(base);
    return keys.length ? keys : [base];
  }, [voices]);

  const handleUploadSubmit = async (result: Qwen3VoiceUploadDialogResult) => {
    const created = await upload(result.input);
    message.success("上传成功");
    if (result.autoStartClone) {
      try {
        await startClone(created.id);
      } catch (e: any) {
        message.warning(e?.message || "自动开始克隆失败，可在列表手动点击“克隆”");
      }
    }
  };

  return (
    <div className="space-y-6">
      <Qwen3ModelSection />

      <section className="bg-white/80 backdrop-blur border rounded-xl p-5 shadow-sm space-y-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h4 className="text-md font-semibold text-gray-900">Qwen3-TTS 克隆音色</h4>
            {error ? <div className="text-xs text-red-600 mt-1">{error}</div> : null}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => refresh()}
              disabled={loading}
              className={`px-3 py-1.5 text-sm rounded-md border ${loading ? "bg-gray-100 text-gray-400" : "bg-white hover:bg-gray-50 text-gray-700"}`}
            >
              <span className="inline-flex items-center gap-2">
                <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
                刷新
              </span>
            </button>
            <button
              onClick={() => setUploadOpen(true)}
              disabled={loading}
              className={`px-3 py-1.5 text-sm rounded-md ${loading ? "bg-gray-300 text-gray-500" : "bg-blue-600 text-white hover:bg-blue-700"}`}
            >
              <span className="inline-flex items-center gap-2">
                <Plus className="h-4 w-4" />
                上传参考音频
              </span>
            </button>
          </div>
        </div>

        <Qwen3VoiceList
          voices={voices}
          cloneEventByVoiceId={cloneEventByVoiceId}
          activeVoiceId={activeVoiceId}
          configId={configId}
          provider="qwen3_tts"
          onSetActive={onSetActive}
          onStartClone={async (voiceId) => {
            try {
              await startClone(voiceId);
            } catch (e: any) {
              message.error(e?.message || "启动克隆失败");
            }
          }}
          onEdit={(v) => setEditVoice(v)}
          onDelete={async (voiceId, removeFiles) => {
            await remove(voiceId, removeFiles);
          }}
        />
      </section>

      <Qwen3VoiceUploadDialog
        isOpen={uploadOpen}
        modelKeys={modelKeys}
        onClose={() => setUploadOpen(false)}
        onSubmit={handleUploadSubmit}
      />

      <Qwen3VoiceEditDialog
        isOpen={Boolean(editVoice)}
        voice={editVoice}
        modelKeys={modelKeys}
        onClose={() => setEditVoice(null)}
        onSubmit={async (voiceId, p) => {
          await patch(voiceId, p);
          message.success("已保存");
        }}
      />
    </div>
  );
};

export default Qwen3VoiceSection;

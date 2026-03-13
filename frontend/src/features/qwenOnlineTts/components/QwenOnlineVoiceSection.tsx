import React, { useCallback, useState } from "react";
import { RefreshCw } from "lucide-react";
import { message } from "@/services/message";
import { useQwenOnlineVoices } from "../hooks/useQwenOnlineVoices";
import QwenOnlineVoiceList from "./QwenOnlineVoiceList";
import QwenOnlineVoiceUploadDialog, {
  type QwenOnlineVoiceUploadDialogResult,
} from "./QwenOnlineVoiceUploadDialog";
import type { QwenOnlineTtsVoice } from "../types";

export type QwenOnlineVoiceSectionProps = {
  configId: string | null;
  activeVoiceId: string;
  onSetActive: (voiceId: string) => Promise<void> | void;
};

export const QwenOnlineVoiceSection: React.FC<QwenOnlineVoiceSectionProps> = ({
  configId,
  activeVoiceId,
  onSetActive,
}) => {
  const { voices, loading, error, refresh, upload, patch, remove } =
    useQwenOnlineVoices();

  const [uploadOpen, setUploadOpen] = useState<boolean>(false);
  const [editVoice, setEditVoice] = useState<QwenOnlineTtsVoice | null>(null);

  const closeDialog = () => {
    setUploadOpen(false);
    setEditVoice(null);
  };

  const handleUploadSubmit = async (
    result: QwenOnlineVoiceUploadDialogResult
  ) => {
    if ("edit" in result && result.edit) {
      await patch(result.voiceId, result.patch);
      message.success("已保存");
    } else {
      const r = result as { edit?: false; input: any };
      const created = await upload(r.input, configId || undefined);
      await onSetActive(created.id);
      message.success("上传成功，已设为当前音色");
    }
    closeDialog();
  };

  const handleSetActive = useCallback(
    async (voiceId: string) => {
      await onSetActive(voiceId);
    },
    [onSetActive]
  );

  const handleEdit = (voice: QwenOnlineTtsVoice) => {
    setEditVoice(voice);
    setUploadOpen(true);
  };

  const handleDelete = async (voiceId: string, removeFiles: boolean) => {
    await remove(voiceId, removeFiles);
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h4 className="text-md font-semibold text-gray-900">复刻音色</h4>
          <p className="text-xs text-gray-500 mt-0.5">
            上传参考音频创建专属音色
          </p>
        </div>
        <button
          onClick={() => refresh()}
          disabled={loading}
          className={`p-1.5 rounded-md text-gray-500 hover:bg-gray-100 transition-all ${
            loading ? "animate-spin" : ""
          }`}
          title="刷新列表"
        >
          <RefreshCw className="h-4 w-4" />
        </button>
      </div>

      {error && (
        <div className="text-xs text-red-600 bg-red-50 p-2 rounded">
          {error}
        </div>
      )}

      <QwenOnlineVoiceList
        voices={voices}
        activeVoiceId={activeVoiceId}
        configId={configId}
        provider="qwen_online_tts"
        onSetActive={handleSetActive}
        onEdit={handleEdit}
        onDelete={handleDelete}
        onUpload={() => setUploadOpen(true)}
      />

      <QwenOnlineVoiceUploadDialog
        isOpen={uploadOpen}
        voice={editVoice || undefined}
        onClose={closeDialog}
        onSubmit={handleUploadSubmit}
      />
    </div>
  );
};

export default QwenOnlineVoiceSection;

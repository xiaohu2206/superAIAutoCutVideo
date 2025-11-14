import { ttsService } from "@/services/ttsService";
import { PlayCircle } from "lucide-react";
import React, { useMemo, useState } from "react";
import type { TtsVoice } from "../../types";

interface Props {
  provider: string;
  configId: string | null;
  voices: TtsVoice[];
  activeVoiceId: string;
  hasCredentials: boolean;
}

export const TtsPreviewPlayer: React.FC<Props> = ({ provider, configId, voices, activeVoiceId, hasCredentials }) => {
  const [text, setText] = useState<string>("你好，这是一段试听文本。");
  const [loading, setLoading] = useState<boolean>(false);
  const activeVoice = useMemo(() => voices.find((v) => v.id === activeVoiceId), [voices, activeVoiceId]);

  const handlePreview = async () => {
    if (!activeVoice) return;
    try {
      setLoading(true);
      if (hasCredentials && configId) {
        const res = await ttsService.previewVoice(activeVoice.id, {
          config_id: configId,
          text,
        });
        const url = res?.data?.audio_url || activeVoice.sample_wav_url;
        const audio = new Audio(url);
        audio.play();
      } else {
        const audio = new Audio(activeVoice.sample_wav_url);
        audio.play();
      }
    } catch (error) {
      const audio = new Audio(activeVoice.sample_wav_url);
      audio.play();
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <h4 className="text-md font-semibold text-gray-900 mb-2">预览</h4>
      <div className="flex items-center gap-3">
        <input
          type="text"
          value={text}
          onChange={(e) => setText(e.target.value)}
          className="px-3 py-2 border border-gray-300 rounded-md flex-1"
          placeholder="输入预览文本"
        />
        <button
          className="inline-flex items-center px-3 py-2 bg-gray-100 hover:bg-gray-200 rounded-md text-gray-800 text-sm"
          onClick={handlePreview}
          disabled={!activeVoice || loading}
        >
          <PlayCircle className="h-4 w-4 mr-1" /> 使用当前音色试听
        </button>
      </div>
      {!hasCredentials && (
        <div className="text-xs text-orange-600 mt-2">凭据不完整，回退播放音色示例音频</div>
      )}
    </div>
  );
};

export default TtsPreviewPlayer;
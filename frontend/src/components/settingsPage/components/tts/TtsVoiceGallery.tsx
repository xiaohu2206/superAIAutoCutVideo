import { apiClient } from "@/services/clients";
import { ttsService } from "@/services/ttsService";
import { Headphones, PlayCircle, Volume2 } from "lucide-react";
import React from "react";
import type { TtsVoice } from "../../types";

interface Props {
  voices: TtsVoice[];
  activeVoiceId: string;
  configId: string | null;
  hasCredentials: boolean;
  onSetActive: (voiceId: string) => Promise<void> | void;
}

export const TtsVoiceGallery: React.FC<Props> = ({ voices, activeVoiceId, configId, hasCredentials, onSetActive }) => {
  const audioRef = React.useRef<HTMLAudioElement | null>(null);
  const playingVoiceIdRef = React.useRef<string | null>(null);

  const stopCurrent = () => {
    const a = audioRef.current;
    if (a) {
      a.pause();
      a.currentTime = 0;
      audioRef.current = null;
      playingVoiceIdRef.current = null;
    }
  };

  const resolveUrl = (url: string): string => {
    if (!url) return url;
    const isAbsolute = /^https?:\/\//i.test(url);
    if (isAbsolute) return url;
    if (url.startsWith("/")) {
      return `${apiClient.getBaseUrl()}${url}`;
    }
    return url;
  };

  const playUrl = (url: string, voiceId: string) => {
    stopCurrent();
    const audio = new Audio(resolveUrl(url));
    audioRef.current = audio;
    playingVoiceIdRef.current = voiceId;
    audio.onended = () => {
      audioRef.current = null;
      playingVoiceIdRef.current = null;
    };
    audio.play();
  };

  const handlePreview = async (voice: TtsVoice) => {
    const current = audioRef.current;
    if (playingVoiceIdRef.current === voice.id && current && !current.paused) {
      stopCurrent();
      return;
    }
    try {
      if (hasCredentials && configId) {
        const res = await ttsService.previewVoice(voice.id, {
          config_id: configId,
          text: "您好，欢迎使用智能配音。",
        });
        const url = res?.data?.sample_wav_url || res?.data?.audio_url || voice.sample_wav_url;
        playUrl(url, voice.id);
      } else {
        if (voice.sample_wav_url) {
          playUrl(voice.sample_wav_url, voice.id);
        }
      }
    } catch (error) {
      if (voice.sample_wav_url) {
        playUrl(voice.sample_wav_url, voice.id);
      }
    }
  };

  React.useEffect(() => {
    return () => stopCurrent();
  }, []);

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4">
      {voices.map((v) => {
        const isActive = v.id === activeVoiceId;
        return (
          <div key={v.id} className={`border rounded-md p-3 ${isActive ? "border-blue-500" : "border-gray-200"}`}>
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                <Volume2 className="h-4 w-4 text-gray-700" />
                <span className="font-medium text-gray-900 text-sm">{v.name}</span>
              </div>
              {isActive && (
                <span className="text-xs bg-blue-50 text-blue-700 px-2 py-1 rounded">当前已选</span>
              )}
            </div>
            {v.description && (
              <p className="text-xs text-gray-600 mb-3 line-clamp-2">{v.description}</p>
            )}
            <div className="flex items-center gap-2">
              <button
                className="inline-flex items-center px-2 py-1 text-xs bg-gray-100 hover:bg-gray-200 rounded-md text-gray-700"
                onClick={() => handlePreview(v)}
                title="试听"
              >
                <PlayCircle className="h-4 w-4 mr-1" /> 试听
              </button>
              <button
                className="inline-flex items-center px-2 py-1 text-xs bg-blue-600 hover:bg-blue-700 rounded-md text-white"
                onClick={() => onSetActive(v.id)}
                title="设为当前"
                disabled={!hasCredentials}
              >
                <Headphones className="h-4 w-4 mr-1" /> 设为当前
              </button>
              {!hasCredentials && (
                <span className="text-xs text-orange-600">请先填写凭据</span>
              )}
            </div>
          </div>
        );
      })}
      {voices.length === 0 && (
        <div className="text-gray-500 text-sm">暂无音色，请选择引擎或检查网络。</div>
      )}
    </div>
  );
};

export default TtsVoiceGallery;

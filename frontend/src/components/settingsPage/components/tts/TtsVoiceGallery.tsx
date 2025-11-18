import { apiClient } from "@/services/clients";
import { ttsService } from "@/services/ttsService";
import { Headphones, PlayCircle, Volume2 } from "lucide-react";
import React from "react";
import type { TtsTestResult, TtsVoice } from "../../types";
import { LabeledGroup } from "./LabeledGroup";
import { getGenderLabel } from "./utils";

interface Props {
  voices: TtsVoice[];
  activeVoiceId: string;
  configId: string | null;
  hasCredentials: boolean;
  testResult?: TtsTestResult | null;
  testDurationMs?: number | null;
  onSetActive: (voiceId: string) => Promise<void> | void;
}

export const TtsVoiceGallery: React.FC<Props> = ({ voices, activeVoiceId, configId, hasCredentials, testResult, testDurationMs, onSetActive }) => {
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
  
  const grouped = React.useMemo(() => {
    const buckets: Record<string, TtsVoice[]> = {};
    voices.forEach(v => {
      const key = v.voice_quality || "未标注";
      if (!buckets[key]) buckets[key] = [];
      buckets[key].push(v);
    });
    return buckets;
  }, [voices]);

  const groupNames = React.useMemo(() => {
    return Object.keys(grouped).sort((a, b) => {
      const na = parseInt(a, 10);
      const nb = parseInt(b, 10);
      if (!isNaN(na) && !isNaN(nb)) return nb - na;
      return a.localeCompare(b);
    });
  }, [grouped]);

  

  return (
    <div className="space-y-6">
      {groupNames.map(groupName => (
        <div key={groupName}>
            <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-3">
              <h5 className="text-sm font-semibold text-gray-800">模型类型: {groupName}</h5>
              <LabeledGroup
                label="标签"
                items={Array.from(
                  new Set((grouped[groupName] || []).map(v => v.voice_type_tag).filter(Boolean))
                ).map(tag => String(tag))}
              />
            </div>
            <div className="flex items-center gap-3">
              <span className="text-[10px] text-gray-500">共 {grouped[groupName].length} 个音色</span>
            </div>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4">
            {grouped[groupName].map((v) => {
              const isActive = v.id === activeVoiceId;
              return (
                <div key={v.id} className={`border rounded-md p-3 ${isActive ? "border-blue-500" : "border-gray-200"}`}>
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <Volume2 className="h-4 w-4 text-gray-700" />
                      <span className="font-medium text-gray-900 text-sm">{v.name}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      {v.gender && (
                        <span className="text-[10px] px-2 py-0.5 rounded-full bg-gray-100 text-gray-700 border border-gray-200">
                          {getGenderLabel(v.gender)}
                        </span>
                      )}
                      {isActive && (
                        <span className="text-xs bg-blue-50 text-blue-700 px-2 py-1 rounded">当前已选</span>
                      )}
                    </div>
                  </div>
                  {v.description && (
                    <p className="text-xs text-gray-600 mb-3 line-clamp-2">{v.description}</p>
                  )}
                  <div className="flex flex-wrap gap-1 mb-3">
                    {v.voice_type_tag && (
                      <span className="text-[10px] px-2 py-0.5 rounded bg-gray-100 text-gray-700 border border-gray-200">
                        {v.voice_type_tag}
                      </span>
                    )}
                    {Array.isArray(v.tags) && v.tags.length > 0 && v.tags.slice(1).map(tag => (
                      <span key={tag} className="text-[10px] px-2 py-0.5 rounded bg-gray-100 text-gray-700 border border-gray-200">
                        {tag}
                      </span>
                    ))}
                    {v.voice_human_style && (
                      <span className="text-[10px] px-2 py-0.5 rounded bg-gray-50 text-gray-600 border border-gray-200">
                        {v.voice_human_style}
                      </span>
                    )}
                  </div>
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
          </div>
        </div>
      ))}
      {voices.length === 0 && (
        <div className="text-gray-500 text-sm">暂无音色，请选择引擎或检查网络。</div>
      )}
    </div>
  );
};

export default TtsVoiceGallery;

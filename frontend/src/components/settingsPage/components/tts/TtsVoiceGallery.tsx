import { apiClient } from "@/services/clients";
import { ttsService } from "@/services/ttsService";
import { ChevronDown, ChevronUp, Play, Pause, Check, Loader } from "lucide-react";
import React from "react";
import type { TtsTestResult, TtsVoice } from "../../types";
import { LabeledGroup } from "./LabeledGroup";
import { getGenderLabel } from "./utils";

interface Props {
  voices: TtsVoice[];
  activeVoiceId: string;
  configId: string | null;
  provider?: string;
  hasCredentials: boolean;
  testResult?: TtsTestResult | null;
  testDurationMs?: number | null;
  onSetActive: (voiceId: string) => Promise<void> | void;
}

const VoiceRow = React.memo(({ 
  voice, 
  isActive, 
  isPlaying, 
  isLoading,
  isDisabled,
  progress,
  onPreview, 
  onSelect, 
  canSelect 
}: {
  voice: TtsVoice;
  isActive: boolean;
  isPlaying: boolean;
  isLoading: boolean;
  isDisabled: boolean;
  progress?: number;
  onPreview: (v: TtsVoice) => void;
  onSelect: (id: string) => void;
  canSelect: boolean;
}) => {
  return (
    <div className={`
      group flex items-center gap-3 px-4 h-[48px] border-b border-gray-100 last:border-0 transition-all cursor-default relative
      ${isActive ? "bg-blue-50/60" : "hover:bg-gray-50"}
    `}>
      {/* Play Button */}
      <button
        onClick={(e) => {
          e.stopPropagation();
          onPreview(voice);
        }}
        className={`
          flex-shrink-0 w-8 h-8 flex items-center justify-center rounded-full transition-all
          ${isPlaying 
            ? "bg-blue-100 text-blue-600" 
            : "bg-gray-100 text-gray-500 group-hover:bg-blue-600 group-hover:text-white group-hover:shadow-sm"}
        `}
        disabled={isDisabled}
        title="点击试听"
      >
        {isLoading ? (
          <Loader className="w-3.5 h-3.5 animate-spin" />
        ) : isPlaying ? (
          <Pause className="w-3.5 h-3.5 fill-current" />
        ) : (
          <Play className="w-3.5 h-3.5 ml-0.5 fill-current" />
        )}
      </button>

      {/* Main Info */}
      <div className="flex-1 min-w-0 flex items-center gap-3">
        <span className={`text-sm font-medium truncate min-w-[80px] ${isActive ? "text-blue-700" : "text-gray-900"}`}>
          {voice.name}
        </span>
        
        {/* Tags */}
        <div className="flex items-center gap-1.5 flex-shrink-0">
          {voice.gender && (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-gray-100 text-gray-500 border border-gray-200">
              {getGenderLabel(voice.gender)}
            </span>
          )}
          {voice.voice_type_tag && (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-gray-100 text-gray-500 border border-gray-200 hidden sm:inline-block">
              {voice.voice_type_tag}
            </span>
          )}
          {voice.voice_human_style && (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-orange-50 text-orange-600 border border-orange-100 hidden md:inline-block">
              {voice.voice_human_style}
            </span>
          )}
        </div>

        {/* Description - truncate heavily */}
        {voice.description && (
          <span className="hidden lg:block text-xs text-gray-400 truncate max-w-[300px] ml-auto mr-4">
            {voice.description}
          </span>
        )}
      </div>

      {/* Action */}
      <div className="flex-shrink-0 ml-auto pl-2">
        {isActive ? (
           <div className="flex items-center gap-1.5 text-blue-600 bg-blue-100/50 px-2.5 py-1 rounded-full border border-blue-200/50">
              <Check className="w-3.5 h-3.5" />
              <span className="text-xs font-medium">使用中</span>
           </div>
        ) : (
            <button
              onClick={() => onSelect(voice.id)}
              disabled={!canSelect}
              className={`
                text-xs px-3 py-1.5 rounded-md border transition-all font-medium
                ${canSelect 
                  ? "bg-white border-gray-200 text-gray-700 hover:border-blue-300 hover:text-blue-600 hover:bg-blue-50 hover:shadow-sm" 
                  : "bg-gray-50 border-gray-100 text-gray-400 cursor-not-allowed"}
              `}
            >
              选择
            </button>
        )}
      </div>
      {isPlaying && typeof progress === "number" && (
        <div className="absolute left-0 right-0 bottom-0 h-[2px] bg-blue-100">
          <div
            className="h-full bg-blue-500 transition-all"
            style={{ width: `${Math.max(0, Math.min(100, (progress || 0) * 100))}%` }}
          />
        </div>
      )}
    </div>
  );
});

export const TtsVoiceGallery: React.FC<Props> = ({ voices, activeVoiceId, configId, provider, hasCredentials, testResult, testDurationMs, onSetActive }) => {
  const audioRef = React.useRef<HTMLAudioElement | null>(null);
  const [playingVoiceId, setPlayingVoiceId] = React.useState<string | null>(null);
  const [previewLoadingVoiceId, setPreviewLoadingVoiceId] = React.useState<string | null>(null);
  const [playProgress, setPlayProgress] = React.useState<number>(0);
  void testResult;
  void testDurationMs;
  const canSelect = provider === "tencent_tts" ? true : hasCredentials;

  const stopCurrent = () => {
    const a = audioRef.current;
    if (a) {
      a.pause();
      a.currentTime = 0;
      audioRef.current = null;
      setPlayingVoiceId(null);
      setPlayProgress(0);
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
    setPlayingVoiceId(voiceId);
    setPlayProgress(0);
    audio.ontimeupdate = () => {
      const d = audio.duration || 0;
      const c = audio.currentTime || 0;
      setPlayProgress(d > 0 ? c / d : 0);
    };
    audio.onended = () => {
      audioRef.current = null;
      setPlayingVoiceId(null);
      setPlayProgress(0);
    };
    audio.play();
  };

  const handlePreview = async (voice: TtsVoice) => {
    if (playingVoiceId === voice.id) {
      stopCurrent();
      return;
    }
    const busyVoiceId = previewLoadingVoiceId || playingVoiceId;
    if (busyVoiceId && busyVoiceId !== voice.id) {
      return;
    }
    try {
      const getDefaultPreviewText = (v: TtsVoice): string => {
        const lang = (v.language || "").toLowerCase();
        const code = (lang.split("-")[0] || "");
        if (code === "zh") return "您好，欢迎使用智能配音。";
        if (code === "en") return "Hello, welcome to smart voiceover.";
        if (code === "ja") return "こんにちは、スマート音声合成へようこそ。";
        if (code === "ko") return "안녕하세요, 스마트 보이스오버에 오신 것을 환영합니다.";
        if (code === "es") return "Hola, bienvenido al doblaje inteligente.";
        if (code === "fr") return "Bonjour, bienvenue sur la voix off intelligente.";
        if (code === "de") return "Hallo, willkommen bei der intelligenten Sprachsynthese.";
        if (code === "ru") return "Здравствуйте, добро пожаловать в интеллектуальное озвучивание.";
        if (code === "it") return "Ciao, benvenuto nel doppiaggio intelligente.";
        if (code === "pt") return "Olá, bem-vindo à locução inteligente.";
        if (code === "hi") return "नमस्ते, स्मार्ट वॉयसओवर में आपका स्वागत है.";
        if (code === "ar") return "مرحبًا، مرحبًا بك في التعليق الصوتي الذكي.";
        if (code === "tr") return "Merhaba, akıllı seslendirmeye hoş geldiniz.";
        if (code === "vi") return "Xin chào, chào mừng đến với thuyết minh thông minh.";
        if (code === "th") return "สวัสดี ยินดีต้อนรับสู่เสียงพากย์อัจฉริยะ";
        if (code === "id") return "Halo, selamat datang di sulih suara pintar.";
        return "Hello, welcome to smart voiceover.";
      };

      if (hasCredentials && configId) {
        setPreviewLoadingVoiceId(voice.id);
        const res = await ttsService.previewVoice(voice.id, {
          config_id: configId,
          provider,
          text: getDefaultPreviewText(voice),
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
    finally {
      setPreviewLoadingVoiceId((prev) => (prev === voice.id ? null : prev));
    }
  };

  React.useEffect(() => {
    return () => stopCurrent();
  }, []);
  
  // 仅展示中文和英文音色
  const voicesForDisplay = React.useMemo(() => {
    if (provider === "tencent_tts") return voices;
    return voices.filter(v => {
      const lang = (v.language || "").toLowerCase();
      return lang.startsWith("zh") || lang.startsWith("en");
    });
  }, [provider, voices]);

  const grouped = React.useMemo(() => {
    const buckets: Record<string, TtsVoice[]> = {};
    voicesForDisplay.forEach(v => {
      const lang = (v.language || "").toLowerCase();
      const key = provider === "tencent_tts"
        ? (v.category || "其他")
        : (lang.startsWith("zh") ? "中文" : lang.startsWith("en") ? "英文" : (v.language || "未标注语言"));
      if (!buckets[key]) buckets[key] = [];
      buckets[key].push(v);
    });
    return buckets;
  }, [provider, voicesForDisplay]);

  const groupNames = React.useMemo(() => {
    const names = Object.keys(grouped);
    const priority = (x: string) => {
      if (provider === "tencent_tts") return 0;
      return x === "中文" ? 0 : x === "英文" ? 1 : 2;
    };
    return names.sort((a, b) => {
      const pa = priority(a);
      const pb = priority(b);
      if (pa !== pb) return pa - pb;
      return a.localeCompare(b);
    });
  }, [grouped]);

  const [openGroups, setOpenGroups] = React.useState<Record<string, boolean>>({});
  const toggleGroup = (name: string) => {
    setOpenGroups(prev => {
      const current = prev[name] ?? (provider === "tencent_tts" ? true : (name === "中文" || name === "英文"));
      return { ...prev, [name]: !current };
    });
  };

  return (
    <div className="space-y-4">
      {groupNames.map(groupName => (
        <div key={groupName} className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
          <div
            className="px-4 py-3 bg-gray-50/50 border-b border-gray-100 cursor-pointer hover:bg-gray-50 transition-colors"
            onClick={() => toggleGroup(groupName)}
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3 flex-wrap min-w-0">
                <h5 className="text-sm font-semibold text-gray-800">语言: {groupName}</h5>
                <div className="min-w-0 max-w-full overflow-x-auto">
                  <LabeledGroup
                    label="标签"
                    items={Array.from(
                      new Set((grouped[groupName] || []).map(v => v.voice_type_tag).filter(Boolean))
                    ).map(tag => String(tag))}
                  />
                </div>
                <span className="text-[10px] text-gray-500 bg-gray-100 px-1.5 py-0.5 rounded-full">
                   {grouped[groupName].length}
                </span>
              </div>
              {(openGroups[groupName] ?? (provider === "tencent_tts" ? true : (groupName === "中文" || groupName === "英文"))) ? (
                <ChevronUp className="h-4 w-4 text-gray-400" />
              ) : (
                <ChevronDown className="h-4 w-4 text-gray-400" />
              )}
            </div>
          </div>
          {(openGroups[groupName] ?? (provider === "tencent_tts" ? true : (groupName === "中文" || groupName === "英文"))) && (
            <div className="divide-y divide-gray-100">
              {grouped[groupName].map((v) => (
                <VoiceRow 
                  key={v.id} 
                  voice={v} 
                  isActive={v.id === activeVoiceId} 
                  isPlaying={playingVoiceId === v.id}
                  isLoading={previewLoadingVoiceId === v.id}
                  isDisabled={Boolean((previewLoadingVoiceId || playingVoiceId) && (v.id !== (previewLoadingVoiceId || playingVoiceId)))}
                  progress={playingVoiceId === v.id ? playProgress : 0}
                  onPreview={handlePreview}
                  onSelect={onSetActive}
                  canSelect={canSelect}
                />
              ))}
            </div>
          )}
        </div>
      ))}
      {voicesForDisplay.length === 0 && (
        <div className="text-gray-500 text-sm text-center py-8 bg-gray-50 rounded-lg border border-dashed border-gray-200">
          暂无音色，请选择引擎或检查网络。
        </div>
      )}
    </div>
  );
};

export default TtsVoiceGallery;

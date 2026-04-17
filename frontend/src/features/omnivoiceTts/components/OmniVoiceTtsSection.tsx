import { apiClient } from "@/services/clients";
import { message } from "@/services/message";
import { ttsService } from "@/services/ttsService";
import type { TtsTestResult, TtsVoice } from "@/components/settingsPage/types";
import {
  AlertCircle,
  CheckCircle,
  Loader,
  RefreshCw,
  Trash2,
  Upload,
  Wifi,
  WifiOff,
  X,
} from "lucide-react";
import React, { useCallback, useEffect, useState } from "react";
import { createPortal } from "react-dom";

export type OmniVoiceTtsSectionProps = {
  configId: string | null;
  activeVoiceId: string;
  onSetActive: (voiceId: string) => Promise<void>;
  onConnectionChange?: (connected: boolean) => void;
  onVoicesRefresh?: () => Promise<void>;
  onConfigRefresh?: () => Promise<void>;
  onTestConnection: () => void | Promise<void>;
  testing: boolean;
  testResult: TtsTestResult | null;
  testDurationMs: number | null;
};

const resolveUrl = (url: string): string => {
  if (!url) return url;
  if (/^https?:\/\//i.test(url)) return url;
  if (url.startsWith("/")) return `${apiClient.getBaseUrl()}${url}`;
  return url;
};

export const OmniVoiceTtsSection: React.FC<OmniVoiceTtsSectionProps> = ({
  configId,
  activeVoiceId,
  onSetActive,
  onConnectionChange,
  onVoicesRefresh,
  onConfigRefresh,
  onTestConnection,
  testing,
  testResult,
  testDurationMs,
}) => {
  const [host, setHost] = useState("127.0.0.1");
  const [port, setPort] = useState(8970);
  const [scanBack, setScanBack] = useState(10);
  const [connecting, setConnecting] = useState(false);
  const [connected, setConnected] = useState(false);
  const [baseUrl, setBaseUrl] = useState<string | null>(null);

  const [voices, setVoices] = useState<TtsVoice[]>([]);
  const [loadingVoices, setLoadingVoices] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [deleteDialog, setDeleteDialog] = useState<{
    open: boolean;
    voice: TtsVoice | null;
  }>({ open: false, voice: null });

  const [previewText, setPreviewText] = useState(
    "您好，这是一段 OmniVoice 测试配音。"
  );
  const [previewLoading, setPreviewLoading] = useState(false);
  const audioRef = React.useRef<HTMLAudioElement | null>(null);

  const syncStatus = useCallback(async () => {
    try {
      const res = await ttsService.getOmniVoiceTtsStatus();
      const ok = Boolean(res?.data?.connected);
      setConnected(ok);
      setBaseUrl(res?.data?.base_url || null);
      onConnectionChange?.(ok);
      return ok;
    } catch {
      setConnected(false);
      onConnectionChange?.(false);
      return false;
    }
  }, [onConnectionChange]);

  const loadVoicesLocal = useCallback(async () => {
    setLoadingVoices(true);
    try {
      const res = await ttsService.getVoices("omnivoice_tts");
      if (res?.success) {
        setVoices(res.data || []);
      } else {
        setVoices([]);
      }
    } catch (e) {
      console.error(e);
      setVoices([]);
    } finally {
      setLoadingVoices(false);
    }
  }, []);

  useEffect(() => {
    void (async () => {
      await syncStatus();
    })();
  }, [syncStatus]);

  useEffect(() => {
    if (connected) {
      void loadVoicesLocal();
    } else {
      setVoices([]);
    }
  }, [connected, loadVoicesLocal]);

  const stopAudio = () => {
    const a = audioRef.current;
    if (a) {
      a.pause();
      audioRef.current = null;
    }
  };

  useEffect(() => () => stopAudio(), []);

  const handleConnect = async () => {
    const h = host.trim();
    if (!h) {
      message.error("请填写主机 IP 或域名");
      return;
    }
    setConnecting(true);
    try {
      const res = await ttsService.connectOmniVoiceTts({
        host: h,
        port,
        api_prefix: "/api",
        scan_back: scanBack,
      });
      if (res?.success) {
        message.success(res.message || "已连接 OmniVoice");
        await syncStatus();
        await loadVoicesLocal();
        await onVoicesRefresh?.();
      } else {
        message.error(res?.message || "连接失败");
        await syncStatus();
      }
    } catch (e: any) {
      message.error(e?.message || "连接失败");
      await syncStatus();
    } finally {
      setConnecting(false);
    }
  };

  const handleDisconnect = async () => {
    try {
      await ttsService.disconnectOmniVoiceTts();
      message.success("已断开");
      stopAudio();
      await syncStatus();
      setVoices([]);
    } catch (e: any) {
      message.error(e?.message || "断开失败");
    }
  };

  const handleUpload: React.ChangeEventHandler<HTMLInputElement> = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    if (!connected) {
      message.warning("请先连接 OmniVoice 服务");
      return;
    }
    setUploading(true);
    try {
      const res = await ttsService.uploadOmniVoiceTtsCloneVoice(file);
      if (res?.success) {
        message.success("上传成功");
        await loadVoicesLocal();
        await onVoicesRefresh?.();
      } else {
        message.error("上传失败");
      }
    } catch (err: any) {
      message.error(err?.message || "上传失败");
    } finally {
      setUploading(false);
    }
  };

  const openDeleteDialog = (v: TtsVoice) => {
    if (!connected) {
      message.warning("请先连接 OmniVoice");
      return;
    }
    setDeleteDialog({ open: true, voice: v });
  };

  const confirmDeleteVoice = async () => {
    const v = deleteDialog.voice;
    if (!v || !connected) return;
    setDeletingId(v.id);
    try {
      const res = await ttsService.deleteOmniVoiceTtsCloneVoice(v.id);
      if (!res?.success) {
        message.error("删除失败");
        return;
      }
      if (v.id === activeVoiceId && configId) {
        const pr = await ttsService.patchConfig(configId, {
          active_voice_id: "",
        });
        if (!pr?.success) {
          message.warning("音色已删除，但清空当前音色配置失败，请手动选择");
        }
        await onConfigRefresh?.();
      }
      message.success("已删除");
      setDeleteDialog({ open: false, voice: null });
      await loadVoicesLocal();
      await onVoicesRefresh?.();
    } catch (err: any) {
      message.error(err?.message || "删除失败");
    } finally {
      setDeletingId(null);
    }
  };

  const handleSelectAndActivate = async (voiceId: string) => {
    if (!connected) {
      message.warning("请先连接 OmniVoice");
      return;
    }
    try {
      await ttsService.selectOmniVoiceTtsCloneVoice(voiceId);
      await onSetActive(voiceId);
      message.success("已设为当前音色");
    } catch (err: any) {
      message.error(err?.message || "选择音色失败");
    }
  };

  const handlePreviewRow = async (voice: TtsVoice) => {
    if (!configId || !connected) {
      message.warning("请先连接并完成配置");
      return;
    }
    setPreviewLoading(true);
    stopAudio();
    try {
      const res = await ttsService.previewVoice(voice.id, {
        config_id: configId,
        provider: "omnivoice_tts",
        text: previewText.trim() || "您好，欢迎使用智能配音。",
      });
      const url =
        res?.data?.audio_url ||
        res?.data?.sample_wav_url ||
        voice.sample_wav_url;
      if (!url) {
        message.error("未返回试听地址");
        return;
      }
      const audio = new Audio(resolveUrl(url));
      audioRef.current = audio;
      await audio.play();
    } catch (err: any) {
      message.error(err?.message || "试听失败");
    } finally {
      setPreviewLoading(false);
    }
  };

  const handleGeneratePreview = async () => {
    if (!activeVoiceId) {
      message.warning("请先在列表中选择一个音色作为当前音色");
      return;
    }
    if (!configId || !connected) {
      message.warning("请先连接 OmniVoice");
      return;
    }
    setPreviewLoading(true);
    stopAudio();
    try {
      const res = await ttsService.previewVoice(activeVoiceId, {
        config_id: configId,
        provider: "omnivoice_tts",
        text: previewText.trim() || "您好，欢迎使用智能配音。",
      });
      const url = res?.data?.audio_url || res?.data?.sample_wav_url;
      if (!url) {
        message.error("未返回音频地址");
        return;
      }
      const audio = new Audio(resolveUrl(url));
      audioRef.current = audio;
      await audio.play();
    } catch (err: any) {
      message.error(err?.message || "生成失败");
    } finally {
      setPreviewLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h4 className="text-md font-semibold text-gray-900 mb-2">
          OmniVoice（局域网）
        </h4>
        <p className="text-sm text-gray-600 mb-4">
          在局域网机器上启动 OmniVoice API（默认端口 8970，路径前缀 /api），在此填写 IP
          并连接后即可管理克隆音色与试听。
        </p>

        <div className="flex flex-wrap items-end gap-3 mb-3">
          <div>
            <label className="block text-xs text-gray-500 mb-1">主机</label>
            <input
              className="px-3 py-2 border border-gray-300 rounded-lg w-44 text-sm"
              value={host}
              onChange={(e) => setHost(e.target.value)}
              placeholder="192.168.x.x"
              disabled={connecting}
            />
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">起始端口</label>
            <input
              type="number"
              className="px-3 py-2 border border-gray-300 rounded-lg w-24 text-sm"
              value={port}
              min={1}
              max={65535}
              onChange={(e) => setPort(Number(e.target.value) || 8970)}
              disabled={connecting}
            />
          </div>
          <button
            type="button"
            onClick={() => void handleConnect()}
            disabled={connecting}
            className="px-4 py-2 rounded-lg bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 disabled:opacity-50 inline-flex items-center gap-2"
          >
            {connecting ? (
              <Loader className="w-4 h-4 animate-spin" />
            ) : (
              <Wifi className="w-4 h-4" />
            )}
            连接
          </button>
          <button
            type="button"
            onClick={() => void handleDisconnect()}
            disabled={!connected}
            className="px-4 py-2 rounded-lg border border-gray-300 text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-50 inline-flex items-center gap-2"
          >
            <WifiOff className="w-4 h-4" />
            断开
          </button>
          <button
            type="button"
            onClick={() => void syncStatus()}
            className="px-3 py-2 rounded-lg border border-gray-200 text-sm text-gray-600 hover:bg-gray-50"
          >
            刷新状态
          </button>
        </div>

        <div className="flex flex-wrap items-center gap-3 text-sm">
          {connecting ? (
            <span className="inline-flex items-center gap-1 text-blue-600">
              <Loader className="w-4 h-4 animate-spin" /> 连接中…
            </span>
          ) : connected ? (
            <span className="inline-flex items-center gap-1 text-green-600">
              <CheckCircle className="w-4 h-4" /> 已连接
              {baseUrl && (
                <span className="text-gray-500 font-mono text-xs">{baseUrl}</span>
              )}
            </span>
          ) : (
            <span className="inline-flex items-center gap-1 text-amber-600">
              <AlertCircle className="w-4 h-4" /> 未连接
            </span>
          )}
        </div>
      </div>

      <div className="border-t border-gray-100 pt-4 space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h5 className="text-sm font-semibold text-gray-900">克隆音色</h5>
          <div className="flex items-center gap-2">
            <label className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg border border-dashed border-gray-300 text-sm text-gray-700 cursor-pointer hover:bg-gray-50">
              <Upload className="w-4 h-4" />
              {uploading ? "上传中…" : "上传音频"}
              <input
                type="file"
                className="hidden"
                accept="audio/wav,audio/x-wav,audio/mpeg,audio/mp3,audio/flac,audio/mp4,audio/aac,.wav,.mp3,.flac,.m4a,.ogg,.aac,.opus"
                disabled={!connected || uploading}
                onChange={handleUpload}
              />
            </label>
            <button
              type="button"
              className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg border border-gray-200 text-sm text-gray-700 hover:bg-gray-50"
              disabled={!connected || loadingVoices}
              onClick={() => void loadVoicesLocal().then(() => onVoicesRefresh?.())}
            >
              <RefreshCw
                className={`w-4 h-4 ${loadingVoices ? "animate-spin" : ""}`}
              />
              刷新列表
            </button>
          </div>
        </div>
        <p className="text-xs text-gray-500">
          支持 wav / mp3 / flac / m4a / ogg / aac / opus；显示名称默认使用上传文件名。
        </p>

        <div className="max-h-56 overflow-y-auto border border-gray-200 rounded-lg divide-y divide-gray-100">
          {!connected && (
            <div className="p-4 text-sm text-gray-500 text-center">
              连接成功后可获取克隆音色列表
            </div>
          )}
          {connected && loadingVoices && voices.length === 0 && (
            <div className="p-4 text-sm text-gray-500 flex items-center justify-center gap-2">
              <Loader className="w-4 h-4 animate-spin" /> 加载中…
            </div>
          )}
          {connected && !loadingVoices && voices.length === 0 && (
            <div className="p-4 text-sm text-gray-500 text-center">
              暂无克隆音色，请上传音频文件
            </div>
          )}
          {voices.map((v) => {
            const active = v.id === activeVoiceId;
            return (
              <div
                key={v.id}
                className={`flex flex-wrap items-center gap-2 px-3 py-2 text-sm ${
                  active ? "bg-blue-50/80" : ""
                }`}
              >
                <span className="font-medium text-gray-900 truncate flex-1 min-w-[120px]">
                  {v.name}
                </span>
                <span className="text-xs text-gray-400 font-mono truncate max-w-[180px]">
                  {v.id}
                </span>
                <button
                  type="button"
                  className={`text-xs px-2 py-1 rounded border ${
                    active
                      ? "border-blue-300 bg-blue-100 text-blue-800"
                      : "border-gray-200 hover:bg-gray-50"
                  }`}
                  disabled={!connected}
                  onClick={() => void handleSelectAndActivate(v.id)}
                >
                  {active ? "使用中" : "使用"}
                </button>
                <button
                  type="button"
                  className="text-xs px-2 py-1 rounded border border-gray-200 hover:bg-gray-50"
                  disabled={!connected || previewLoading}
                  onClick={() => void handlePreviewRow(v)}
                >
                  试听
                </button>
                <button
                  type="button"
                  className="text-xs px-2 py-1 rounded border border-red-200 text-red-600 hover:bg-red-50 disabled:opacity-50"
                  disabled={!connected || deletingId === v.id}
                  title="从 OmniVoice 删除此克隆音色"
                  onClick={() => openDeleteDialog(v)}
                >
                  {deletingId === v.id ? (
                    <Loader className="w-3.5 h-3.5 animate-spin inline" />
                  ) : (
                    <Trash2 className="w-3.5 h-3.5 inline" />
                  )}
                </button>
              </div>
            );
          })}
        </div>
      </div>

      <div className="border-t border-gray-100 pt-4 space-y-2">
        <h5 className="text-sm font-semibold text-gray-900">生成语音并试听</h5>
        <textarea
          className="w-full min-h-[88px] px-3 py-2 border border-gray-300 rounded-lg text-sm"
          value={previewText}
          onChange={(e) => setPreviewText(e.target.value)}
          placeholder="输入要合成的文本…"
        />
        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={() => void handleGeneratePreview()}
            disabled={previewLoading || !connected || !activeVoiceId}
            className="px-4 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 disabled:opacity-50"
          >
            {previewLoading ? "生成中…" : "生成语音并试听"}
          </button>
          {!activeVoiceId && (
            <span className="text-xs text-amber-600">请先「选择使用」一个音色</span>
          )}
        </div>
      </div>

      <div className="border-t border-gray-100 pt-4">
        <h5 className="text-sm font-semibold text-gray-900 mb-2">连通性测试</h5>
        <p className="text-xs text-gray-500 mb-2">
          验证当前 TTS 配置与 OmniVoice 后端是否可用（与引擎测试一致）。
        </p>
        <button
          type="button"
          onClick={() => void onTestConnection()}
          disabled={testing || !connected}
          className="px-4 py-2 rounded-lg border border-gray-300 text-sm hover:bg-gray-50 disabled:opacity-50 inline-flex items-center gap-2"
        >
          {testing && <Loader className="w-4 h-4 animate-spin" />}
          测试连通性
        </button>
        {typeof testDurationMs === "number" && (
          <span className="ml-2 text-xs text-gray-500">
            响应 {testDurationMs} ms
          </span>
        )}
        {testResult && (
          <p
            className={`mt-2 text-sm ${
              testResult.success ? "text-green-700" : "text-red-600"
            }`}
          >
            {testResult.message}
          </p>
        )}
      </div>

      {deleteDialog.open && deleteDialog.voice
        ? createPortal(
            <div className="fixed inset-0 z-50 overflow-y-auto">
              <div
                className="fixed inset-0 bg-black bg-opacity-50 transition-opacity"
                onClick={
                  deletingId
                    ? undefined
                    : () => setDeleteDialog({ open: false, voice: null })
                }
              />
              <div className="flex items-center justify-center min-h-screen p-4">
                <div className="relative bg-white rounded-lg shadow-xl max-w-md w-full">
                  <div className="flex items-center justify-between p-5 border-b border-gray-200">
                    <h3 className="text-lg font-semibold text-gray-900">
                      确认删除
                    </h3>
                    <button
                      type="button"
                      onClick={() =>
                        setDeleteDialog({ open: false, voice: null })
                      }
                      disabled={!!deletingId}
                      className="text-gray-400 hover:text-gray-600 transition-colors disabled:opacity-50"
                    >
                      <X className="h-5 w-5" />
                    </button>
                  </div>
                  <div className="p-5 space-y-3">
                    <p className="text-sm text-gray-700">
                      确定从 OmniVoice 删除音色{" "}
                      <span className="font-semibold">
                        「{deleteDialog.voice.name}」
                      </span>
                      吗？此操作不可恢复。
                    </p>
                    <div className="text-xs text-gray-500 break-words p-2 bg-gray-50 rounded font-mono">
                      ID: {deleteDialog.voice.id}
                    </div>
                  </div>
                  <div className="bg-gray-50 px-5 py-4 flex items-center justify-end gap-3 border-t border-gray-200">
                    <button
                      type="button"
                      onClick={() =>
                        setDeleteDialog({ open: false, voice: null })
                      }
                      disabled={!!deletingId}
                      className="px-4 py-2 text-gray-700 bg-white border border-gray-300 hover:bg-gray-50 rounded-lg font-medium transition-colors disabled:opacity-50"
                    >
                      取消
                    </button>
                    <button
                      type="button"
                      onClick={() => void confirmDeleteVoice()}
                      disabled={!!deletingId}
                      className="px-5 py-2 bg-red-600 text-white rounded-lg font-medium hover:bg-red-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      <span className="inline-flex items-center gap-2">
                        {deletingId === deleteDialog.voice.id ? (
                          <Loader className="h-4 w-4 animate-spin" />
                        ) : null}
                        删除
                      </span>
                    </button>
                  </div>
                </div>
              </div>
            </div>,
            document.body
          )
        : null}
    </div>
  );
};

export default OmniVoiceTtsSection;

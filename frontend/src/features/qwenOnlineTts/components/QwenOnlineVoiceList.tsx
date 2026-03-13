import { useState } from "react";
import { createPortal } from "react-dom";
import { message } from "@/services/message";
import { ttsService } from "@/services/ttsService";
import { apiClient } from "@/services/clients";
import {
  Check,
  Loader,
  Pencil,
  Play,
  Pause,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import type { QwenOnlineTtsVoice } from "../types";
import React from "react";

const resolveUrl = (url: string): string => {
  if (!url) return url;
  const isAbsolute = /^https?:\/\//i.test(url);
  if (isAbsolute) return url;
  if (url.startsWith("/")) {
    return `${apiClient.getBaseUrl()}${url}`;
  }
  return url;
};

const statusBadge = (status: string) => {
  const s = String(status || "").toLowerCase();
  if (s === "ready") return "bg-green-50 text-green-700 border-green-200";
  if (s === "cloning") return "bg-blue-50 text-blue-700 border-blue-200";
  if (s === "failed") return "bg-red-50 text-red-700 border-red-200";
  return "bg-gray-100 text-gray-600 border-gray-200";
};

const statusText = (status: string) => {
  const s = String(status || "").toLowerCase();
  if (s === "ready") return "就绪";
  if (s === "cloning") return "处理中";
  if (s === "failed") return "失败";
  return status || "未知";
};

export type QwenOnlineVoiceListProps = {
  voices: QwenOnlineTtsVoice[];
  activeVoiceId: string;
  configId: string | null;
  provider: string;
  onSetActive: (voiceId: string) => Promise<void> | void;
  onEdit: (voice: QwenOnlineTtsVoice) => void;
  onDelete: (voiceId: string, removeFiles: boolean) => Promise<void> | void;
  onUpload: () => void;
};

const QwenOnlineVoiceList: React.FC<QwenOnlineVoiceListProps> = ({
  voices,
  activeVoiceId,
  configId,
  provider,
  onSetActive,
  onEdit,
  onDelete,
  onUpload,
}) => {
  const audioRef = React.useRef<HTMLAudioElement | null>(null);
  const previewTokenRef = React.useRef(0);
  const [playingVoiceId, setPlayingVoiceId] = React.useState<string | null>(
    null
  );
  const [previewLoadingVoiceId, setPreviewLoadingVoiceId] = React.useState<
    string | null
  >(null);

  const [deleteDialog, setDeleteDialog] = useState<{
    open: boolean;
    voice: QwenOnlineTtsVoice | null;
  }>({
    open: false,
    voice: null,
  });
  const [removeFiles, setRemoveFiles] = useState<boolean>(false);
  const [deleteBusy, setDeleteBusy] = useState<boolean>(false);

  const stopCurrent = () => {
    const a = audioRef.current;
    if (a) {
      a.pause();
      a.currentTime = 0;
      audioRef.current = null;
      setPlayingVoiceId(null);
    }
  };

  const playUrl = (url: string, voiceId: string) => {
    stopCurrent();
    const audio = new Audio(resolveUrl(url));
    audioRef.current = audio;
    setPlayingVoiceId(voiceId);
    audio.onended = () => {
      audioRef.current = null;
      setPlayingVoiceId(null);
    };
    audio.play();
  };

  const handlePreview = async (voice: QwenOnlineTtsVoice) => {
    if (playingVoiceId === voice.id) {
      stopCurrent();
      return;
    }
    if (previewLoadingVoiceId === voice.id) {
      previewTokenRef.current += 1;
      setPreviewLoadingVoiceId(null);
      return;
    }
    const busyVoiceId = previewLoadingVoiceId || playingVoiceId;
    if (busyVoiceId && busyVoiceId !== voice.id) return;
    if (!configId) {
      message.error("缺少 config_id，无法试听");
      return;
    }
    const token = (previewTokenRef.current += 1);
    try {
      setPreviewLoadingVoiceId(voice.id);
      const res = await ttsService.previewVoice(voice.id, {
        provider,
        config_id: configId,
        text: "",
      });
      if (previewTokenRef.current !== token) return;
      const url = res?.data?.audio_url || res?.data?.sample_wav_url;
      if (!url) {
        message.error("试听失败：未返回音频链接");
        return;
      }
      playUrl(url, voice.id);
    } catch (e: any) {
      if (previewTokenRef.current === token) {
        message.error(e?.message || "试听失败");
      }
    } finally {
      if (previewTokenRef.current === token) {
        setPreviewLoadingVoiceId((prev) => (prev === voice.id ? null : prev));
      }
    }
  };

  React.useEffect(() => {
    return () => stopCurrent();
  }, []);

  const sorted = [...voices].sort((a, b) =>
    (b.updated_at || "").localeCompare(a.updated_at || "")
  );

  const openDelete = (v: QwenOnlineTtsVoice) => {
    setDeleteDialog({ open: true, voice: v });
    setRemoveFiles(false);
  };

  const confirmDelete = async () => {
    if (!deleteDialog.voice) return;
    setDeleteBusy(true);
    try {
      await onDelete(deleteDialog.voice.id, removeFiles);
      setDeleteDialog({ open: false, voice: null });
      message.success("已删除");
    } catch (e: any) {
      message.error(e?.message || "删除失败");
    } finally {
      setDeleteBusy(false);
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-sm text-gray-500">
          共 {voices.length} 个复刻音色
        </span>
        <button
          onClick={onUpload}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors"
        >
          <Upload className="h-4 w-4" />
          上传参考音频
        </button>
      </div>

      {sorted.map((v) => {
        const isActive = v.id === activeVoiceId;
        const isPlaying = playingVoiceId === v.id;
        const isLoading = previewLoadingVoiceId === v.id;
        const canSelect = String(v.status || "").toLowerCase() === "ready";
        const isCloning = String(v.status || "").toLowerCase() === "cloning";

        return (
          <div
            key={v.id}
            className={`border rounded-lg bg-white ${
              isActive ? "border-blue-200 bg-blue-50/30" : "border-gray-200"
            }`}
          >
            <div className="px-4 py-3 flex items-start gap-3">
              <button
                onClick={() => handlePreview(v)}
                className={`
                  flex-shrink-0 w-9 h-9 flex items-center justify-center rounded-full transition-all
                  ${
                    isPlaying
                      ? "bg-blue-100 text-blue-600"
                      : "bg-gray-100 text-gray-600 hover:bg-blue-600 hover:text-white"
                  }
                `}
                disabled={isCloning}
                title="试听"
              >
                {isLoading ? (
                  <Loader className="w-4 h-4 animate-spin" />
                ) : isPlaying ? (
                  <Pause className="w-4 h-4 fill-current" />
                ) : (
                  <Play className="w-4 h-4 ml-0.5 fill-current" />
                )}
              </button>

              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 flex-wrap mb-1">
                  <div
                    className="text-sm font-medium text-gray-900 truncate max-w-[200px]"
                    title={v.id}
                  >
                    {v.name}
                  </div>
                  <span
                    className={`text-[10px] px-1.5 py-0.5 rounded border ${statusBadge(
                      v.status
                    )}`}
                  >
                    {statusText(v.status)}
                  </span>
                </div>

                <div className="flex items-center gap-3 text-[11px] text-gray-500">
                  <span title="模型">{v.model}</span>
                  {v.ref_text && (
                    <>
                      <span className="w-px h-3 bg-gray-200" />
                      <span title="参考文本" className="truncate max-w-[150px]">
                        {v.ref_text}
                      </span>
                    </>
                  )}
                </div>

                {isCloning && v.progress > 0 && v.progress < 100 ? (
                  <div className="mt-2">
                    <div className="flex items-center gap-2">
                      <div className="flex-1 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                        <div
                          className="h-full bg-blue-500 rounded-full transition-all"
                          style={{ width: `${v.progress}%` }}
                        />
                      </div>
                      <span className="text-xs text-gray-500">
                        {v.progress}%
                      </span>
                    </div>
                  </div>
                ) : null}

                {String(v.status || "").toLowerCase() === "failed" &&
                v.last_error ? (
                  <div className="mt-2 text-xs text-red-600 whitespace-pre-wrap break-words bg-red-50 p-2 rounded border border-red-100">
                    {v.last_error}
                  </div>
                ) : null}
              </div>

              <div className="flex items-center gap-2 flex-shrink-0 self-center">
                {isActive ? (
                  <div className="flex items-center gap-1.5 text-blue-600 bg-blue-100/50 px-2.5 py-1 rounded-full border border-blue-200/50">
                    <Check className="w-3.5 h-3.5" />
                    <span className="text-xs font-medium">使用中</span>
                  </div>
                ) : (
                  <button
                    onClick={() => onSetActive(v.id)}
                    disabled={!canSelect}
                    className={`
                      text-xs px-3 py-1.5 rounded-md border transition-all font-medium
                      ${
                        canSelect
                          ? "bg-white border-gray-200 text-gray-700 hover:border-blue-300 hover:text-blue-600 hover:bg-blue-50"
                          : "bg-gray-50 border-gray-100 text-gray-400 cursor-not-allowed"
                      }
                    `}
                    title={canSelect ? "设为当前音色" : "音色未就绪"}
                  >
                    选择
                  </button>
                )}

                <button
                  onClick={() => onEdit(v)}
                  disabled={isCloning}
                  className={`text-xs px-2 py-1.5 rounded-md border font-medium ${
                    isCloning
                      ? "bg-gray-50 border-gray-100 text-gray-400 cursor-not-allowed"
                      : "bg-white border-gray-200 text-gray-700 hover:bg-gray-50"
                  }`}
                  title="编辑"
                >
                  <Pencil className="h-3.5 w-3.5" />
                </button>

                <button
                  onClick={() => openDelete(v)}
                  disabled={isCloning}
                  className={`text-xs px-2 py-1.5 rounded-md border font-medium ${
                    isCloning
                      ? "bg-gray-50 border-gray-100 text-gray-400 cursor-not-allowed"
                      : "bg-white border-gray-200 text-red-600 hover:bg-red-50 hover:border-red-200"
                  }`}
                  title="删除"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
            </div>
          </div>
        );
      })}

      {sorted.length === 0 ? (
        <div className="text-center py-8 border-2 border-dashed border-gray-200 rounded-lg">
          <p className="text-sm text-gray-500 mb-3">暂无复刻音色</p>
          <button
            onClick={onUpload}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors"
          >
            <Upload className="h-4 w-4" />
            上传参考音频
          </button>
        </div>
      ) : null}

      {deleteDialog.open && deleteDialog.voice
        ? createPortal(
            <div className="fixed inset-0 z-50 overflow-y-auto">
              <div
                className="fixed inset-0 bg-black bg-opacity-50 transition-opacity"
                onClick={
                  deleteBusy
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
                      onClick={() =>
                        setDeleteDialog({ open: false, voice: null })
                      }
                      disabled={deleteBusy}
                      className="text-gray-400 hover:text-gray-600 transition-colors disabled:opacity-50"
                    >
                      <X className="h-5 w-5" />
                    </button>
                  </div>
                  <div className="p-5 space-y-3">
                    <div className="text-sm text-gray-700">
                      确定要删除音色{" "}
                      <span className="font-semibold">
                        "{deleteDialog.voice.name}"
                      </span>{" "}
                      吗？
                    </div>

                    <label className="flex items-center gap-2 text-sm text-gray-700">
                      <input
                        type="checkbox"
                        checked={removeFiles}
                        disabled={deleteBusy}
                        onChange={(e) => setRemoveFiles(e.target.checked)}
                      />
                      同时删除关联文件
                    </label>

                    <div className="text-xs text-gray-500 break-words mt-2 p-2 bg-gray-50 rounded">
                      ID: {deleteDialog.voice.id}
                    </div>
                  </div>
                  <div className="bg-gray-50 px-5 py-4 flex items-center justify-end gap-3 border-t border-gray-200">
                    <button
                      type="button"
                      onClick={() =>
                        setDeleteDialog({ open: false, voice: null })
                      }
                      disabled={deleteBusy}
                      className="px-4 py-2 text-gray-700 bg-white border border-gray-300 hover:bg-gray-50 rounded-lg font-medium transition-colors disabled:opacity-50"
                    >
                      取消
                    </button>
                    <button
                      type="button"
                      onClick={confirmDelete}
                      disabled={deleteBusy}
                      className="px-5 py-2 bg-red-600 text-white rounded-lg font-medium hover:bg-red-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      <span className="inline-flex items-center gap-2">
                        {deleteBusy ? (
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

export default QwenOnlineVoiceList;

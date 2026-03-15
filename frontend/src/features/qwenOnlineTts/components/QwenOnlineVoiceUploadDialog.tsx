import { useState, useRef, useEffect } from "react";
import { createPortal } from "react-dom";
import { Loader, Upload, X, ChevronDown, Check } from "lucide-react";
import { message } from "@/services/message";
import type {
  QwenOnlineTtsVoice,
  QwenOnlineTtsUploadVoiceInput,
} from "../types";
import { QWEN_ONLINE_TTS_MODELS } from "../constants";

export type QwenOnlineVoiceUploadDialogProps = {
  isOpen: boolean;
  voice?: QwenOnlineTtsVoice;
  onClose: () => void;
  onSubmit: (result: QwenOnlineVoiceUploadDialogResult) => Promise<void>;
};

export type QwenOnlineVoiceUploadDialogResult =
  | QwenOnlineVoiceUploadDialogEditResult
  | QwenOnlineVoiceUploadDialogNewResult;

export type QwenOnlineVoiceUploadDialogNewResult = {
  edit?: false;
  input: QwenOnlineTtsUploadVoiceInput;
};

export type QwenOnlineVoiceUploadDialogEditResult = {
  edit: true;
  voiceId: string;
  patch: Partial<QwenOnlineTtsVoice>;
};

const ACCEPTED_TYPES = [
  "audio/mpeg",
  "audio/mp3",
  "audio/wav",
  "audio/x-wav",
  "audio/m4a",
  "audio/x-m4a",
  "audio/flac",
  "audio/ogg",
  "audio/aac",
];

const DEFAULT_MODEL = "qwen3-tts-vc-2026-01-22";
const MODEL_VALUE_SET: ReadonlySet<string> = new Set(
  QWEN_ONLINE_TTS_MODELS.map((m) => m.value)
);

const QwenOnlineVoiceUploadDialog: React.FC<
  QwenOnlineVoiceUploadDialogProps
> = ({ isOpen, voice, onClose, onSubmit }) => {
  const [file, setFile] = useState<File | null>(null);
  const [name, setName] = useState<string>("");
  const [model, setModel] = useState<string>(DEFAULT_MODEL);
  const [refText, setRefText] = useState<string>("");
  const [submitting, setSubmitting] = useState<boolean>(false);
  const [dragOver, setDragOver] = useState<boolean>(false);
  const [modelDropdownOpen, setModelDropdownOpen] = useState<boolean>(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const modelDropdownRef = useRef<HTMLDivElement>(null);

  const isEdit = !!voice;
  const canSubmit = isEdit || (!!file && !submitting);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        modelDropdownRef.current &&
        !modelDropdownRef.current.contains(event.target as Node)
      ) {
        setModelDropdownOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  useEffect(() => {
    if (!isOpen) return;
    setFile(null);
    setName(voice?.name ?? "");
    setModel(voice?.model ?? DEFAULT_MODEL);
    setRefText(voice?.ref_text ?? "");
  }, [isOpen, voice]);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (f) {
      if (!ACCEPTED_TYPES.includes(f.type)) {
        message.warning(
          "不支持的文件类型，请选择音频文件（mp3/wav/m4a/flac/ogg/aac）"
        );
        return;
      }
      setFile(f);
      if (!name) {
        const baseName = f.name.replace(/\.[^/.]+$/, "");
        setName(baseName.slice(0, 50));
      }
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const f = e.dataTransfer.files?.[0];
    if (f) {
      if (!ACCEPTED_TYPES.includes(f.type)) {
        message.warning(
          "不支持的文件类型，请选择音频文件（mp3/wav/m4a/flac/ogg/aac）"
        );
        return;
      }
      setFile(f);
      if (!name) {
        const baseName = f.name.replace(/\.[^/.]+$/, "");
        setName(baseName.slice(0, 50));
      }
    }
  };

  const handleSubmit = async () => {
    if (!canSubmit) return;
    const resolvedModel = (model || DEFAULT_MODEL).trim();
    if (!MODEL_VALUE_SET.has(resolvedModel)) {
      message.warning(
        `模型仅支持：${QWEN_ONLINE_TTS_MODELS.map((m) => m.value).join(" / ")}`
      );
      return;
    }

    setSubmitting(true);
    try {
      if (isEdit && voice) {
        const nextName = name.trim();
        const nextRefText = refText.trim();
        const patch: Partial<QwenOnlineTtsVoice> = {};
        if (nextName && nextName !== voice.name) patch.name = nextName;
        if (nextRefText && nextRefText !== (voice.ref_text ?? "")) {
          patch.ref_text = nextRefText;
        }
        if (resolvedModel !== voice.model) patch.model = resolvedModel;
        if (Object.keys(patch).length === 0) {
          handleClose();
          return;
        }

        await onSubmit({
          edit: true,
          voiceId: voice.id,
          patch: {
            ...patch,
          },
        });
      } else if (file) {
        await onSubmit({
          edit: false,
          input: {
            file,
            name: name.trim() || undefined,
            model: resolvedModel || undefined,
            ref_text: refText.trim() || undefined,
          },
        });
      }
    } catch (e: any) {
      message.error(e?.message || "操作失败");
    } finally {
      setSubmitting(false);
    }
  };

  const handleClose = () => {
    if (!submitting) {
      setFile(null);
      setName("");
      setModel(DEFAULT_MODEL);
      setRefText("");
      onClose();
    }
  };

  if (!isOpen) return null;

  return createPortal(
    <div className="fixed inset-0 z-50 overflow-y-auto">
      <div
        className="fixed inset-0 bg-black bg-opacity-50 transition-opacity"
        onClick={submitting ? undefined : handleClose}
      />
      <div className="flex items-center justify-center min-h-screen p-4">
        <div className="relative bg-white rounded-lg shadow-xl max-w-lg w-full">
          <div className="flex items-center justify-between p-5 border-b border-gray-200">
            <h3 className="text-lg font-semibold text-gray-900">
              {isEdit ? "编辑复刻音色" : "上传参考音频"}
            </h3>
            <button
              onClick={handleClose}
              disabled={submitting}
              className="text-gray-400 hover:text-gray-600 transition-colors disabled:opacity-50"
            >
              <X className="h-5 w-5" />
            </button>
          </div>

          <div className="p-5 space-y-4">
            {!isEdit && (
              <div
                onClick={() => fileInputRef.current?.click()}
                onDragOver={(e) => {
                  e.preventDefault();
                  setDragOver(true);
                }}
                onDragLeave={() => setDragOver(false)}
                onDrop={handleDrop}
                className={`
                  border-2 border-dashed rounded-lg p-8 text-center transition-colors cursor-pointer
                  ${
                    dragOver
                      ? "border-blue-400 bg-blue-50"
                      : "border-gray-300 hover:border-gray-400"
                  }
                  ${file ? "border-green-400 bg-green-50" : ""}
                `}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept={ACCEPTED_TYPES.join(",")}
                  onChange={handleFileChange}
                  className="hidden"
                />
                {file ? (
                  <div className="space-y-2">
                    <div className="text-sm font-medium text-gray-900">
                      {file.name}
                    </div>
                    <div className="text-xs text-gray-500">
                      {(file.size / 1024 / 1024).toFixed(2)} MB
                    </div>
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        setFile(null);
                        // Reset input value so same file can be selected again if needed
                        if (fileInputRef.current) {
                          fileInputRef.current.value = "";
                        }
                      }}
                      className="text-xs text-red-600 hover:underline"
                    >
                      移除
                    </button>
                  </div>
                ) : (
                  <div className="space-y-2">
                    <Upload className="h-8 w-8 mx-auto text-gray-400" />
                    <div className="text-sm text-gray-600">
                      拖拽音频文件到此处，或{" "}
                      <span className="text-blue-600 hover:underline cursor-pointer">
                        点击选择
                      </span>
                    </div>
                    <div className="text-xs text-gray-500">
                      支持 mp3/wav/m4a/flac/ogg/aac
                    </div>
                  </div>
                )}
              </div>
            )}

            <div>
              <label className="block text-sm text-gray-700 mb-1">
                名称（可选）
              </label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="音色名称"
                maxLength={50}
                className="px-3 py-2 border border-gray-300 rounded-md w-full"
              />
            </div>

            <div ref={modelDropdownRef} className="relative">
              <label className="block text-sm text-gray-700 mb-1">模型</label>
              <div className="relative">
                <input
                  type="text"
                  value={model}
                  onChange={(e) => setModel(e.target.value)}
                  onFocus={() => setModelDropdownOpen(true)}
                  placeholder="输入或选择模型"
                  className="px-3 py-2 pr-8 border border-gray-300 rounded-md w-full focus:outline-none focus:ring-2 focus:ring-blue-100 focus:border-blue-500 transition-colors"
                />
                <button
                  type="button"
                  onClick={() => setModelDropdownOpen(!modelDropdownOpen)}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 p-1 rounded-full hover:bg-gray-100 transition-colors"
                >
                  <ChevronDown
                    className={`h-4 w-4 transition-transform duration-200 ${
                      modelDropdownOpen ? "rotate-180" : ""
                    }`}
                  />
                </button>
              </div>

              {modelDropdownOpen && (
                <ul className="absolute z-10 w-full mt-1 bg-white border border-gray-200 rounded-md shadow-lg max-h-60 overflow-auto py-1">
                  {QWEN_ONLINE_TTS_MODELS.map((m) => {
                    const isSelected = model === m.value;
                    return (
                      <li
                        key={m.value}
                        onClick={() => {
                          setModel(m.value);
                          setModelDropdownOpen(false);
                        }}
                        className={`
                          px-3 py-2 text-sm cursor-pointer flex items-center justify-between transition-colors
                          ${
                            isSelected
                              ? "bg-blue-50 text-blue-600 font-medium"
                              : "text-gray-700 hover:bg-gray-50"
                          }
                        `}
                      >
                        <span>{m.label}</span>
                        {isSelected && <Check className="h-4 w-4" />}
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>

            <div>
              <label className="block text-sm text-gray-700 mb-1">
                参考文本（可选）
              </label>
              <textarea
                value={refText}
                onChange={(e) => setRefText(e.target.value)}
                placeholder="可选，提供参考文本有助于提升克隆效果"
                rows={3}
                className="px-3 py-2 border border-gray-300 rounded-md w-full"
              />
            </div>
          </div>

          <div className="bg-gray-50 px-5 py-4 flex items-center justify-end gap-3 border-t border-gray-200">
            <button
              type="button"
              onClick={handleClose}
              disabled={submitting}
              className="px-4 py-2 text-gray-700 bg-white border border-gray-300 hover:bg-gray-50 rounded-lg font-medium transition-colors disabled:opacity-50"
            >
              取消
            </button>
            <button
              type="button"
              onClick={handleSubmit}
              disabled={!canSubmit}
              className="px-5 py-2 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed inline-flex items-center gap-2"
            >
              {submitting ? <Loader className="h-4 w-4 animate-spin" /> : null}
              {isEdit ? "保存" : "上传并创建"}
            </button>
          </div>
        </div>
      </div>
    </div>,
    document.body
  );
};

export default QwenOnlineVoiceUploadDialog;

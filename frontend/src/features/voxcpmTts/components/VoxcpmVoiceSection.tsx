import React, { useCallback, useMemo, useState } from "react";
import { Plus, RefreshCw, ShieldAlert } from "lucide-react";
import { message } from "@/services/message";
import { useVoxcpmVoices } from "../hooks/useVoxcpmVoices";
import { useVoxcpmModels } from "../hooks/useVoxcpmModels";
import VoxcpmVoiceList from "./VoxcpmVoiceList";
import VoxcpmVoiceUploadDialog, { type VoxcpmVoiceUploadDialogResult, type VoxcpmVoiceUploadDialogEditResult } from "./VoxcpmVoiceUploadDialog";
import VoxcpmModelOptionsList from "./VoxcpmModelOptionsList";
import type { VoxcpmTtsDownloadProvider, VoxcpmTtsVoice } from "../types";

export type VoxcpmVoiceSectionProps = {
  configId: string | null;
  activeVoiceId: string;
  onSetActive: (voiceId: string) => Promise<void> | void;
};

export const VoxcpmVoiceSection: React.FC<VoxcpmVoiceSectionProps> = ({ configId, activeVoiceId, onSetActive }) => {
  const {
    voices,
    loading,
    cloneEventByVoiceId,
    refresh: refreshVoices,
    upload,
    patch,
    remove,
    startClone,
  } = useVoxcpmVoices();
  const {
    models: localModels,
    modelByKey,
    loading: modelsLoading,
    error: modelsError,
    downloadsByKey,
    refresh: refreshModels,
    validate: validateModel,
    openModelDirInExplorer,
    downloadModel,
    stopDownload,
  } = useVoxcpmModels();

  const [uploadOpen, setUploadOpen] = useState<boolean>(false);
  const [editVoice, setEditVoice] = useState<VoxcpmTtsVoice | null>(null);
  
  const [providerByOptionId, setProviderByOptionId] = useState<Record<string, VoxcpmTtsDownloadProvider>>({});
  const [copiedOptionId, setCopiedOptionId] = useState<string | null>(null);

  const closeAllDialogs = () => {
    setUploadOpen(false);
    setEditVoice(null);
  };

  const isUploadDialogOpen = uploadOpen || !!editVoice;

  const modelKeys = useMemo(() => {
    const keys = localModels
      .filter((m) => m.key.startsWith("voxcpm"))
      .map((m) => m.key);
    if (!keys.includes("voxcpm_0_5b")) keys.unshift("voxcpm_0_5b");
    if (!keys.includes("voxcpm_1_5b")) keys.unshift("voxcpm_1_5b");
    return Array.from(new Set(keys));
  }, [localModels]);

  const downloadOptions = useMemo(() => {
    return [
      { 
        id: "voxcpm_1_5b", 
        label: "VoxCPM1.5", 
        keys: ["voxcpm_1_5b"],
        size: "约 1.95GB",
        description: "效果更好，建议显存 8G+ 使用"
      },
      { 
        id: "voxcpm_0_5b", 
        label: "VoxCPM-0.5B", 
        keys: ["voxcpm_0_5b"],
        size: "约 1.6GB",
        description: "速度快，适合显存 4G+ 使用"
      },
    ];
  }, []);

  const getProvider = (optionId: string): VoxcpmTtsDownloadProvider => providerByOptionId[optionId] || "modelscope";

  const getModelStatus = (keys: string[]) => {
    const items = keys.map((k) => modelByKey.get(k)).filter(Boolean);
    const existsAll = keys.length > 0 && keys.every((k) => Boolean(modelByKey.get(k)?.exists));
    const validAll = keys.length > 0 && keys.every((k) => Boolean(modelByKey.get(k)?.valid));
    const missing = items.flatMap((m) => (Array.isArray(m?.missing) ? m!.missing : []));
    return { existsAll, validAll, missing: Array.from(new Set(missing)) };
  };

  const getBadgeInfo = (status: { existsAll: boolean; validAll: boolean; missing: string[] }) => {
     if (!status.existsAll) return { className: "bg-gray-100 text-gray-600 border-gray-200", text: "未发现" };
     if (status.validAll) return { className: "bg-green-50 text-green-700 border-green-200", text: "可用" };
     return { className: "bg-orange-50 text-orange-700 border-orange-200", text: "缺文件" };
  };

  const isModelAvailable = useCallback((key: string) => {
    const m = modelByKey.get(key);
    return Boolean(m?.exists && m?.valid);
  }, [modelByKey]);

  const canCreate = useMemo(() => {
    const isAnyModelUsable = (keys: string[]) => keys.some((k) => isModelAvailable(k));
    return isAnyModelUsable(modelKeys);
  }, [modelKeys, isModelAvailable]);

  const handleDownload = async (option: { id: string; keys: string[] }) => {
    const provider = getProvider(option.id);
    await Promise.all(option.keys.map((key) => downloadModel(key, provider)));
  };

  const handleStop = async (option: { id: string; keys: string[] }) => {
    const targets = option.keys.filter((key) => downloadsByKey[key]?.status === "running");
    await Promise.all(targets.map((key) => stopDownload(key)));
  };

  const handleValidate = async (option: { id: string; keys: string[] }) => {
    for (const key of option.keys) {
      await validateModel(key);
    }
  };

  const handleOpenModelDir = async (option: { id: string; keys: string[] }) => {
    try {
      const key = option.keys[0];
      if (!key) {
        message.error("未找到模型key");
        return;
      }
      await openModelDirInExplorer(key);
      setCopiedOptionId(option.id);
      setTimeout(() => setCopiedOptionId((prev) => (prev === option.id ? null : prev)), 1200);
      message.success("已打开模型目录");
    } catch (e: any) {
      message.error(e?.message || "打开失败");
    }
  };

  const handleUploadSubmit = async (result: VoxcpmVoiceUploadDialogResult | VoxcpmVoiceUploadDialogEditResult) => {
    if ('edit' in result && result.edit) {
        await patch(result.voiceId, result.patch);
        message.success("已保存");
    } else {
        const r = result as VoxcpmVoiceUploadDialogResult;
        const created = await upload(r.input);
        await onSetActive(created.id);
        message.success("上传成功，已设为当前音色");
        if (r.autoStartClone) {
          try {
            await startClone(created.id);
          } catch (e: any) {
            message.warning(e?.message || "自动开始克隆失败，可在列表手动点击\"克隆\"");
          }
        }
    }
    closeAllDialogs();
  };

  return (
    <>
    <div className="space-y-6">
      <section className="bg-white/80 backdrop-blur border rounded-xl p-5 shadow-sm space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h4 className="text-md font-semibold text-gray-900">VoxCPM-TTS 音色库</h4>
          </div>
        </div>
        <div className="bg-gray-50/50 p-3 rounded-lg border border-gray-100 space-y-3">
          <div className="flex items-start justify-between gap-3">
            <div className="text-xs text-gray-600 leading-5">
              上传一段 3-10s 的参考音频，克隆其音色特征。需要 VoxCPM 模型。
            </div>
            <div className="flex items-center gap-2 flex-shrink-0">
              <button
                onClick={() => refreshVoices()}
                disabled={loading}
                className="p-1.5 rounded-md text-gray-500 hover:bg-white hover:text-gray-700 hover:shadow-sm transition-all"
                title="刷新列表"
              >
                <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
              </button>
              <button
                onClick={() => setUploadOpen(true)}
                disabled={loading || !canCreate}
                className={`px-3 py-1.5 text-sm rounded-md ${loading || !canCreate ? "bg-gray-300 text-gray-500" : "bg-orange-600 text-white hover:bg-orange-700"}`}
              >
                <span className="inline-flex items-center gap-2">
                  <Plus className="h-4 w-4" />
                  上传参考音频
                </span>
              </button>
            </div>
          </div>

          <div className="flex flex-col gap-3">
            <div className="flex items-center justify-between px-1">
                 <div className="flex items-center gap-2">
                    <span className="text-xs text-gray-500 font-medium">模型列表 ({downloadOptions.length})</span>
                    {modelsError && (
                        <span className="text-xs text-red-600 flex items-center gap-1" title={modelsError}>
                            <ShieldAlert className="h-3.5 w-3.5" />
                            模型异常
                        </span>
                    )}
                 </div>
                  <button
                    onClick={() => refreshModels()}
                    disabled={modelsLoading}
                    className={`p-1 text-xs rounded-md transition-all flex items-center gap-1 ${
                      modelsLoading ? "text-gray-400" : "text-gray-500 hover:text-gray-700 hover:bg-gray-100"
                    }`}
                    title="刷新模型状态"
                  >
                      <RefreshCw className={`h-3 w-3 ${modelsLoading ? "animate-spin" : ""}`} />
                      刷新
                  </button>
            </div>

            <VoxcpmModelOptionsList
              options={downloadOptions}
              modelsLoading={modelsLoading}
              downloadsByKey={Object.fromEntries(
                Object.entries(downloadsByKey).map(([key, v]) => [
                  key,
                  v ? { key: v.key, progress: v.progress, message: v.message, status: v.status, totalBytes: v.totalBytes, downloadedBytes: v.downloadedBytes, phase: v.phase, type: v.type } : null,
                ])
              )}
              getModelStatus={getModelStatus}
              getBadgeInfo={getBadgeInfo}
              getProvider={getProvider}
              onChangeProvider={(id, provider) =>
                setProviderByOptionId((prev) => ({ ...prev, [id]: provider }))
              }
              onDownload={handleDownload}
              onStop={handleStop}
              onValidate={handleValidate}
              onOpenDir={handleOpenModelDir}
              copiedOptionId={copiedOptionId}
            />
          </div>
        </div>
        </section>
    </div>
      <section className=" mt-6 bg-white/80 backdrop-blur border rounded-xl p-5 shadow-sm space-y-4">
        <div className="flex items-center justify-between border-b border-gray-100 pb-3">
          <div className="flex items-center gap-2">
            <h4 className="text-md font-semibold text-gray-900">已创建音色列表</h4>
            <span className="bg-gray-100 text-gray-600 text-xs px-2 py-0.5 rounded-full font-medium">
              {voices.length}
            </span>
          </div>
        </div>
        <VoxcpmVoiceList
          voices={voices}
          cloneEventByVoiceId={cloneEventByVoiceId}
          activeVoiceId={activeVoiceId}
          configId={configId}
          provider="voxcpm_tts"
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
      <VoxcpmVoiceUploadDialog
        isOpen={isUploadDialogOpen}
        voice={editVoice}
        modelKeys={modelKeys}
        isModelAvailable={isModelAvailable}
        onClose={closeAllDialogs}
        onSubmit={handleUploadSubmit}
      />
    </>
  );
};

export default VoxcpmVoiceSection;

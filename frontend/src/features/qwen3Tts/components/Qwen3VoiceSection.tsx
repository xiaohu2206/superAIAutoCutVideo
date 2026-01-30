import React, { useMemo, useState } from "react";
import { Plus, RefreshCw, ShieldAlert, Layers, Mic2, Palette, Sparkles } from "lucide-react";
import { message } from "@/services/message";
import { useQwen3Voices } from "../hooks/useQwen3Voices";
import { useQwen3Models } from "../hooks/useQwen3Models";
import Qwen3VoiceEditDialog from "./Qwen3VoiceEditDialog";
import Qwen3VoiceList from "./Qwen3VoiceList";
import Qwen3VoiceUploadDialog, { type Qwen3VoiceUploadDialogResult } from "./Qwen3VoiceUploadDialog";
import Qwen3CustomRoleDialog, { type Qwen3CustomRoleDialogResult } from "./Qwen3CustomRoleDialog.tsx";
import Qwen3VoiceDesignDialog, { type Qwen3VoiceDesignDialogResult } from "./Qwen3VoiceDesignDialog.tsx";
import Qwen3ModelOptionsList from "./Qwen3ModelOptionsList";
import type { Qwen3TtsDownloadProvider, Qwen3TtsVoice } from "../types";

export type Qwen3VoiceSectionProps = {
  configId: string | null;
  activeVoiceId: string;
  onSetActive: (voiceId: string) => Promise<void> | void;
};

type CreateMode = "clone" | "custom_role" | "voice_design";

export const Qwen3VoiceSection: React.FC<Qwen3VoiceSectionProps> = ({ configId, activeVoiceId, onSetActive }) => {
  const {
    voices,
    loading,
    error,
    cloneEventByVoiceId,
    refresh: refreshVoices,
    upload,
    createCustomRole,
    createDesignClone,
    patch,
    remove,
    startClone,
  } = useQwen3Voices();
  const {
    models: localModels,
    modelByKey,
    loading: modelsLoading,
    error: modelsError,
    downloadsByKey,
    refresh: refreshModels,
    validate: validateModel,
    getModelPath,
    downloadModel,
    stopDownload,
  } = useQwen3Models();

  const [createMode, setCreateMode] = useState<CreateMode>("clone");
  const [uploadOpen, setUploadOpen] = useState<boolean>(false);
  const [customRoleOpen, setCustomRoleOpen] = useState<boolean>(false);
  const [designOpen, setDesignOpen] = useState<boolean>(false);
  const [editVoice, setEditVoice] = useState<Qwen3TtsVoice | null>(null);
  
  const [providerByOptionId, setProviderByOptionId] = useState<Record<string, Qwen3TtsDownloadProvider>>({});
  const [copiedOptionId, setCopiedOptionId] = useState<string | null>(null);

  // Filter model keys for each mode
  const baseModelKeys = useMemo(() => {
    const keys = localModels
      .filter((m) => m.model_type === "base" || (!m.model_type && m.key.includes("base")))
      .map((m) => m.key);
    if (!keys.includes("base_0_6b")) keys.unshift("base_0_6b");
    return Array.from(new Set(keys));
  }, [localModels]);

  const customModelKeys = useMemo(() => {
    const keys = localModels
      .filter((m) => m.model_type === "custom_voice" || (!m.model_type && m.key.includes("custom")))
      .map((m) => m.key);
    if (!keys.includes("custom_0_6b")) keys.unshift("custom_0_6b");
    return Array.from(new Set(keys));
  }, [localModels]);

  const designModelKeys = useMemo(() => {
    const keys = localModels
      .filter((m) => m.model_type === "voice_design" || (!m.model_type && m.key.includes("design")))
      .map((m) => m.key);
    // VoiceDesign usually only has 1.7B or specific models
    if (!keys.includes("voice_design_1_7b") && localModels.some(m => m.key === "voice_design_1_7b")) {
        keys.unshift("voice_design_1_7b");
    }
    return Array.from(new Set(keys));
  }, [localModels]);

  const allModelKeys = useMemo(() => {
      return Array.from(new Set([...baseModelKeys, ...customModelKeys, ...designModelKeys]));
  }, [baseModelKeys, customModelKeys, designModelKeys]);

  const downloadOptions = useMemo(() => {
    if (createMode === "clone") {
      return [
        { id: "base_1_7b_hf", label: "Qwen/Qwen3-TTS-12Hz-1.7B-Base", keys: ["base_1_7b"] },
        { id: "base_0_6b_hf", label: "Qwen/Qwen3-TTS-12Hz-0.6B-Base", keys: ["base_0_6b"] },
      ];
    }
    if (createMode === "custom_role") {
      return [
        { id: "custom_1_7b_hf", label: "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice", keys: ["custom_1_7b"] },
        { id: "custom_0_6b_hf", label: "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice", keys: ["custom_0_6b"] },
      ];
    }
    return [
      { id: "voice_design_1_7b_hf", label: "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign", keys: ["voice_design_1_7b"] },
      { id: "base_1_7b_hf", label: "Qwen/Qwen3-TTS-12Hz-1.7B-Base", keys: ["base_1_7b"] },
      { id: "base_0_6b_hf", label: "Qwen/Qwen3-TTS-12Hz-0.6B-Base", keys: ["base_0_6b"] },
    ];
  }, [createMode]);

  const getProvider = (optionId: string): Qwen3TtsDownloadProvider => providerByOptionId[optionId] || "modelscope";

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

  const canCreateInMode = useMemo(() => {
    const isModelUsable = (key: string) => {
      const m = modelByKey.get(key);
      return Boolean(m?.exists && m?.valid);
    };
    const isAnyModelUsable = (keys: string[]) => keys.some((k) => isModelUsable(k));

    if (createMode === "clone") {
      return isAnyModelUsable(baseModelKeys);
    }
    if (createMode === "custom_role") {
      return isAnyModelUsable(customModelKeys);
    }

    const voiceDesignOk = isModelUsable("voice_design_1_7b");
    const base1_7bOk = isModelUsable("base_1_7b");
    const baseAllOk = isModelUsable("base_1_7b") && isModelUsable("base_0_6b");
    return voiceDesignOk && (base1_7bOk || baseAllOk);
  }, [baseModelKeys, createMode, customModelKeys, modelByKey]);

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

  const handleCopyPath = async (option: { id: string; keys: string[] }) => {
    try {
      if (option.keys.length === 1) {
        const p = await getModelPath(option.keys[0]);
        await navigator.clipboard.writeText(p);
      } else {
        const lines: string[] = [];
        for (const key of option.keys) {
          const p = await getModelPath(key);
          lines.push(`${key}: ${p}`);
        }
        await navigator.clipboard.writeText(lines.join("\n"));
      }
      setCopiedOptionId(option.id);
      setTimeout(() => setCopiedOptionId((prev) => (prev === option.id ? null : prev)), 1200);
      message.success("已复制模型目录路径");
    } catch (e: any) {
      message.error(e?.message || "复制失败");
    }
  };


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

  const handleCustomRoleSubmit = async (result: Qwen3CustomRoleDialogResult) => {
    await createCustomRole(result.input);
    message.success("创建成功");
  };

  const handleDesignSubmit = async (result: Qwen3VoiceDesignDialogResult) => {
    await createDesignClone(result.input);
    message.success("已创建并开始生成");
  };

  const renderCreateButton = () => {
    const disabled = loading || !canCreateInMode;
    if (createMode === "clone") {
        return (
            <button
              onClick={() => setUploadOpen(true)}
              disabled={disabled}
              className={`px-3 py-1.5 text-sm rounded-md ${disabled ? "bg-gray-300 text-gray-500" : "bg-blue-600 text-white hover:bg-blue-700"}`}
            >
              <span className="inline-flex items-center gap-2">
                <Plus className="h-4 w-4" />
                上传参考音频
              </span>
            </button>
        )
    }
    if (createMode === "custom_role") {
        return (
            <button
              onClick={() => setCustomRoleOpen(true)}
              disabled={disabled}
              className={`px-3 py-1.5 text-sm rounded-md ${disabled ? "bg-gray-300 text-gray-500" : "bg-purple-600 text-white hover:bg-purple-700"}`}
            >
              <span className="inline-flex items-center gap-2">
                <Plus className="h-4 w-4" />
                创建角色音色
              </span>
            </button>
        )
    }
    if (createMode === "voice_design") {
        return (
            <button
              onClick={() => setDesignOpen(true)}
              disabled={disabled}
              className={`px-3 py-1.5 text-sm rounded-md ${disabled ? "bg-gray-300 text-gray-500" : "bg-indigo-600 text-white hover:bg-indigo-700"}`}
            >
              <span className="inline-flex items-center gap-2">
                <Sparkles className="h-4 w-4" />
                设计新音色
              </span>
            </button>
        )
    }
    return null;
  }
  console.log("downloadsByKey", downloadsByKey)
  return (
    <>
    <div className="space-y-6">
      <section className="bg-white/80 backdrop-blur border rounded-xl p-5 shadow-sm space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h4 className="text-md font-semibold text-gray-900">Qwen3-TTS 音色库</h4>
            {error ? <div className="text-xs text-red-600 mt-1">{error}</div> : null}
          </div>
          
          <div className="flex bg-gray-100/80 p-1 rounded-lg">
            <button
                onClick={() => setCreateMode("clone")}
                className={`flex-1 px-3 py-1.5 text-xs font-medium rounded-md transition-all flex items-center justify-center gap-1.5 ${
                    createMode === "clone" ? "bg-white text-blue-700 shadow-sm" : "text-gray-600 hover:text-gray-900"
                }`}
            >
                <Layers className="w-3.5 h-3.5" />
                普通克隆
            </button>
            <button
                onClick={() => setCreateMode("custom_role")}
                className={`flex-1 px-3 py-1.5 text-xs font-medium rounded-md transition-all flex items-center justify-center gap-1.5 ${
                    createMode === "custom_role" ? "bg-white text-purple-700 shadow-sm" : "text-gray-600 hover:text-gray-900"
                }`}
            >
                <Mic2 className="w-3.5 h-3.5" />
                默认角色
            </button>
            <button
                onClick={() => setCreateMode("voice_design")}
                className={`flex-1 px-3 py-1.5 text-xs font-medium rounded-md transition-all flex items-center justify-center gap-1.5 ${
                    createMode === "voice_design" ? "bg-white text-indigo-700 shadow-sm" : "text-gray-600 hover:text-gray-900"
                }`}
            >
                <Palette className="w-3.5 h-3.5" />
                设计克隆
            </button>
          </div>
        </div>

        <div className="bg-gray-50/50 p-3 rounded-lg border border-gray-100 space-y-3">
          <div className="flex items-start justify-between gap-3">
            <div className="text-xs text-gray-600 leading-5">
              {createMode === "clone" && "上传一段 3-10s 的参考音频，克隆其音色特征。需要 Base 模型。"}
              {createMode === "custom_role" && "使用 CustomVoice 模型内置的固定角色（如 Vivian, Ryan 等）。无需上传。"}
              {createMode === "voice_design" && "通过文本描述设计一个新音色，自动生成参考音频并克隆。需要 VoiceDesign + Base 模型。"}
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
              {renderCreateButton()}
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

            <Qwen3ModelOptionsList
              options={downloadOptions}
              modelsLoading={modelsLoading}
              downloadsByKey={Object.fromEntries(
                Object.entries(downloadsByKey).map(([key, v]) => [
                  key,
                  v ? { key: v.key, progress: v.progress, message: v.message, status: v.status, totalBytes: v.totalBytes, downloadedBytes: v.downloadedBytes } : null,
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
              onCopyPath={handleCopyPath}
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
        modelKeys={baseModelKeys}
        onClose={() => setUploadOpen(false)}
        onSubmit={handleUploadSubmit}
      />

      <Qwen3CustomRoleDialog
        isOpen={customRoleOpen}
        modelKeys={customModelKeys}
        onClose={() => setCustomRoleOpen(false)}
        onSubmit={handleCustomRoleSubmit}
      />

      <Qwen3VoiceDesignDialog
        isOpen={designOpen}
        voiceDesignModelKeys={designModelKeys}
        baseModelKeys={baseModelKeys}
        onClose={() => setDesignOpen(false)}
        onSubmit={handleDesignSubmit}
      />

      <Qwen3VoiceEditDialog
        isOpen={Boolean(editVoice)}
        voice={editVoice}
        modelKeys={allModelKeys}
        onClose={() => setEditVoice(null)}
        onSubmit={async (voiceId, p) => {
          await patch(voiceId, p);
          message.success("已保存");
        }}
      />
    </>
  );
};

export default Qwen3VoiceSection;

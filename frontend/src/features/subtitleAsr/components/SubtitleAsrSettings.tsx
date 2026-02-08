import React, { useEffect, useMemo, useState } from "react";
import { Cpu, Loader, Play, ShieldCheck } from "lucide-react";
import { message } from "@/services/message";
import { funAsrService } from "../services/funAsrService";
import { FUN_ASR_MODEL_OPTIONS } from "../constants";
import type { FunAsrDownloadProvider, FunAsrModelStatus } from "../types";
import { useFunAsrModels } from "../hooks/useFunAsrModels";
import FunAsrModelOptionsList from "./FunAsrModelOptionsList";

const badgeInfo = (st: { existsAll: boolean; validAll: boolean }) => {
  if (st.validAll) return { className: "bg-green-50 text-green-700 border-green-200", text: "可用" };
  if (st.existsAll) return { className: "bg-orange-50 text-orange-700 border-orange-200", text: "缺文件" };
  return { className: "bg-gray-100 text-gray-600 border-gray-200", text: "未安装" };
};

export const SubtitleAsrSettings: React.FC = () => {
  const { modelByKey, loading, downloadsByKey, validate, openModelDirInExplorer, downloadModel, stopDownload } = useFunAsrModels();

  const [providerByOptionId, setProviderByOptionId] = useState<Record<string, FunAsrDownloadProvider>>({
    nano_2512: "modelscope",
    mlt_nano_2512: "modelscope",
  });
  const [copiedOptionId, setCopiedOptionId] = useState<string | null>(null);
  console.log("modelByKeywww: ", modelByKey)
  const getModelStatus = (keys: string[]) => {
    const list = keys.map((k) => modelByKey.get(k)).filter(Boolean) as FunAsrModelStatus[];
    const existsAll = keys.length > 0 && keys.every((k) => Boolean(modelByKey.get(k)?.exists));
    const validAll = keys.length > 0 && keys.every((k) => Boolean(modelByKey.get(k)?.valid));
    const missing = list
      .flatMap((m) => (Array.isArray(m.missing) ? m.missing : []))
      .filter((x) => x);
    return { existsAll, validAll, missing };
  };

  const onDownload = async (opt: { id: string; keys: string[]; label: string }) => {
    const provider = providerByOptionId[opt.id] || "modelscope";
    for (const k of opt.keys) {
      const prov = k === "fsmn_vad" ? "modelscope" : provider;
      await downloadModel(k, prov, opt.id);
    }
  };

  const onStop = async (opt: { keys: string[] }) => {
    for (const k of opt.keys) {
      await stopDownload(k);
    }
  };

  const onValidate = async (opt: { keys: string[] }) => {
    for (const k of opt.keys) {
      await validate(k);
    }
  };

  const onOpenDir = async (opt: { keys: string[]; id: string }) => {
    try {
      await openModelDirInExplorer(opt.keys[0]);
      setCopiedOptionId(opt.id);
      window.setTimeout(() => setCopiedOptionId((prev) => (prev === opt.id ? null : prev)), 900);
    } catch (e: any) {
      message.error(e?.message || "打开目录失败");
    }
  };

  const options = useMemo(() => {
    return FUN_ASR_MODEL_OPTIONS.map((o) => ({
      id: o.id,
      label: o.label,
      keys: o.keys,
      description: o.description,
    }));
  }, []);

  const downloadsCompact = useMemo(() => {
    const map: Record<string, any> = {};
    Object.entries(downloadsByKey).forEach(([key, st]) => {
      map[key] = {
        key,
        progress: st.progress,
        message: st.message,
        status: st.status,
        downloadedBytes: st.downloadedBytes,
        totalBytes: st.totalBytes,
        ownerOptionId: st.ownerOptionId,
      };
    });
    return map;
  }, [downloadsByKey]);

  const [accLoading, setAccLoading] = useState(false);
  const [acc, setAcc] = useState<any>(null);

  const refreshAcceleration = async () => {
    setAccLoading(true);
    try {
      const res = await funAsrService.getAccelerationStatus();
      if (!res?.success) {
        message.error(res?.message || "获取加速状态失败");
        return;
      }
      setAcc(res.data || null);
    } catch (e: any) {
      message.error(e?.message || "获取加速状态失败");
    } finally {
      setAccLoading(false);
    }
  };

  useEffect(() => {
    void refreshAcceleration();
  }, []);

  const [testModelKey, setTestModelKey] = useState<string>("fun_asr_nano_2512");
  const [testLanguage, setTestLanguage] = useState<string>("中文");
  const [testItn, setTestItn] = useState<boolean>(true);
  const [testing, setTesting] = useState(false);
  const [testText, setTestText] = useState<string>("");

  const supportedLangs = useMemo(() => {
    const m = modelByKey.get(testModelKey);
    const langs = (m?.languages || []).filter(Boolean);
    if (langs.length) return langs;
    return testModelKey.includes("mlt") ? FUN_ASR_MODEL_OPTIONS[1].recommendedLanguages : FUN_ASR_MODEL_OPTIONS[0].recommendedLanguages;
  }, [modelByKey, testModelKey]);

  useEffect(() => {
    if (supportedLangs.length && !supportedLangs.includes(testLanguage)) {
      setTestLanguage(supportedLangs[0]);
    }
  }, [supportedLangs, testLanguage]);

  const runTest = async () => {
    setTesting(true);
    setTestText("");
    try {
      const res = await funAsrService.testModel({ key: testModelKey, language: testLanguage, itn: testItn });
      if (!res?.success) throw new Error(res?.message || "测试失败");
      const t = String(res.data?.text || "").trim();
      setTestText(t || "(未识别到文本)");
      message.success("测试完成");
    } catch (e: any) {
      message.error(e?.message || "测试失败");
    } finally {
      setTesting(false);
    }
  };

  const accelerationView = useMemo(() => {
    if (!acc?.acceleration) return null;
    const a = acc.acceleration;
    const isGpu = a.supported;
    const gpuName = a.gpu ? ` (${a.gpu})` : "";

    return {
      isGpu,
      text: isGpu ? "GPU" : "CPU",
      title: isGpu
        ? `支持 GPU 加速，默认设备: ${a.preferred_device}${gpuName}`
        : `不支持 GPU 加速，原因: ${(a.reasons || []).join(", ") || "unknown"}`,
      className: isGpu ? "bg-green-50 text-green-700 border-green-200" : "bg-gray-50 text-gray-600 border-gray-200",
    };
  }, [acc]);

  return (
    <div className="space-y-6">
      <section className="bg-white/80 backdrop-blur border rounded-xl p-5 shadow-sm space-y-3">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div className="flex items-center gap-2">
            <Cpu className="h-5 w-5 text-gray-700" />
            <h4 className="text-md font-semibold text-gray-900">加速状态</h4>
          </div>
          <button
            onClick={refreshAcceleration}
            disabled={accLoading}
            className="px-3 py-1.5 text-xs rounded-md border bg-white hover:bg-gray-50 disabled:opacity-50"
          >
            {accLoading ? "刷新中…" : "刷新"}
          </button>
        </div>
        <div
          className={`text-xs border rounded-lg p-3 whitespace-pre-wrap break-words ${
            accelerationView?.className || "text-gray-700 bg-gray-50 border-gray-200"
          }`}
        >
          {accelerationView ? (
            <>
              <div className="font-semibold mb-1">当前运行设备: {accelerationView.text}</div>
              <div className="opacity-80 leading-relaxed">{accelerationView.title}</div>
            </>
          ) : (
            "暂无数据"
          )}
        </div>
      </section>

      <section className="bg-white/80 backdrop-blur border rounded-xl p-5 shadow-sm space-y-3">
        <div className="flex items-center gap-2">
          <ShieldCheck className="h-5 w-5 text-gray-700" />
          <h4 className="text-md font-semibold text-gray-900">模型管理</h4>
        </div>

        <FunAsrModelOptionsList
          options={options}
          modelsLoading={loading}
          downloadsByKey={downloadsCompact}
          getModelStatus={getModelStatus}
          getBadgeInfo={(st) => badgeInfo(st)}
          getProvider={(id) => providerByOptionId[id] || "modelscope"}
          onChangeProvider={(id, prov) => setProviderByOptionId((prev) => ({ ...prev, [id]: prov }))}
          onDownload={onDownload}
          onStop={onStop}
          onValidate={onValidate}
          onOpenDir={onOpenDir}
          copiedOptionId={copiedOptionId}
        />
      </section>

      <section className="bg-white/80 backdrop-blur border rounded-xl p-5 shadow-sm space-y-3">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <h4 className="text-md font-semibold text-gray-900">默认音频测试</h4>
          <button
            onClick={runTest}
            disabled={testing}
            className="flex items-center gap-2 px-3 py-1.5 text-xs rounded-md border bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {testing ? <Loader className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
            {testing ? "测试中…" : "开始测试"}
          </button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div>
            <label className="block text-sm text-gray-700 mb-1">模型</label>
            <select
              value={testModelKey}
              onChange={(e) => setTestModelKey(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md bg-white"
              disabled={testing}
            >
              <option value="fun_asr_nano_2512">Fun-ASR-Nano-2512</option>
              <option value="fun_asr_mlt_nano_2512">Fun-ASR-MLT-Nano-2512</option>
            </select>
          </div>
          <div>
            <label className="block text-sm text-gray-700 mb-1">语言</label>
            <select
              value={testLanguage}
              onChange={(e) => setTestLanguage(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md bg-white"
              disabled={testing}
            >
              {supportedLangs.map((x) => (
                <option key={x} value={x}>
                  {x}
                </option>
              ))}
            </select>
          </div>
          <div className="flex items-end">
            <label className="flex items-center gap-2 text-sm text-gray-700">
              <input type="checkbox" checked={testItn} disabled={testing} onChange={(e) => setTestItn(e.target.checked)} />
              itn（逆文本归一化）
            </label>
          </div>
        </div>

        <div className="text-xs text-gray-700 bg-gray-50 border rounded-lg p-3 whitespace-pre-wrap break-words min-h-[44px]">
          {testing ? "测试中…" : testText || "点击“开始测试”验证模型与环境是否可用。"}
        </div>
      </section>
    </div>
  );
};

export default SubtitleAsrSettings;

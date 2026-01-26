import React, { useMemo, useState } from "react";
import { Check, Copy, Download, RefreshCw, ShieldAlert } from "lucide-react";
import { message } from "@/services/message";
import { useQwen3Models } from "../hooks/useQwen3Models";
import type { Qwen3TtsDownloadProvider, Qwen3TtsModelStatus } from "../types";

const badgeClass = (m: Qwen3TtsModelStatus) => {
  if (!m.exists) return "bg-gray-100 text-gray-600 border-gray-200";
  if (m.valid) return "bg-green-50 text-green-700 border-green-200";
  return "bg-orange-50 text-orange-700 border-orange-200";
};

const badgeText = (m: Qwen3TtsModelStatus) => {
  if (!m.exists) return "未发现";
  if (m.valid) return "可用";
  return "缺文件";
};

export const Qwen3ModelSection: React.FC = () => {
  const { models, loading, error, download, refresh, validate, getModelPath, downloadModel } = useQwen3Models();
  const [providerByKey, setProviderByKey] = useState<Record<string, Qwen3TtsDownloadProvider>>({});
  const [copiedKey, setCopiedKey] = useState<string | null>(null);

  const sorted = useMemo(() => {
    const rank = (k: string) => (k.includes("tokenizer") ? 0 : k.includes("base") ? 1 : k.includes("custom") ? 2 : 9);
    return [...models].sort((a, b) => {
      const ra = rank(a.key);
      const rb = rank(b.key);
      if (ra !== rb) return ra - rb;
      return a.key.localeCompare(b.key);
    });
  }, [models]);

  const handleCopyPath = async (key: string) => {
    try {
      const p = await getModelPath(key);
      await navigator.clipboard.writeText(p);
      setCopiedKey(key);
      setTimeout(() => setCopiedKey((prev) => (prev === key ? null : prev)), 1200);
      message.success("已复制模型目录路径");
    } catch (e: any) {
      message.error(e?.message || "复制失败");
    }
  };

  const getProvider = (key: string): Qwen3TtsDownloadProvider => providerByKey[key] || "hf";

  return (
    <section className="bg-white/80 backdrop-blur border rounded-xl p-5 shadow-sm space-y-4">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <h4 className="text-md font-semibold text-gray-900">Qwen3-TTS 模型</h4>
          {error ? (
            <span className="text-xs text-red-600 flex items-center gap-1">
              <ShieldAlert className="h-4 w-4" />
              {error}
            </span>
          ) : null}
        </div>
        <button
          onClick={() => refresh()}
          disabled={loading}
          className={`px-3 py-1.5 text-sm rounded-md border ${loading ? "bg-gray-100 text-gray-400" : "bg-white hover:bg-gray-50 text-gray-700"}`}
        >
          <span className="inline-flex items-center gap-2">
            <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
            刷新
          </span>
        </button>
      </div>

      <div className="text-xs text-gray-600 leading-5">
        可选两种方式：点击下载自动拉取，或手动把已下载的模型目录复制到目标路径（目录名对应模型 key）。
      </div>

      <div className="space-y-2">
        {sorted.map((m) => {
          const isDownloading = download?.key === m.key;
          return (
            <div key={m.key} className="border rounded-lg bg-white">
              <div className="px-4 py-3 flex items-center gap-3">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-gray-900 truncate">{m.key}</span>
                    <span className={`text-[11px] px-2 py-0.5 rounded-full border ${badgeClass(m)}`}>
                      {badgeText(m)}
                    </span>
                    {Array.isArray(m.missing) && m.missing.length > 0 ? (
                      <span className="text-[11px] text-orange-700 truncate">缺失: {m.missing.join(", ")}</span>
                    ) : null}
                  </div>
                  <div className="mt-1 text-[11px] text-gray-500 truncate" title={m.path}>
                    {m.path}
                  </div>
                  {isDownloading ? (
                    <div className="mt-2">
                      <div className="flex items-center justify-between text-[11px] text-gray-600">
                        <span className="truncate">{download?.message || "下载中…"}</span>
                        <span className="tabular-nums">{Math.round(download?.progress || 0)}%</span>
                      </div>
                      <div className="mt-1 h-2 rounded bg-gray-100 overflow-hidden">
                        <div className="h-full bg-blue-600 transition-all" style={{ width: `${Math.max(0, Math.min(100, download?.progress || 0))}%` }} />
                      </div>
                    </div>
                  ) : null}
                </div>

                <div className="flex items-center gap-2 flex-shrink-0">
                  <select
                    value={getProvider(m.key)}
                    onChange={(e) => setProviderByKey((prev) => ({ ...prev, [m.key]: e.target.value as Qwen3TtsDownloadProvider }))}
                    className="text-sm border rounded-md px-2 py-1 bg-white"
                    disabled={loading || isDownloading}
                    title="下载源"
                  >
                    <option value="hf">HuggingFace</option>
                    <option value="modelscope">ModelScope</option>
                  </select>

                  <button
                    onClick={() => downloadModel(m.key, getProvider(m.key))}
                    disabled={loading || isDownloading}
                    className={`px-3 py-1.5 text-sm rounded-md border ${
                      loading || isDownloading ? "bg-gray-100 text-gray-400" : "bg-white hover:bg-gray-50 text-gray-700"
                    }`}
                    title="下载模型"
                  >
                    <span className="inline-flex items-center gap-2">
                      <Download className="h-4 w-4" />
                      下载
                    </span>
                  </button>

                  <button
                    onClick={() => validate(m.key)}
                    disabled={loading || isDownloading}
                    className={`px-3 py-1.5 text-sm rounded-md border ${
                      loading || isDownloading ? "bg-gray-100 text-gray-400" : "bg-white hover:bg-gray-50 text-gray-700"
                    }`}
                    title="校验"
                  >
                    <span className="inline-flex items-center gap-2">
                      <ShieldAlert className="h-4 w-4" />
                      校验
                    </span>
                  </button>

                  <button
                    onClick={() => handleCopyPath(m.key)}
                    disabled={loading || isDownloading}
                    className={`px-3 py-1.5 text-sm rounded-md border ${
                      loading || isDownloading ? "bg-gray-100 text-gray-400" : "bg-white hover:bg-gray-50 text-gray-700"
                    }`}
                    title="复制目标路径（用于手动拷贝）"
                  >
                    <span className="inline-flex items-center gap-2">
                      {copiedKey === m.key ? <Check className="h-4 w-4 text-green-600" /> : <Copy className="h-4 w-4" />}
                      {copiedKey === m.key ? "已复制" : "复制路径"}
                    </span>
                  </button>
                </div>
              </div>
            </div>
          );
        })}

        {sorted.length === 0 && !loading ? (
          <div className="text-sm text-gray-500">暂无模型条目</div>
        ) : null}
      </div>
    </section>
  );
};

export default Qwen3ModelSection;


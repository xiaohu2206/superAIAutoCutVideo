import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Eye, ShieldCheck, Play, Loader, FolderOpen, Download, XCircle, RefreshCw, Info } from "lucide-react";
import { useMoondreamModels } from "../hooks/useMoondreamModels";
import { moondreamService } from "../services/moondreamService";
import { message } from "@/services/message";
import { TauriCommands } from "@/services/clients";

export const VisionModelSettings: React.FC = () => {
    const { modelByKey, loading, validate, openModelDirInExplorer, downloadTask, downloadModel, stopDownload } = useMoondreamModels();
    
    const modelKey = "moondream2_gguf";
    const status = modelByKey.get(modelKey);
    
    const [testing, setTesting] = useState(false);
    const [testResult, setTestResult] = useState<string>("");
    
    const [provider, setProvider] = useState<"modelscope" | "hf">("modelscope");

    const [accLoading, setAccLoading] = useState(false);
    const [accData, setAccData] = useState<any>(null);
    
    const [accDebugOpen, setAccDebugOpen] = useState<boolean>(false);

    const refreshAcceleration = useCallback(async () => {
        setAccLoading(true);
        try {
            const res = await moondreamService.getAccelerationStatus();
            if (!res?.success) {
                message.error(res?.message || "获取加速状态失败");
                return;
            }
            setAccData(res.data || null);
            
        } catch (e: any) {
            message.error(e?.message || "获取加速状态失败");
        } finally {
            setAccLoading(false);
        }
    }, []);

    useEffect(() => {
        void refreshAcceleration();
    }, [refreshAcceleration]);

    const runTest = async () => {
        setTesting(true);
        setTestResult("");
        try {
            const res = await moondreamService.testModel("Describe this image.");
            if (res.success && res.data) {
                setTestResult(res.data.text);
                message.success("测试完成");
            } else {
                message.error(res.message || "测试失败");
            }
        } catch (e: any) {
            message.error(e.message || "测试失败");
        } finally {
            setTesting(false);
        }
    };
    
    const isDownloading = downloadTask && downloadTask.key === modelKey && downloadTask.status === "running";

    

    const accelerationView = useMemo(() => {
        const a = (accData as any)?.acceleration;
        const runtime = (accData as any)?.runtime;
        const resolved = (accData as any)?.resolved;
        const resolvedDevice = String(resolved?.device || "cpu");
        const isGpu = resolvedDevice.toLowerCase().startsWith("cuda");
        const labelPrefix = runtime?.loaded ? "当前推理" : "推理设备";
        const gpuName = a?.gpu?.name ? ` (${a.gpu.name})` : "";
        const title = a?.supported
            ? `支持 GPU 加速，默认设备: ${a.preferred_device}${gpuName}`
            : `不支持 GPU 加速，原因: ${(a?.reasons || []).join(",") || "unknown"}`;
        return {
            className: isGpu ? "bg-green-50 text-green-700 border-green-200" : "bg-gray-100 text-gray-600 border-gray-200",
            text: `${labelPrefix}: ${isGpu ? "GPU" : "CPU"}`,
            title,
        };
    }, [accData]);

    

    const formatBytes = (bytes?: number) => {
        if (bytes === undefined) return "-";
        if (bytes === 0) return "0 B";
        const k = 1024;
        const sizes = ["B", "KB", "MB", "GB", "TB"];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
    };
    
    return (
        <div className="space-y-6">
            <section className="bg-white/80 backdrop-blur border rounded-xl p-5 shadow-sm space-y-3">
                <div className="flex items-center gap-2">
                    <ShieldCheck className="h-5 w-5 text-gray-700" />
                    <h4 className="text-md font-semibold text-gray-900">模型管理</h4>
                </div>
                 <div className="flex items-center gap-2">
                    <button
                        type="button"
                        onClick={() => setAccDebugOpen((prev) => !prev)}
                        className={`text-xs px-2 py-0.5 rounded-full border ${accelerationView.className}`}
                        title={accelerationView.title}
                        aria-expanded={accDebugOpen}
                    >
                        {accelerationView.text}
                    </button>
                    <button
                            type="button"
                            onClick={() => refreshAcceleration()}
                            disabled={accLoading}
                            className="p-1.5 rounded-md text-gray-500 hover:bg-gray-100 hover:text-gray-700 disabled:opacity-50"
                            title="刷新加速状态"
                        >
                            <RefreshCw className={`h-4 w-4 ${accLoading ? "animate-spin" : ""}`} />
                        </button>
                </div>
                {accDebugOpen ? (
                    <div className="mt-2 rounded-lg border border-gray-200 bg-gray-50 px-3 py-2">
                        <div className="text-[11px] text-gray-500 mb-1">/api/vision/moondream/acceleration-status</div>
                        <pre className="text-[11px] leading-4 whitespace-pre-wrap break-words text-gray-800 max-h-56 overflow-auto">
                            {JSON.stringify(accData ?? null, null, 2)}
                        </pre>
                    </div>
                ) : null}
                <div className="bg-white border rounded-lg p-3 shadow-sm">
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                         <div className="flex items-start gap-3">
                            <div className={`p-2 rounded-lg ${status?.exists ? "bg-blue-50 text-blue-600" : "bg-gray-100 text-gray-500"}`}>
                                <Eye className="w-5 h-5" />
                            </div>
                            <div>
                                <div className="flex items-center gap-2 flex-wrap">
                                    <h5 className="text-sm font-medium text-gray-900">Moondream2 (GGUF)</h5>
                                     <span
                                        className={`text-[10px] px-1.5 py-0.5 rounded-full border ${
                                            status?.valid 
                                            ? "bg-green-50 text-green-700 border-green-200" 
                                            : (status?.exists ? "bg-orange-50 text-orange-700 border-orange-200" : "bg-gray-100 text-gray-600 border-gray-200")
                                        }`}
                                        title={status?.missing?.length ? `缺失: ${status.missing.join(", ")}` : ""}
                                      >
                                        {status?.valid ? "可用" : (status?.exists ? "缺文件" : "未安装")}
                                      </span>
                                </div>
                                <div className="mt-1 text-xs text-gray-500">轻量级视觉语言模型，支持图像描述与问答</div>
                            </div>
                         </div>
                         
                         <div className="flex items-center gap-2 self-end sm:self-center">
                            {isDownloading ? (
                                <button
                                    onClick={() => stopDownload(modelKey)}
                                    className="px-2.5 py-1 text-xs border border-red-200 bg-red-50 text-red-700 hover:bg-red-100 rounded h-7 flex items-center gap-1"
                                >
                                    <XCircle className="h-3.5 w-3.5" />
                                    停止
                                </button>
                            ) : (
                                !status?.valid && (
                                    <>
                                      <select 
                                        value={provider} 
                                        onChange={e => setProvider(e.target.value as any)}
                                        className="h-7 text-xs border-gray-300 rounded focus:ring-blue-500 focus:border-blue-500"
                                      >
                                          <option value="modelscope">ModelScope</option>
                                          <option value="hf">HuggingFace</option>
                                      </select>
                                      <button
                                          onClick={() => downloadModel(provider)}
                                          className="px-2.5 py-1 text-xs border border-blue-200 bg-blue-50 text-blue-700 hover:bg-blue-100 rounded h-7 flex items-center gap-1"
                                      >
                                          <Download className="h-3.5 w-3.5" />
                                          下载
                                      </button>
                                    </>
                                )
                            )}
                            <button
                                onClick={() => validate(modelKey)}
                                disabled={loading || Boolean(isDownloading)}
                                className="px-2.5 py-1 text-xs border rounded hover:bg-gray-50 text-gray-700 h-7 flex items-center gap-1"
                                title="校验完整性"
                            >
                                <ShieldCheck className="h-3.5 w-3.5" />
                                校验
                            </button>
                            <button
                                onClick={openModelDirInExplorer}
                                disabled={loading}
                                className="px-2.5 py-1 text-xs border rounded hover:bg-gray-50 text-gray-700 h-7 flex items-center gap-1"
                                title="打开模型目录"
                            >
                                <FolderOpen className="h-3.5 w-3.5" />
                                目录
                            </button>
                         </div>
                    </div>
                    
                    {isDownloading && (
                        <div className="mt-3 bg-blue-50/50 border border-blue-100 rounded p-3">
                            <div className="flex justify-between text-xs text-gray-600 mb-1">
                                <span>{downloadTask?.message || "正在下载..."}</span>
                                <span>{Math.round(downloadTask?.progress || 0)}%</span>
                            </div>
                            <div className="w-full h-1.5 bg-gray-200 rounded-full overflow-hidden">
                                <div 
                                    className="h-full bg-blue-600 transition-all duration-300"
                                    style={{ width: `${downloadTask?.progress || 0}%` }}
                                />
                            </div>
                            <div className="flex justify-between text-[10px] text-gray-400 mt-1">
                                <span>{formatBytes(downloadTask?.downloaded_bytes)} / {formatBytes(downloadTask?.total_bytes)}</span>
                                <span>源: {downloadTask?.provider === "hf" ? "HuggingFace" : "ModelScope"}</span>
                            </div>
                        </div>
                    )}
                    
                    {!status?.valid && !isDownloading && (
                         <div className="mt-3 bg-blue-50 border border-blue-200 rounded-lg p-3 text-sm text-blue-800 flex gap-2">
                            <Info className="w-5 h-5 flex-shrink-0 text-blue-600" />
                            <div className="space-y-1">
                                <p className="font-medium">模型下载说明：</p>
                                <ul className="list-disc list-inside text-blue-700 space-y-0.5 ml-1">
                                    <li>支持点击按钮在线下载，也支持手动下载后复制到对应目录。</li>
                                    <li>
                                        手动下载入口：
                                        <button 
                                            onClick={() => TauriCommands.openExternalLink("https://my.feishu.cn/wiki/NI0qwbHftith0kkxhHJcjGlJnRc")}
                                            className="ml-1 inline-flex items-center bg-transparent border-none cursor-pointer p-0 text-blue-700 underline hover:text-blue-900"
                                            type="button"
                                        >
                                            网盘下载
                                        </button>
                                    </li>
                                    <li>下载所有必需文件（configuration.json, moondream2-mmproj-f16.gguf, moondream2-text-model-f16.gguf, moondream2.preset.json）。</li>
                                    <li>点击“目录”打开文件夹，将下载的文件放入其中；再点击“校验”确认安装成功。</li>
                                </ul>
                            {status?.missing && status.missing.length > 0 && (
                                <div className="mt-2 text-red-600 text-xs">
                                    缺失文件: {status.missing.join(", ")}
                                </div>
                            )}
                            </div>
                         </div>
                    )}
                </div>
            </section>
            
          

            <section className="bg-white/80 backdrop-blur border rounded-xl p-5 shadow-sm space-y-3">
                 <div className="flex items-center justify-between gap-3 flex-wrap">
                    <h4 className="text-md font-semibold text-gray-900">模型测试</h4>
                    <button
                        onClick={runTest}
                        disabled={testing || !status?.valid || Boolean(isDownloading)}
                        className="flex items-center gap-2 px-3 py-1.5 text-xs rounded-md border bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                        {testing ? <Loader className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                        {testing ? "测试中…" : "开始测试"}
                    </button>
                 </div>
                 
                 <div className="text-xs text-gray-700 bg-gray-50 border rounded-lg p-3 whitespace-pre-wrap break-words min-h-[44px]">
                    {testing ? "正在生成图像描述..." : (testResult || "点击“开始测试”验证模型是否可用（将生成一张随机图像并进行描述）。")}
                 </div>
            </section>
        </div>
    );
};

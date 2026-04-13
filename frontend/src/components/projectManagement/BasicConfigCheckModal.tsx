import React, { useEffect, useMemo, useState } from "react";
import { CheckCircle2, Loader2, X, XCircle } from "lucide-react";
import contentModelService from "../../services/contentModelService";
import videoModelService from "../../services/videoModelService";
import ttsService from "../../services/ttsService";
import healthService from "../../services/healthService";
import jianyingService from "../../services/jianyingService";

type StepStatus = "pending" | "running" | "success" | "failed";

type StepResult = {
  status: StepStatus;
  message?: string;
  detail?: any;
};

interface BasicConfigCheckModalProps {
  isOpen: boolean;
  onClose: () => void;
}

const BasicConfigCheckModal: React.FC<BasicConfigCheckModalProps> = ({ isOpen, onClose }) => {
  const [running, setRunning] = useState(false);
  const [contentResult, setContentResult] = useState<StepResult>({ status: "pending" });
  const [videoResult, setVideoResult] = useState<StepResult>({ status: "pending" });
  const [ttsResult, setTtsResult] = useState<StepResult>({ status: "pending" });
  const [asrResult, setAsrResult] = useState<StepResult>({ status: "pending" });
  const [jianyingResult, setJianyingResult] = useState<StepResult>({ status: "pending" });

  const totalSteps = 5;
  const doneSteps = useMemo(() => {
    const s = [
      contentResult.status,
      videoResult.status,
      ttsResult.status,
      asrResult.status,
      jianyingResult.status,
    ];
    return s.filter((x) => x === "success" || x === "failed").length;
  }, [contentResult.status, videoResult.status, ttsResult.status, asrResult.status, jianyingResult.status]);
  const progress = Math.round((doneSteps / totalSteps) * 100);

  const reset = () => {
    setContentResult({ status: "pending" });
    setVideoResult({ status: "pending" });
    setTtsResult({ status: "pending" });
    setAsrResult({ status: "pending" });
    setJianyingResult({ status: "pending" });
  };

  const getRespMessage = (resp: any, fallback: string) => {
    const m1 = resp?.message;
    if (typeof m1 === "string" && m1.trim()) return m1;
    const m2 = resp?.data?.message;
    if (typeof m2 === "string" && m2.trim()) return m2;
    const err = resp?.data?.error || resp?.error;
    if (typeof err === "string" && err.trim()) return err;
    return fallback;
  };

  const runChecks = async () => {
    if (running) return;
    setRunning(true);
    reset();

    let phase: "content" | "video" | "tts" | "asr" | "jianying" = "content";
    try {
      phase = "content";
      setContentResult({ status: "running" });
      const contentResp: any = await contentModelService.testActiveConnection();
      const contentOk = !!contentResp?.success;
      setContentResult({
        status: contentOk ? "success" : "failed",
        message: getRespMessage(contentResp, contentOk ? "可用" : "不可用"),
        detail: contentResp?.data,
      });

      phase = "video";
      setVideoResult({ status: "running" });
      const videoResp: any = await videoModelService.testActiveConnection();
      const videoOk = !!videoResp?.success;
      setVideoResult({
        status: videoOk ? "success" : "failed",
        message: getRespMessage(videoResp, videoOk ? "可用" : "不可用"),
        detail: videoResp?.data,
      });

      phase = "tts";
      setTtsResult({ status: "running" });
      const ttsResp: any = await ttsService.testActiveConnection();
      const ttsOk = !!ttsResp?.success;
      setTtsResult({
        status: ttsOk ? "success" : "failed",
        message: getRespMessage(ttsResp, ttsOk ? "可用" : "不可用"),
        detail: ttsResp?.data,
      });

      phase = "asr";
      setAsrResult({ status: "running" });
      const asrResp: any = await healthService.testBcutAsrConnection();
      const asrOk = !!asrResp?.success;
      setAsrResult({
        status: asrOk ? "success" : "failed",
        message: getRespMessage(asrResp, asrOk ? " ASR 可用" : "不可用"),
        detail: asrResp?.data,
      });

      phase = "jianying";
      setJianyingResult({ status: "running" });
      const jyResp: any = await jianyingService.getDraftPath();
      const jyPath = jyResp?.data?.path as string | null | undefined;
      const jyExists = !!jyResp?.data?.exists;
      const jyApiOk = !!jyResp?.success;
      let jyMsg: string;
      if (!jyApiOk) {
        jyMsg = getRespMessage(jyResp, "获取剪映草稿路径失败");
      } else if (!jyPath) {
        jyMsg = "未配置剪映草稿路径，请到【设置 → 剪映草稿路径】配置";
      } else if (!jyExists) {
        jyMsg = `路径无效或不存在：${jyPath}`;
      } else {
        jyMsg = "路径有效";
      }
      const jyOk = jyApiOk && !!jyPath && jyExists;
      setJianyingResult({
        status: jyOk ? "success" : "failed",
        message: jyMsg,
        detail: jyResp?.data,
      });
    } catch (e: any) {
      const msg = typeof e?.message === "string" ? e.message : "请求失败";
      if (phase === "content") {
        setContentResult({ status: "failed", message: msg, detail: e });
        setVideoResult({ status: "pending" });
        setTtsResult({ status: "pending" });
        setAsrResult({ status: "pending" });
        setJianyingResult({ status: "pending" });
      } else if (phase === "video") {
        setVideoResult({ status: "failed", message: msg, detail: e });
        setTtsResult({ status: "pending" });
        setAsrResult({ status: "pending" });
        setJianyingResult({ status: "pending" });
      } else if (phase === "tts") {
        setTtsResult({ status: "failed", message: msg, detail: e });
        setAsrResult({ status: "pending" });
        setJianyingResult({ status: "pending" });
      } else if (phase === "asr") {
        setAsrResult({ status: "failed", message: msg, detail: e });
        setJianyingResult({ status: "pending" });
      } else {
        setJianyingResult({ status: "failed", message: msg, detail: e });
      }
    } finally {
      setRunning(false);
    }
  };

  useEffect(() => {
    if (!isOpen) return;
    void runChecks();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen]);

  if (!isOpen) return null;

  const StepRow = ({
    title,
    result,
  }: {
    title: string;
    result: StepResult;
  }) => {
    const icon =
      result.status === "running" ? (
        <Loader2 className="h-5 w-5 text-blue-600 animate-spin" />
      ) : result.status === "success" ? (
        <CheckCircle2 className="h-5 w-5 text-green-600" />
      ) : result.status === "failed" ? (
        <XCircle className="h-5 w-5 text-red-600" />
      ) : (
        <div className="h-5 w-5 rounded-full border border-gray-300" />
      );

    const badge =
      result.status === "running"
        ? "检测中..."
        : result.status === "success"
          ? "通过"
          : result.status === "failed"
            ? "失败"
            : "等待";

    const badgeCls =
      result.status === "running"
        ? "bg-blue-50 text-blue-700"
        : result.status === "success"
          ? "bg-green-50 text-green-700"
          : result.status === "failed"
            ? "bg-red-50 text-red-700"
            : "bg-gray-50 text-gray-700";

    return (
      <div className="flex items-start justify-between gap-4 py-3">
        <div className="flex items-start gap-3 min-w-0">
          <div className="mt-0.5 shrink-0">{icon}</div>
          <div className="min-w-0">
            <div className="text-sm font-semibold text-gray-900">{title}</div>
            {result.message && (
              <div className="text-xs text-gray-600 mt-1 break-words">{result.message}</div>
            )}
          </div>
        </div>
        <span className={`shrink-0 px-2 py-1 rounded-md text-xs font-medium ${badgeCls}`}>
          {badge}
        </span>
      </div>
    );
  };

  const allDone =
    (contentResult.status === "success" || contentResult.status === "failed") &&
    (videoResult.status === "success" || videoResult.status === "failed") &&
    (ttsResult.status === "success" || ttsResult.status === "failed") &&
    (asrResult.status === "success" || asrResult.status === "failed") &&
    (jianyingResult.status === "success" || jianyingResult.status === "failed");

  const overallOk =
    contentResult.status === "success" &&
    videoResult.status === "success" &&
    ttsResult.status === "success" &&
    asrResult.status === "success" &&
    jianyingResult.status === "success";

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      <div className="fixed inset-0 bg-black bg-opacity-50 transition-opacity" onClick={running ? undefined : onClose} />

      <div className="flex items-center justify-center min-h-screen p-4">
        <div className="relative bg-white rounded-lg shadow-xl max-w-lg w-full">
          <div className="flex items-center justify-between p-6 border-b border-gray-200">
            <div className="flex items-center space-x-3">
              <div className="flex items-center justify-center w-10 h-10 bg-blue-100 rounded-lg">
                <Loader2 className={`h-5 w-5 text-blue-600 ${running ? "animate-spin" : ""}`} />
              </div>
              <div>
                <h3 className="text-xl font-semibold text-gray-900">基础连通检测</h3>
                <div className="text-xs text-gray-500 mt-0.5">
                  依次检测：文案生成模型、视频模型、配音、内置字幕识别、剪映草稿路径
                </div>
              </div>
            </div>
            <button
              onClick={onClose}
              disabled={running}
              className="text-gray-400 hover:text-gray-600 transition-colors disabled:opacity-50"
            >
              <X className="h-6 w-6" />
            </button>
          </div>

          <div className="p-6 space-y-4">
            <div>
              <div className="flex items-center justify-between mb-2">
                <div className="text-sm font-medium text-gray-700">进度</div>
                <div className="text-sm text-gray-600">{progress}%</div>
              </div>
              <div className="w-full h-2 bg-gray-100 rounded-full overflow-hidden">
                <div className="h-2 bg-blue-600 transition-all" style={{ width: `${progress}%` }} />
              </div>
            </div>

            <div className="divide-y divide-gray-100 border border-gray-200 rounded-lg px-4">
              <StepRow title="1) 测试文案生成模型" result={contentResult} />
              <StepRow title="2) 测试视频生成模型" result={videoResult} />
              <StepRow title="3) 测试配音" result={ttsResult} />
              <StepRow title="4) 测试字幕识别（只测内置API）" result={asrResult} />
              <StepRow title="5) 剪映草稿路径" result={jianyingResult} />
            </div>

            {allDone && (
              <div
                className={`px-4 py-3 rounded-lg text-sm ${
                  overallOk ? "bg-green-50 text-green-700" : "bg-amber-50 text-amber-700"
                }`}
              >
                {overallOk
                  ? "基础连通检测通过，可以开始使用。"
                  : "检测未完全通过，请到【设置 → 模型配置】与【音色 / 配音】检查启用项与密钥；字幕识别失败多为网络或接口不可达（使用 bcut 提取字幕时需可达）；剪映草稿路径未通过时请到【设置 → 剪映草稿路径】配置或自动查找。"}
              </div>
            )}
          </div>

          <div className="bg-gray-50 px-6 py-4 flex items-center justify-end space-x-3 border-t border-gray-200">
            <button
              type="button"
              onClick={onClose}
              disabled={running}
              className="px-4 py-2 text-gray-700 bg-white border border-gray-300 hover:bg-gray-50 rounded-lg font-medium transition-colors disabled:opacity-50"
            >
              关闭
            </button>
            <button
              type="button"
              onClick={() => void runChecks()}
              disabled={running}
              className="px-6 py-2 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {running ? "检测中..." : "重新检测"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default BasicConfigCheckModal;


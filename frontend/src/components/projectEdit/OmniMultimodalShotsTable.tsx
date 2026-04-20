import React, { useMemo, useState } from "react";
import { Eye, Play, X } from "lucide-react";
import type { OmniMultimodalResult, OmniMultimodalShot } from "../../types/omniMultimodal";

interface OmniMultimodalShotsTableProps {
  result: OmniMultimodalResult | null;
  onPlayShot: (start: number, end: number) => void;
}

function shotSubtitle(s: OmniMultimodalShot): string {
  const t = (s.subtitle_full_text || s.subtitle?.full_text || "").trim();
  return t;
}

function formatVisual(v: OmniMultimodalShot["visual"]): string {
  if (!v) return "";
  const parts = [
    v.brief && `摘要：${v.brief}`,
    v.desc && `画面：${v.desc}`,
    v.action && `动作：${v.action}`,
    v.emotion && `情绪：${v.emotion}`,
  ].filter(Boolean);
  return parts.join("\n");
}

/** 与后端 Step2 完成判定一致：有非空向量 + visual 对象，且非 pending/error */
function isOmniStep2Ok(s: OmniMultimodalShot): boolean {
  const st = String(s.omni_step2_status || "").trim().toLowerCase();
  if (st === "pending" || st === "error") return false;
  const emb = s.embedding;
  if (!Array.isArray(emb) || emb.length === 0) return false;
  const vis = s.visual;
  return vis != null && typeof vis === "object";
}

function isOmniStep2Error(s: OmniMultimodalShot): boolean {
  return String(s.omni_step2_status || "").trim().toLowerCase() === "error";
}

const OmniMultimodalShotsTable: React.FC<OmniMultimodalShotsTableProps> = ({ result, onPlayShot }) => {
  const [isModalOpen, setIsModalOpen] = useState(false);

  const shots = useMemo(() => (Array.isArray(result?.shots) ? result!.shots! : []), [result]);

  const metaLine = useMemo(() => {
    const m = result?.omni_pipeline_meta;
    if (!m || typeof m !== "object") return "";
    const vl = typeof m.vl_model === "string" ? m.vl_model : "";
    const emb = typeof m.embedding_model === "string" ? m.embedding_model : "";
    if (vl && emb) return `${vl} · ${emb}`;
    return vl || emb || "";
  }, [result?.omni_pipeline_meta]);

  const analyzedVisionCount = useMemo(() => shots.filter((s) => isOmniStep2Ok(s)).length, [shots]);
  const visionErrorCount = useMemo(() => shots.filter((s) => isOmniStep2Error(s)).length, [shots]);
  const notOkCount = Math.max(shots.length - analyzedVisionCount, 0);
  const nonErrorNotOkCount = Math.max(notOkCount - visionErrorCount, 0);

  if (!result || shots.length === 0) {
    return null;
  }

  return (
    <div className="space-y-4 mt-6">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-gray-900">Omni 多模态镜头结果</h2>
      </div>

      <p className="text-sm text-gray-600">点击下方区域可查看每个语义段的字幕与多模态分析摘要。</p>

      <div className="relative group cursor-pointer" onClick={() => setIsModalOpen(true)}>
        <div className="w-full min-h-10 px-4 py-2 font-mono text-sm border border-fuchsia-200 rounded-lg bg-fuchsia-50/40 overflow-hidden text-gray-700 hover:border-fuchsia-400 hover:ring-1 hover:ring-fuchsia-300 transition-all flex items-center justify-between gap-4">
          <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <span>
              共 {shots.length} 个语义镜头段，已成功分析画面 {analyzedVisionCount} 个
              {visionErrorCount > 0 && (
                <span className="text-amber-600">（分析失败 {visionErrorCount} 个）</span>
              )}
              {typeof result.total_duration === "number" ? (
                <span className="text-gray-500">（视频约 {result.total_duration.toFixed(1)}s）</span>
              ) : null}
            </span>
            {nonErrorNotOkCount > 0 && (
              <span className="text-red-500 text-xs font-medium">
                还有 {nonErrorNotOkCount} 个镜头未成功完成画面分析
              </span>
            )}
          </span>
          {metaLine ? <span className="text-gray-500 text-xs truncate max-w-[50%]">{metaLine}</span> : null}
        </div>

        <div className="absolute inset-0 bg-black bg-opacity-0 group-hover:bg-opacity-5 flex items-center justify-center transition-all rounded-lg pointer-events-none">
          <div className="opacity-0 group-hover:opacity-100 bg-white shadow-sm border border-gray-200 px-3 py-1.5 rounded-full text-sm font-medium text-gray-700 flex items-center">
            <Eye className="w-3 h-3 mr-1.5" />
            查看详情
          </div>
        </div>

        <div className="absolute top-2 right-2 bg-gray-100 px-2 py-1 rounded text-xs text-gray-600 hidden group-hover:block">
          点击展开
        </div>
      </div>

      {isModalOpen && (
        <div className="fixed inset-0 z-50 overflow-y-auto">
          <div className="fixed inset-0 bg-black bg-opacity-50 transition-opacity" onClick={() => setIsModalOpen(false)} />
          <div className="flex items-center justify-center min-h-screen p-4">
            <div className="relative bg-white rounded-lg shadow-xl max-w-6xl w-full flex flex-col max-h-[90vh]">
              <div className="flex items-center justify-between p-6 border-b border-gray-200 bg-white rounded-t-lg sticky top-0 z-10">
                <div className="flex items-center gap-4 flex-wrap">
                  <h3 className="text-xl font-semibold text-gray-900">Omni 多模态详情</h3>
                  <div className="text-sm text-gray-500 bg-gray-100 px-2 py-1 rounded">共 {shots.length} 段</div>
                  {metaLine ? (
                    <div className="text-xs text-gray-500 bg-fuchsia-50 px-2 py-1 rounded border border-fuchsia-100">{metaLine}</div>
                  ) : null}
                </div>
                <button
                  type="button"
                  onClick={() => setIsModalOpen(false)}
                  className="text-gray-400 hover:text-gray-600 transition-colors p-1 rounded hover:bg-gray-100"
                >
                  <X className="h-6 w-6" />
                </button>
              </div>

              <div className="bg-gray-50 px-6 py-3 border-b border-gray-200 font-medium text-sm text-gray-700 grid grid-cols-12 gap-4 sticky top-[72px] z-0">
                <div className="col-span-1">序号</div>
                <div className="col-span-2">操作</div>
                <div className="col-span-2">时间段</div>
                <div className="col-span-3">字幕</div>
                <div className="col-span-4">多模态分析</div>
              </div>

              <div className="overflow-y-auto p-0 flex-1 bg-white">
                {shots.map((shot, idx) => {
                  const id = shot.shot_id ?? idx + 1;
                  const range = `${Number(shot.start).toFixed(2)} — ${Number(shot.end).toFixed(2)}`;
                  const sub = shotSubtitle(shot);
                  const vis = formatVisual(shot.visual);
                  return (
                    <div
                      key={`${id}-${idx}`}
                      className="px-6 py-3 border-b border-gray-100 text-sm text-gray-600 grid grid-cols-12 gap-4 items-start hover:bg-fuchsia-50/40 transition-colors"
                    >
                      <div className="col-span-1 font-medium text-gray-900">{id}</div>
                      <div className="col-span-2">
                        <button
                          type="button"
                          onClick={() => onPlayShot(Number(shot.start), Number(shot.end))}
                          className="flex items-center text-fuchsia-700 hover:text-fuchsia-900 transition-colors bg-fuchsia-50 hover:bg-fuchsia-100 px-2 py-1 rounded-md text-xs font-medium border border-fuchsia-200"
                        >
                          <Play className="w-3 h-3 mr-1 fill-current" />
                          播放片段
                        </button>
                      </div>
                      <div className="col-span-2 font-mono text-xs bg-gray-100 px-2 py-1 rounded inline-block text-center w-fit text-gray-700">
                        {range}
                      </div>
                      <div className="col-span-3 text-gray-800 whitespace-pre-wrap break-words" title={sub}>
                        {sub || <span className="text-gray-400 italic">无</span>}
                      </div>
                      <div
                        className="col-span-4 text-gray-800 text-xs leading-relaxed whitespace-pre-wrap break-words"
                        title={vis}
                      >
                        {vis || <span className="text-gray-400 italic">—</span>}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default OmniMultimodalShotsTable;

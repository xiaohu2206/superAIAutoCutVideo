import React, { useState } from "react";
import { Edit3, Loader, RefreshCcw, Save, Trash2, X } from "lucide-react";
import type { SubtitleMeta, SubtitleSegment } from "../../types/project";

interface SubtitleEditorProps {
  segments: SubtitleSegment[];
  subtitleMeta: SubtitleMeta | null;
  loading: boolean;
  saving: boolean;
  onReload: () => void;
  onSave: () => void;
  onChange: (next: SubtitleSegment[]) => void;
}

const pad2 = (n: number) => String(n).padStart(2, "0");
const pad3 = (n: number) => String(n).padStart(3, "0");

const formatTime = (seconds: number) => {
  const s = Math.max(0, Number.isFinite(seconds) ? seconds : 0);
  const totalMs = Math.round(s * 1000);
  const ms = totalMs % 1000;
  const totalSec = Math.floor(totalMs / 1000);
  const sec = totalSec % 60;
  const totalMin = Math.floor(totalSec / 60);
  const min = totalMin % 60;
  const hour = Math.floor(totalMin / 60);
  return `${pad2(hour)}:${pad2(min)}:${pad2(sec)}.${pad3(ms)}`;
};

const buildBadge = (text: string, className: string) => (
  <span className={`text-xs px-2.5 py-1 font-medium rounded-full border ${className}`}>
    {text}
  </span>
);

const SubtitleEditor: React.FC<SubtitleEditorProps> = ({
  segments,
  subtitleMeta,
  loading,
  saving,
  onReload,
  onSave,
  onChange,
}) => {
  const canSave = segments.length > 0 && !saving && !loading;
  const [isModalOpen, setIsModalOpen] = useState(false);

  const totalDuration = segments.length > 0 ? formatTime(segments[segments.length - 1].end_time) : "00:00:00.000";

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 flex-wrap">
          <h2 className="text-lg font-semibold text-gray-900">字幕（可编辑）</h2>
          {subtitleMeta?.source === "user"
            ? buildBadge("已上传", "bg-green-50 text-green-700 border-green-100")
            : subtitleMeta?.source === "extracted"
              ? buildBadge("已提取", "bg-violet-50 text-violet-700 border-violet-100")
              : null}
          {subtitleMeta?.status === "extracting"
            ? buildBadge("提取中", "bg-blue-50 text-blue-700 border-blue-100")
            : subtitleMeta?.status === "failed"
              ? buildBadge("失败", "bg-red-50 text-red-700 border-red-100")
              : subtitleMeta?.status === "ready"
                ? buildBadge("就绪", "bg-gray-50 text-gray-700 border-gray-200")
                : null}
          {subtitleMeta?.updated_by_user ? buildBadge("已编辑", "bg-amber-50 text-amber-700 border-amber-100") : null}
        </div>
      </div>

      <p className="text-sm text-gray-600">点击下方区域可编辑字幕内容。</p>

      <div className="relative group cursor-pointer" onClick={() => setIsModalOpen(true)}>
        <div className="w-full h-10 px-4 py-2 font-mono text-sm border border-gray-300 rounded-lg bg-gray-50 overflow-hidden text-gray-700 hover:border-violet-400 hover:ring-1 hover:ring-violet-400 transition-all flex items-center justify-between">
          {segments.length === 0 ? (
            <span className="text-gray-400">暂无字幕内容，请先提取字幕或上传字幕。</span>
          ) : (
            <>
              <span>共 {segments.length} 条字幕</span>
              <span className="text-gray-500 text-xs">总时长: {totalDuration}</span>
            </>
          )}
        </div>
        <div className="absolute inset-0 bg-black bg-opacity-0 group-hover:bg-opacity-5 flex items-center justify-center transition-all rounded-lg pointer-events-none">
          <div className="opacity-0 group-hover:opacity-100 bg-white shadow-sm border border-gray-200 px-3 py-1.5 rounded-full text-sm font-medium text-gray-700 flex items-center">
            <Edit3 className="w-3 h-3 mr-1.5" />
            点击编辑
          </div>
        </div>
        {segments.length > 0 && (
          <div className="absolute top-2 right-2 bg-gray-100 px-2 py-1 rounded text-xs text-gray-600 hidden group-hover:block">
            点击展开
          </div>
        )}
      </div>

      {isModalOpen ? (
        <div className="fixed inset-0 z-50 overflow-y-auto">
          <div className="fixed inset-0 bg-black bg-opacity-50 transition-opacity" onClick={() => setIsModalOpen(false)} />
          <div className="flex items-center justify-center min-h-screen p-4">
            <div className="relative bg-white rounded-lg shadow-xl max-w-4xl w-full flex flex-col max-h-[90vh]">
              <div className="flex items-center justify-between p-6 border-b border-gray-200">
                <div className="flex items-center gap-2 flex-wrap">
                  <h3 className="text-xl font-semibold text-gray-900">编辑字幕</h3>
                  {segments.length > 0 && (
                    <div className="text-sm text-gray-500 bg-gray-100 px-2 py-1 rounded">
                      共 {segments.length} 条字幕 | 总时长: {totalDuration}
                    </div>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={onReload}
                    disabled={loading || saving}
                    className="flex items-center px-3 py-2 text-gray-700 rounded-lg hover:bg-gray-100 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {loading ? (
                      <>
                        <Loader className="h-4 w-4 mr-2 animate-spin" />
                        加载中...
                      </>
                    ) : (
                      <>
                        <RefreshCcw className="h-4 w-4 mr-2" />
                        重新加载
                      </>
                    )}
                  </button>
                  <button
                    onClick={onSave}
                    disabled={!canSave}
                    className="flex items-center px-3 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {saving ? (
                      <>
                        <Loader className="h-4 w-4 mr-2 animate-spin" />
                        保存中...
                      </>
                    ) : (
                      <>
                        <Save className="h-4 w-4 mr-2" />
                        保存
                      </>
                    )}
                  </button>
                  <button
                    onClick={() => setIsModalOpen(false)}
                    className="text-gray-400 hover:text-gray-600 transition-colors p-1 rounded"
                    aria-label="关闭"
                  >
                    <X className="h-5 w-5" />
                  </button>
                </div>
              </div>
              <div className="p-6 flex-1 overflow-y-auto">
                {segments.length === 0 ? (
                  <div className="text-sm text-gray-600">暂无字幕内容，请先提取字幕或上传字幕。</div>
                ) : (
                  <div className="border border-gray-200 rounded-lg overflow-hidden">
                    <div className="max-h-[60vh] overflow-auto">
                      <div className="divide-y divide-gray-100">
                        {segments.map((seg, idx) => (
                          <div key={seg.id || `${idx}`} className="p-3">
                            <div className="flex items-center justify-between gap-2">
                              <div className="text-xs text-gray-500">
                                <span className="font-mono">{formatTime(seg.start_time)}</span>
                                <span className="mx-1">-</span>
                                <span className="font-mono">{formatTime(seg.end_time)}</span>
                              </div>
                              <div className="flex items-center gap-2">
                                <span className="text-xs text-gray-400">#{idx + 1}</span>
                                <button
                                  type="button"
                                  onClick={() => {
                                    const next = segments.filter((_, i) => i !== idx);
                                    onChange(next);
                                  }}
                                  className="px-2 py-1 text-xs text-red-600 hover:bg-red-50 rounded border border-red-100"
                                  title="删除该字幕"
                                >
                                  <Trash2 className="h-3 w-3" />
                                </button>
                              </div>
                            </div>
                            <textarea
                              value={seg.text || ""}
                              onChange={(e) => {
                                const next = segments.map((s, i) => (i === idx ? { ...s, text: e.target.value } : s));
                                onChange(next);
                              }}
                              className="mt-2 w-full min-h-[54px] border border-gray-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-violet-500 focus:border-transparent outline-none"
                            />
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
};

export default SubtitleEditor;

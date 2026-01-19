import React from "react";
import { Loader, RefreshCcw, Save, Trash2 } from "lucide-react";
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

  return (
    <div className="bg-white rounded-lg shadow-md p-6 space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
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

        <div className="flex items-center gap-2">
          <button
            onClick={onReload}
            disabled={loading || saving}
            className="flex items-center py-2  text-gray-700 rounded-lg hover:bg-gray-200 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? (
              <>
                <Loader className="h-4 w-4 mr-2 animate-spin" />
                加载中...
              </>
            ) : (
              <>
                <RefreshCcw className="h-4 w-4 ml-2 mr-2" />
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
                <Save className="h-4 w-4" />
              </>
            )}
          </button>
        </div>
      </div>

      {segments.length === 0 ? (
        <div className="text-sm text-gray-600">
          暂无字幕内容，请先提取字幕或上传字幕。
        </div>
      ) : (
        <div className="border border-gray-200 rounded-lg overflow-hidden">
          <div className="max-h-[360px] overflow-auto">
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
  );
};

export default SubtitleEditor;

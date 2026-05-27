import { Check, ChevronDown, ChevronUp, Loader, Search, X } from "lucide-react";
import React from "react";
import type { OmniSelectableShot, OmniShotOptionsSegment } from "../../../types/omniMultimodal";
import type { ScriptSegment } from "../../../types/project";
import { durationLabel, scoreText, secondsToTime, visualText } from "./omniScriptWorkspaceUtils";

export interface ShotPickerModalProps {
  isOpen: boolean;
  videoUrl: string;
  segment: ScriptSegment;
  segmentIndex: number;
  options?: OmniShotOptionsSegment;
  loading: boolean;
  error: string | null;
  onClose: () => void;
  onApply: (shot: OmniSelectableShot) => void;
}

const ShotPickerModal: React.FC<ShotPickerModalProps> = ({
  isOpen,
  videoUrl,
  segment,
  segmentIndex,
  options,
  loading,
  error,
  onClose,
  onApply,
}) => {
  const videoRef = React.useRef<HTMLVideoElement>(null);
  const [query, setQuery] = React.useState("");
  const [previewShot, setPreviewShot] = React.useState<OmniSelectableShot | null>(null);
  const [preferredExpanded, setPreferredExpanded] = React.useState(true);

  const preferred = options?.preferred_shots ?? [];
  const other = options?.other_shots ?? [];

  React.useEffect(() => {
    if (!isOpen) return;
    setQuery("");
    setPreviewShot(preferred[0] ?? other[0] ?? null);
  }, [isOpen, options?.segment_id]);

  React.useEffect(() => {
    if (!isOpen || !previewShot || !videoRef.current) return;
    const video = videoRef.current;
    video.currentTime = Math.max(0, previewShot.start);
    video.play().catch(() => undefined);
  }, [isOpen, previewShot]);

  React.useEffect(() => {
    if (!isOpen || !previewShot || !videoRef.current) return undefined;
    const video = videoRef.current;
    const onTimeUpdate = () => {
      if (video.currentTime >= previewShot.end) {
        video.pause();
      }
    };
    video.addEventListener("timeupdate", onTimeUpdate);
    return () => video.removeEventListener("timeupdate", onTimeUpdate);
  }, [isOpen, previewShot]);

  const filterShot = React.useCallback(
    (shot: OmniSelectableShot) => {
      const q = query.trim().toLowerCase();
      if (!q) return true;
      const haystack = [
        String(shot.shot_id ?? ""),
        shot.subtitle_full_text,
        shot.summary,
        shot.reason,
        shot.visual?.brief,
        shot.visual?.desc,
        shot.visual?.action,
        shot.visual?.emotion,
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return haystack.includes(q);
    },
    [query]
  );

  const renderShot = (shot: OmniSelectableShot, rank?: number) => {
    const active = previewShot?.shot_id === shot.shot_id;
    const applied = segment.shot_id != null && String(segment.shot_id) === String(shot.shot_id);
    const detailClamp = active ? "" : "line-clamp-2";
    return (
      <button
        key={`${shot.option_source}-${shot.shot_id}-${shot.start}`}
        type="button"
        onClick={() => setPreviewShot(shot)}
        className={`w-full text-left border rounded-lg p-3 transition-colors ${
          active
            ? "border-blue-500 bg-blue-50 ring-1 ring-blue-400/50 dark:border-blue-400 dark:bg-blue-950/60 dark:ring-blue-500/40"
            : "border-gray-200 hover:border-gray-300 hover:bg-gray-50 dark:border-gray-600 dark:hover:border-gray-500 dark:hover:bg-gray-800/60"
        }`}
      >
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2 text-sm font-medium text-gray-900 dark:text-gray-100">
              <span>{rank ? `#${rank}` : `shot ${shot.shot_id}`}</span>
              <span className="font-mono text-xs text-gray-500 dark:text-gray-400">
                {secondsToTime(shot.start)} - {secondsToTime(shot.end)}
              </span>
            </div>
            <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
              分数：{scoreText(shot)} · 时长：{durationLabel(shot.start, shot.end)}
            </div>
          </div>
          {applied ? (
            <span className="shrink-0 text-xs text-green-700 bg-green-50 dark:text-green-300 dark:bg-green-900/40 px-2 py-1 rounded">
              已应用
            </span>
          ) : null}
        </div>
        {shot.subtitle_full_text ? (
          <p className={`mt-2 text-xs text-gray-700 dark:text-gray-300 whitespace-pre-wrap break-words ${detailClamp}`}>
            字幕：{shot.subtitle_full_text}
          </p>
        ) : null}
        {visualText(shot) ? (
          <p className={`mt-1 text-xs text-gray-600 dark:text-gray-400 whitespace-pre-wrap break-words ${detailClamp}`}>
            视觉：{visualText(shot)}
          </p>
        ) : null}
        {shot.reason ? (
          <p className={`mt-1 text-xs text-gray-500 dark:text-gray-400 whitespace-pre-wrap break-words ${detailClamp}`}>
            原因：{shot.reason}
          </p>
        ) : null}
      </button>
    );
  };

  if (!isOpen) return null;

  const isApplied = React.useCallback(
    (shot: OmniSelectableShot) =>
      segment.shot_id != null && String(segment.shot_id) === String(shot.shot_id),
    [segment.shot_id]
  );

  const sortAppliedFirst = React.useCallback(
    (a: OmniSelectableShot, b: OmniSelectableShot) => {
      const aApplied = isApplied(a) ? 1 : 0;
      const bApplied = isApplied(b) ? 1 : 0;
      return bApplied - aApplied;
    },
    [isApplied]
  );

  const filteredPreferred = preferred.filter(filterShot).sort(sortAppliedFirst);
  const filteredOther = other.filter(filterShot).sort(sortAppliedFirst);

  return (
    <div className="fixed inset-0 z-[70] bg-black/60 flex items-center justify-center p-4" onClick={onClose}>
      <div
        className="bg-white dark:bg-gray-900 rounded-lg shadow-2xl w-full max-w-6xl max-h-[90vh] overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="px-5 py-4 border-b border-gray-200 dark:border-gray-700 flex items-start justify-between gap-4">
          <div className="min-w-0">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">选择镜头 · 第 {segmentIndex + 1} 条</h3>
            <p className="mt-1 text-sm text-gray-600 dark:text-gray-400">
              {secondsToTime(segment.start_time)} - {secondsToTime(segment.end_time)} ·{" "}
              {durationLabel(segment.start_time, segment.end_time)}
              {segment.shot_id != null ? ` · 当前 shot ${segment.shot_id}` : " · 未标记镜头"}
            </p>
            <p className="mt-2 text-sm text-gray-800 dark:text-gray-200 line-clamp-2">{segment.text || "无文本"}</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-2 rounded hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-500 dark:text-gray-400"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_420px] gap-0 h-[calc(90vh-112px)]">
          <div className="p-5 border-r border-gray-200 dark:border-gray-700 overflow-y-auto min-h-0">
            <div className="aspect-video bg-black rounded-lg overflow-hidden">
              {videoUrl ? (
                <video ref={videoRef} src={videoUrl} controls className="w-full h-full object-contain" />
              ) : (
                <div className="h-full flex items-center justify-center text-sm text-gray-300">暂无可预览视频</div>
              )}
            </div>
            <div className="mt-4 flex items-center justify-between gap-3">
              <div className="text-sm text-gray-700 dark:text-gray-300">
                {previewShot ? (
                  <>
                    <span className="font-medium">预览 shot {previewShot.shot_id}</span>
                    <span className="ml-2 font-mono text-xs text-gray-500 dark:text-gray-400">
                      {secondsToTime(previewShot.start)} - {secondsToTime(previewShot.end)}
                    </span>
                  </>
                ) : (
                  "请选择一个候选镜头"
                )}
              </div>
              <button
                type="button"
                disabled={!previewShot}
                onClick={() => previewShot && onApply(previewShot)}
                className="inline-flex items-center px-3 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <Check className="h-4 w-4 mr-2" />
                使用此镜头
              </button>
            </div>
          </div>

          <div className="p-5 overflow-y-auto min-h-0">
            <div className="relative mb-4">
              <Search className="absolute left-3 top-2.5 h-4 w-4 text-gray-400" />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="搜索 shot_id、字幕、摘要"
                className="w-full pl-9 pr-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-800 focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none"
              />
            </div>

            {loading ? (
              <div className="py-12 text-center text-sm text-gray-500 dark:text-gray-400">
                <Loader className="h-5 w-5 mx-auto mb-2 animate-spin" />
                正在加载候选镜头...
              </div>
            ) : error ? (
              <div className="p-4 bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-800 rounded-lg text-sm text-red-700 dark:text-red-300">
                {error}
              </div>
            ) : (
              <div className="space-y-5">
                <section>
                  <button
                    type="button"
                    onClick={() => setPreferredExpanded((v) => !v)}
                    className="w-full flex items-center justify-between gap-2 mb-2 text-left rounded hover:bg-gray-50 dark:hover:bg-gray-800/60 -mx-1 px-1 py-0.5 transition-colors"
                    aria-expanded={preferredExpanded}
                  >
                    <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100">推荐镜头</h4>
                    <span className="shrink-0 text-gray-400 dark:text-gray-500" title={preferredExpanded ? "折叠" : "展开"}>
                      {preferredExpanded ? (
                        <ChevronUp className="h-4 w-4" />
                      ) : (
                        <ChevronDown className="h-4 w-4" />
                      )}
                    </span>
                  </button>
                  {preferredExpanded ? (
                    <div className="space-y-2">
                      {filteredPreferred.length ? (
                        filteredPreferred.map((shot, index) => renderShot(shot, index + 1))
                      ) : (
                        <div className="text-sm text-gray-500 dark:text-gray-400 border border-dashed border-gray-200 dark:border-gray-600 rounded-lg p-4">
                          暂无推荐镜头
                        </div>
                      )}
                    </div>
                  ) : null}
                </section>
                <section>
                  <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-2">其它镜头</h4>
                  <div className="space-y-2">
                    {filteredOther.length ? (
                      filteredOther.map((shot) => renderShot(shot))
                    ) : (
                      <div className="text-sm text-gray-500 dark:text-gray-400 border border-dashed border-gray-200 dark:border-gray-600 rounded-lg p-4">
                        暂无其它镜头，请先完成 Omni 多模态管线
                      </div>
                    )}
                  </div>
                </section>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default ShotPickerModal;

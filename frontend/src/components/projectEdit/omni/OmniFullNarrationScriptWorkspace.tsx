import { Check, Clock, Loader, Play, Save, Search, X } from "lucide-react";
import React from "react";
import { projectService } from "../../../services/projectService";
import type { OmniSelectableShot, OmniShotOptionsResponse, OmniShotOptionsSegment } from "../../../types/omniMultimodal";
import type { Project, ScriptSegment, VideoScript } from "../../../types/project";
import { formatMs } from "../../../utils/timecode";

export interface OmniFullNarrationScriptWorkspaceProps {
  project: Project;
  editedScript: string;
  setEditedScript: (script: string) => void;
  isSaving: boolean;
  onSave: () => void;
}

const secondsToTime = (seconds: number) => formatMs(Math.max(0, seconds || 0) * 1000);

const durationLabel = (start?: number, end?: number) => {
  const value = Math.max(0, Number(end || 0) - Number(start || 0));
  return `${value.toFixed(2)}s`;
};

const isOriginalAudio = (segment: ScriptSegment) => {
  const raw = segment.OST;
  if (typeof raw === "boolean") return raw;
  return String(raw ?? "").trim() === "1";
};

const ttsStatusLabel = (segment: ScriptSegment) => {
  if (isOriginalAudio(segment)) return "原片声音";
  if (!segment.tts_audio_path) return "未配音";
  if (segment.tts_source === "manual") return "单条配音";
  if (segment.tts_source === "bulk") return "批量配音";
  return "已配音";
};

const visualText = (shot?: OmniSelectableShot | null) => {
  if (!shot) return "";
  const parts = [
    shot.summary,
    shot.visual?.brief,
    shot.visual?.desc,
    shot.visual?.action,
    shot.visual?.emotion,
  ].filter(Boolean);
  return parts.join(" / ");
};

const scoreText = (shot: OmniSelectableShot) => {
  const score = shot.final_score ?? shot.score;
  return typeof score === "number" ? score.toFixed(4) : "-";
};

const makeScriptJson = (script: VideoScript) => JSON.stringify(script, null, 2);
const PLAYBACK_RATES = [0.5, 0.75, 1, 1.25, 1.5, 2];

interface ShotPickerModalProps {
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
    return (
      <button
        key={`${shot.option_source}-${shot.shot_id}-${shot.start}`}
        type="button"
        onClick={() => setPreviewShot(shot)}
        className={`w-full text-left border rounded-lg p-3 transition-colors ${
          active ? "border-blue-500 bg-blue-50" : "border-gray-200 hover:border-gray-300 hover:bg-gray-50"
        }`}
      >
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2 text-sm font-medium text-gray-900">
              <span>{rank ? `#${rank}` : `shot ${shot.shot_id}`}</span>
              <span className="font-mono text-xs text-gray-500">
                {secondsToTime(shot.start)} - {secondsToTime(shot.end)}
              </span>
            </div>
            <div className="mt-1 text-xs text-gray-500">分数：{scoreText(shot)} · 时长：{durationLabel(shot.start, shot.end)}</div>
          </div>
          {applied ? <span className="shrink-0 text-xs text-green-700 bg-green-50 px-2 py-1 rounded">已应用</span> : null}
        </div>
        {shot.subtitle_full_text ? <p className="mt-2 text-xs text-gray-700 line-clamp-2">字幕：{shot.subtitle_full_text}</p> : null}
        {visualText(shot) ? <p className="mt-1 text-xs text-gray-600 line-clamp-2">视觉：{visualText(shot)}</p> : null}
        {shot.reason ? <p className="mt-1 text-xs text-gray-500 line-clamp-2">原因：{shot.reason}</p> : null}
      </button>
    );
  };

  if (!isOpen) return null;

  const filteredPreferred = preferred.filter(filterShot);
  const filteredOther = other.filter(filterShot);

  return (
    <div className="fixed inset-0 z-[70] bg-black/60 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white rounded-lg shadow-2xl w-full max-w-6xl max-h-[90vh] overflow-hidden" onClick={(e) => e.stopPropagation()}>
        <div className="px-5 py-4 border-b border-gray-200 flex items-start justify-between gap-4">
          <div className="min-w-0">
            <h3 className="text-lg font-semibold text-gray-900">选择镜头 · 第 {segmentIndex + 1} 条</h3>
            <p className="mt-1 text-sm text-gray-600">
              {secondsToTime(segment.start_time)} - {secondsToTime(segment.end_time)} · {durationLabel(segment.start_time, segment.end_time)}
              {segment.shot_id != null ? ` · 当前 shot ${segment.shot_id}` : " · 未标记镜头"}
            </p>
            <p className="mt-2 text-sm text-gray-800 line-clamp-2">{segment.text || "无文本"}</p>
          </div>
          <button type="button" onClick={onClose} className="p-2 rounded hover:bg-gray-100 text-gray-500">
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_420px] gap-0 h-[calc(90vh-112px)]">
          <div className="p-5 border-r border-gray-200 overflow-y-auto min-h-0">
            <div className="aspect-video bg-black rounded-lg overflow-hidden">
              {videoUrl ? (
                <video ref={videoRef} src={videoUrl} controls className="w-full h-full object-contain" />
              ) : (
                <div className="h-full flex items-center justify-center text-sm text-gray-300">暂无可预览视频</div>
              )}
            </div>
            <div className="mt-4 flex items-center justify-between gap-3">
              <div className="text-sm text-gray-700">
                {previewShot ? (
                  <>
                    <span className="font-medium">预览 shot {previewShot.shot_id}</span>
                    <span className="ml-2 font-mono text-xs text-gray-500">
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
                className="w-full pl-9 pr-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none"
              />
            </div>

            {loading ? (
              <div className="py-12 text-center text-sm text-gray-500">
                <Loader className="h-5 w-5 mx-auto mb-2 animate-spin" />
                正在加载候选镜头...
              </div>
            ) : error ? (
              <div className="p-4 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">{error}</div>
            ) : (
              <div className="space-y-5">
                <section>
                  <h4 className="text-sm font-semibold text-gray-900 mb-2">推荐镜头</h4>
                  <div className="space-y-2">
                    {filteredPreferred.length ? filteredPreferred.map((shot, index) => renderShot(shot, index + 1)) : (
                      <div className="text-sm text-gray-500 border border-dashed border-gray-200 rounded-lg p-4">暂无推荐镜头</div>
                    )}
                  </div>
                </section>
                <section>
                  <h4 className="text-sm font-semibold text-gray-900 mb-2">其它镜头</h4>
                  <div className="space-y-2">
                    {filteredOther.length ? filteredOther.map((shot) => renderShot(shot)) : (
                      <div className="text-sm text-gray-500 border border-dashed border-gray-200 rounded-lg p-4">暂无其它镜头，请先完成 Omni 多模态管线</div>
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

const OmniFullNarrationScriptWorkspace: React.FC<OmniFullNarrationScriptWorkspaceProps> = ({
  project,
  editedScript,
  setEditedScript,
  isSaving,
  onSave,
}) => {
  const videoRef = React.useRef<HTMLVideoElement>(null);
  const scriptListRef = React.useRef<HTMLDivElement>(null);
  const scriptRowRefs = React.useRef<Array<HTMLDivElement | null>>([]);
  const [selectedIndex, setSelectedIndex] = React.useState(0);
  const [pickerIndex, setPickerIndex] = React.useState<number | null>(null);
  const [shotOptions, setShotOptions] = React.useState<OmniShotOptionsResponse | null>(null);
  const [shotOptionsLoading, setShotOptionsLoading] = React.useState(false);
  const [shotOptionsError, setShotOptionsError] = React.useState<string | null>(null);
  const [isSequencePlaying, setIsSequencePlaying] = React.useState(false);
  const [playbackRate, setPlaybackRate] = React.useState(1);

  const parsed = React.useMemo(() => {
    if (!editedScript.trim()) return { script: null as VideoScript | null, error: null as string | null };
    try {
      const data = JSON.parse(editedScript) as VideoScript;
      if (!data || !Array.isArray(data.segments)) {
        return { script: null, error: "脚本 JSON 必须包含 segments 数组" };
      }
      return { script: data, error: null };
    } catch (e) {
      return { script: null, error: e instanceof Error ? e.message : "JSON 解析失败" };
    }
  }, [editedScript]);

  const script = parsed.script;
  const segments = script?.segments ?? [];
  const hasParsedScript = Boolean(script);
  const selectedSegment = segments[selectedIndex] ?? segments[0];
  const videoUrl = project.merged_video_path
    ? projectService.getMergedVideoUrl(project.id)
    : project.video_path
      ? projectService.getVideoStreamUrl(project.id)
      : "";

  React.useEffect(() => {
    if (selectedIndex >= segments.length) {
      setSelectedIndex(Math.max(0, segments.length - 1));
    }
  }, [selectedIndex, segments.length]);

  React.useEffect(() => {
    scriptRowRefs.current = scriptRowRefs.current.slice(0, segments.length);
  }, [segments.length]);

  React.useEffect(() => {
    const container = scriptListRef.current;
    const row = scriptRowRefs.current[selectedIndex];
    if (!container || !row) return;

    const containerRect = container.getBoundingClientRect();
    const rowRect = row.getBoundingClientRect();
    const relativeTop = rowRect.top - containerRect.top;
    const relativeBottom = rowRect.bottom - containerRect.top;
    const viewHeight = container.clientHeight;
    const margin = 8;

    if (relativeTop >= margin && relativeBottom <= viewHeight - margin) return;

    let nextScrollTop: number;
    if (rowRect.height + margin * 2 > viewHeight || relativeTop < margin) {
      nextScrollTop = container.scrollTop + relativeTop - margin;
    } else {
      nextScrollTop = container.scrollTop + relativeBottom - viewHeight + margin;
    }

    container.scrollTo({
      top: Math.max(0, nextScrollTop),
      behavior: isSequencePlaying ? "smooth" : "auto",
    });
  }, [isSequencePlaying, selectedIndex]);

  React.useEffect(() => {
    if (!segments.length && isSequencePlaying) {
      setIsSequencePlaying(false);
    }
  }, [isSequencePlaying, segments.length]);

  React.useEffect(() => {
    if (!project.id || !hasParsedScript) return;
    let cancelled = false;
    setShotOptionsLoading(true);
    setShotOptionsError(null);
    projectService
      .getOmniShotOptions(project.id)
      .then((data) => {
        if (!cancelled) setShotOptions(data);
      })
      .catch((e) => {
        if (!cancelled) setShotOptionsError(e instanceof Error ? e.message : "候选镜头加载失败");
      })
      .finally(() => {
        if (!cancelled) setShotOptionsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [project.id, hasParsedScript]);

  React.useEffect(() => {
    if (!selectedSegment || !videoRef.current) return;
    const video = videoRef.current;
    video.currentTime = Math.max(0, selectedSegment.start_time || 0);
  }, [selectedSegment?.id, selectedSegment?.start_time]);

  React.useEffect(() => {
    if (!videoRef.current) return;
    videoRef.current.playbackRate = playbackRate;
  }, [playbackRate, videoUrl]);

  React.useEffect(() => {
    if (!selectedSegment || !videoRef.current) return undefined;
    const video = videoRef.current;
    const endEpsilon = 0.04;
    const onTimeUpdate = () => {
      if (video.currentTime < selectedSegment.end_time - endEpsilon) return;
      if (isSequencePlaying) {
        const nextIndex = selectedIndex + 1;
        const nextSegment = segments[nextIndex];
        if (nextSegment) {
          setSelectedIndex(nextIndex);
          video.currentTime = Math.max(0, nextSegment.start_time || 0);
          video.playbackRate = playbackRate;
          video.play().catch(() => undefined);
          return;
        }
        setIsSequencePlaying(false);
      }
      video.pause();
    };
    const onPlay = () => {
      if (video.currentTime < selectedSegment.start_time || video.currentTime >= selectedSegment.end_time) {
        video.currentTime = Math.max(0, selectedSegment.start_time || 0);
      }
      video.playbackRate = playbackRate;
    };
    const onPause = () => {
      if (video.currentTime < selectedSegment.end_time - endEpsilon) {
        setIsSequencePlaying(false);
      }
    };
    video.addEventListener("timeupdate", onTimeUpdate);
    video.addEventListener("play", onPlay);
    video.addEventListener("pause", onPause);
    return () => {
      video.removeEventListener("timeupdate", onTimeUpdate);
      video.removeEventListener("play", onPlay);
      video.removeEventListener("pause", onPause);
    };
  }, [isSequencePlaying, playbackRate, segments, selectedIndex, selectedSegment]);

  const optionsBySegmentId = React.useMemo(() => {
    const map = new Map<string, OmniShotOptionsSegment>();
    for (const item of shotOptions?.segments ?? []) {
      map.set(String(item.segment_id), item);
    }
    return map;
  }, [shotOptions]);

  const setScriptSegment = React.useCallback(
    (index: number, updater: (segment: ScriptSegment) => ScriptSegment) => {
      if (!script) return;
      const next: VideoScript = {
        ...script,
        segments: script.segments.map((segment, i) => (i === index ? updater({ ...segment }) : segment)),
        metadata: {
          ...(script.metadata ?? {}),
          updated_at: new Date().toISOString(),
        },
      };
      setEditedScript(makeScriptJson(next));
    },
    [script, setEditedScript]
  );

  const playSegment = React.useCallback(
    (index: number) => {
      setIsSequencePlaying(false);
      setSelectedIndex(index);
      const segment = segments[index];
      if (!segment || !videoRef.current) return;
      const video = videoRef.current;
      video.currentTime = Math.max(0, segment.start_time || 0);
      video.playbackRate = playbackRate;
      video.play().catch(() => undefined);
    },
    [playbackRate, segments]
  );

  const toggleSequencePlayback = React.useCallback(() => {
    const video = videoRef.current;
    const startSegment = segments[selectedIndex];
    if (!video || !startSegment) return;
    if (isSequencePlaying) {
      setIsSequencePlaying(false);
      video.pause();
      return;
    }
    setIsSequencePlaying(true);
    video.playbackRate = playbackRate;
    if (video.currentTime < startSegment.start_time || video.currentTime >= startSegment.end_time) {
      video.currentTime = Math.max(0, startSegment.start_time || 0);
    }
    video.play().catch(() => {
      setIsSequencePlaying(false);
    });
  }, [isSequencePlaying, playbackRate, selectedIndex, segments]);

  const applyShot = React.useCallback(
    (shot: OmniSelectableShot) => {
      if (pickerIndex == null) return;
      setScriptSegment(pickerIndex, (segment) => ({
        ...segment,
        start_time: shot.start,
        end_time: shot.end,
        shot_id: shot.shot_id,
        shot_source: "manual",
      }));
      setSelectedIndex(pickerIndex);
      setPickerIndex(null);
    },
    [pickerIndex, setScriptSegment]
  );

  if (!script || parsed.error) {
    return (
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-gray-900">Omni 解说脚本（JSON）</h2>
          <button
            type="button"
            onClick={onSave}
            disabled={!editedScript.trim() || isSaving}
            className="flex items-center px-3 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isSaving ? <Loader className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
          </button>
        </div>
        {parsed.error ? <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">JSON 解析失败：{parsed.error}</div> : null}
        <textarea
          value={editedScript}
          onChange={(e) => setEditedScript(e.target.value)}
          placeholder="脚本数据将以 JSON 格式显示在这里..."
          className="w-full h-[600px] px-4 py-3 font-mono text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-violet-500 focus:border-transparent outline-none transition-all resize-none"
        />
      </div>
    );
  }

  const pickerSegment = pickerIndex == null ? null : segments[pickerIndex];
  const pickerOptions = pickerSegment
    ? optionsBySegmentId.get(String(pickerSegment.id ?? pickerIndex + 1))
    : undefined;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-gray-900">Omni 镜头校对工作区</h2>
          <p className="text-sm text-gray-600">选择镜头会更新当前条目的时间段和 shot_id，仍需点击保存持久化。</p>
        </div>
        <button
          type="button"
          onClick={onSave}
          disabled={!editedScript.trim() || isSaving}
          className="flex items-center px-3 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {isSaving ? (
            <>
              <Loader className="h-4 w-4 mr-2 animate-spin" />
              保存中...
            </>
          ) : (
            <>
              <Save className="h-4 w-4 mr-2" />
              保存脚本
            </>
          )}
        </button>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-[420px_minmax(0,1fr)] gap-5">
        <aside className="space-y-4">
          <div className="aspect-video bg-black rounded-lg overflow-hidden">
            {videoUrl ? (
              <video ref={videoRef} src={videoUrl} controls className="w-full h-full object-contain" />
            ) : (
              <div className="h-full flex items-center justify-center text-sm text-gray-300">暂无可预览视频</div>
            )}
          </div>
          {selectedSegment ? (
            <div className="rounded-lg bg-gray-900/95 px-4 py-3 min-h-[56px] flex items-center justify-center text-center">
              {selectedSegment.text ? (
                <p className="text-base text-white leading-relaxed whitespace-pre-wrap break-words">
                  {selectedSegment.text}
                </p>
              ) : (
                <span className="text-sm text-gray-400">
                  {isOriginalAudio(selectedSegment) ? "原片声音段，无解说文案" : "暂无解说文案"}
                </span>
              )}
            </div>
          ) : null}
          {selectedSegment ? (
            <div className="border border-gray-200 rounded-lg p-4 space-y-3">
              <div className="flex items-center justify-between text-sm">
                <span className="font-medium text-gray-900">第 {selectedIndex + 1} 条片段</span>
                <span className="font-mono text-xs text-gray-500">{durationLabel(selectedSegment.start_time, selectedSegment.end_time)}</span>
              </div>
              <div className="flex items-center text-sm text-gray-700">
                <Clock className="h-4 w-4 mr-2 text-gray-400" />
                <span className="font-mono">
                  {secondsToTime(selectedSegment.start_time)} - {secondsToTime(selectedSegment.end_time)}
                </span>
              </div>
              <div className="grid grid-cols-2 gap-2 text-xs text-gray-600">
                <div className="bg-gray-50 rounded p-2">镜头：{selectedSegment.shot_id ?? "未标记"}</div>
                <div className="bg-gray-50 rounded p-2">配音：{ttsStatusLabel(selectedSegment)}</div>
              </div>
              <div className="flex flex-wrap items-center gap-2 pt-1">
                <button
                  type="button"
                  onClick={toggleSequencePlayback}
                  disabled={!videoUrl || !segments.length}
                  className={`inline-flex items-center px-3 py-2 rounded-lg text-sm transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${
                    isSequencePlaying
                      ? "bg-red-600 text-white hover:bg-red-700"
                      : "bg-blue-600 text-white hover:bg-blue-700"
                  }`}
                >
                  <Play className="h-4 w-4 mr-2" />
                  {isSequencePlaying ? "停止连播" : "从当前镜头连播"}
                </button>
                <label className="inline-flex items-center gap-2 text-sm text-gray-700">
                  倍速
                  <select
                    value={playbackRate}
                    onChange={(e) => setPlaybackRate(Number(e.target.value) || 1)}
                    className="border border-gray-300 rounded-lg px-2 py-1.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none"
                  >
                    {PLAYBACK_RATES.map((rate) => (
                      <option key={rate} value={rate}>
                        {rate}x
                      </option>
                    ))}
                  </select>
                </label>
              </div>
            </div>
          ) : null}
        </aside>

        <section className="min-w-0">
          <div className="border border-gray-200 rounded-lg overflow-hidden">
            <div className="grid grid-cols-[64px_150px_88px_minmax(220px,1fr)_112px_164px] gap-0 bg-gray-50 px-3 py-2 text-xs font-medium text-gray-600">
              <span>序号</span>
              <span>时间段</span>
              <span>类型</span>
              <span>解说文本</span>
              <span>镜头</span>
              <span>操作</span>
            </div>
            <div ref={scriptListRef} className="divide-y divide-gray-100 max-h-[640px] overflow-y-auto">
              {segments.map((segment, index) => {
                const selected = index === selectedIndex;
                return (
                  <div
                    ref={(node) => {
                      scriptRowRefs.current[index] = node;
                    }}
                    key={`${segment.id ?? index}-${index}`}
                    role="button"
                    tabIndex={0}
                    onClick={() => playSegment(index)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") playSegment(index);
                    }}
                    className={`grid grid-cols-[64px_150px_88px_minmax(220px,1fr)_112px_164px] gap-0 px-3 py-3 items-start cursor-pointer ${
                      selected ? "bg-blue-50" : "hover:bg-gray-50"
                    }`}
                  >
                    <div className="text-sm font-medium text-gray-900">{index + 1}</div>
                    <div className="font-mono text-xs text-gray-600">
                      <div>{secondsToTime(segment.start_time)}</div>
                      <div>{secondsToTime(segment.end_time)}</div>
                    </div>
                    <div className="text-xs text-gray-700">{isOriginalAudio(segment) ? "原片声音" : "单独配音"}</div>
                    <div onClick={(e) => e.stopPropagation()}>
                      <textarea
                        value={segment.text || ""}
                        onChange={(e) => setScriptSegment(index, (s) => ({ ...s, text: e.target.value }))}
                        className="w-full min-h-[62px] resize-y border border-gray-200 rounded px-2 py-1 text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none"
                      />
                      <div className="mt-1 text-xs text-gray-500">配音：{ttsStatusLabel(segment)}</div>
                    </div>
                    <div className="text-xs text-gray-700 break-all">{segment.shot_id ?? "未标记"}</div>
                    <div className="flex flex-col gap-2" onClick={(e) => e.stopPropagation()}>
                      <button
                        type="button"
                        onClick={() => playSegment(index)}
                        className="inline-flex items-center justify-center px-2 py-1.5 border border-gray-300 rounded text-xs hover:bg-gray-50"
                      >
                        <Play className="h-3.5 w-3.5 mr-1" />
                        预览
                      </button>
                      <button
                        type="button"
                        onClick={() => setPickerIndex(index)}
                        disabled={shotOptionsLoading || Boolean(shotOptionsError)}
                        title={shotOptionsError || undefined}
                        className="inline-flex items-center justify-center px-2 py-1.5 bg-blue-600 text-white rounded text-xs hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        {shotOptionsLoading ? <Loader className="h-3.5 w-3.5 mr-1 animate-spin" /> : null}
                        选择镜头
                      </button>
                      {!isOriginalAudio(segment) ? (
                        <button
                          type="button"
                          disabled
                          className="inline-flex items-center justify-center px-2 py-1.5 border border-gray-200 text-gray-400 rounded text-xs cursor-not-allowed"
                          title="单条配音接口将在下一步接入"
                        >
                          单条配音
                        </button>
                      ) : null}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
          {shotOptionsError ? <p className="mt-2 text-sm text-red-600">候选镜头加载失败：{shotOptionsError}</p> : null}
        </section>
      </div>

      {pickerSegment ? (
        <ShotPickerModal
          isOpen={pickerIndex != null}
          videoUrl={videoUrl}
          segment={pickerSegment}
          segmentIndex={pickerIndex ?? 0}
          options={pickerOptions}
          loading={shotOptionsLoading}
          error={shotOptionsError}
          onClose={() => setPickerIndex(null)}
          onApply={applyShot}
        />
      ) : null}
    </div>
  );
};

export default OmniFullNarrationScriptWorkspace;

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { projectService } from "../../services/projectService";
import type { OmniSelectableShot, OmniShotOptionsResponse, OmniShotOptionsSegment } from "../../types/omniMultimodal";
import type { Project, ScriptSegment, VideoScript } from "../../types/project";
import {
  computeTtsTextHash,
  getEffectiveDuration,
  getOmniSegmentsTextSignature,
  getSegmentPlayEndTime,
  isOriginalAudio,
  isPlaybackOriginalLabel,
  isValidSegmentTts,
  clampSegmentTimes,
  makeScriptJson,
} from "../../components/projectEdit/omni/omniScriptWorkspaceUtils";

export interface UseOmniScriptWorkspaceOptions {
  project: Project;
  editedScript: string;
  setEditedScript: (script: string) => void;
  /** 脚本结构/文案变更后与服务端对齐（防抖） */
  syncScriptToServer?: (scriptOverride?: VideoScript) => Promise<VideoScript | null>;
  /** 单条配音队列进行中时暂停自动保存，避免与 TTS 写回争用 revision */
  segmentTtsQueueActive?: boolean;
  syncScriptDebounceMs?: number;
}

export function useOmniScriptWorkspace({
  project,
  editedScript,
  setEditedScript,
  syncScriptToServer,
  segmentTtsQueueActive = false,
  syncScriptDebounceMs = 500,
}: UseOmniScriptWorkspaceOptions) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const ttsAudioRef = useRef<HTMLAudioElement>(null);
  const scriptListRef = useRef<HTMLDivElement>(null);
  const scriptRowRefs = useRef<Array<HTMLDivElement | null>>([]);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [pickerIndex, setPickerIndex] = useState<number | null>(null);
  const [shotOptions, setShotOptions] = useState<OmniShotOptionsResponse | null>(null);
  const [shotOptionsLoading, setShotOptionsLoading] = useState(false);
  const [shotOptionsError, setShotOptionsError] = useState<string | null>(null);
  const [isSequencePlaying, setIsSequencePlaying] = useState(false);
  const [playbackRate, setPlaybackRate] = useState(1);
  const [textHashes, setTextHashes] = useState<Record<number, string>>({});
  const [videoDuration, setVideoDuration] = useState(0);
  const sequencePlayingRef = useRef(false);
  const segmentFinishedRef = useRef<number | null>(null);
  const syncScriptTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pendingSyncScriptRef = useRef<VideoScript | null>(null);

  const flushSyncScriptToServer = useCallback(
    (scriptOverride?: VideoScript) => {
      if (!syncScriptToServer) return;
      if (syncScriptTimerRef.current) {
        clearTimeout(syncScriptTimerRef.current);
        syncScriptTimerRef.current = null;
      }
      const toSync = scriptOverride ?? pendingSyncScriptRef.current;
      pendingSyncScriptRef.current = null;
      if (!toSync) return;
      void syncScriptToServer(toSync);
    },
    [syncScriptToServer]
  );

  const scheduleSyncScriptToServer = useCallback(
    (script: VideoScript) => {
      if (!syncScriptToServer || segmentTtsQueueActive) return;
      pendingSyncScriptRef.current = script;
      if (syncScriptTimerRef.current) clearTimeout(syncScriptTimerRef.current);
      syncScriptTimerRef.current = setTimeout(() => {
        syncScriptTimerRef.current = null;
        const toSync = pendingSyncScriptRef.current;
        pendingSyncScriptRef.current = null;
        if (!toSync) return;
        void syncScriptToServer(toSync);
      }, syncScriptDebounceMs);
    },
    [segmentTtsQueueActive, syncScriptDebounceMs, syncScriptToServer]
  );

  useEffect(
    () => () => {
      if (syncScriptTimerRef.current) clearTimeout(syncScriptTimerRef.current);
    },
    []
  );

  useEffect(() => {
    if (!segmentTtsQueueActive) return;
    if (syncScriptTimerRef.current) {
      clearTimeout(syncScriptTimerRef.current);
      syncScriptTimerRef.current = null;
    }
    pendingSyncScriptRef.current = null;
  }, [segmentTtsQueueActive]);

  const parsed = useMemo(() => {
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
  const segmentsTextSignature = useMemo(() => getOmniSegmentsTextSignature(segments), [segments]);
  const textHashByContentRef = useRef<Map<string, string>>(new Map());
  const hasParsedScript = Boolean(script);
  const selectedSegment = segments[selectedIndex] ?? segments[0];
  const videoUrl = project.merged_video_path
    ? projectService.getMergedVideoUrl(project.id)
    : project.video_path
      ? projectService.getVideoStreamUrl(project.id)
      : "";

  useEffect(() => {
    if (selectedIndex >= segments.length) {
      setSelectedIndex(Math.max(0, segments.length - 1));
    }
  }, [selectedIndex, segments.length]);

  useEffect(() => {
    scriptRowRefs.current = scriptRowRefs.current.slice(0, segments.length);
  }, [segments.length]);

  useEffect(() => {
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
      behavior: "auto",
    });
  }, [selectedIndex]);

  useEffect(() => {
    if (!segments.length && isSequencePlaying) {
      setIsSequencePlaying(false);
    }
  }, [isSequencePlaying, segments.length]);

  useEffect(() => {
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

  useEffect(() => {
    let cancelled = false;

    const rebuildFromCache = () => {
      const next: Record<number, string> = {};
      segments.forEach((seg, idx) => {
        if (isOriginalAudio(seg)) return;
        const h = textHashByContentRef.current.get((seg.text || "").trim());
        if (h) next[idx] = h;
      });
      return next;
    };

    segments.forEach((s) => {
      if (isOriginalAudio(s)) return;
      const text = (s.text || "").trim();
      if (textHashByContentRef.current.has(text)) return;
      void computeTtsTextHash(text).then((hash) => {
        if (cancelled) return;
        textHashByContentRef.current.set(text, hash);
        setTextHashes((prev) => {
          const next = rebuildFromCache();
          const prevKeys = Object.keys(prev).sort().join(",");
          const nextKeys = Object.keys(next).sort().join(",");
          if (prevKeys === nextKeys && segments.every((_, i) => prev[i] === next[i])) return prev;
          return next;
        });
      });
    });

    setTextHashes((prev) => {
      const next = rebuildFromCache();
      const prevKeys = Object.keys(prev).sort().join(",");
      const nextKeys = Object.keys(next).sort().join(",");
      if (prevKeys === nextKeys && segments.every((_, i) => prev[i] === next[i])) return prev;
      return next;
    });

    return () => {
      cancelled = true;
    };
  }, [segments, segmentsTextSignature]);

  const stopTtsPlayback = useCallback(() => {
    const audio = ttsAudioRef.current;
    if (!audio) return;
    audio.pause();
    audio.removeAttribute("src");
  }, []);

  const syncDubbingForSegment = useCallback(
    (segment: ScriptSegment, index: number, opts?: { videoOnly?: boolean }) => {
      const video = videoRef.current;
      const audio = ttsAudioRef.current;
      const hash = textHashes[index];
      const useDub = isValidSegmentTts(segment, hash) && Boolean(segment.tts_audio_path);
      if (!useDub || !audio) {
        stopTtsPlayback();
        if (video) video.volume = 1;
        return false;
      }
      if (video) video.volume = 0;
      if (opts?.videoOnly) return true;
      const url = projectService.getWebFileUrl(
        segment.tts_audio_path!,
        segment.tts_updated_at || segment.tts_text_hash
      );
      if (audio.src !== url) audio.src = url;
      audio.playbackRate = playbackRate;
      audio.currentTime = 0;
      void audio.play().catch(() => undefined);
      return true;
    },
    [playbackRate, stopTtsPlayback, textHashes]
  );

  useEffect(() => {
    sequencePlayingRef.current = isSequencePlaying;
  }, [isSequencePlaying]);

  useEffect(() => {
    if (!selectedSegment || !videoRef.current) return;
    const video = videoRef.current;
    video.currentTime = Math.max(0, selectedSegment.start_time || 0);
  }, [selectedSegment?.id, selectedSegment?.start_time]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video || !videoUrl) return undefined;
    const onMeta = () => {
      const d = video.duration;
      if (Number.isFinite(d) && d > 0) setVideoDuration(d);
    };
    video.addEventListener("loadedmetadata", onMeta);
    onMeta();
    return () => video.removeEventListener("loadedmetadata", onMeta);
  }, [videoUrl]);

  useEffect(() => {
    if (videoRef.current) videoRef.current.playbackRate = playbackRate;
    if (ttsAudioRef.current) ttsAudioRef.current.playbackRate = playbackRate;
  }, [playbackRate, videoUrl]);

  useEffect(() => {
    if (!selectedSegment || !videoRef.current) return undefined;
    const video = videoRef.current;
    const audio = ttsAudioRef.current;
    const endEpsilon = 0.04;

    const playEndTime = () =>
      getSegmentPlayEndTime(selectedSegment, textHashes[selectedIndex], videoDuration);

    const finishSegment = () => {
      if (segmentFinishedRef.current === selectedIndex) return;
      segmentFinishedRef.current = selectedIndex;
      audio?.pause();
      if (sequencePlayingRef.current) {
        const nextIndex = selectedIndex + 1;
        const nextSegment = segments[nextIndex];
        if (nextSegment) {
          segmentFinishedRef.current = null;
          setSelectedIndex(nextIndex);
          video.currentTime = Math.max(0, nextSegment.start_time || 0);
          video.playbackRate = playbackRate;
          syncDubbingForSegment(nextSegment, nextIndex);
          video.play().catch(() => undefined);
          return;
        }
        setIsSequencePlaying(false);
        sequencePlayingRef.current = false;
        stopTtsPlayback();
        video.volume = 1;
      }
      video.pause();
    };

    const onTimeUpdate = () => {
      const endAt = playEndTime();
      if (video.currentTime < endAt - endEpsilon) return;
      finishSegment();
    };

    const onAudioEnded = () => {
      const hash = textHashes[selectedIndex];
      if (!isValidSegmentTts(selectedSegment, hash)) return;
      finishSegment();
    };

    const onPlay = () => {
      segmentFinishedRef.current = null;
      const endAt = playEndTime();
      if (video.currentTime < selectedSegment.start_time || video.currentTime >= endAt) {
        video.currentTime = Math.max(0, selectedSegment.start_time || 0);
      }
      video.playbackRate = playbackRate;
      syncDubbingForSegment(selectedSegment, selectedIndex);
    };

    const onPause = () => {
      const endAt = playEndTime();
      if (video.currentTime < endAt - endEpsilon) {
        setIsSequencePlaying(false);
        sequencePlayingRef.current = false;
        stopTtsPlayback();
        video.volume = 1;
      }
    };

    video.addEventListener("timeupdate", onTimeUpdate);
    video.addEventListener("play", onPlay);
    video.addEventListener("pause", onPause);
    audio?.addEventListener("ended", onAudioEnded);
    return () => {
      video.removeEventListener("timeupdate", onTimeUpdate);
      video.removeEventListener("play", onPlay);
      video.removeEventListener("pause", onPause);
      audio?.removeEventListener("ended", onAudioEnded);
    };
  }, [
    isSequencePlaying,
    playbackRate,
    segments,
    selectedIndex,
    selectedSegment,
    stopTtsPlayback,
    syncDubbingForSegment,
    textHashes,
    videoDuration,
  ]);

  const optionsBySegmentId = useMemo(() => {
    const map = new Map<string, OmniShotOptionsSegment>();
    for (const item of shotOptions?.segments ?? []) {
      map.set(String(item.segment_id), item);
    }
    return map;
  }, [shotOptions]);

  const mutateSegments = useCallback(
    (
      mutator: (segments: ScriptSegment[]) => ScriptSegment[],
      options?: { syncImmediately?: boolean }
    ) => {
      if (!script) return;
      const next: VideoScript = {
        ...script,
        segments: mutator(script.segments),
        metadata: {
          ...(script.metadata ?? {}),
          updated_at: new Date().toISOString(),
        },
      };
      setEditedScript(makeScriptJson(next));
      if (options?.syncImmediately) flushSyncScriptToServer(next);
      else scheduleSyncScriptToServer(next);
    },
    [flushSyncScriptToServer, scheduleSyncScriptToServer, script, setEditedScript]
  );

  const setScriptSegment = useCallback(
    (index: number, updater: (segment: ScriptSegment) => ScriptSegment) => {
      mutateSegments((segments) => segments.map((segment, i) => (i === index ? updater({ ...segment }) : segment)));
    },
    [mutateSegments]
  );

  const duplicateSegment = useCallback(
    (index: number) => {
      mutateSegments((segments) => {
        const source = segments[index];
        if (!source) return segments;
        const copy: ScriptSegment = {
          ...source,
          id: `${source.id}_copy_${Date.now()}`,
          tts_audio_path: undefined,
          tts_audio_duration: undefined,
          tts_source: undefined,
          tts_text_hash: undefined,
          tts_updated_at: undefined,
        };
        const next = [...segments];
        next.splice(index + 1, 0, copy);
        return next;
      }, { syncImmediately: true });
      setSelectedIndex((current) => {
        if (current > index) return current + 1;
        return current;
      });
      setPickerIndex((current) => {
        if (current == null) return null;
        if (current > index) return current + 1;
        return current;
      });
    },
    [mutateSegments]
  );

  const deleteSegment = useCallback(
    (index: number) => {
      mutateSegments((segments) => segments.filter((_, i) => i !== index), { syncImmediately: true });
      setSelectedIndex((current) => {
        if (current > index) return current - 1;
        if (current === index) return Math.max(0, index - 1);
        return current;
      });
      setPickerIndex((current) => {
        if (current == null) return null;
        if (current === index) return null;
        if (current > index) return current - 1;
        return current;
      });
    },
    [mutateSegments]
  );

  const moveSegment = useCallback(
    (index: number, direction: -1 | 1) => {
      const target = index + direction;
      if (target < 0 || target >= segments.length) return;
      mutateSegments(
        (list) => {
          const next = [...list];
          [next[index], next[target]] = [next[target], next[index]];
          return next;
        },
        { syncImmediately: true }
      );
      setSelectedIndex((current) => {
        if (current === index) return target;
        if (current === target) return index;
        return current;
      });
      setPickerIndex((current) => {
        if (current === index) return target;
        if (current === target) return index;
        return current;
      });
    },
    [mutateSegments, segments.length]
  );

  const toggleSegmentType = useCallback(
    (index: number) => {
      setScriptSegment(index, (segment) => {
        if (isOriginalAudio(segment)) {
          return {
            ...segment,
            OST: 0,
            text: isPlaybackOriginalLabel(segment.text) ? "" : segment.text,
          };
        }
        const originalCount =
          (script?.segments.filter((item, i) => i !== index && isOriginalAudio(item)).length ?? 0) + 1;
        return {
          ...segment,
          OST: 1,
          text: segment.text?.trim() ? segment.text : `播放原片${originalCount}`,
        };
      });
    },
    [script?.segments, setScriptSegment]
  );

  const playSegment = useCallback(
    (index: number) => {
      setIsSequencePlaying(false);
      setSelectedIndex(index);
      const segment = segments[index];
      if (!segment || !videoRef.current) return;
      const video = videoRef.current;
      video.currentTime = Math.max(0, segment.start_time || 0);
      video.playbackRate = playbackRate;
      const dubbed = syncDubbingForSegment(segment, index);
      if (!dubbed) {
        video.volume = 1;
        stopTtsPlayback();
      }
      video.play().catch(() => undefined);
    },
    [playbackRate, segments, stopTtsPlayback, syncDubbingForSegment]
  );

  const playSegmentTts = useCallback(
    (index: number) => {
      const segment = segments[index];
      if (!segment?.tts_audio_path) return;
      const hash = textHashes[index];
      if (!isValidSegmentTts(segment, hash)) return;
      const audio = ttsAudioRef.current;
      const video = videoRef.current;
      if (!audio) return;
      if (video) {
        video.pause();
        video.volume = 1;
      }
      stopTtsPlayback();
      audio.src = projectService.getWebFileUrl(
        segment.tts_audio_path,
        segment.tts_updated_at || segment.tts_text_hash
      );
      audio.playbackRate = playbackRate;
      audio.currentTime = 0;
      void audio.play().catch(() => undefined);
    },
    [playbackRate, segments, stopTtsPlayback, textHashes]
  );

  const playAdjacentSegment = useCallback(
    (direction: -1 | 1) => {
      const nextIndex = selectedIndex + direction;
      if (nextIndex < 0 || nextIndex >= segments.length) return;
      playSegment(nextIndex);
    },
    [playSegment, selectedIndex, segments.length]
  );

  const toggleSequencePlayback = useCallback(() => {
    const video = videoRef.current;
    const startSegment = segments[selectedIndex];
    if (!video || !startSegment) return;
    if (isSequencePlaying) {
      setIsSequencePlaying(false);
      video.pause();
      stopTtsPlayback();
      video.volume = 1;
      return;
    }
    setIsSequencePlaying(true);
    video.playbackRate = playbackRate;
    if (video.currentTime < startSegment.start_time || video.currentTime >= startSegment.end_time) {
      video.currentTime = Math.max(0, startSegment.start_time || 0);
    }
    syncDubbingForSegment(startSegment, selectedIndex);
    video.play().catch(() => {
      setIsSequencePlaying(false);
      stopTtsPlayback();
      video.volume = 1;
    });
  }, [isSequencePlaying, playbackRate, selectedIndex, segments, stopTtsPlayback, syncDubbingForSegment]);

  const applyShot = useCallback(
    (shot: OmniSelectableShot) => {
      if (pickerIndex == null || !script) return;
      mutateSegments(
        (list) =>
          list.map((segment, i) =>
            i === pickerIndex
              ? {
                  ...segment,
                  start_time: shot.start,
                  end_time: shot.end,
                  shot_id: shot.shot_id,
                  shot_source: "manual",
                }
              : segment
          ),
        { syncImmediately: true }
      );
      setSelectedIndex(pickerIndex);
      setPickerIndex(null);
    },
    [mutateSegments, pickerIndex, script]
  );

  const updateSegmentTimeRange = useCallback(
    (index: number, range: { start_time: number; end_time: number }) => {
      setScriptSegment(index, (segment) => {
        const effectiveDuration = getEffectiveDuration(
          videoDuration,
          segment.start_time,
          segment.end_time,
          range.start_time,
          range.end_time
        );
        return {
          ...segment,
          ...clampSegmentTimes(range.start_time, range.end_time, effectiveDuration),
        };
      });
    },
    [setScriptSegment, videoDuration]
  );

  const pickerSegment = pickerIndex == null ? null : segments[pickerIndex];
  const pickerOptions = pickerSegment
    ? optionsBySegmentId.get(String(pickerSegment.id ?? (pickerIndex ?? 0) + 1))
    : undefined;

  return {
    parsed,
    script,
    segments,
    videoUrl,
    videoDuration,
    videoRef,
    ttsAudioRef,
    textHashes,
    scriptListRef,
    scriptRowRefs,
    selectedIndex,
    selectedSegment,
    pickerIndex,
    setPickerIndex,
    pickerSegment,
    pickerOptions,
    shotOptionsLoading,
    shotOptionsError,
    isSequencePlaying,
    playbackRate,
    setPlaybackRate,
    setScriptSegment,
    deleteSegment,
    duplicateSegment,
    moveSegment,
    toggleSegmentType,
    playSegment,
    playSegmentTts,
    playAdjacentSegment,
    toggleSequencePlayback,
    applyShot,
    updateSegmentTimeRange,
  };
}

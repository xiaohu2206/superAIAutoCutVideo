import { convertFileSrc } from "@tauri-apps/api/core";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Project, SubtitleMeta, SubtitleSegment } from "../types/project";
import { useTauriFileDrop } from "./useTauriFileDrop";
import { useVideoOrderDrag } from "./useVideoOrderDrag";
import { useWsTaskProgress, type WsProgressLog } from "./useWsTaskProgress";

export interface UploadVideosFn {
  (files: FileList | File[], onProgress?: (p: number) => void): Promise<void>;
}

export interface UploadSubtitleFn {
  (file: File, onProgress?: (p: number) => void): Promise<void>;
}

export interface UseProjectEditUploadStepOptions {
  projectId: string;
  project?: Project | null;
  merging: boolean;
  mergeProgress: number;
  subtitleLoading: boolean;
  subtitleMeta: SubtitleMeta | null;
  subtitleSegments: SubtitleSegment[] | null;
  uploadVideos: UploadVideosFn;
  uploadSubtitle: UploadSubtitleFn;
  deleteSubtitle: () => Promise<void>;
  extractSubtitle: (
    options?:
      | boolean
      | {
          force?: boolean;
          asr_provider?: "bcut" | "fun_asr";
          asr_model_key?: string | null;
          asr_language?: string | null;
          itn?: boolean;
          hotwords?: string[];
        }
  ) => Promise<void>;
  fetchSubtitle: () => Promise<any>;
  saveSubtitle: (payload: { segments?: SubtitleSegment[]; content?: string }) => Promise<void>;
  deleteVideoItem: (path: string) => Promise<void>;
  reorderVideos: (videoPaths: string[]) => Promise<void>;
  mergeVideos: () => Promise<void>;
  refreshProject: () => Promise<void>;
  showSuccess: (text: string, durationSec?: number) => void;
  showErrorText: (text: string, durationSec?: number) => void;
  showError: (err: unknown, fallback: string) => void | Promise<void>;
}

export interface UseProjectEditUploadStepReturn {
  showAdvancedConfig: boolean;
  setShowAdvancedConfig: React.Dispatch<React.SetStateAction<boolean>>;
  uploadingSubtitle: boolean;
  subtitleUploadProgress: number;
  isDraggingSubtitle: boolean;
  onSubtitleFileChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  onDeleteSubtitle: () => void;
  onSubtitleDragOver: (e: React.DragEvent<HTMLDivElement>) => void;
  onSubtitleDragLeave: (e: React.DragEvent<HTMLDivElement>) => void;
  onSubtitleDrop: (e: React.DragEvent<HTMLDivElement>) => void;
  videoOrder: string[];
  dragIndex: number | null;
  isDraggingVideo: boolean;
  uploadingVideo: boolean;
  videoUploadProgress: number;
  videoInputRef: React.RefObject<HTMLInputElement>;
  onVideoDragOver: (e: React.DragEvent<HTMLDivElement>) => void;
  onVideoDragLeave: (e: React.DragEvent<HTMLDivElement>) => void;
  onVideoDrop: (e: React.DragEvent<HTMLDivElement>) => void;
  onVideoFileChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  onMergeClick: () => void;
  onItemDragStart: (index: number) => void;
  onItemDragOver: (e: React.DragEvent<HTMLDivElement>, overIndex: number) => void;
  onItemDrop: (e: React.DragEvent<HTMLDivElement>) => void;
  onDeleteVideoItem: (path: string) => void;
  extractingSubtitle: boolean;
  subtitleExtractProgress: number;
  subtitleExtractLogs: WsProgressLog[];
  onExtractSubtitle: () => void;
  subtitleAsr: { provider: "bcut" | "fun_asr"; modelKey: string; language: string };
  onSubtitleAsrChange: (next: { provider: "bcut" | "fun_asr"; modelKey: string; language: string }) => void;
  subtitleDraft: SubtitleSegment[];
  subtitleSaving: boolean;
  onReloadSubtitle: () => void;
  onSaveSubtitle: () => void;
  onSubtitleDraftChange: (next: SubtitleSegment[]) => void;
}

export function useProjectEditUploadStep(
  options: UseProjectEditUploadStepOptions
): UseProjectEditUploadStepReturn {
  const [showAdvancedConfig, setShowAdvancedConfig] = useState(false);

  const [isDraggingVideo, setIsDraggingVideo] = useState(false);
  const [uploadingVideo, setUploadingVideo] = useState(false);
  const [videoUploadProgress, setVideoUploadProgress] = useState<number>(0);

  const [uploadingSubtitle, setUploadingSubtitle] = useState(false);
  const [subtitleUploadProgress, setSubtitleUploadProgress] = useState<number>(0);
  const [isDraggingSubtitle, setIsDraggingSubtitle] = useState(false);

  const [extractingSubtitle, setExtractingSubtitle] = useState(false);
  const [subtitleExtractProgress, setSubtitleExtractProgress] = useState(0);
  const [subtitleExtractLogs, setSubtitleExtractLogs] = useState<WsProgressLog[]>([]);
  const [subtitleDraft, setSubtitleDraft] = useState<SubtitleSegment[]>([]);
  const [subtitleSaving, setSubtitleSaving] = useState(false);
  const [subtitleAsr, setSubtitleAsr] = useState<{ provider: "bcut" | "fun_asr"; modelKey: string; language: string }>({
    provider: "bcut",
    modelKey: "fun_asr_nano_2512",
    language: "中文",
  });

  const videoInputRef = useRef<HTMLInputElement>(null);
  const uploadingVideoRef = useRef(false);
  const subtitleSegmentsSerializedRef = useRef<string | null>(null);
  const lastAsrSnapshotRef = useRef<string>("");

  useEffect(() => {
    const p = options.project;
    if (!p) return;
    const snap = `${p.id}|${String((p as any).asr_provider || "")}|${String((p as any).asr_model_key || "")}|${String((p as any).asr_language || "")}`;
    if (snap === lastAsrSnapshotRef.current) return;
    lastAsrSnapshotRef.current = snap;
    const provider = (String((p as any).asr_provider || "bcut").trim().toLowerCase() === "fun_asr" ? "fun_asr" : "bcut") as
      | "bcut"
      | "fun_asr";
    const modelKey = String((p as any).asr_model_key || "fun_asr_nano_2512").trim() || "fun_asr_nano_2512";
    const language = String((p as any).asr_language || "中文").trim() || "中文";
    setSubtitleAsr({ provider, modelKey, language });
  }, [options.project?.id, (options.project as any)?.asr_provider, (options.project as any)?.asr_model_key, (options.project as any)?.asr_language]);

  useEffect(() => {
    uploadingVideoRef.current = uploadingVideo;
  }, [uploadingVideo]);

  const {
    videoOrder,
    dragIndex,
    handleItemDragStart,
    handleItemDragOver,
    handleItemDrop,
  } = useVideoOrderDrag({
    projectVideoPaths: options.project?.video_paths,
    reorderVideos: options.reorderVideos,
    showSuccess: options.showSuccess,
    showError: options.showError,
  });

  const onDeleteSubtitle = useCallback(async () => {
    try {
      await options.deleteSubtitle();
      options.showSuccess("字幕已删除！");
    } catch (err) {
      options.showError(err, "删除字幕失败");
    }
  }, [options]);

  const onDeleteVideoItem = useCallback(
    async (path: string) => {
      try {
        await options.deleteVideoItem(path);
        options.showSuccess("视频已删除！");
      } catch (err) {
        options.showError(err, "删除视频失败");
      }
    },
    [options]
  );

  const onMergeClick = useCallback(async () => {
    const project = options.project;
    if (!project) return;
    if (!Array.isArray(project.video_paths) || project.video_paths.length < 2) return;

    try {
      const before = project.video_paths.join("|");
      const after = videoOrder.join("|");
      if (before !== after) {
        await options.reorderVideos(videoOrder);
      }
      await options.mergeVideos();
      options.showSuccess("合并视频完成！");
    } catch (err) {
      options.showError(err, "合并视频失败");
    }
  }, [options, videoOrder]);

  const onVideoFileChange = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const files = e.target.files;
      if (!files || files.length === 0) return;

      setUploadingVideo(true);
      setVideoUploadProgress(0);
      try {
        await options.uploadVideos(files, (p) => setVideoUploadProgress(p));
        options.showSuccess("视频文件上传成功！");
      } catch (err) {
        options.showError(err, "上传视频失败");
      } finally {
        setUploadingVideo(false);
        setTimeout(() => setVideoUploadProgress(0), 800);
      }
    },
    [options]
  );

  const onVideoDragOver = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    try {
      if (e.dataTransfer) {
        e.dataTransfer.dropEffect = "copy";
      }
    } catch {
      void 0;
    }
    setIsDraggingVideo(true);
  }, []);

  const onVideoDragLeave = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDraggingVideo(false);
  }, []);

  const onVideoDrop = useCallback(
    async (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      e.stopPropagation();
      setIsDraggingVideo(false);
      const files = e.dataTransfer.files;
      if (!files || files.length === 0) return;

      setUploadingVideo(true);
      setVideoUploadProgress(0);
      try {
        await options.uploadVideos(files, (p) => setVideoUploadProgress(p));
        options.showSuccess("视频文件上传成功！");
      } catch (err) {
        options.showError(err, "上传视频失败");
      } finally {
        setUploadingVideo(false);
        setTimeout(() => setVideoUploadProgress(0), 800);
      }
    },
    [options]
  );

  const onSubtitleDragOver = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.dataTransfer) {
      e.dataTransfer.dropEffect = "copy";
    }
    setIsDraggingSubtitle(true);
  }, []);

  const onSubtitleDragLeave = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDraggingSubtitle(false);
  }, []);

  const onSubtitleDrop = useCallback(
    async (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      e.stopPropagation();
      setIsDraggingSubtitle(false);
      const files = e.dataTransfer.files;
      if (!files || files.length === 0) return;
      const file = files[0];

      setUploadingSubtitle(true);
      setSubtitleUploadProgress(0);
      try {
        await options.uploadSubtitle(file, (p) => setSubtitleUploadProgress(p));
        options.showSuccess("字幕文件上传成功！");
      } catch (err) {
        options.showError(err, "上传字幕失败");
      } finally {
        setUploadingSubtitle(false);
        setTimeout(() => setSubtitleUploadProgress(0), 800);
      }
    },
    [options]
  );

  const onSubtitleFileChange = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const files = e.target.files;
      if (!files || files.length === 0) return;
      const file = files[0];

      setUploadingSubtitle(true);
      setSubtitleUploadProgress(0);
      try {
        await options.uploadSubtitle(file, (p) => setSubtitleUploadProgress(p));
        options.showSuccess("字幕文件上传成功！");
      } catch (err) {
        options.showError(err, "上传字幕失败");
      } finally {
        setUploadingSubtitle(false);
        setTimeout(() => setSubtitleUploadProgress(0), 800);
      }
    },
    [options]
  );

  const handleTauriPathsUpload = useCallback(
    async (paths: string[]) => {
      if (!paths || paths.length === 0) return;
      if (uploadingVideoRef.current) return;
      const videoExts = [".mp4", ".mov", ".mkv", ".avi", ".flv", ".wmv", ".webm", ".m4v"];
      const filtered = paths.filter((p) => {
        const lower = p.toLowerCase();
        return videoExts.some((ext) => lower.endsWith(ext));
      });
      if (filtered.length === 0) return;

      setUploadingVideo(true);
      setVideoUploadProgress(0);
      try {
        const files = await Promise.all(
          filtered.map(async (p) => {
            const url = convertFileSrc(p);
            const res = await fetch(url);
            if (!res.ok) throw new Error(`读取文件失败: ${p}`);
            const blob = await res.blob();
            const name = p.split(/[/\\]/).pop() || "file";
            return new File([blob], name, { type: blob.type || "application/octet-stream" });
          })
        );
        if (files.length > 0) {
          await options.uploadVideos(files, (pr) => setVideoUploadProgress(pr));
          options.showSuccess("视频文件上传成功！");
        }
      } catch (err) {
        options.showError(err, "上传视频失败");
      } finally {
        setUploadingVideo(false);
        setTimeout(() => setVideoUploadProgress(0), 800);
      }
    },
    [options]
  );

  useTauriFileDrop(
    useMemo(
      () => ({
        onHovered: () => setIsDraggingVideo(true),
        onCancelled: () => setIsDraggingVideo(false),
        onDropped: async (paths: string[]) => {
          setIsDraggingVideo(false);
          await handleTauriPathsUpload(paths);
        },
      }),
      [handleTauriPathsUpload]
    )
  );

  const onExtractSubtitle = useCallback(async () => {
    const project = options.project;
    if (!project) return;
    if (!project.video_path) {
      options.showErrorText("请先上传视频文件");
      return;
    }
    if (project.subtitle_source === "user" && project.subtitle_path) {
      options.showErrorText("已上传字幕，需先删除才能提取");
      return;
    }
    if (project.subtitle_status === "extracting") {
      options.showErrorText("正在提取中");
      return;
    }
    // 每次都强制重新提取，不使用缓存的音频
    let force = true;
    if (project.subtitle_updated_by_user) {
      force = window.confirm("字幕已被编辑，重新提取将覆盖修改内容，是否继续？");
      if (!force) return;
    }

    setExtractingSubtitle(true);
    setSubtitleExtractProgress(0);
    setSubtitleExtractLogs([]);
    try {
      const isFun = subtitleAsr.provider === "fun_asr";
      await options.extractSubtitle({
        force,
        asr_provider: subtitleAsr.provider,
        asr_model_key: isFun ? subtitleAsr.modelKey : null,
        asr_language: isFun ? subtitleAsr.language : "中文",
      });
      // HTTP 请求成功，确保状态更新
      setSubtitleExtractProgress(100);
      setExtractingSubtitle(false);
      options.showSuccess("字幕提取成功！");
      void options.refreshProject();
      void options.fetchSubtitle().catch(() => void 0);
    } catch (err) {
      options.showError(err, "提取字幕失败");
      setExtractingSubtitle(false);
      setSubtitleExtractProgress(0);
    }
  }, [options, subtitleAsr]);

  useWsTaskProgress({
    scope: "extract_subtitle",
    projectId: options.project?.id,
    onProgress: setSubtitleExtractProgress,
    onLog: (log) => setSubtitleExtractLogs((prev) => [...prev, log]),
    onCompleted: () => {
      setSubtitleExtractProgress(100);
      setExtractingSubtitle(false);
      options.showSuccess("字幕提取成功！");
      void options.refreshProject();
      void options.fetchSubtitle().catch(() => void 0);
    },
    onError: (m) => {
      setExtractingSubtitle(false);
      setSubtitleExtractProgress(0);
      options.showErrorText(m.message || "字幕提取失败");
    },
  });

  useEffect(() => {
    if (options.project?.subtitle_path) {
      void options.fetchSubtitle().catch(() => void 0);
    } else {
      setSubtitleDraft([]);
    }
  }, [options.project?.id, options.project?.subtitle_path, options.fetchSubtitle]);

  useEffect(() => {
    const incoming = options.subtitleSegments || [];
    const serialized = JSON.stringify(incoming);
    if (subtitleSegmentsSerializedRef.current === serialized) {
      return;
    }
    subtitleSegmentsSerializedRef.current = serialized;
    setSubtitleDraft(incoming);
  }, [options.subtitleSegments]);

  const onReloadSubtitle = useCallback(async () => {
    try {
      await options.fetchSubtitle();
    } catch (err) {
      options.showError(err, "获取字幕失败");
    }
  }, [options]);

  const onSaveSubtitle = useCallback(async () => {
    if (!subtitleDraft.length) {
      options.showErrorText("字幕内容为空");
      return;
    }
    setSubtitleSaving(true);
    try {
      await options.saveSubtitle({ segments: subtitleDraft });
      options.showSuccess("字幕保存成功！");
    } catch (err) {
      options.showError(err, "保存字幕失败");
    } finally {
      setSubtitleSaving(false);
    }
  }, [options, subtitleDraft]);

  return {
    showAdvancedConfig,
    setShowAdvancedConfig,
    uploadingSubtitle,
    subtitleUploadProgress,
    isDraggingSubtitle,
    onSubtitleFileChange,
    onDeleteSubtitle,
    onSubtitleDragOver,
    onSubtitleDragLeave,
    onSubtitleDrop,
    videoOrder,
    dragIndex,
    isDraggingVideo,
    uploadingVideo,
    videoUploadProgress,
    videoInputRef,
    onVideoDragOver,
    onVideoDragLeave,
    onVideoDrop,
    onVideoFileChange,
    onMergeClick,
    onItemDragStart: handleItemDragStart,
    onItemDragOver: handleItemDragOver,
    onItemDrop: handleItemDrop,
    onDeleteVideoItem,
    extractingSubtitle,
    subtitleExtractProgress,
    subtitleExtractLogs,
    onExtractSubtitle,
    subtitleAsr,
    onSubtitleAsrChange: setSubtitleAsr,
    subtitleDraft,
    subtitleSaving,
    onReloadSubtitle,
    onSaveSubtitle,
    onSubtitleDraftChange: setSubtitleDraft,
  };
}

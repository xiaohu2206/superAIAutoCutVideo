import { convertFileSrc } from "@tauri-apps/api/core";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useAuth } from "../components/auth/AuthContext";

const OMNI_PIPELINE_LICENSE_GATE_MSG =
  "运行 Omni 管线需要先登录，并在个人中心绑定处于生效中的 License。";

/** 与 CreateProjectModal handleSubmit 中 omni License 错误判定一致 */
const OMNI_LICENSE_ERROR_RE = /license|401|403|登录|未授权|无权限|过期|校验|绑定/i;

function readSacvAuthTokenTrimmed(): string {
  if (typeof localStorage === "undefined") return "";
  return localStorage.getItem("sacv_auth_token")?.trim() ?? "";
}
import type { OmniMultimodalResult } from "../types/omniMultimodal";
import type { Project, SubtitleMeta, SubtitleSegment } from "../types/project";
import { projectService } from "../services/projectService";
import { TASK_SUBMITTED_EVENT } from "../components/projectEdit/TaskQueueFloatingBall";
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
  projectTaskBusy?: boolean;
  subtitleMeta: SubtitleMeta | null;
  subtitleSegments: SubtitleSegment[] | null;
  uploadVideos: UploadVideosFn;
  uploadSubtitle: UploadSubtitleFn;
  deleteSubtitle: () => Promise<void>;
  extractSubtitle: (options?: {
    task_id?: string | null;
    force?: boolean;
    asr_provider?: "bcut" | "fun_asr";
    asr_model_key?: string | null;
    asr_language?: string | null;
    itn?: boolean;
    hotwords?: string[];
  }) => Promise<void>;
  fetchSubtitle: () => Promise<any>;
  saveSubtitle: (payload: { segments?: SubtitleSegment[]; content?: string }) => Promise<void>;
  deleteVideoItem: (path: string) => Promise<void>;
  reorderVideos: (videoPaths: string[]) => Promise<void>;
  mergeVideos: () => Promise<void>;
  refreshProject: () => Promise<void>;
  extractScenes: (options?: { force?: boolean; task_id?: string | null; asr_provider?: "bcut" | "fun_asr"; asr_model_key?: string | null; asr_language?: string | null; itn?: boolean; hotwords?: string[]; analyzeVision?: boolean; visionMode?: string; visionKeyFrames?: 1 | 3; visionAction?: "auto" | "continue" | "restart" }) => Promise<void>;
  cancelSceneExtraction: () => Promise<void>;
  sceneResult: any | null;
  extractingScene: boolean;
  sceneExtractProgress: number;
  sceneExtractMessage: string;
  sceneExtractPhase: string | null;
  runOmniPipeline: (options?: {
    force?: boolean;
    task_id?: string | null;
    multimodal_action?: "auto" | "continue" | "restart";
  }) => Promise<void>;
  runOmniPipelineWithSubtitle: (options?: {
    task_id?: string | null;
    force?: boolean;
    asr_provider?: "bcut" | "fun_asr";
    asr_model_key?: string | null;
    asr_language?: string | null;
    itn?: boolean;
    hotwords?: string[];
    pipeline_task_id?: string | null;
    pipeline_force?: boolean;
    multimodal_action?: "auto" | "continue" | "restart";
  }) => Promise<void>;
  cancelOmniPipeline: () => Promise<void>;
  extractingOmniPipeline: boolean;
  omniPipelineProgress: number;
  omniPipelineMessage: string;
  omniPipelinePhase: string | null;
  omniPipelineShowProgressBar: boolean;
  omniPipelineCanStop: boolean;
  omniMultimodalResult: OmniMultimodalResult | null;
  onShowLogin?: () => void;
  onShowProfile?: () => void;
  showSuccess: (text: string, durationSec?: number) => void;
  showErrorText: (text: string, durationSec?: number) => void;
  showError: (err: unknown, fallback: string) => void | Promise<void>;
}

export interface UseProjectEditUploadStepReturn {
  /** 已登录（本地有 sacv token），Omni 管线按钮可点；完整 License 仍由后端校验 */
  omniRunPipelineAuthReady: boolean;
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
  oneClickGenerateEnabled: boolean;
  onOneClickGenerateEnabledChange: (enabled: boolean) => void;
  oneClickGenerateTarget: "draft" | "video";
  onOneClickGenerateTargetChange: (target: "draft" | "video") => void;
  isStartingOneClickGenerate: boolean;
  subtitleDraft: SubtitleSegment[];
  subtitleSaving: boolean;
  onReloadSubtitle: () => void;
  onSaveSubtitle: () => void;
  onSubtitleDraftChange: (next: SubtitleSegment[]) => void;
  onExtractScenes: (options?: { analyzeVision: boolean; visionMode: string; visionKeyFrames?: 1 | 3; visionAction?: "auto" | "continue" | "restart" }) => void;
  onStopSceneExtraction: () => void;
  isStoppingSceneExtraction: boolean;
  extractingScene: boolean;
  sceneExtractProgress: number;
  sceneResult: any | null;
  sceneExtractMessage: string;
  sceneExtractPhase: string | null;
  visionChoiceModalOpen: boolean;
  onVisionChoiceContinue: () => void;
  onVisionChoiceRestart: () => void;
  onVisionChoiceCancel: () => void;
  subtitleOverwriteModalOpen: boolean;
  onSubtitleOverwriteConfirm: () => void;
  onSubtitleOverwriteCancel: () => void;
  onRunOmniPipeline: () => void;
  onRunOmniPipelineWithSubtitle: () => void;
  onStopOmniPipeline: () => void;
  isStoppingOmniPipeline: boolean;
  extractingOmniPipeline: boolean;
  omniPipelineProgress: number;
  omniPipelineMessage: string;
  omniPipelinePhase: string | null;
  omniPipelineShowProgressBar: boolean;
  omniPipelineCanStop: boolean;
  omniMultimodalResult: OmniMultimodalResult | null;
  omniMultimodalChoiceModalOpen: boolean;
  onOmniMultimodalChoiceContinue: () => void;
  onOmniMultimodalChoiceRestart: () => void;
  onOmniMultimodalChoiceCancel: () => void;
}

export function useProjectEditUploadStep(
  options: UseProjectEditUploadStepOptions
): UseProjectEditUploadStepReturn {
  const { isAuthenticated } = useAuth();
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
  const [currentSubtitleTaskId, setCurrentSubtitleTaskId] = useState<string | null>(null);
  const [subtitleDraft, setSubtitleDraft] = useState<SubtitleSegment[]>([]);
  const [subtitleSaving, setSubtitleSaving] = useState(false);
  const [subtitleAsr, setSubtitleAsr] = useState<{ provider: "bcut" | "fun_asr"; modelKey: string; language: string }>({
    provider: "bcut",
    modelKey: "fun_asr_nano_2512",
    language: "中文",
  });
  const [oneClickGenerateEnabled, setOneClickGenerateEnabled] = useState(true);
  const [oneClickGenerateTarget, setOneClickGenerateTarget] = useState<"draft" | "video">("draft");
  const [isStartingOneClickGenerate, setIsStartingOneClickGenerate] = useState(false);

  const videoInputRef = useRef<HTMLInputElement>(null);
  const uploadingVideoRef = useRef(false);
  const subtitleSegmentsSerializedRef = useRef<string | null>(null);
  const lastAsrSnapshotRef = useRef<string>("");
  const lastSubtitleProgressLogKeyRef = useRef<string>("");
  const pendingVisionExtractOptsRef = useRef<{
    analyzeVision: boolean;
    visionMode: string;
    visionKeyFrames?: 1 | 3;
    visionAction?: "auto" | "continue" | "restart";
  } | null>(null);
  const subtitleOverwriteResolverRef = useRef<((value: boolean) => void) | null>(null);

  const [visionChoiceModalOpen, setVisionChoiceModalOpen] = useState(false);
  const [omniMultimodalChoiceModalOpen, setOmniMultimodalChoiceModalOpen] = useState(false);
  const [subtitleOverwriteModalOpen, setSubtitleOverwriteModalOpen] = useState(false);
  const [isStoppingSceneExtraction, setIsStoppingSceneExtraction] = useState(false);
  const [isStoppingOmniPipeline, setIsStoppingOmniPipeline] = useState(false);

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
    const p = options.project;
    if (!p) return;
    setOneClickGenerateEnabled(p.one_click_generate_enabled !== false);
    setOneClickGenerateTarget(p.one_click_generate_target === "video" ? "video" : "draft");
  }, [options.project?.id, options.project?.one_click_generate_enabled, options.project?.one_click_generate_target]);

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

  const askSubtitleOverwrite = useCallback((): Promise<boolean> => {
    return new Promise((resolve) => {
      subtitleOverwriteResolverRef.current = resolve;
      setSubtitleOverwriteModalOpen(true);
    });
  }, []);

  const onSubtitleOverwriteConfirm = useCallback(() => {
    setSubtitleOverwriteModalOpen(false);
    const r = subtitleOverwriteResolverRef.current;
    subtitleOverwriteResolverRef.current = null;
    r?.(true);
  }, []);

  const onSubtitleOverwriteCancel = useCallback(() => {
    setSubtitleOverwriteModalOpen(false);
    const r = subtitleOverwriteResolverRef.current;
    subtitleOverwriteResolverRef.current = null;
    r?.(false);
  }, []);

  const startOneClickGenerate = useCallback(async (opts?: {
    force?: boolean;
    analyzeVision?: boolean;
    visionMode?: string;
    visionKeyFrames?: 1 | 3;
    visionAction?: "auto" | "continue" | "restart";
    multimodalAction?: "auto" | "continue" | "restart";
  }) => {
    const project = options.project;
    if (!project) return;
    if (!project.video_path) {
      options.showErrorText("请先上传视频文件");
      return;
    }
    if (project.project_type === "omni" && !readSacvAuthTokenTrimmed()) {
      if (!isAuthenticated) options.onShowLogin?.();
      else options.onShowProfile?.();
      return;
    }
    if (options.projectTaskBusy) {
      options.showErrorText("当前项目已有任务在队列中，请等待完成后再操作");
      return;
    }
    setIsStartingOneClickGenerate(true);
    try {
      const isFun = subtitleAsr.provider === "fun_asr";
      await projectService.flushPendingUpdates(project.id);
      await projectService.updateProjectQueued(project.id, {
        one_click_generate_enabled: true,
        one_click_generate_target: oneClickGenerateTarget,
      });
      const res = await projectService.startOneClickGenerate(project.id, {
        target: oneClickGenerateTarget,
        force: Boolean(opts?.force),
        asr_provider: subtitleAsr.provider,
        asr_model_key: isFun ? subtitleAsr.modelKey : null,
        asr_language: isFun ? subtitleAsr.language : "中文",
        analyzeVision: Boolean(opts?.analyzeVision),
        visionMode: opts?.visionMode ?? "all",
        visionKeyFrames: opts?.visionKeyFrames,
        visionAction: opts?.visionAction ?? "auto",
        multimodal_action: opts?.multimodalAction ?? "auto",
      });
      window.dispatchEvent(new CustomEvent(TASK_SUBMITTED_EVENT));
      const label = oneClickGenerateTarget === "video" ? "视频" : "剪映草稿";
      options.showSuccess(res?.task_id ? `一键生成${label}任务已提交` : "一键生成任务已提交");
      void options.refreshProject();
    } catch (err) {
      options.showError(err, oneClickGenerateTarget === "video" ? "一键生成视频失败" : "一键生成草稿失败");
    } finally {
      setIsStartingOneClickGenerate(false);
    }
  }, [oneClickGenerateTarget, options, subtitleAsr, isAuthenticated]);

  const onExtractSubtitle = useCallback(async () => {
    const project = options.project;
    if (!project) return;
    if (!project.video_path) {
      options.showErrorText("请先上传视频文件");
      return;
    }
    if (options.projectTaskBusy) {
      options.showErrorText("当前项目已有任务在队列中，请等待完成后再操作");
      return;
    }
    if (project.subtitle_source === "user" && project.subtitle_path && !oneClickGenerateEnabled) {
      options.showErrorText("已上传字幕，需先删除才能提取");
      return;
    }
    let forceOverwrite = false;
    if (project.subtitle_updated_by_user) {
      const ok = await askSubtitleOverwrite();
      if (!ok) return;
      forceOverwrite = true;
    }

    if (oneClickGenerateEnabled && project.project_type === "subtitle") {
      await startOneClickGenerate({ force: forceOverwrite });
      return;
    }

    setExtractingSubtitle(true);
    setSubtitleExtractProgress(0);
    setSubtitleExtractLogs([]);
    try {
      const isFun = subtitleAsr.provider === "fun_asr";
      const taskId =
        globalThis.crypto &&
        "randomUUID" in globalThis.crypto &&
        typeof (globalThis.crypto as any).randomUUID === "function"
          ? (globalThis.crypto as any).randomUUID()
          : `${Date.now()}_${Math.random().toString(16).slice(2)}`;
      setCurrentSubtitleTaskId(taskId);
      await options.extractSubtitle({
        task_id: taskId,
        force: forceOverwrite,
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
  }, [options, subtitleAsr, askSubtitleOverwrite, oneClickGenerateEnabled, startOneClickGenerate]);

  useWsTaskProgress({
    scope: "extract_subtitle",
    projectId: options.project?.id,
    taskId: currentSubtitleTaskId ?? options.project?.subtitle_extract_run_id ?? undefined,
    onProgress: setSubtitleExtractProgress,
    onLog: (log) => setSubtitleExtractLogs((prev) => [...prev, log]),
    onCompleted: () => {
      setSubtitleExtractProgress(100);
      setExtractingSubtitle(false);
      setCurrentSubtitleTaskId(null);
      options.showSuccess("字幕提取成功！");
      void options.refreshProject();
      void options.fetchSubtitle().catch(() => void 0);
    },
    onError: (m) => {
      setExtractingSubtitle(false);
      setCurrentSubtitleTaskId(null);
      setSubtitleExtractProgress(0);
      options.showErrorText(m.message || "字幕提取失败");
    },
  });

  useEffect(() => {
    const projectId = options.project?.id;
    const active = Boolean(projectId) && (extractingSubtitle || options.project?.subtitle_status === "extracting");
    if (!projectId || !active) return;

    let cancelled = false;
    const syncSubtitleProgress = async () => {
      try {
        const latest = await projectService.getProjectLatestTasks(projectId);
        if (cancelled) return;
        const task = latest?.extract_subtitle;
        if (!task) return;

        const taskId = task.task_id ? String(task.task_id) : "";
        if (currentSubtitleTaskId && taskId && taskId !== currentSubtitleTaskId) return;
        if (taskId && !currentSubtitleTaskId) {
          setCurrentSubtitleTaskId(taskId);
        }

        if (typeof task.progress === "number") {
          setSubtitleExtractProgress(Math.max(0, Math.min(100, task.progress)));
        }

        const logKey = `${task.type || ""}|${task.phase || ""}|${task.progress ?? ""}|${task.message || ""}`;
        if (task.message && logKey !== lastSubtitleProgressLogKeyRef.current) {
          lastSubtitleProgressLogKeyRef.current = logKey;
          setSubtitleExtractLogs((prev) => [
            ...prev,
            {
              timestamp: task.timestamp || new Date().toISOString(),
              message: task.message || "",
              phase: task.phase,
              type: task.type,
            },
          ]);
        }

        const status = String(task.status || "").toLowerCase();
        const type = String(task.type || "").toLowerCase();
        if (status === "completed" || type === "completed") {
          setSubtitleExtractProgress(100);
          setExtractingSubtitle(false);
          setCurrentSubtitleTaskId(null);
          void options.refreshProject();
          void options.fetchSubtitle().catch(() => void 0);
        } else if (status === "failed" || type === "error") {
          setExtractingSubtitle(false);
          setCurrentSubtitleTaskId(null);
          setSubtitleExtractProgress(0);
          options.showErrorText(task.message || "字幕提取失败");
        } else if (status === "cancelled" || type === "cancelled") {
          setExtractingSubtitle(false);
          setCurrentSubtitleTaskId(null);
        }
      } catch (err) {
        console.debug("sync subtitle progress failed", err);
      }
    };

    void syncSubtitleProgress();
    const id = window.setInterval(() => void syncSubtitleProgress(), 1500);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [
    options.project?.id,
    options.project?.subtitle_status,
    extractingSubtitle,
    currentSubtitleTaskId,
    options.refreshProject,
    options.fetchSubtitle,
    options.showErrorText,
  ]);

  /** 刷新后根据服务端状态恢复「正在提取字幕」与 WS 进度（编排接口长时间阻塞时同理） */
  useEffect(() => {
    const st = options.project?.subtitle_status;
    if (st === "extracting") {
      setExtractingSubtitle(true);
      return;
    }
    if (
      st === "ready" ||
      st === "failed" ||
      st === "none" ||
      st === undefined
    ) {
      if (!options.subtitleLoading) {
        setExtractingSubtitle(false);
      }
    }
  }, [options.project?.subtitle_status, options.subtitleLoading]);

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

  const onOneClickGenerateEnabledChange = useCallback((enabled: boolean) => {
    setOneClickGenerateEnabled(enabled);
    const projectId = options.project?.id;
    if (projectId) {
      void projectService.updateProjectQueued(projectId, {
        one_click_generate_enabled: enabled,
      }).catch(() => void 0);
    }
  }, [options.project?.id]);

  const onOneClickGenerateTargetChange = useCallback((target: "draft" | "video") => {
    setOneClickGenerateTarget(target);
    const projectId = options.project?.id;
    if (projectId) {
      void projectService.updateProjectQueued(projectId, {
        one_click_generate_target: target,
      }).catch(() => void 0);
    }
  }, [options.project?.id]);

  const executeExtractScenes = useCallback(
    async (
      opts: { analyzeVision: boolean; visionMode: string; visionKeyFrames?: 1 | 3; visionAction?: "auto" | "continue" | "restart" } | undefined,
      visionAction: "auto" | "continue" | "restart"
    ) => {
      // visual 项目：先同步完成字幕提取（HTTP 阻塞至结束），再提交镜头提取任务；进度仍由 WS 驱动。
      if (options.project?.project_type === "visual") {
        const p = options.project;
        const canStartSubtitle =
          !(p.subtitle_source === "user" && Boolean(p.subtitle_path)) &&
          !extractingSubtitle &&
          !options.subtitleLoading;
        if (canStartSubtitle) {
          let shouldStartSubtitle = true;
          let subtitleForce = false;
          if (p.subtitle_updated_by_user) {
            shouldStartSubtitle = await askSubtitleOverwrite();
            if (shouldStartSubtitle) subtitleForce = true;
          }
          if (shouldStartSubtitle) {
            setExtractingSubtitle(true);
            setSubtitleExtractProgress(0);
            setSubtitleExtractLogs([]);
            const isFun = subtitleAsr.provider === "fun_asr";
            const subTaskId =
              globalThis.crypto &&
              "randomUUID" in globalThis.crypto &&
              typeof (globalThis.crypto as any).randomUUID === "function"
                ? (globalThis.crypto as any).randomUUID()
                : `${Date.now()}_${Math.random().toString(16).slice(2)}`;
            setCurrentSubtitleTaskId(subTaskId);
            try {
              await options.extractSubtitle({
                task_id: subTaskId,
                force: subtitleForce,
                asr_provider: subtitleAsr.provider,
                asr_model_key: isFun ? subtitleAsr.modelKey : null,
                asr_language: isFun ? subtitleAsr.language : "中文",
              });
              setSubtitleExtractProgress(100);
              setExtractingSubtitle(false);
              void options.refreshProject();
              void options.fetchSubtitle().catch(() => void 0);
            } catch (err) {
              options.showError(err, "提取字幕失败");
              setExtractingSubtitle(false);
              setSubtitleExtractProgress(0);
              return;
            }
          }
        }
      }

      const isFun = subtitleAsr.provider === "fun_asr";
      await options.extractScenes({
        force: false,
        asr_provider: subtitleAsr.provider,
        asr_model_key: isFun ? subtitleAsr.modelKey : null,
        asr_language: isFun ? subtitleAsr.language : "中文",
        ...(opts || {}),
        visionAction,
      });
      options.showSuccess("镜头提取任务已提交");
    },
    [options, subtitleAsr, extractingSubtitle, askSubtitleOverwrite]
  );

  const onVisionChoiceContinue = useCallback(() => {
    setVisionChoiceModalOpen(false);
    const opts = pendingVisionExtractOptsRef.current;
    pendingVisionExtractOptsRef.current = null;
    if (opts) {
      if (oneClickGenerateEnabled && options.project?.project_type === "visual") {
        void startOneClickGenerate({ ...opts, visionAction: "continue" }).catch((err) => options.showError(err, "一键生成失败"));
      } else {
        void executeExtractScenes(opts, "continue").catch((err) => options.showError(err, "镜头提取失败"));
      }
    }
  }, [executeExtractScenes, oneClickGenerateEnabled, options, startOneClickGenerate]);

  const onVisionChoiceRestart = useCallback(() => {
    setVisionChoiceModalOpen(false);
    const opts = pendingVisionExtractOptsRef.current;
    pendingVisionExtractOptsRef.current = null;
    if (opts) {
      if (oneClickGenerateEnabled && options.project?.project_type === "visual") {
        void startOneClickGenerate({ ...opts, visionAction: "restart" }).catch((err) => options.showError(err, "一键生成失败"));
      } else {
        void executeExtractScenes(opts, "restart").catch((err) => options.showError(err, "镜头提取失败"));
      }
    }
  }, [executeExtractScenes, oneClickGenerateEnabled, options, startOneClickGenerate]);

  const onVisionChoiceCancel = useCallback(() => {
    setVisionChoiceModalOpen(false);
    pendingVisionExtractOptsRef.current = null;
  }, []);

  const onExtractScenes = useCallback(
    async (opts?: { analyzeVision: boolean; visionMode: string; visionKeyFrames?: 1 | 3; visionAction?: "auto" | "continue" | "restart" }) => {
      if (!options.project) return;
      if (!options.project.video_path) {
        options.showErrorText("请先上传视频文件");
        return;
      }
      if (options.projectTaskBusy) {
        options.showErrorText("当前项目已有任务在队列中，请等待完成后再操作");
        return;
      }
      try {
        const p = options.project;
        const visionAction: "auto" | "continue" | "restart" = opts?.visionAction ?? "auto";
        if (opts?.analyzeVision && p.scenes_path && visionAction === "auto") {
          pendingVisionExtractOptsRef.current = opts;
          setVisionChoiceModalOpen(true);
          return;
        }
        if (oneClickGenerateEnabled && p.project_type === "visual") {
          let forceOverwrite = false;
          if (p.subtitle_updated_by_user) {
            const ok = await askSubtitleOverwrite();
            if (!ok) return;
            forceOverwrite = true;
          }
          await startOneClickGenerate({ ...(opts || {}), visionAction, force: forceOverwrite });
          return;
        }
        await executeExtractScenes(opts, visionAction);
      } catch (err) {
        options.showError(err, "镜头提取失败");
      }
    },
    [options, executeExtractScenes, oneClickGenerateEnabled, askSubtitleOverwrite, startOneClickGenerate]
  );

  const onStopSceneExtraction = useCallback(async () => {
    if (isStoppingSceneExtraction) return;
    try {
      setIsStoppingSceneExtraction(true);
      await options.cancelSceneExtraction();
      options.showSuccess("正在停止镜头提取...");
    } catch (err) {
      options.showError(err, "停止镜头提取失败");
    } finally {
      setIsStoppingSceneExtraction(false);
    }
  }, [options, isStoppingSceneExtraction]);

  const onRunOmniPipeline = useCallback(async () => {
    const p = options.project;
    if (!p) return;
    if (!readSacvAuthTokenTrimmed()) {
      options.showErrorText(OMNI_PIPELINE_LICENSE_GATE_MSG);
      return;
    }
    if (!p.video_path && !p.merged_video_path) {
      options.showErrorText("请先上传视频文件");
      return;
    }
    if (!p.subtitle_path || (p.subtitle_status && p.subtitle_status !== "ready")) {
      options.showErrorText("请先提取或上传字幕（Omni 管线依赖字幕）");
      return;
    }
    if (p.omni_multimodal_json_path) {
      setOmniMultimodalChoiceModalOpen(true);
      return;
    }
    try {
      await options.runOmniPipeline({ multimodal_action: "auto" });
      options.showSuccess("Omni 管线任务已提交");
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      if (OMNI_LICENSE_ERROR_RE.test(msg)) {
        if (!isAuthenticated) options.onShowLogin?.();
        else options.onShowProfile?.();
      }
      options.showError(err, "Omni 管线失败");
    }
  }, [options, isAuthenticated]);

  const onRunOmniPipelineWithSubtitle = useCallback(async () => {
    const p = options.project;
    if (!p) return;
    if (!readSacvAuthTokenTrimmed()) {
      if (!isAuthenticated) options.onShowLogin?.();
      else options.onShowProfile?.();
      return;
    }
    if (!p.video_path && !p.merged_video_path) {
      options.showErrorText("请先上传视频文件");
      return;
    }

    const needSubtitlePhase =
      !p.subtitle_path || (Boolean(p.subtitle_status) && p.subtitle_status !== "ready");
    if (needSubtitlePhase && p.subtitle_source === "user" && Boolean(p.subtitle_path)) {
      options.showErrorText("已上传字幕，需先删除才能提取");
      return;
    }

    let subtitleForce = false;
    if (needSubtitlePhase && p.subtitle_updated_by_user) {
      const ok = await askSubtitleOverwrite();
      if (!ok) return;
      subtitleForce = true;
    }

    if (oneClickGenerateEnabled) {
      if (p.omni_multimodal_json_path) {
        setOmniMultimodalChoiceModalOpen(true);
        return;
      }
      await startOneClickGenerate({ force: subtitleForce, multimodalAction: "auto" });
      return;
    }

    if (needSubtitlePhase) {
      setExtractingSubtitle(true);
      setSubtitleExtractProgress(0);
      setSubtitleExtractLogs([]);
    }

    const isFun = subtitleAsr.provider === "fun_asr";
    const subtitleTaskId =
      globalThis.crypto &&
      "randomUUID" in globalThis.crypto &&
      typeof (globalThis.crypto as any).randomUUID === "function"
        ? (globalThis.crypto as any).randomUUID()
        : `${Date.now()}_${Math.random().toString(16).slice(2)}`;
    if (needSubtitlePhase) {
      setCurrentSubtitleTaskId(subtitleTaskId);
    }

    // 已有 Omni 多模态结果时：只按需补字幕，再由弹窗里 continue/restart 单独提交管线（与原先顺序一致）
    if (p.omni_multimodal_json_path) {
      if (needSubtitlePhase) {
        try {
          await options.extractSubtitle({
            task_id: subtitleTaskId,
            force: subtitleForce,
            asr_provider: subtitleAsr.provider,
            asr_model_key: isFun ? subtitleAsr.modelKey : null,
            asr_language: isFun ? subtitleAsr.language : "中文",
          });
          setSubtitleExtractProgress(100);
          setExtractingSubtitle(false);
          void options.refreshProject();
          void options.fetchSubtitle().catch(() => void 0);
        } catch (err) {
          options.showError(err, "提取字幕失败");
          setExtractingSubtitle(false);
          setSubtitleExtractProgress(0);
          return;
        }
      }
      setOmniMultimodalChoiceModalOpen(true);
      return;
    }

    try {
      await options.runOmniPipelineWithSubtitle({
        task_id: subtitleTaskId,
        force: subtitleForce,
        asr_provider: subtitleAsr.provider,
        asr_model_key: isFun ? subtitleAsr.modelKey : null,
        asr_language: isFun ? subtitleAsr.language : "中文",
        multimodal_action: "auto",
      });
      if (needSubtitlePhase) {
        setSubtitleExtractProgress(100);
        setExtractingSubtitle(false);
      }
      void options.refreshProject();
      void options.fetchSubtitle().catch(() => void 0);
      options.showSuccess("Omni 管线任务已提交");
    } catch (err) {
      if (needSubtitlePhase) {
        setExtractingSubtitle(false);
        setSubtitleExtractProgress(0);
      }
      const msg = err instanceof Error ? err.message : String(err);
      if (OMNI_LICENSE_ERROR_RE.test(msg)) {
        if (!isAuthenticated) options.onShowLogin?.();
        else options.onShowProfile?.();
      }
      const fallback =
        needSubtitlePhase && !/Omni|管线|license|401|403|登录/i.test(msg) ? "提取字幕或 Omni 管线失败" : "Omni 管线失败";
      options.showError(err, fallback);
    }
  }, [options, subtitleAsr, askSubtitleOverwrite, isAuthenticated, oneClickGenerateEnabled, startOneClickGenerate]);

  const onOmniMultimodalChoiceContinue = useCallback(() => {
    if (!readSacvAuthTokenTrimmed()) {
      options.showErrorText(OMNI_PIPELINE_LICENSE_GATE_MSG);
      return;
    }
    setOmniMultimodalChoiceModalOpen(false);
    if (oneClickGenerateEnabled && options.project?.project_type === "omni") {
      void startOneClickGenerate({ multimodalAction: "continue" }).catch((err) => {
        const msg = err instanceof Error ? err.message : String(err);
        if (OMNI_LICENSE_ERROR_RE.test(msg)) {
          if (!isAuthenticated) options.onShowLogin?.();
          else options.onShowProfile?.();
        }
        options.showError(err, "Omni 一键生成失败");
      });
      return;
    }
    void options
      .runOmniPipeline({ multimodal_action: "continue" })
      .then(() => options.showSuccess("Omni 管线任务已提交"))
      .catch((err) => {
        const msg = err instanceof Error ? err.message : String(err);
        if (OMNI_LICENSE_ERROR_RE.test(msg)) {
          if (!isAuthenticated) options.onShowLogin?.();
          else options.onShowProfile?.();
        }
        options.showError(err, "Omni 管线失败");
      });
  }, [options, isAuthenticated, oneClickGenerateEnabled, startOneClickGenerate]);

  const onOmniMultimodalChoiceRestart = useCallback(() => {
    if (!readSacvAuthTokenTrimmed()) {
      options.showErrorText(OMNI_PIPELINE_LICENSE_GATE_MSG);
      return;
    }
    setOmniMultimodalChoiceModalOpen(false);
    if (oneClickGenerateEnabled && options.project?.project_type === "omni") {
      void startOneClickGenerate({ force: true, multimodalAction: "restart" }).catch((err) => {
        const msg = err instanceof Error ? err.message : String(err);
        if (OMNI_LICENSE_ERROR_RE.test(msg)) {
          if (!isAuthenticated) options.onShowLogin?.();
          else options.onShowProfile?.();
        }
        options.showError(err, "Omni 一键生成失败");
      });
      return;
    }
    void options
      .runOmniPipeline({ multimodal_action: "restart" })
      .then(() => options.showSuccess("Omni 管线任务已提交"))
      .catch((err) => {
        const msg = err instanceof Error ? err.message : String(err);
        if (OMNI_LICENSE_ERROR_RE.test(msg)) {
          if (!isAuthenticated) options.onShowLogin?.();
          else options.onShowProfile?.();
        }
        options.showError(err, "Omni 管线失败");
      });
  }, [options, isAuthenticated, oneClickGenerateEnabled, startOneClickGenerate]);

  const onOmniMultimodalChoiceCancel = useCallback(() => {
    setOmniMultimodalChoiceModalOpen(false);
  }, []);

  const onStopOmniPipeline = useCallback(async () => {
    if (isStoppingOmniPipeline) return;
    try {
      setIsStoppingOmniPipeline(true);
      await options.cancelOmniPipeline();
      options.showSuccess("正在停止 Omni 管线...");
    } catch (err) {
      options.showError(err, "停止 Omni 管线失败");
    } finally {
      setIsStoppingOmniPipeline(false);
    }
  }, [options, isStoppingOmniPipeline]);

  const omniRunPipelineAuthReady = Boolean(readSacvAuthTokenTrimmed());

  return {
    omniRunPipelineAuthReady,
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
    oneClickGenerateEnabled,
    onOneClickGenerateEnabledChange,
    oneClickGenerateTarget,
    onOneClickGenerateTargetChange,
    isStartingOneClickGenerate,
    subtitleDraft,
    subtitleSaving,
    onReloadSubtitle,
    onSaveSubtitle,
    onSubtitleDraftChange: setSubtitleDraft,
    onExtractScenes,
    onStopSceneExtraction,
    isStoppingSceneExtraction,
    extractingScene: options.extractingScene,
    sceneExtractProgress: options.sceneExtractProgress,
    sceneResult: options.sceneResult,
    sceneExtractMessage: options.sceneExtractMessage,
    sceneExtractPhase: options.sceneExtractPhase,
    visionChoiceModalOpen,
    onVisionChoiceContinue,
    onVisionChoiceRestart,
    onVisionChoiceCancel,
    subtitleOverwriteModalOpen,
    onSubtitleOverwriteConfirm,
    onSubtitleOverwriteCancel,
    onRunOmniPipeline,
    onRunOmniPipelineWithSubtitle,
    onStopOmniPipeline,
    isStoppingOmniPipeline,
    extractingOmniPipeline: options.extractingOmniPipeline,
    omniPipelineProgress: options.omniPipelineProgress,
    omniPipelineMessage: options.omniPipelineMessage,
    omniPipelinePhase: options.omniPipelinePhase,
    omniPipelineShowProgressBar: options.omniPipelineShowProgressBar,
    omniPipelineCanStop: options.omniPipelineCanStop,
    omniMultimodalResult: options.omniMultimodalResult,
    omniMultimodalChoiceModalOpen,
    onOmniMultimodalChoiceContinue,
    onOmniMultimodalChoiceRestart,
    onOmniMultimodalChoiceCancel,
  };
}

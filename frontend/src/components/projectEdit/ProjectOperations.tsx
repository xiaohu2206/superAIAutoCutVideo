import { AlertCircle, Check, ChevronDown, Clipboard, FileVideo, FolderOpen, Loader, Play, Scissors, Square, X, FileText } from "lucide-react";
import React, { useEffect, useMemo, useState } from "react";
import { message } from "../../services/message";
import { projectService } from "../../services/projectService";
import { NarrationType, Project } from "../../types/project";
import { Dropdown } from "../ui/Dropdown";

interface ProjectOperationsProps {
  project: Project;
  isGeneratingCopywriting: boolean;
  handleGenerateCopywriting: () => void;
  handleStopGenerateCopywriting: () => void;
  isStoppingCopywriting: boolean;
  copywritingGenProgress: number;
  copywritingGenLogs: { timestamp: string; message: string; type?: string }[];
  isGeneratingScript: boolean;
  handleGenerateScript: () => void;
  generateScriptDisabled: boolean;
  generateScriptDisabledReason?: string;
  scriptGenProgress: number;
  scriptGenLogs: { timestamp: string; message: string; type?: string }[];
  isGeneratingVideo: boolean;
  handleGenerateVideo: () => void;
  handleStopGenerateVideo: () => void;
  isStoppingVideo: boolean;
  videoGenProgress: number;
  videoGenLogs: { timestamp: string; message: string; type?: string }[];
  isGeneratingDraft: boolean;
  handleGenerateDraft: () => void;
  handleStopGenerateDraft: () => void;
  isStoppingDraft: boolean;
  draftGenProgress: number;
  draftGenLogs: { timestamp: string; message: string; type?: string }[];
  showMergedPreview: boolean;
  setShowMergedPreview: (show: boolean) => void;
  refreshProject: () => Promise<void>;
}

const ProjectOperations: React.FC<ProjectOperationsProps> = ({
  project,
  isGeneratingCopywriting,
  handleGenerateCopywriting,
  handleStopGenerateCopywriting,
  isStoppingCopywriting,
  copywritingGenProgress,
  copywritingGenLogs,
  isGeneratingScript,
  handleGenerateScript,
  generateScriptDisabled,
  generateScriptDisabledReason,
  scriptGenProgress,
  scriptGenLogs,
  isGeneratingVideo,
  handleGenerateVideo,
  handleStopGenerateVideo,
  isStoppingVideo,
  videoGenProgress,
  videoGenLogs,
  isGeneratingDraft,
  handleGenerateDraft,
  handleStopGenerateDraft,
  isStoppingDraft,
  draftGenProgress,
  draftGenLogs,
  showMergedPreview,
  setShowMergedPreview,
  refreshProject,
}) => {
  const [outputVideoCacheBust, setOutputVideoCacheBust] = useState<number>(0);
  const [copying, setCopying] = useState(false);
  const [opening, setOpening] = useState(false);
  const [filmModalOpen, setFilmModalOpen] = useState(false);
  const [filmDraft, setFilmDraft] = useState("");
  const [savingFilmContext, setSavingFilmContext] = useState(false);
  const [copyingFilmPrompt, setCopyingFilmPrompt] = useState(false);
  const [referenceModalOpen, setReferenceModalOpen] = useState(false);
  const [referenceDraft, setReferenceDraft] = useState("");
  const [savingReference, setSavingReference] = useState(false);

  const isMovieNarration = project.narration_type === NarrationType.MOVIE;
  const hasFilmContextSaved = Boolean((project.narration_film_context || "").trim());
  const hasReferenceCopywritingSaved = Boolean((project.narration_reference_copywriting || "").trim());

  const filmExtractPrompt = useMemo(() => {
    const raw = project.video_current_name || "";
    const title = raw.replace(/\.[^./\\]+$/, "").trim() || project.name?.trim() || "电影名称";
    return `帮忙提取《${title}》这部电影的「1、电影的整体脉络简介」「2、涉及到的人物简介」，输出为 markdown 格式到代码块`;
  }, [project.video_current_name, project.name]);

  useEffect(() => {
    if (!filmModalOpen) return;
    setFilmDraft(project.narration_film_context ?? "");
  }, [filmModalOpen, project.id, project.narration_film_context]);

  useEffect(() => {
    if (!referenceModalOpen) return;
    setReferenceDraft(project.narration_reference_copywriting ?? "");
  }, [referenceModalOpen, project.id, project.narration_reference_copywriting]);

  const draftPath = project?.jianying_draft_last_dir || project?.jianying_draft_last_dir_web || "";
  const isGeneratingAny = isGeneratingCopywriting || isGeneratingScript || isGeneratingVideo || isGeneratingDraft;
  const copywritingButtonDisabled =
    !project?.video_path ||
    !project?.subtitle_path ||
    (project?.subtitle_status ? project.subtitle_status !== "ready" : false) ||
    isGeneratingAny;
  const scriptButtonDisabled =
    generateScriptDisabled || isGeneratingCopywriting || isGeneratingVideo || isGeneratingDraft || isGeneratingScript;
  const scriptButtonTitle = generateScriptDisabled
    ? (generateScriptDisabledReason || "暂不可生成脚本")
    : isGeneratingVideo
    ? "视频生成中，暂不可生成脚本"
    : isGeneratingDraft
    ? "草稿生成中，暂不可生成脚本"
    : isGeneratingCopywriting
    ? "文案生成中，暂不可生成脚本"
    : undefined;

  useEffect(() => {
    if (!isGeneratingVideo && project.output_video_path) {
      setOutputVideoCacheBust(Date.now());
    }
  }, [isGeneratingVideo, project.output_video_path]);

  const handleCopyDraftPath = async () => {
    if (!draftPath) {
      message.error("尚未生成剪映草稿");
      return;
    }
    try {
      setCopying(true);
      await navigator.clipboard.writeText(draftPath.toString());
      message.success("草稿路径已复制到剪贴板");
    } catch (e) {
      void e;
      message.error("复制失败");
    } finally {
      setCopying(false);
    }
  };

  const handleOpenDraftDir = async () => {
    if (!draftPath) {
      message.error("尚未生成剪映草稿");
      return;
    }
    try {
      setOpening(true);
      await projectService.openPathInExplorer(project.id, draftPath.toString());
      message.success("已打开文件管理器");
    } catch (e: any) {
      message.error(e?.message || "打开文件管理器失败");
    } finally {
      setOpening(false);
    }
  };

  const handleOpenFilmContextModal = (e: React.MouseEvent) => {
    e.preventDefault();
    setFilmModalOpen(true);
  };

  const handleCopyFilmPrompt = async () => {
    try {
      setCopyingFilmPrompt(true);
      await navigator.clipboard.writeText(filmExtractPrompt);
      message.success("提示词已复制");
    } catch {
      message.error("复制失败");
    } finally {
      setCopyingFilmPrompt(false);
    }
  };

  const handleSaveFilmContext = async () => {
    try {
      setSavingFilmContext(true);
      await projectService.updateProjectQueued(project.id, {
        narration_film_context: filmDraft.trim() ? filmDraft.trim() : "",
      });
      await refreshProject();
      message.success("影片信息已保存");
      setFilmModalOpen(false);
    } catch (e: any) {
      message.error(e?.message || "保存失败");
    } finally {
      setSavingFilmContext(false);
    }
  };

  const handleOpenReferenceModal = (e: React.MouseEvent) => {
    e.preventDefault();
    setReferenceModalOpen(true);
  };

  const handleSaveReferenceCopywriting = async () => {
    try {
      setSavingReference(true);
      await projectService.updateProjectQueued(project.id, {
        narration_reference_copywriting: referenceDraft.trim() ? referenceDraft.trim() : "",
      });
      await refreshProject();
      message.success("洗稿文案已保存");
      setReferenceModalOpen(false);
    } catch (e: any) {
      message.error(e?.message || "保存失败");
    } finally {
      setSavingReference(false);
    }
  };

  const handleOpenOutputVideoInExplorer = async () => {
    if (!project.output_video_path) {
      message.error("尚未生成输出视频");
      return;
    }
    try {
      setOpening(true);
      await projectService.openPathInExplorer(project.id, project.output_video_path);
      message.success("已打开文件管理器");
    } catch (e: any) {
      message.error(e?.message || "打开文件管理器失败");
    } finally {
      setOpening(false);
    }
  };

  return (
    <div className="pt-4 border-t border-gray-200 flex flex-wrap items-start gap-3">
      <div className="flex flex-col items-start space-y-2">
        <button
          onClick={handleGenerateCopywriting}
          disabled={copywritingButtonDisabled}
          className="flex items-center justify-center px-6 py-2 bg-indigo-600 text-white rounded-lg font-medium shadow-sm hover:bg-indigo-700 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {isGeneratingCopywriting ? (
            <>
              <Loader className="h-5 w-5 mr-2 animate-spin" />
              生成中...
            </>
          ) : (
            <>生成解说文案</>
          )}
        </button>
        
        {isMovieNarration && (
          <div className="flex items-center gap-2 pl-1">
            {!hasReferenceCopywritingSaved && (
              <button
                onClick={handleOpenFilmContextModal}
                className={`flex items-center gap-1.5 px-2.5 py-1 text-xs rounded-md border transition-colors ${
                  hasFilmContextSaved 
                    ? "bg-indigo-50 border-indigo-200 text-indigo-700 hover:bg-indigo-100" 
                    : "bg-white border-gray-200 text-gray-600 hover:bg-gray-50 hover:text-gray-900"
                }`}
                title="设置影片脉络与人物简介"
              >
                {hasFilmContextSaved ? <Check className="h-3.5 w-3.5" /> : <FileText className="h-3.5 w-3.5" />}
                <span>附加影片信息</span>
              </button>
            )}
            <button
              onClick={handleOpenReferenceModal}
              className={`flex items-center gap-1.5 px-2.5 py-1 text-xs rounded-md border transition-colors ${
                hasReferenceCopywritingSaved 
                  ? "bg-indigo-50 border-indigo-200 text-indigo-700 hover:bg-indigo-100" 
                  : "bg-white border-gray-200 text-gray-600 hover:bg-gray-50 hover:text-gray-900"
              }`}
              title="设置洗稿文案"
            >
              {hasReferenceCopywritingSaved ? <Check className="h-3.5 w-3.5" /> : <FileText className="h-3.5 w-3.5" />}
              <span>洗稿（推荐）</span>
            </button>
          </div>
        )}
      </div>

      <button
        onClick={handleGenerateScript}
        disabled={scriptButtonDisabled}
        title={scriptButtonTitle}
        className="flex items-center px-6 py-2 bg-violet-600 text-white rounded-lg font-medium hover:bg-violet-800 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {isGeneratingScript ? (
          <>
            <Loader className="h-5 w-5 mr-2 animate-spin" />
            生成中...
          </>
        ) : (
          <>
            生成解说脚本
          </>
        )}
      </button>

       {project.script && project.video_path && 
       <Dropdown
        disabled={isGeneratingAny}
        trigger={
          <button className="flex items-center px-6 py-2 bg-violet-600 text-white rounded-lg font-medium shadow-md hover:bg-violet-700 transition-colors">
            视频操作
            <ChevronDown className="ml-2 h-4 w-4" />
          </button>
        }
        items={[
         {
            label: (
              <>
                {isGeneratingDraft ? <Loader className="h-4 w-4 mr-2 animate-spin" /> : <Scissors className="h-4 w-4 mr-2" />}
                {isGeneratingDraft ? "生成草稿中..." : "生成剪映草稿"}
              </>
            ),
            onClick: handleGenerateDraft,
            disabled: !project.script || !project.video_path || isGeneratingAny,
          },
          {
            label: (
              <>
                {isGeneratingVideo ? <Loader className="h-4 w-4 mr-2 animate-spin" /> : <Play className="h-4 w-4 mr-2" />}
                {isGeneratingVideo ? "生成视频中..." : "生成视频"}
              </>
            ),
            onClick: handleGenerateVideo,
            disabled: !project.script || !project.video_path || isGeneratingAny,
          },
        ]}
      />
      }
      {/* 生成视频实时进度显示 */}
      {(isGeneratingCopywriting || (copywritingGenProgress > 0 && copywritingGenProgress < 100)) && (
        <div className="w-full ml-0 mt-3">
          <div className="flex items-center justify-between text-xs text-gray-600 mb-1">
            <span>文案生成进度(预计1～2分钟)</span>
            <div className="flex items-center gap-2">
              <span>{Math.round(copywritingGenProgress)}%</span>
              <button
                onClick={handleStopGenerateCopywriting}
                disabled={isStoppingCopywriting}
                title="停止生成"
                className="group flex items-center gap-1 px-2 py-0.5 rounded-md border border-gray-200 bg-white hover:bg-red-50 hover:border-red-200 hover:text-red-600 text-gray-500 transition-all shadow-sm disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isStoppingCopywriting ? (
                  <Loader className="h-3 w-3 animate-spin" />
                ) : (
                  <Square className="h-3 w-3 fill-current" />
                )}
                <span className="text-xs font-medium">停止</span>
              </button>
            </div>
          </div>
          <div className="w-full h-2 mb-2 bg-gray-200 rounded">
            <div
              className="h-2 bg-indigo-600 rounded transition-all"
              style={{ width: `${Math.round(copywritingGenProgress)}%` }}
            />
          </div>
          {copywritingGenLogs.length > 0 && (
            <div className="mb-2 space-y-1">
              {copywritingGenLogs.slice(-1).map((log, idx) => (
                <div key={`${log.timestamp}-${idx}`} className="text-xs text-gray-700 flex items-center">
                  {log.type === "error" ? (
                    <AlertCircle className="h-3 w-3 mr-1 text-red-600" />
                  ) : (
                    <Loader className="h-3 w-3 mr-1 text-indigo-600" />
                  )}
                  <span className="break-all">{log.message}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* 生成视频实时进度显示 */}
      {(isGeneratingVideo || (videoGenProgress > 0 && videoGenProgress < 100)) && (
        <div className="w-full mt-3">
          <div className="flex items-center justify-between text-xs text-gray-600 mb-1">
            <span>视频生成进度</span>
            <div className="flex items-center gap-2">
              <span>{Math.round(videoGenProgress)}%</span>
              <button
                onClick={handleStopGenerateVideo}
                disabled={isStoppingVideo}
                title="停止生成"
                className="group flex items-center gap-1 px-2 py-0.5 rounded-md border border-gray-200 bg-white hover:bg-red-50 hover:border-red-200 hover:text-red-600 text-gray-500 transition-all shadow-sm disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isStoppingVideo ? (
                  <Loader className="h-3 w-3 animate-spin" />
                ) : (
                  <Square className="h-3 w-3 fill-current" />
                )}
                <span className="text-xs font-medium">停止</span>
              </button>
            </div>
          </div>
          <div className="w-full h-2 bg-gray-200 rounded">
            <div
              className="h-2 bg-blue-600 rounded transition-all"
              style={{ width: `${Math.round(videoGenProgress)}%` }}
            />
          </div>
          {/* 步骤日志 */}
          {videoGenLogs.length > 0 && (
            <div className="mt-2 space-y-1">
              {videoGenLogs.slice(-1).map((log, idx) => (
                <div key={`${log.timestamp}-${idx}`} className="text-xs text-gray-700 flex items-center">
                  {log.type === "error" ? (
                    <AlertCircle className="h-3 w-3 mr-1 text-red-600" />
                  ) : (
                    <Loader className="h-3 w-3 mr-1 text-blue-600" />
                  )}
                  <span className="break-all">{log.message}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {(isGeneratingDraft || (draftGenProgress > 0 && draftGenProgress < 100)) && (
        <div className="w-full mt-3">
          <div className="flex items-center justify-between text-xs text-gray-600 mb-1">
            <span>剪映草稿生成进度</span>
            <div className="flex items-center gap-2">
              <span>{Math.round(draftGenProgress)}%</span>
              <button
                onClick={handleStopGenerateDraft}
                disabled={isStoppingDraft}
                title="停止生成"
                className="group flex items-center gap-1 px-2 py-0.5 rounded-md border border-gray-200 bg-white hover:bg-red-50 hover:border-red-200 hover:text-red-600 text-gray-500 transition-all shadow-sm disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isStoppingDraft ? (
                  <Loader className="h-3 w-3 animate-spin" />
                ) : (
                  <Square className="h-3 w-3 fill-current" />
                )}
                <span className="text-xs font-medium">停止</span>
              </button>
            </div>
          </div>
          <div className="w-full h-2 bg-gray-200 rounded">
            <div
              className="h-2 bg-blue-600 rounded transition-all"
              style={{ width: `${Math.round(draftGenProgress)}%` }}
            />
          </div>
          {draftGenLogs.length > 0 && (
            <div className="mt-2 space-y-1">
              {draftGenLogs.slice(-1).map((log, idx) => (
                <div key={`${log.timestamp}-${idx}`} className="text-xs text-gray-700 flex items-center">
                  {log.type === "error" ? (
                    <AlertCircle className="h-3 w-3 mr-1 text-red-600" />
                  ) : (
                    <Loader className="h-3 w-3 mr-1 text-blue-600" />
                  )}
                  <span className="break-all">{log.message}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* 合并视频预览弹窗 */}
      {filmModalOpen && (
        <div className="fixed inset-0 z-[55] overflow-y-auto">
          <div className="fixed inset-0 bg-black/60 backdrop-blur-sm transition-opacity" onClick={() => setFilmModalOpen(false)} />
          <div className="flex items-center justify-center min-h-screen p-4">
            <div
              className="relative bg-white rounded-xl shadow-2xl w-full max-w-3xl flex flex-col max-h-[90vh] ring-1 ring-black/5"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center justify-between p-5 border-b border-gray-100 shrink-0">
                <h3 className="text-lg font-semibold text-gray-900">附加影片信息</h3>
                <button
                  type="button"
                  onClick={() => setFilmModalOpen(false)}
                  className="text-gray-400 hover:text-gray-600 hover:bg-gray-100 p-1.5 rounded-lg transition-colors"
                  aria-label="关闭"
                >
                  <X className="h-5 w-5" />
                </button>
              </div>
              <div className="p-6 space-y-5 text-sm text-gray-700 overflow-y-auto">
                <p className="leading-relaxed text-gray-600 text-base">
                  请复制下方提示词，打开{" "}
                  <a
                    href="https://doubao.com/"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-indigo-600 hover:text-indigo-700 font-medium hover:underline"
                  >
                    豆包
                  </a>
                  或{" "}
                  <a
                    href="https://chatgpt.com"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-indigo-600 hover:text-indigo-700 font-medium hover:underline"
                  >
                    ChatGPT
                  </a>
                  的网页对话，将模型回复的影片信息粘贴到下方输入框，保存后即可在生成解说文案时自动带上。
                </p>
                <div className="bg-gray-50/50 rounded-lg p-4 border border-gray-100">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-sm font-medium text-gray-700">可复制提示词</span>
                    <button
                      type="button"
                      onClick={handleCopyFilmPrompt}
                      disabled={copyingFilmPrompt}
                      className="text-xs flex items-center gap-1.5 px-2.5 py-1.5 rounded-md border border-gray-200 bg-white hover:bg-gray-50 text-gray-600 transition-colors disabled:opacity-50 shadow-sm"
                    >
                      {copyingFilmPrompt ? <Loader className="h-4 w-4 animate-spin" /> : <Clipboard className="h-4 w-4" />}
                      复制提示词
                    </button>
                  </div>
                  <pre className="text-sm bg-white border border-gray-200 rounded-md p-3.5 whitespace-pre-wrap break-words max-h-40 overflow-y-auto text-gray-600 font-mono shadow-sm">
                    {filmExtractPrompt}
                  </pre>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">影片信息（粘贴模型输出）</label>
                  <textarea
                    value={filmDraft}
                    onChange={(e) => setFilmDraft(e.target.value)}
                    rows={12}
                    placeholder="将豆包 / ChatGPT 返回的影片脉络与人物简介粘贴到这里…"
                    className="w-full border border-gray-300 rounded-lg px-4 py-3 text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition-shadow shadow-sm placeholder:text-gray-400 resize-y"
                  />
                </div>
              </div>
              <div className="flex justify-end gap-3 p-5 border-t border-gray-100 bg-gray-50/50 rounded-b-xl shrink-0">
                <button
                  type="button"
                  onClick={() => setFilmModalOpen(false)}
                  className="px-4 py-2 text-gray-700 bg-white border border-gray-300 rounded-lg text-sm font-medium hover:bg-gray-50 transition-colors shadow-sm"
                >
                  取消
                </button>
                <button
                  type="button"
                  onClick={handleSaveFilmContext}
                  disabled={savingFilmContext}
                  className="px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700 transition-colors disabled:opacity-50 flex items-center gap-2 shadow-sm"
                >
                  {savingFilmContext ? <Loader className="h-4 w-4 animate-spin" /> : null}
                  保存并关闭
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {referenceModalOpen && (
        <div className="fixed inset-0 z-[55] overflow-y-auto">
          <div className="fixed inset-0 bg-black/60 backdrop-blur-sm transition-opacity" onClick={() => setReferenceModalOpen(false)} />
          <div className="flex items-center justify-center min-h-screen p-4">
            <div
              className="relative bg-white rounded-xl shadow-2xl w-full max-w-3xl flex flex-col max-h-[90vh] ring-1 ring-black/5"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center justify-between p-5 border-b border-gray-100 shrink-0">
                <h3 className="text-lg font-semibold text-gray-900">洗稿</h3>
                <button
                  type="button"
                  onClick={() => setReferenceModalOpen(false)}
                  className="text-gray-400 hover:text-gray-600 hover:bg-gray-100 p-1.5 rounded-lg transition-colors"
                  aria-label="关闭"
                >
                  <X className="h-5 w-5" />
                </button>
              </div>
              <div className="p-6 space-y-4 text-sm text-gray-700 overflow-y-auto">
                <div className="bg-blue-50/50 border border-blue-100 rounded-lg p-4">
                  <p className="leading-relaxed text-blue-800 text-sm">
                    在抖音提取这个解说影片的文案，直接复制进来，会帮你把字幕部分去掉，简单润色，效果比直接生成好。
                  </p>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">参考文案全文</label>
                  <textarea
                    value={referenceDraft}
                    onChange={(e) => setReferenceDraft(e.target.value)}
                    rows={16}
                    placeholder="粘贴参考文案…"
                    className="w-full border border-gray-300 rounded-lg px-4 py-3 text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition-shadow shadow-sm placeholder:text-gray-400 resize-y"
                  />
                </div>
              </div>
              <div className="flex justify-end gap-3 p-5 border-t border-gray-100 bg-gray-50/50 rounded-b-xl shrink-0">
                <button
                  type="button"
                  onClick={() => setReferenceModalOpen(false)}
                  className="px-4 py-2 text-gray-700 bg-white border border-gray-300 rounded-lg text-sm font-medium hover:bg-gray-50 transition-colors shadow-sm"
                >
                  取消
                </button>
                <button
                  type="button"
                  onClick={handleSaveReferenceCopywriting}
                  disabled={savingReference}
                  className="px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700 transition-colors disabled:opacity-50 flex items-center gap-2 shadow-sm"
                >
                  {savingReference ? <Loader className="h-4 w-4 animate-spin" /> : null}
                  保存并关闭
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {showMergedPreview && project?.merged_video_path && (
        <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center">
          <div className="bg-white rounded-lg shadow-xl w-full max-w-3xl mx-4">
            <div className="flex items-center justify-between p-3 border-b">
              <div className="flex items-center text-sm font-medium text-gray-800">
                <FileVideo className="h-4 w-4 mr-1" /> 合并视频预览
              </div>
              <button
                onClick={() => setShowMergedPreview(false)}
                className="text-gray-600 hover:text-gray-900"
                title="关闭预览"
              >
                ✕
              </button>
            </div>
            <div className="p-3">
              <video
                key={project.merged_video_path}
                src={projectService.getWebFileUrl(project.merged_video_path, outputVideoCacheBust)}
                controls
                className="w-full rounded-lg bg-black max-h-[70vh]"
                preload="metadata"
              />
            </div>
          </div>
        </div>
      )}
      {/* 生成脚本实时进度显示 */}
      {(isGeneratingScript || (scriptGenProgress > 0 && scriptGenProgress < 100)) && (
        <div className="w-full ml-0 mt-3">
          <div className="flex items-center justify-between text-xs text-gray-600 mb-1">
            <span>脚本生成进度(预计3～5分钟)</span>
            <span>{Math.round(scriptGenProgress)}%</span>
          </div>
          <div className="w-full h-2 mb-2 bg-gray-200 rounded">
            <div
              className="h-2 bg-blue-600 rounded transition-all"
              style={{ width: `${Math.round(scriptGenProgress)}%` }}
            />
          </div>
          {/* 步骤日志 */}
          {scriptGenLogs.length > 0 && (
            <div className="mb-2 space-y-1">
              {scriptGenLogs.slice(-1).map((log, idx) => (
                <div key={`${log.timestamp}-${idx}`} className="text-xs text-gray-700 flex items-center">
                  {log.type === "error" ? (
                    <AlertCircle className="h-3 w-3 mr-1 text-red-600" />
                  ) : (
                    <Loader className="h-3 w-3 mr-1 text-blue-600" />
                  )}
                  <span className="break-all">{log.message}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
     
      {(draftPath || project.output_video_path) && (
        <div className="w-full mt-4 bg-gray-50 rounded-lg border border-gray-200 divide-y divide-gray-200 overflow-hidden">
          {/* 草稿目录 */}
          {draftPath && (
            <div className="px-4 py-3 flex items-center justify-between hover:bg-gray-100 transition-colors">
              <div className="flex items-center min-w-0 mr-4 overflow-hidden">
                <FolderOpen className="h-4 w-4 text-gray-500 mr-2 flex-shrink-0" />
                <span className="text-xs font-medium text-gray-500 mr-2 flex-shrink-0">草稿路径:</span>
                <span className="text-xs text-gray-700 truncate font-mono select-all" title={draftPath.toString()}>
                  {draftPath.toString()}
                </span>
              </div>
              <div className="flex items-center space-x-1 flex-shrink-0">
                <button
                  onClick={handleCopyDraftPath}
                  className={`p-1.5 rounded-md transition-all ${
                    copying 
                      ? "bg-green-100 text-green-600" 
                      : "text-gray-400 hover:text-gray-700 hover:bg-gray-200"
                  }`}
                  title="复制路径"
                >
                  {copying ? <Check className="h-3.5 w-3.5" /> : <Clipboard className="h-3.5 w-3.5" />}
                </button>
                <button
                  onClick={handleOpenDraftDir}
                  className="p-1.5 text-gray-400 hover:text-blue-600 hover:bg-blue-50 rounded-md transition-all"
                  title="打开文件管理器"
                >
                  {opening ? <Loader className="h-3.5 w-3.5 animate-spin" /> : <FolderOpen className="h-3.5 w-3.5" />}
                </button>
              </div>
            </div>
          )}

          {/* 输出视频 */}
          {project.output_video_path && (
            <div className="px-4 py-3 flex items-center justify-between hover:bg-gray-100 transition-colors">
              <div className="flex items-center min-w-0 overflow-hidden">
                <FileVideo className="h-4 w-4 text-blue-500 mr-2 flex-shrink-0" />
                <span className="text-xs font-medium text-gray-500 mr-2 flex-shrink-0">成品:</span>
                <button
                  onClick={handleOpenOutputVideoInExplorer}
                  className="text-xs text-blue-600 hover:text-blue-700 hover:underline truncate font-medium text-left"
                  title="在文件管理器中定位"
                >
                  {project.output_video_path.split("/").pop()}
                </button>
              </div>
              <button
                onClick={handleOpenOutputVideoInExplorer}
                className="ml-2 text-xs px-2 py-1 text-gray-600 rounded hover:bg-blue-50 hover:text-blue-600 hover:border-blue-200 transition-all shadow-sm"
              >
                <FolderOpen className="h-3.5 w-3.5" />
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default ProjectOperations;

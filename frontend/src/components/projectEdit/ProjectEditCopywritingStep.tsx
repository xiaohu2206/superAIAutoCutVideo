import { AlertCircle, ArrowRight, Loader, Square } from "lucide-react";
import React, { useState } from "react";
import type { Project } from "../../types/project";
import type { WsProgressLog } from "../../hooks/useWsTaskProgress";
import CopywritingAdvancedConfig from "./advancedConfig/CopywritingAdvancedConfig";
import CopywritingSection from "./CopywritingSection";
import { message } from "../../services/message";
import { Check, FileText, X } from "lucide-react";
import { projectService } from "../../services/projectService";
import { NarrationType } from "../../types/project";

interface ProjectEditCopywritingStepProps {
  project: Project;
  refreshProject: () => Promise<void>;
  projectTaskBusy?: boolean;

  isGeneratingCopywriting: boolean;
  handleGenerateCopywriting: () => void;
  handleStopGenerateCopywriting: () => void;
  isStoppingCopywriting: boolean;
  copywritingGenProgress: number;
  copywritingGenLogs: WsProgressLog[];

  editedCopywriting: string;
  setEditedCopywriting: (copywriting: string) => void;
  isSavingCopywriting: boolean;
  handleSaveCopywriting: (content?: string) => void;

  onGoToGenerateStep: () => void;
}

const ProjectEditCopywritingStep: React.FC<ProjectEditCopywritingStepProps> = ({
  project,
  refreshProject,
  projectTaskBusy = false,
  isGeneratingCopywriting,
  handleGenerateCopywriting,
  handleStopGenerateCopywriting,
  isStoppingCopywriting,
  copywritingGenProgress,
  copywritingGenLogs,
  editedCopywriting,
  setEditedCopywriting,
  isSavingCopywriting,
  handleSaveCopywriting,
  onGoToGenerateStep,
}) => {
  const [showAdvancedConfig, setShowAdvancedConfig] = React.useState(false);
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
  const hasCopywriting = Boolean(project?.narration_copywriting?.content);

  const filmExtractPrompt = React.useMemo(() => {
    const raw = project.video_current_name || "";
    const title = raw.replace(/\.[^./\\]+$/, "").trim() || project.name?.trim() || "电影名称";
    return `帮忙提取《${title}》这部电影的「1、电影的整体脉络简介」「2、涉及到的人物简介」，输出为 markdown 格式到代码块`;
  }, [project.video_current_name, project.name]);

  React.useEffect(() => {
    if (!filmModalOpen) return;
    setFilmDraft(project.narration_film_context ?? "");
  }, [filmModalOpen, project.id, project.narration_film_context]);

  React.useEffect(() => {
    if (!referenceModalOpen) return;
    setReferenceDraft(project.narration_reference_copywriting ?? "");
  }, [referenceModalOpen, project.id, project.narration_reference_copywriting]);

  const copywritingButtonDisabled =
    !project?.video_path ||
    !project?.subtitle_path ||
    (project?.subtitle_status ? project.subtitle_status !== "ready" : false) ||
    projectTaskBusy ||
    isGeneratingCopywriting;
  const copywritingDisabledReason =
    projectTaskBusy
      ? "当前项目已有任务在队列中，请等待完成后再操作"
      : isGeneratingCopywriting
      ? "解说文案生成中，请等待完成"
      : !project?.video_path
      ? "请先上传视频文件"
      : !project?.subtitle_path
      ? "请先提取或上传字幕"
      : project?.subtitle_status && project.subtitle_status !== "ready"
      ? "字幕尚未就绪，请等待字幕处理完成"
      : undefined;

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

  return (
    <>
      <div className="bg-white rounded-lg shadow-md p-6 space-y-6 dark:border dark:border-[#2a2a2a] dark:bg-[#1f1f1f] dark:shadow-black/30">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-zinc-100">文案生成</h2>
          <button
            onClick={() => setShowAdvancedConfig((v) => !v)}
            className="text-blue-600 hover:text-blue-800 text-sm dark:text-blue-300 dark:hover:text-blue-200"
          >
            <span className="text-xs text-gray-500 dark:text-zinc-400">（解说文案字数、解说风格）</span>
            高级配置
          </button>
        </div>

        {showAdvancedConfig && (
          <CopywritingAdvancedConfig
            projectId={project.id}
            narrationType={project.narration_type}
            hasReferenceCopywriting={Boolean((project.narration_reference_copywriting || "").trim())}
          />
        )}

        <div className="pt-4 border-t border-gray-200 flex flex-wrap items-start gap-3 dark:border-[#2a2a2a]">
          <div className="flex flex-col items-start space-y-2">
            <button
              onClick={() => {
                if (copywritingButtonDisabled) {
                  message.warning(copywritingDisabledReason || "当前不可生成文案");
                  return;
                }
                handleGenerateCopywriting();
              }}
              aria-disabled={copywritingButtonDisabled}
              className={`flex items-center justify-center px-6 py-2 bg-indigo-600 text-white rounded-lg font-medium shadow-sm hover:bg-indigo-700 transition-all ${copywritingButtonDisabled ? "opacity-50 cursor-not-allowed" : ""}`}
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
                    onClick={() => setFilmModalOpen(true)}
                    className={`flex items-center gap-1.5 px-2.5 py-1 text-xs rounded-md border transition-colors ${
                      hasFilmContextSaved
                        ? "bg-indigo-50 border-indigo-200 text-indigo-700 hover:bg-indigo-100 dark:border-indigo-400/20 dark:bg-indigo-500/10 dark:text-indigo-300 dark:hover:bg-indigo-500/15"
                        : "bg-white border-gray-200 text-gray-600 hover:bg-gray-50 hover:text-gray-900 dark:border-[#2a2a2a] dark:bg-[#242424] dark:text-zinc-300 dark:hover:bg-white/10 dark:hover:text-zinc-100"
                    }`}
                    title="设置影片脉络与人物简介"
                  >
                    {hasFilmContextSaved ? <Check className="h-3.5 w-3.5" /> : <FileText className="h-3.5 w-3.5" />}
                    <span>附加影片信息</span>
                  </button>
                )}
                <button
                  onClick={() => setReferenceModalOpen(true)}
                  className={`flex items-center gap-1.5 px-2.5 py-1 text-xs rounded-md border transition-colors ${
                    hasReferenceCopywritingSaved
                      ? "bg-indigo-50 border-indigo-200 text-indigo-700 hover:bg-indigo-100 dark:border-indigo-400/20 dark:bg-indigo-500/10 dark:text-indigo-300 dark:hover:bg-indigo-500/15"
                      : "bg-white border-gray-200 text-gray-600 hover:bg-gray-50 hover:text-gray-900 dark:border-[#2a2a2a] dark:bg-[#242424] dark:text-zinc-300 dark:hover:bg-white/10 dark:hover:text-zinc-100"
                  }`}
                  title="设置洗稿文案"
                >
                  {hasReferenceCopywritingSaved ? <Check className="h-3.5 w-3.5" /> : <FileText className="h-3.5 w-3.5" />}
                  <span>洗稿（推荐）</span>
                </button>
              </div>
            )}
          </div>

          {/* 文案生成进度 */}
          {isGeneratingCopywriting && (
            <div className="w-full ml-0 mt-3">
              <div className="flex items-center justify-between text-xs text-gray-600 mb-1 dark:text-zinc-400">
                <span>文案生成进度(预计1～2分钟)</span>
                <div className="flex items-center gap-2">
                  <span>{Math.round(copywritingGenProgress)}%</span>
                  <button
                    onClick={handleStopGenerateCopywriting}
                    disabled={isStoppingCopywriting}
                    title="停止生成"
                    className="group flex items-center gap-1 px-2 py-0.5 rounded-md border border-gray-200 bg-white hover:bg-red-50 hover:border-red-200 hover:text-red-600 text-gray-500 transition-all shadow-sm disabled:opacity-50 disabled:cursor-not-allowed dark:border-[#2a2a2a] dark:bg-white/5 dark:text-zinc-400 dark:hover:border-red-400/30 dark:hover:bg-red-500/10 dark:hover:text-red-300"
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
              <div className="w-full h-2 mb-2 bg-gray-200 rounded dark:bg-white/10">
                <div
                  className="h-2 bg-indigo-600 rounded transition-all"
                  style={{ width: `${Math.round(copywritingGenProgress)}%` }}
                />
              </div>
              {copywritingGenLogs.length > 0 && (
                <div className="mb-2 space-y-1">
                  {copywritingGenLogs.slice(-1).map((log, idx) => (
                    <div key={`${log.timestamp}-${idx}`} className="text-xs text-gray-700 flex items-center dark:text-zinc-300">
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
        </div>
      </div>

      {/* 文案编辑区 */}
      <div className="bg-white rounded-lg shadow-md p-6 space-y-4 dark:border dark:border-[#2a2a2a] dark:bg-[#1f1f1f] dark:shadow-black/30">
        <CopywritingSection
          editedCopywriting={editedCopywriting}
          setEditedCopywriting={setEditedCopywriting}
          isSavingCopywriting={isSavingCopywriting}
          handleSaveCopywriting={handleSaveCopywriting}
        />

        {/* 进入下一步按钮 */}
        {hasCopywriting && (
          <div className="pt-4 border-t border-gray-200 flex justify-end dark:border-[#2a2a2a]">
            <button
              onClick={onGoToGenerateStep}
              className="flex items-center px-6 py-2.5 bg-blue-600 text-white rounded-lg font-medium shadow-sm hover:bg-blue-700 transition-all"
            >
              生成视频
              <ArrowRight className="h-4 w-4 ml-2" />
            </button>
          </div>
        )}
      </div>

      {/* 附加影片信息弹窗 */}
      {filmModalOpen && (
        <div className="fixed inset-0 z-[55] overflow-y-auto">
          <div className="fixed inset-0 bg-black/60 backdrop-blur-sm transition-opacity" onClick={() => setFilmModalOpen(false)} />
          <div className="flex items-center justify-center min-h-screen p-4">
            <div
              className="relative bg-white rounded-xl shadow-2xl w-full max-w-3xl flex flex-col max-h-[90vh] ring-1 ring-black/5 dark:border dark:border-[#2a2a2a] dark:bg-[#1f1f1f] dark:ring-[#2a2a2a] dark:shadow-black/50"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center justify-between p-5 border-b border-gray-100 shrink-0 dark:border-[#2a2a2a]">
                <h3 className="text-lg font-semibold text-gray-900 dark:text-zinc-100">附加影片信息</h3>
                <button
                  type="button"
                  onClick={() => setFilmModalOpen(false)}
                  className="text-gray-400 hover:text-gray-600 hover:bg-gray-100 p-1.5 rounded-lg transition-colors dark:text-zinc-500 dark:hover:bg-white/10 dark:hover:text-zinc-100"
                  aria-label="关闭"
                >
                  <X className="h-5 w-5" />
                </button>
              </div>
              <div className="p-6 space-y-5 text-sm text-gray-700 overflow-y-auto dark:text-zinc-300">
                <p className="leading-relaxed text-gray-600 text-base dark:text-zinc-300">
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
                <div className="bg-gray-50/50 rounded-lg p-4 border border-gray-100 dark:border-[#2a2a2a] dark:bg-[#181818]">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-sm font-medium text-gray-700 dark:text-zinc-200">可复制提示词</span>
                    <button
                      type="button"
                      onClick={handleCopyFilmPrompt}
                      disabled={copyingFilmPrompt}
                      className="text-xs flex items-center gap-1.5 px-2.5 py-1.5 rounded-md border border-gray-200 bg-white hover:bg-gray-50 text-gray-600 transition-colors disabled:opacity-50 shadow-sm dark:border-[#2a2a2a] dark:bg-white/5 dark:text-zinc-300 dark:hover:bg-white/10"
                    >
                      {copyingFilmPrompt ? <Loader className="h-4 w-4 animate-spin" /> : null}
                      复制提示词
                    </button>
                  </div>
                  <pre className="text-sm bg-white border border-gray-200 rounded-md p-3.5 whitespace-pre-wrap break-words max-h-40 overflow-y-auto text-gray-600 font-mono shadow-sm dark:border-[#2a2a2a] dark:bg-[#242424] dark:text-zinc-300">
                    {filmExtractPrompt}
                  </pre>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2 dark:text-zinc-200">影片信息（粘贴模型输出）</label>
                  <textarea
                    value={filmDraft}
                    onChange={(e) => setFilmDraft(e.target.value)}
                    rows={12}
                    placeholder="将豆包 / ChatGPT 返回的影片脉络与人物简介粘贴到这里…"
                    className="w-full border border-gray-300 rounded-lg px-4 py-3 text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition-shadow shadow-sm placeholder:text-gray-400 resize-y dark:border-[#2a2a2a] dark:bg-[#242424] dark:text-zinc-100 dark:placeholder:text-zinc-500 dark:focus:ring-indigo-500/30"
                  />
                </div>
              </div>
              <div className="flex justify-end gap-3 p-5 border-t border-gray-100 bg-gray-50/50 rounded-b-xl shrink-0 dark:border-[#2a2a2a] dark:bg-[#181818]">
                <button
                  type="button"
                  onClick={() => setFilmModalOpen(false)}
                  className="px-4 py-2 text-gray-700 bg-white border border-gray-300 rounded-lg text-sm font-medium hover:bg-gray-50 transition-colors shadow-sm dark:border-[#2a2a2a] dark:bg-white/5 dark:text-zinc-100 dark:hover:bg-white/10"
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

      {/* 洗稿弹窗 */}
      {referenceModalOpen && (
        <div className="fixed inset-0 z-[55] overflow-y-auto">
          <div className="fixed inset-0 bg-black/60 backdrop-blur-sm transition-opacity" onClick={() => setReferenceModalOpen(false)} />
          <div className="flex items-center justify-center min-h-screen p-4">
            <div
              className="relative bg-white rounded-xl shadow-2xl w-full max-w-3xl flex flex-col max-h-[90vh] ring-1 ring-black/5 dark:border dark:border-[#2a2a2a] dark:bg-[#1f1f1f] dark:ring-[#2a2a2a] dark:shadow-black/50"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center justify-between p-5 border-b border-gray-100 shrink-0 dark:border-[#2a2a2a]">
                <h3 className="text-lg font-semibold text-gray-900 dark:text-zinc-100">洗稿</h3>
                <button
                  type="button"
                  onClick={() => setReferenceModalOpen(false)}
                  className="text-gray-400 hover:text-gray-600 hover:bg-gray-100 p-1.5 rounded-lg transition-colors dark:text-zinc-500 dark:hover:bg-white/10 dark:hover:text-zinc-100"
                  aria-label="关闭"
                >
                  <X className="h-5 w-5" />
                </button>
              </div>
              <div className="p-6 space-y-4 text-sm text-gray-700 overflow-y-auto dark:text-zinc-300">
                <div className="bg-blue-50/50 border border-blue-100 rounded-lg p-4 dark:border-blue-400/20 dark:bg-blue-500/10">
                  <p className="leading-relaxed text-blue-800 text-sm dark:text-blue-200">
                    在抖音提取这个解说影片的文案，直接复制进来，会帮你把字幕部分去掉，简单润色，效果比直接生成好。
                  </p>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2 dark:text-zinc-200">参考文案全文</label>
                  <textarea
                    value={referenceDraft}
                    onChange={(e) => setReferenceDraft(e.target.value)}
                    rows={16}
                    placeholder="粘贴参考文案…"
                    className="w-full border border-gray-300 rounded-lg px-4 py-3 text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition-shadow shadow-sm placeholder:text-gray-400 resize-y dark:border-[#2a2a2a] dark:bg-[#242424] dark:text-zinc-100 dark:placeholder:text-zinc-500 dark:focus:ring-indigo-500/30"
                  />
                </div>
              </div>
              <div className="flex justify-end gap-3 p-5 border-t border-gray-100 bg-gray-50/50 rounded-b-xl shrink-0 dark:border-[#2a2a2a] dark:bg-[#181818]">
                <button
                  type="button"
                  onClick={() => setReferenceModalOpen(false)}
                  className="px-4 py-2 text-gray-700 bg-white border border-gray-300 rounded-lg text-sm font-medium hover:bg-gray-50 transition-colors shadow-sm dark:border-[#2a2a2a] dark:bg-white/5 dark:text-zinc-100 dark:hover:bg-white/10"
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
    </>
  );
};

export default ProjectEditCopywritingStep;

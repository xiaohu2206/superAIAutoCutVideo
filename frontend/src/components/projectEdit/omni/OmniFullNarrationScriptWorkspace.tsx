import { Loader, Mic } from "lucide-react";
import React, { useCallback } from "react";
import type { Project, VideoScript } from "../../../types/project";
import { useOmniScriptTts } from "../../../hooks/omni/useOmniScriptTts";
import { useOmniScriptWorkspace } from "../../../hooks/omni/useOmniScriptWorkspace";
import OmniScriptPreviewPanel from "./OmniScriptPreviewPanel";
import OmniScriptSegmentList from "./OmniScriptSegmentList";
import ShotPickerModal from "./ShotPickerModal";

export interface OmniFullNarrationScriptWorkspaceProps {
  project: Project;
  editedScript: string;
  setEditedScript: (script: string) => void;
  setEditedScriptFromServer?: (script: string) => void;
  onSegmentTtsQueueActive?: (active: boolean) => void;
  syncScriptToServer?: (scriptOverride?: VideoScript) => Promise<VideoScript | null>;
  scriptDirty?: boolean;
  segmentTtsQueueActive?: boolean;
  isSaving: boolean;
  refreshProject: () => Promise<void>;
}

const OmniFullNarrationScriptWorkspace: React.FC<OmniFullNarrationScriptWorkspaceProps> = ({
  project,
  editedScript,
  setEditedScript,
  setEditedScriptFromServer,
  onSegmentTtsQueueActive,
  syncScriptToServer,
  scriptDirty = false,
  segmentTtsQueueActive = false,
  isSaving,
  refreshProject,
}) => {
  const workspace = useOmniScriptWorkspace({
    project,
    editedScript,
    setEditedScript,
    syncScriptToServer,
    segmentTtsQueueActive,
  });
  const { parsed, script } = workspace;

  const scriptTts = useOmniScriptTts({
    project,
    script,
    editedScript,
    setEditedScript,
    setEditedScriptFromServer,
    onSegmentTtsQueueActive,
    syncScriptToServer,
    scriptDirty,
    isSaving,
    refreshProject,
    textHashes: workspace.textHashes,
  });

  const handleRedubSegment = useCallback(
    async (index: number) => {
      const data = await scriptTts.handleSegmentTts(index);
      if (data?.tts_audio_path) {
        workspace.playSegmentTts(index);
      }
    },
    [scriptTts, workspace]
  );

  if (!script || parsed.error) {
    return (
      <div className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Omni 解说脚本（JSON）</h2>
          <span className="text-xs text-gray-500 dark:text-gray-400">
            {isSaving ? (
              <span className="inline-flex items-center gap-1">
                <Loader className="h-3.5 w-3.5 animate-spin" />
                正在保存…
              </span>
            ) : (
              "修改后自动保存"
            )}
          </span>
        </div>
        {parsed.error ? (
          <div className="p-3 bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-800 rounded-lg text-sm text-red-700 dark:text-red-300">
            JSON 解析失败：{parsed.error}
          </div>
        ) : null}
        <textarea
          value={editedScript}
          onChange={(e) => setEditedScript(e.target.value)}
          placeholder="脚本数据将以 JSON 格式显示在这里..."
          className="w-full h-[600px] px-4 py-3 font-mono text-sm text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-900 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-violet-500 focus:border-transparent outline-none transition-all resize-none"
        />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Omni 镜头校对工作区</h2>
          <p className="text-sm text-gray-600 dark:text-gray-400">选择镜头会更新时间段与 shot_id，修改后自动保存。</p>
        </div>
        <div className="flex flex-wrap items-center gap-2 shrink-0">
          <button
            type="button"
            onClick={() => void scriptTts.handleBulkTts()}
            disabled={Boolean(scriptTts.bulkDisabledReason)}
            title={
              scriptTts.bulkDisabledReason ||
              (scriptTts.allDubbed
                ? "重新为所有解说段生成配音（保留单条手动配音）"
                : "为未配音的解说段批量生成配音")
            }
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm bg-violet-600 text-white hover:bg-violet-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {scriptTts.bulkBusy ? (
              <Loader className="h-4 w-4 animate-spin" />
            ) : (
              <Mic className="h-4 w-4" />
            )}
            {scriptTts.bulkBusy
              ? `${scriptTts.bulkButtonLabel} ${Math.round(scriptTts.bulkProgress)}%`
              : scriptTts.bulkButtonLabel}
          </button>
          <span className="text-xs text-gray-500 dark:text-gray-400">
            {isSaving ? (
              <span className="inline-flex items-center gap-1.5">
                <Loader className="h-3.5 w-3.5 animate-spin" />
                正在保存…
              </span>
            ) : (
              "已开启自动保存"
            )}
          </span>
        </div>
      </div>
      {scriptTts.bulkBusy ? (
        <div className="h-1.5 rounded-full bg-gray-200 dark:bg-gray-700 overflow-hidden">
          <div
            className="h-full bg-violet-600 transition-all duration-300"
            style={{ width: `${Math.min(100, scriptTts.bulkProgress)}%` }}
          />
        </div>
      ) : null}
      <p className="text-xs text-gray-500 dark:text-gray-400">
        {scriptTts.allDubbed
          ? "已全部配音，可点「重新配音」整批重跑（单条手动配音仍会保留）。播放镜头时以配音时长为准。"
          : "已有有效配音的段落会保留；修改解说文案后需重新配音。播放镜头时以配音时长为准。"}
      </p>

      <div className="grid grid-cols-1 xl:grid-cols-[420px_minmax(0,1fr)] gap-5">
        <OmniScriptPreviewPanel
          videoRef={workspace.videoRef}
          ttsAudioRef={workspace.ttsAudioRef}
          videoUrl={workspace.videoUrl}
          selectedSegment={workspace.selectedSegment}
          selectedIndex={workspace.selectedIndex}
          segmentsCount={workspace.segments.length}
          selectedTextHash={workspace.textHashes[workspace.selectedIndex]}
          isSequencePlaying={workspace.isSequencePlaying}
          playbackRate={workspace.playbackRate}
          onPlaybackRateChange={workspace.setPlaybackRate}
          onPlayAdjacent={workspace.playAdjacentSegment}
          onToggleSequencePlayback={workspace.toggleSequencePlayback}
          onPlaySegmentTts={() => workspace.playSegmentTts(workspace.selectedIndex)}
          videoDuration={workspace.videoDuration}
          onRangeChange={(range) =>
            workspace.updateSegmentTimeRange(workspace.selectedIndex, range)
          }
        />
        <OmniScriptSegmentList
          segments={workspace.segments}
          selectedIndex={workspace.selectedIndex}
          scriptListRef={workspace.scriptListRef}
          scriptRowRefs={workspace.scriptRowRefs}
          shotOptionsLoading={workspace.shotOptionsLoading}
          shotOptionsError={workspace.shotOptionsError}
          textHashes={workspace.textHashes}
          segmentTtsProcessingIndex={scriptTts.segmentTtsProcessingIndex}
          segmentTtsQueuedIndices={scriptTts.segmentTtsQueuedIndices}
          segmentKeys={scriptTts.segmentKeys}
          segmentTtsOps={scriptTts.segmentTtsOps}
          segmentTtsQueueActive={scriptTts.segmentTtsQueueActive}
          bulkTtsBusy={scriptTts.bulkBusy}
          onPlaySegment={workspace.playSegment}
          onPlaySegmentTts={workspace.playSegmentTts}
          onRedubSegment={(index) => void handleRedubSegment(index)}
          onToggleSegmentType={workspace.toggleSegmentType}
          onUpdateText={(index, text) => workspace.setScriptSegment(index, (s) => ({ ...s, text }))}
          onOpenPicker={workspace.setPickerIndex}
          onMoveSegment={workspace.moveSegment}
          onDeleteSegment={workspace.deleteSegment}
        />
      </div>

      {workspace.pickerSegment ? (
        <ShotPickerModal
          isOpen={workspace.pickerIndex != null}
          videoUrl={workspace.videoUrl}
          segment={workspace.pickerSegment}
          segmentIndex={workspace.pickerIndex ?? 0}
          options={workspace.pickerOptions}
          loading={workspace.shotOptionsLoading}
          error={workspace.shotOptionsError}
          onClose={() => workspace.setPickerIndex(null)}
          onApply={workspace.applyShot}
        />
      ) : null}
    </div>
  );
};

export default OmniFullNarrationScriptWorkspace;

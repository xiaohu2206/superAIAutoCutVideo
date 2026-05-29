import { ChevronDown, ChevronUp, Copy, Loader, Trash2, Volume2 } from "lucide-react";

import React from "react";

import type { ScriptSegment } from "../../../types/project";
import type { OmniSegmentOpState } from "../../../hooks/omni/useOmniScriptSessionManager";

import NarrationTextField from "./NarrationTextField";

import { SegmentTypeToggle } from "./SegmentTypeToggle";

import {

  isOriginalAudio,

  isStaleSegmentTts,

  isValidSegmentTts,

  ROW_IDLE,

  ROW_SELECTED,

  SCRIPT_LIST_GRID,

  secondsToTime,

  ttsStatusLabel,

} from "./omniScriptWorkspaceUtils";



export interface OmniScriptSegmentListProps {

  segments: ScriptSegment[];

  selectedIndex: number;

  scriptListRef: React.Ref<HTMLDivElement>;

  scriptRowRefs: React.MutableRefObject<Array<HTMLDivElement | null>>;

  shotOptionsLoading: boolean;

  shotOptionsError: string | null;

  textHashes: Record<number, string>;

  segmentTtsProcessingIndex: number | null;

  segmentTtsQueuedIndices: number[];

  segmentKeys?: string[];

  segmentTtsOps?: Record<string, OmniSegmentOpState>;

  segmentTtsQueueActive?: boolean;

  bulkTtsBusy: boolean;

  onPlaySegment: (index: number) => void;

  onPlaySegmentTts: (index: number) => void;

  onRedubSegment: (index: number) => void;

  onToggleSegmentType: (index: number) => void;

  onUpdateText: (index: number, text: string) => void;

  onOpenPicker: (index: number) => void;

  onMoveSegment: (index: number, direction: -1 | 1) => void;

  onDuplicateSegment: (index: number) => void;

  onDeleteSegment: (index: number) => void;

}



const OmniScriptSegmentList: React.FC<OmniScriptSegmentListProps> = ({

  segments,

  selectedIndex,

  scriptListRef,

  scriptRowRefs,

  shotOptionsLoading,

  shotOptionsError,

  textHashes,

  segmentTtsProcessingIndex,

  segmentTtsQueuedIndices,

  segmentKeys = [],

  segmentTtsOps = {},

  segmentTtsQueueActive = false,

  bulkTtsBusy,

  onPlaySegment,

  onPlaySegmentTts,

  onRedubSegment,

  onToggleSegmentType,

  onUpdateText,

  onOpenPicker,

  onMoveSegment,

  onDuplicateSegment,

  onDeleteSegment,

}) => (

  <section className="min-w-0 flex flex-col min-h-0">

    <div className="border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden flex flex-col min-h-0 flex-1">

      <div

        className={`${SCRIPT_LIST_GRID} bg-gray-50 dark:bg-gray-800/80 px-2 py-1.5 text-xs font-medium text-gray-600 dark:text-gray-300 shrink-0`}

      >

        <span>序号</span>

        <span>时间段</span>

        <span>类型</span>

        <span>解说文本</span>

        <span>配音</span>

        <span className="justify-self-end">操作</span>

      </div>

      <div

        ref={scriptListRef}

        className="divide-y divide-gray-100 dark:divide-gray-700/80 overflow-y-auto max-h-[calc(100vh-11rem)] min-h-[320px]"

      >

        {segments.map((segment, index) => {

          const selected = index === selectedIndex;

          const original = isOriginalAudio(segment);

          const textHash = textHashes[index];
          const segmentKey = segmentKeys[index] ?? String(segment.id ?? index + 1);
          const opState = segmentTtsOps[segmentKey];

          const validTts = isValidSegmentTts(segment, textHash);

          const staleTts = isStaleSegmentTts(segment, textHash);

          const ttsProcessing = opState?.ttsRunning ?? segmentTtsProcessingIndex === index;
          const ttsQueued = opState?.ttsQueued ?? segmentTtsQueuedIndices.includes(index);
          const ttsPending = ttsProcessing || ttsQueued;
          const queuePosition = ttsQueued
            ? opState?.queuePosition ||
              segmentTtsQueuedIndices.indexOf(index) + (segmentTtsProcessingIndex != null ? 2 : 1)
            : 0;
          const nonTtsBlocked = Boolean(segmentTtsQueueActive || bulkTtsBusy);
          const blockedByOp = Boolean(opState?.blocked || nonTtsBlocked);
          const blockReason =
            opState?.blockReason ||
            (bulkTtsBusy
              ? "批量配音进行中，完成后可操作"
              : segmentTtsQueueActive
                ? "配音队列进行中，仅允许继续点击配音"
                : undefined);

          const dubLabel = ttsStatusLabel(segment, textHash);

          return (

            <div

              ref={(node) => {

                scriptRowRefs.current[index] = node;

              }}

              key={String(segment.id)}

              role="button"

              tabIndex={0}

              onClick={() => {
                if (nonTtsBlocked) return;
                onPlaySegment(index);
              }}

              onKeyDown={(e) => {

                if (e.key === "Enter" && !nonTtsBlocked) onPlaySegment(index);

              }}

              className={`${SCRIPT_LIST_GRID} px-2 py-1.5 items-center cursor-pointer text-gray-900 dark:text-gray-100 ${

                selected ? ROW_SELECTED : ROW_IDLE

              }`}

            >

              <div className="text-xs font-medium tabular-nums">{index + 1}</div>

              <div className="font-mono text-[11px] text-gray-600 dark:text-gray-300 leading-tight">

                {secondsToTime(segment.start_time)}

                <span className="text-gray-400 dark:text-gray-500"> – </span>

                {secondsToTime(segment.end_time)}

              </div>

              <div onClick={(e) => e.stopPropagation()}>

                <SegmentTypeToggle
                  original={original}
                  disabled={blockedByOp}
                  title={blockReason}
                  onToggle={() => onToggleSegmentType(index)}
                />

              </div>

              <div className="min-w-0" onClick={(e) => e.stopPropagation()}>

                <NarrationTextField

                  value={segment.text || ""}

                  disabled={original || blockedByOp}

                  onChange={(text) => onUpdateText(index, text)}

                />

              </div>

              <div

                className={`text-[11px] leading-tight ${

                  staleTts

                    ? "text-amber-600 dark:text-amber-400"

                    : validTts

                      ? "text-green-700 dark:text-green-400"

                      : "text-gray-500 dark:text-gray-400"

                }`}

                title={dubLabel}

              >

                {original ? "—" : dubLabel}

              </div>

              <div
                className="flex flex-wrap items-center justify-end gap-1 justify-self-end"
                onClick={(e) => e.stopPropagation()}
              >

                {!original ? (

                  <>

                    {validTts ? (

                      <button

                        type="button"

                        onClick={() => onPlaySegmentTts(index)}

                        disabled={ttsPending || nonTtsBlocked}

                        title="播放配音"

                        className="inline-flex items-center justify-center px-1.5 py-0.5 border border-violet-300 dark:border-violet-700 rounded text-[11px] text-violet-700 dark:text-violet-300 hover:bg-violet-50 dark:hover:bg-violet-950/40 disabled:opacity-50"

                      >

                        <Volume2 className="h-3 w-3" />

                      </button>

                    ) : null}

                    <button

                      type="button"

                      onClick={() => onRedubSegment(index)}

                      disabled={ttsPending || bulkTtsBusy || !String(segment.text || "").trim()}

                      title={
                        ttsQueued
                          ? `排队中（第 ${queuePosition} 位）`
                          : ttsProcessing
                            ? "配音生成中…"
                            : validTts || staleTts
                              ? "重新配音（使用当前解说文案）"
                              : "生成配音"
                      }

                      className="inline-flex items-center justify-center px-1.5 py-0.5 bg-violet-600 text-white rounded text-[11px] hover:bg-violet-700 disabled:opacity-50 disabled:cursor-not-allowed min-w-[52px]"

                    >

                      {ttsProcessing ? (
                        <Loader className="h-3 w-3 animate-spin" />
                      ) : ttsQueued ? (
                        "排队"
                      ) : validTts || staleTts ? (
                        "重配"
                      ) : (
                        "配音"
                      )}

                    </button>

                  </>

                ) : null}

                <button

                  type="button"

                  onClick={() => onOpenPicker(index)}

                  disabled={shotOptionsLoading || Boolean(shotOptionsError) || blockedByOp}

                  title={shotOptionsError || "选择镜头"}

                  className="inline-flex items-center justify-center px-1.5 py-0.5 bg-blue-600 text-white rounded text-[11px] hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"

                >

                  {shotOptionsLoading ? <Loader className="h-3 w-3 animate-spin" /> : "换镜头"}

                </button>

                <button

                  type="button"

                  onClick={() => onMoveSegment(index, -1)}

                  disabled={index === 0 || blockedByOp}

                  title="上移"

                  className="inline-flex items-center justify-center p-0.5 border border-gray-300 dark:border-gray-600 rounded text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-40 disabled:cursor-not-allowed"

                >

                  <ChevronUp className="h-3.5 w-3.5" />

                </button>

                <button

                  type="button"

                  onClick={() => onMoveSegment(index, 1)}

                  disabled={index === segments.length - 1 || blockedByOp}

                  title="下移"

                  className="inline-flex items-center justify-center p-0.5 border border-gray-300 dark:border-gray-600 rounded text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-40 disabled:cursor-not-allowed"

                >

                  <ChevronDown className="h-3.5 w-3.5" />

                </button>

                <button

                  type="button"

                  onClick={() => onDuplicateSegment(index)}

                  title="复制并向下插入"

                  disabled={blockedByOp}

                  className="inline-flex items-center justify-center p-0.5 border border-gray-300 dark:border-gray-600 rounded text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-40 disabled:cursor-not-allowed"

                >

                  <Copy className="h-3.5 w-3.5" />

                </button>

                <button

                  type="button"

                  onClick={() => onDeleteSegment(index)}

                  title="删除"

                  disabled={blockedByOp}

                  className="inline-flex items-center justify-center p-0.5 border border-red-200 dark:border-red-800 rounded text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/40 disabled:opacity-40 disabled:cursor-not-allowed"

                >

                  <Trash2 className="h-3.5 w-3.5" />

                </button>

              </div>

            </div>

          );

        })}

      </div>

    </div>

    {shotOptionsError ? (

      <p className="mt-2 text-sm text-red-600 dark:text-red-400">候选镜头加载失败：{shotOptionsError}</p>

    ) : null}

  </section>

);



export default OmniScriptSegmentList;

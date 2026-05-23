import { useMemo, useReducer } from "react";
import type { ScriptSegment, VideoScript } from "../../types/project";

export type OmniSegmentOpState = {
  ttsQueued: boolean;
  ttsRunning: boolean;
  queuePosition: number;
  blocked: boolean;
  blockReason?: string;
};

export type OmniScriptSessionState = {
  queuedKeys: string[];
  runningKey: string | null;
  bulkTtsRunning: boolean;
};

export type OmniScriptSessionAction =
  | { type: "setQueue"; keys: string[] }
  | { type: "setRunning"; key: string | null }
  | { type: "setBulkTtsRunning"; running: boolean }
  | { type: "clearSegment"; key: string };

export const initialOmniScriptSessionState: OmniScriptSessionState = {
  queuedKeys: [],
  runningKey: null,
  bulkTtsRunning: false,
};

export function omniScriptSessionReducer(
  state: OmniScriptSessionState,
  action: OmniScriptSessionAction
): OmniScriptSessionState {
  switch (action.type) {
    case "setQueue":
      return { ...state, queuedKeys: [...action.keys] };
    case "setRunning":
      return { ...state, runningKey: action.key };
    case "setBulkTtsRunning":
      return { ...state, bulkTtsRunning: action.running };
    case "clearSegment":
      return {
        ...state,
        queuedKeys: state.queuedKeys.filter((key) => key !== action.key),
        runningKey: state.runningKey === action.key ? null : state.runningKey,
      };
    default:
      return state;
  }
}

export function getOmniSegmentKey(segment: ScriptSegment | undefined, index: number): string {
  const raw = segment?.id;
  const id = raw == null ? "" : String(raw).trim();
  return id || `__index_${index + 1}`;
}

export function getOmniScriptRevision(script: VideoScript | null | undefined): number | undefined {
  const value = script?.metadata?.omni_revision;
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

export function useOmniScriptSessionManager(script: VideoScript | null | undefined) {
  const [state, dispatch] = useReducer(omniScriptSessionReducer, initialOmniScriptSessionState);

  const segmentKeys = useMemo(
    () => (script?.segments ?? []).map((segment, index) => getOmniSegmentKey(segment, index)),
    [script?.segments]
  );

  const segmentOps = useMemo<Record<string, OmniSegmentOpState>>(() => {
    const out: Record<string, OmniSegmentOpState> = {};
    for (const key of segmentKeys) {
      const ttsQueued = state.queuedKeys.includes(key);
      const ttsRunning = state.runningKey === key;
      const queueIndex = state.queuedKeys.indexOf(key);
      const blocked = state.bulkTtsRunning || ttsQueued || ttsRunning;
      out[key] = {
        ttsQueued,
        ttsRunning,
        queuePosition: queueIndex >= 0 ? queueIndex + (state.runningKey ? 2 : 1) : 0,
        blocked,
        blockReason: state.bulkTtsRunning
          ? "批量配音进行中，完成后可操作"
          : ttsRunning
            ? "该段正在配音，完成后可操作"
            : ttsQueued
              ? "该段已在配音队列中，完成后可操作"
              : undefined,
      };
    }
    return out;
  }, [segmentKeys, state.bulkTtsRunning, state.queuedKeys, state.runningKey]);

  return {
    revision: getOmniScriptRevision(script),
    segmentKeys,
    segmentOps,
    globalOps: {
      bulkTtsRunning: state.bulkTtsRunning,
      segmentTtsQueueActive: state.queuedKeys.length > 0 || state.runningKey != null,
    },
    operationKeys: {
      queuedKeys: state.queuedKeys,
      runningKey: state.runningKey,
    },
    dispatch,
  };
}

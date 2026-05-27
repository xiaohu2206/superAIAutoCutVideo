import { describe, expect, it } from "vitest";
import {
  getOmniScriptRevision,
  getOmniSegmentKey,
  initialOmniScriptSessionState,
  omniScriptSessionReducer,
} from "./useOmniScriptSessionManager";
import type { VideoScript } from "../../types/project";

describe("omniScriptSessionReducer", () => {
  it("tracks queued and running segment keys", () => {
    const queued = omniScriptSessionReducer(initialOmniScriptSessionState, {
      type: "setQueue",
      keys: ["a", "b"],
    });
    const running = omniScriptSessionReducer(queued, { type: "setRunning", key: "a" });

    expect(running.queuedKeys).toEqual(["a", "b"]);
    expect(running.runningKey).toBe("a");
  });

  it("clears a segment from queue and running state", () => {
    const state = {
      queuedKeys: ["a", "b"],
      runningKey: "a",
      bulkTtsRunning: false,
    };
    const next = omniScriptSessionReducer(state, { type: "clearSegment", key: "a" });

    expect(next.queuedKeys).toEqual(["b"]);
    expect(next.runningKey).toBeNull();
  });

  it("tracks bulk tts blocking state", () => {
    const next = omniScriptSessionReducer(initialOmniScriptSessionState, {
      type: "setBulkTtsRunning",
      running: true,
    });

    expect(next.bulkTtsRunning).toBe(true);
  });
});

describe("omni script session helpers", () => {
  it("uses segment id as stable key and falls back to index key", () => {
    expect(getOmniSegmentKey({ id: "seg-1", start_time: 0, end_time: 1, text: "" }, 0)).toBe("seg-1");
    expect(getOmniSegmentKey({ id: "", start_time: 0, end_time: 1, text: "" }, 2)).toBe("__index_3");
  });

  it("reads metadata omni revision", () => {
    const script: VideoScript = {
      version: "1",
      total_duration: 0,
      segments: [],
      metadata: { omni_revision: 7 },
    };

    expect(getOmniScriptRevision(script)).toBe(7);
  });
});

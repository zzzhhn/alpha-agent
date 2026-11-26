import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import { pollProposeJob, type ProposeJobRow } from "@/lib/api/factor-lab";
import { ProposeJobProgress } from "../ProposeActionRow";

const running: ProposeJobRow = {
  id: "pj_synthetic", user_id: 7, status: "running", n: 5,
  created_at: "2026-11-26T11:00:00Z", started_at: "2026-11-26T11:01:00Z",
  finished_at: null, error: null, result: null,
  progress: { stage: "evaluating", generated: 3 },
};
const interrupted: ProposeJobRow = {
  ...running, status: "failed", finished_at: "2026-11-26T11:06:00Z",
  error: "worker_interrupted", error_code: "worker_interrupted",
};

afterEach(() => vi.unstubAllGlobals());

describe("proposal job interruption", () => {
  it("stops polling an interrupted job and keeps its recorded progress", async () => {
    const get = vi.fn().mockResolvedValueOnce(Response.json(running))
      .mockResolvedValueOnce(Response.json(interrupted));
    vi.stubGlobal("fetch", get);
    const updates: ProposeJobRow[] = [];
    expect(await pollProposeJob(running.id, {
      intervalMs: 0, maxAttempts: 5, onUpdate: row => updates.push(row),
    })).toEqual(interrupted);
    expect(updates).toEqual([running, interrupted]);
    expect(get).toHaveBeenCalledTimes(2);
    for (const [path, init] of get.mock.calls) {
      expect(String(path)).toMatch(/\/jobs\/pj_synthetic$/);
      expect(init?.method).toBeUndefined();
    }
  });

  it("carries the last observation when polling ends without a terminal row", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(Response.json(running)));
    await expect(pollProposeJob(running.id, { maxAttempts: 1 }))
      .rejects.toMatchObject({ lastRow: running });
  });

  it("displays known counts and leaves unknown counts absent", () => {
    const markup = renderToStaticMarkup(<ProposeJobProgress job={interrupted} zh />);
    expect(markup).toContain("已生成 3");
    expect(markup).not.toContain("已评估");
    expect(markup).not.toContain("已提交待审");

    const partial = { ...interrupted, result: { proposed: 0, evaluated: 2, dormant: false } };
    const en = renderToStaticMarkup(<ProposeJobProgress job={partial} zh={false} />);
    expect(en).toContain("Generated 3 · Evaluated 2 · Submitted for review 0");
  });
});

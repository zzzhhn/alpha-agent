import {afterEach, describe, expect, it, vi} from "vitest";
import {pollVisible} from "../paper-bot-polling";

afterEach(()=>{vi.useRealTimers();vi.unstubAllGlobals();});

function surfaces() {
  vi.useFakeTimers();
  const doc=Object.assign(new EventTarget(),{hidden:false});
  const win=new EventTarget();
  vi.stubGlobal("document",doc);vi.stubGlobal("window",win);
  return {doc,win};
}

describe("read-only bot status polling",()=>{
  it("recovers from a hung read and ignores its late running result",async()=>{
    surfaces();
    let old:(value:string)=>void=()=>{};
    const read=vi.fn().mockImplementationOnce(()=>new Promise<string>(resolve=>{old=resolve;})).mockResolvedValue("no_trade");
    const receive=vi.fn(),failed=vi.fn();
    const stop=pollVisible({read,receive,failed});
    await vi.advanceTimersByTimeAsync(20000);
    expect(failed).toHaveBeenCalledOnce();
    expect(read.mock.calls[0][0].aborted).toBe(true);
    await vi.advanceTimersByTimeAsync(5000);
    expect(receive).toHaveBeenLastCalledWith("no_trade");
    old("running");await vi.advanceTimersByTimeAsync(0);
    expect(receive).toHaveBeenCalledOnce();
    stop();
  });
  it("pauses hidden reads and immediately reconciles on focus without overlapping reads",async()=>{
    const {doc,win}=surfaces();
    const read=vi.fn().mockResolvedValue("running"),receive=vi.fn();
    const stop=pollVisible({read,receive,failed:vi.fn()});
    await vi.advanceTimersByTimeAsync(0);
    doc.hidden=true;doc.dispatchEvent(new Event("visibilitychange"));
    await vi.advanceTimersByTimeAsync(60000);
    expect(read).toHaveBeenCalledOnce();
    read.mockResolvedValue("no_trade");doc.hidden=false;
    doc.dispatchEvent(new Event("visibilitychange"));win.dispatchEvent(new Event("focus"));
    await vi.advanceTimersByTimeAsync(0);
    expect(read).toHaveBeenCalledTimes(2);
    expect(receive).toHaveBeenLastCalledWith("no_trade");
    stop();await vi.advanceTimersByTimeAsync(60000);
    expect(read).toHaveBeenCalledTimes(2);
  });
});

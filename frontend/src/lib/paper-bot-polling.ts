/** One bounded, visible-tab reader. It never starts or retries a bot decision. */
export function pollVisible<T>({ read, receive, failed, intervalMs = 5000, timeoutMs = 20000 }: {
  read: (signal: AbortSignal) => Promise<T>;
  receive: (value: T) => void;
  failed: () => void;
  intervalMs?: number;
  timeoutMs?: number;
}) {
  let stopped = false;
  let sequence = 0;
  let controller: AbortController | null = null;
  let timer: ReturnType<typeof setTimeout> | undefined;
  async function poll() {
    if (stopped || document.hidden || controller) return;
    if (timer) clearTimeout(timer);
    const version = ++sequence;
    const request = new AbortController();
    controller = request;
    let deadline: ReturnType<typeof setTimeout> | undefined;
    try {
      const value = await Promise.race([
        read(request.signal),
        new Promise<never>((_, reject) => {
          deadline = setTimeout(() => {
            request.abort();
            reject(new Error("status_read_timeout"));
          }, timeoutMs);
        }),
      ]);
      if (!stopped && version === sequence) receive(value);
    } catch {
      if (!stopped && version === sequence && !document.hidden) failed();
    } finally {
      if (deadline) clearTimeout(deadline);
      if (version === sequence) {
        controller = null;
        if (!stopped && !document.hidden) timer = setTimeout(() => void poll(), intervalMs);
      }
    }
  }
  function visibility() {
    if (document.hidden) {
      sequence++;
      controller?.abort();
      controller = null;
      if (timer) clearTimeout(timer);
    } else void poll();
  }
  document.addEventListener("visibilitychange", visibility);
  window.addEventListener("focus", visibility);
  void poll();
  return () => {
    stopped = true;
    sequence++;
    controller?.abort();
    if (timer) clearTimeout(timer);
    document.removeEventListener("visibilitychange", visibility);
    window.removeEventListener("focus", visibility);
  };
}

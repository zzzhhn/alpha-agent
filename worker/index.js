/**
 * Cloudflare Worker — smart router for alpha.bobbyzhong.com
 *
 * When the Cloudflare Tunnel is alive (AutoDL running):
 *   → proxy to live Streamlit dashboard
 * When the tunnel is down (AutoDL off):
 *   → serve pre-generated static HTML report from KV
 */

const TUNNEL_ORIGIN = "https://alpha-tunnel.bobbyzhong.com";
const TUNNEL_TIMEOUT_MS = 2000;

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    // Health check endpoint
    if (url.pathname === "/_health") {
      return new Response(JSON.stringify({ status: "ok", mode: "worker" }), {
        headers: { "Content-Type": "application/json" },
      });
    }

    // Try live Streamlit via tunnel
    try {
      const tunnelUrl = TUNNEL_ORIGIN + url.pathname + url.search;
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), TUNNEL_TIMEOUT_MS);

      const resp = await fetch(tunnelUrl, {
        method: request.method,
        headers: request.headers,
        body: request.method !== "GET" ? request.body : undefined,
        signal: controller.signal,
      });
      clearTimeout(timeout);

      // Tunnel returned an error (502/530 = tunnel down) — fall through to static
      if (resp.status >= 500) {
        throw new Error(`tunnel returned ${resp.status}`);
      }

      // Live response from Streamlit
      const headers = new Headers(resp.headers);
      headers.set("X-Alpha-Mode", "live");
      return new Response(resp.body, {
        status: resp.status,
        headers,
      });
    } catch (_err) {
      // Tunnel unreachable or errored — serve static fallback
    }

    // Fallback: static HTML from KV
    const staticHtml = await env.STATIC_SITE.get("report.html");
    if (staticHtml) {
      return new Response(staticHtml, {
        headers: {
          "Content-Type": "text/html; charset=utf-8",
          "X-Alpha-Mode": "static",
          "Cache-Control": "public, max-age=300",
        },
      });
    }

    // No static content either
    return new Response(
      "<h1>Alpha Agent</h1><p>Demo is currently offline. Visit <a href='https://github.com/zzzhhn/alpha-agent'>GitHub</a> for details.</p>",
      {
        status: 503,
        headers: { "Content-Type": "text/html; charset=utf-8" },
      }
    );
  },
};

/**
 * Cloudflare Worker — smart fallback for alpha.bobbyzhong.com
 *
 * Strategy:
 *   - WebSocket upgrades: pass through directly to tunnel origin (never intercept)
 *   - HTTP requests: try tunnel origin first, fall back to static HTML from KV
 *
 * This ensures Streamlit's WebSocket connections work natively through the
 * Cloudflare Tunnel while still providing a static fallback when the tunnel is down.
 */

const TUNNEL_TIMEOUT_MS = 3000;

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    // Health check endpoint
    if (url.pathname === "/_health") {
      return new Response(JSON.stringify({ status: "ok", mode: "worker" }), {
        headers: { "Content-Type": "application/json" },
      });
    }

    // WebSocket upgrade requests: pass through to origin (tunnel) directly.
    // Workers cannot proxy WebSocket via fetch(), so we let Cloudflare's
    // tunnel handle it natively by NOT intercepting.
    const upgradeHeader = request.headers.get("Upgrade") || "";
    if (upgradeHeader.toLowerCase() === "websocket") {
      // Return fetch to origin — Cloudflare will route to the tunnel CNAME
      return fetch(request);
    }

    // For Streamlit's static assets and API calls, try origin first
    try {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), TUNNEL_TIMEOUT_MS);

      const resp = await fetch(request, { signal: controller.signal });
      clearTimeout(timeout);

      // Tunnel-down errors (502, 530) → fall through to static
      if (resp.status === 530 || resp.status === 502) {
        throw new Error(`origin returned ${resp.status}`);
      }

      return resp;
    } catch (_err) {
      // Origin unreachable or errored
    }

    // Fallback: static HTML from KV (only for HTML page requests)
    const accept = request.headers.get("Accept") || "";
    if (accept.includes("text/html") || url.pathname === "/" || url.pathname === "/qcore") {
      // Choose KV key based on path
      const kvKey = url.pathname === "/qcore" ? "dashboard.html" : "report.html";
      const staticHtml = await env.STATIC_SITE.get(kvKey);
      if (staticHtml) {
        return new Response(staticHtml, {
          headers: {
            "Content-Type": "text/html; charset=utf-8",
            "X-Alpha-Mode": "static",
            "Cache-Control": "public, max-age=300",
          },
        });
      }
    }

    // No static content or non-HTML request
    return new Response(
      "<h1>Alpha Agent</h1><p>Demo is currently offline. Visit <a href='https://github.com/zzzhhn/alpha-agent'>GitHub</a> for details.</p>",
      {
        status: 503,
        headers: { "Content-Type": "text/html; charset=utf-8" },
      }
    );
  },
};

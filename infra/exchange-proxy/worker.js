const ROUTES = Object.freeze({
  upbit: {
    origin: "https://api-manager.upbit.com",
    paths: /^\/api\/v1\/(?:notices|announcements)(?:\/[^/]+)?$/,
  },
  binance: {
    origin: "https://fapi.binance.com",
    paths: /^\/fapi\/v1\/(?:exchangeInfo|klines)$/,
  },
});

function response(message, status) {
  return new Response(JSON.stringify({ error: message }), {
    status,
    headers: { "content-type": "application/json; charset=utf-8" },
  });
}

export default {
  async fetch(request, env) {
    if (request.method !== "GET") return response("method not allowed", 405);
    if (!env.PROXY_TOKEN) return response("proxy is not configured", 503);
    if (request.headers.get("X-Proxy-Token") !== env.PROXY_TOKEN) {
      return response("unauthorized", 401);
    }

    const incoming = new URL(request.url);
    const match = incoming.pathname.match(/^\/(upbit|binance)(\/.*)$/);
    if (!match) return response("not found", 404);
    const route = ROUTES[match[1]];
    const upstreamPath = match[2];
    if (!route.paths.test(upstreamPath)) return response("upstream path not allowed", 404);

    const upstream = new URL(upstreamPath + incoming.search, route.origin);
    const headers = new Headers({
      accept: "application/json, text/plain, */*",
      "accept-language": "ko-KR,ko;q=0.9,en;q=0.8",
      "user-agent": "Mozilla/5.0 listing-analysis-exchange-proxy/1.0",
    });
    if (match[1] === "upbit") {
      headers.set("origin", "https://upbit.com");
      headers.set("referer", "https://upbit.com/service_center/notice");
    }
    return fetch(upstream, { method: "GET", headers, redirect: "follow" });
  },
};

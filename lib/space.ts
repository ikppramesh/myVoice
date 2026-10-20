// Server-side helper: call the myVoice engine (on the Mac, behind a Cloudflare tunnel) with the API key.
import { get } from "@vercel/edge-config";

// The tunnel URL changes whenever the tunnel restarts; the engine publishes the current one to Edge Config
// (deploy/publish_url.py), so it is looked up at request time rather than baked in at deploy time.
// SPACE_URL is only a fallback for setups without Edge Config.
let cached: { url: string; at: number } | null = null;
const CACHE_MS = 10_000;

export async function engineUrl(fresh = false): Promise<string> {
  if (!fresh && cached && Date.now() - cached.at < CACHE_MS) return cached.url;
  let url = "";
  if (process.env.EDGE_CONFIG) {
    try {
      url = (await get<string>("engineUrl")) || "";
    } catch {
      url = cached?.url || "";
    }
  }
  url = (url || process.env.SPACE_URL || "").replace(/\/$/, "");
  cached = { url, at: Date.now() };
  return url;
}

export async function spaceFetch(path: string, init: RequestInit = {}): Promise<Response> {
  if (!process.env.MYVOICE_API_KEY) {
    return Response.json({ detail: "MYVOICE_API_KEY is not configured on Vercel" }, { status: 500 });
  }
  // Retry reads with a freshly looked-up URL (the tunnel may have just moved). Not POSTs: the first
  // attempt may have reached the engine, and a retry would start a duplicate job.
  const retries = (init.method || "GET").toUpperCase() === "GET" ? 2 : 0;
  for (let attempt = 0; ; attempt++) {
    const base = await engineUrl(attempt > 0);
    if (!base) {
      return Response.json({ detail: "The voice engine is offline (no address published yet)." }, { status: 503 });
    }
    try {
      const res = await fetch(`${base}${path}`, {
        ...init,
        cache: "no-store",
        headers: { ...init.headers, "X-API-Key": process.env.MYVOICE_API_KEY, "Content-Type": "application/json" },
      });
      // A dead or starting tunnel answers with an HTML error page.
      if (!(res.headers.get("content-type") || "").includes("application/json")) {
        if (attempt < retries) { await sleep(1500); continue; }
        return Response.json(
          { detail: "The voice engine is offline — is the Mac on and awake? It reconnects automatically." },
          { status: 503 });
      }
      return new Response(res.body, { status: res.status, headers: { "Content-Type": "application/json" } });
    } catch {
      if (attempt < retries) { await sleep(1500); continue; }
      return Response.json(
        { detail: "The voice engine is offline — is the Mac on and awake? It reconnects automatically." },
        { status: 502 });
    }
  }
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

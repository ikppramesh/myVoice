// Server-side helper: call the myVoice engine on the Hugging Face Space with the API key.
export const SPACE_URL = (process.env.SPACE_URL || "").replace(/\/$/, "");

export async function spaceFetch(path: string, init: RequestInit = {}): Promise<Response> {
  if (!SPACE_URL || !process.env.MYVOICE_API_KEY) {
    return Response.json({ detail: "SPACE_URL / MYVOICE_API_KEY not configured on Vercel" }, { status: 500 });
  }
  // The tunnel drops the odd connection; retry reads once before reporting the engine as unreachable.
  // (Not POSTs: the first attempt may have reached the engine, and a retry would start a duplicate job.)
  const retries = (init.method || "GET").toUpperCase() === "GET" ? 1 : 0;
  for (let attempt = 0; ; attempt++) {
    try {
      const res = await fetch(`${SPACE_URL}${path}`, {
        ...init,
        cache: "no-store",
        headers: { ...init.headers, "X-API-Key": process.env.MYVOICE_API_KEY, "Content-Type": "application/json" },
      });
      // A sleeping/starting engine (or a dead tunnel) answers with HTML; give the UI something readable.
      if (!(res.headers.get("content-type") || "").includes("application/json")) {
        if (attempt < retries && res.status >= 500) { await sleep(1500); continue; }
        return Response.json({ detail: "The voice engine is starting up — try again in a minute." }, { status: 503 });
      }
      return new Response(res.body, { status: res.status, headers: { "Content-Type": "application/json" } });
    } catch {
      if (attempt < retries) { await sleep(1500); continue; }
      return Response.json(
        { detail: "Can't reach the voice engine — it may be restarting. Try again in a minute." },
        { status: 502 },
      );
    }
  }
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

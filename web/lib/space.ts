// Server-side helper: call the myVoice engine on the Hugging Face Space with the API key.
export const SPACE_URL = (process.env.SPACE_URL || "").replace(/\/$/, "");

export async function spaceFetch(path: string, init: RequestInit = {}): Promise<Response> {
  if (!SPACE_URL || !process.env.MYVOICE_API_KEY) {
    return Response.json({ detail: "SPACE_URL / MYVOICE_API_KEY not configured on Vercel" }, { status: 500 });
  }
  try {
    const res = await fetch(`${SPACE_URL}${path}`, {
      ...init,
      cache: "no-store",
      headers: { ...init.headers, "X-API-Key": process.env.MYVOICE_API_KEY, "Content-Type": "application/json" },
    });
    // A sleeping/starting Space answers with HTML; give the UI something readable.
    if (!(res.headers.get("content-type") || "").includes("application/json")) {
      return Response.json({ detail: "The voice engine is starting up — try again in a minute." }, { status: 503 });
    }
    return new Response(res.body, { status: res.status, headers: { "Content-Type": "application/json" } });
  } catch {
    return Response.json({ detail: "Can't reach the voice engine (Space)." }, { status: 502 });
  }
}

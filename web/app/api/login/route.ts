import { COOKIE, sessionToken } from "@/lib/session";

export async function POST(req: Request) {
  const { password } = await req.json().catch(() => ({ password: "" }));
  if (!process.env.SITE_PASSWORD || password !== process.env.SITE_PASSWORD) {
    await new Promise((r) => setTimeout(r, 800)); // slow down guessing
    return Response.json({ detail: "Wrong password" }, { status: 401 });
  }
  const res = Response.json({ ok: true });
  res.headers.append("Set-Cookie",
    `${COOKIE}=${await sessionToken()}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=${60 * 60 * 24 * 30}`);
  return res;
}

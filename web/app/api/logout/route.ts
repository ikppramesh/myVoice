import { COOKIE } from "@/lib/session";

export async function POST() {
  const res = Response.json({ ok: true });
  res.headers.append("Set-Cookie", `${COOKIE}=; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=0`);
  return res;
}

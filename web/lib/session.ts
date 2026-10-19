// Stateless session: the cookie holds an HMAC that only someone who knew SITE_PASSWORD could obtain.
export const COOKIE = "myvoice_session";

export async function sessionToken(): Promise<string> {
  const secret = process.env.SESSION_SECRET || process.env.SITE_PASSWORD || "";
  const key = await crypto.subtle.importKey("raw", new TextEncoder().encode(secret), { name: "HMAC", hash: "SHA-256" },
    false, ["sign"]);
  const sig = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(`myvoice:${process.env.SITE_PASSWORD}`));
  return Array.from(new Uint8Array(sig), (b) => b.toString(16).padStart(2, "0")).join("");
}

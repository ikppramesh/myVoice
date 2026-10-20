import { NextRequest, NextResponse } from "next/server";
import { COOKIE, sessionToken } from "./lib/session";

export async function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;
  if (pathname === "/login" || pathname === "/api/login") return NextResponse.next();
  if (process.env.SITE_PASSWORD && req.cookies.get(COOKIE)?.value === (await sessionToken())) {
    return NextResponse.next();
  }
  if (pathname.startsWith("/api/")) return NextResponse.json({ detail: "Not logged in" }, { status: 401 });
  return NextResponse.redirect(new URL("/login", req.url));
}

export const config = { matcher: ["/((?!_next/|favicon.ico).*)"] };

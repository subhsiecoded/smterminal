import { NextResponse } from "next/server";
import { createSessionCookieValue, SESSION_COOKIE, sessionMaxAge } from "@/lib/auth";
import { timingSafeEqual } from "node:crypto";
export const runtime = "nodejs";
export async function POST(request) {
    const configuredPassword = process.env.TERMINAL_ACCESS_PASSWORD;
    const sessionSecret = process.env.TERMINAL_SESSION_SECRET || "";
    if (!configuredPassword || configuredPassword.length < 16 || /^(change-this-|replace-with-)/i.test(configuredPassword)
        || sessionSecret.length < 32 || /^(replace-with-|change-this-)/i.test(sessionSecret)) {
        return NextResponse.json({ detail: "Set a unique website password (16+ characters) and a random session secret (32+ characters) on the server." }, { status: 503 });
    }
    let suppliedPassword = "";
    try {
        const body = await request.json();
        suppliedPassword = typeof body.password === "string" ? body.password : "";
    }
    catch {
        return NextResponse.json({ detail: "Invalid request." }, { status: 400 });
    }
    const a = Buffer.from(suppliedPassword);
    const b = Buffer.from(configuredPassword);
    const matches = a.length === b.length && timingSafeEqual(a, b);
    if (!matches)
        return NextResponse.json({ detail: "Incorrect access password." }, { status: 401 });
    const response = NextResponse.json({ ok: true });
    response.cookies.set({
        name: SESSION_COOKIE,
        value: createSessionCookieValue(),
        httpOnly: true,
        secure: process.env.NODE_ENV === "production",
        sameSite: "strict",
        path: "/",
        maxAge: sessionMaxAge()
    });
    return response;
}

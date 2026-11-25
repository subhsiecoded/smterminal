import { NextResponse } from "next/server";
import { hasValidSession } from "@/lib/auth";
import { createWebSocketTicket } from "@/lib/tickets";
export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export async function GET() {
    if (!(await hasValidSession()))
        return NextResponse.json({ detail: "Unauthorized" }, { status: 401 });
    const wsSecret = process.env.TERMINAL_WS_SECRET || "";
    if (process.env.NODE_ENV === "production" && (wsSecret.length < 32 || /^(replace-with-|change-this-)/i.test(wsSecret))) {
        return NextResponse.json({ detail: "A unique TERMINAL_WS_SECRET of at least 32 characters is required in production." }, { status: 503 });
    }
    return NextResponse.json({
        ticket: createWebSocketTicket(),
        wsBaseUrl: process.env.MARKET_TERMINAL_WS_BASE_URL || "ws://localhost:8000"
    }, { headers: { "Cache-Control": "no-store" } });
}

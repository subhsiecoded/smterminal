import { NextResponse } from "next/server";
import { hasValidSession } from "@/lib/auth";
import { createWebSocketTicket } from "@/lib/tickets";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function resolveWebSocketBaseUrl() {
  const raw = process.env.MARKET_TERMINAL_WS_BASE_URL;
  if (!raw) {
    return process.env.NODE_ENV === "production" ? null : "ws://localhost:8000";
  }

  try {
    const url = new URL(raw);
    const production = process.env.NODE_ENV === "production";
    const allowedProtocol = production ? url.protocol === "wss:" : ["ws:", "wss:"].includes(url.protocol);
    if (
      !allowedProtocol ||
      !url.hostname ||
      url.username ||
      url.password ||
      (url.pathname && url.pathname !== "/") ||
      url.search ||
      url.hash ||
      (production && ["localhost", "127.0.0.1"].includes(url.hostname))
    ) {
      return null;
    }
    return `${url.protocol}//${url.host}`;
  } catch {
    return null;
  }
}

export async function GET() {
  if (!(await hasValidSession())) {
    return NextResponse.json({ detail: "Unauthorized" }, { status: 401 });
  }

  const wsSecret = process.env.TERMINAL_WS_SECRET || "";
  if (
    process.env.NODE_ENV === "production" &&
    (wsSecret.length < 32 || /^(replace-with-|change-this-|dev-only-)/i.test(wsSecret))
  ) {
    return NextResponse.json(
      { detail: "A unique TERMINAL_WS_SECRET of at least 32 characters is required in production." },
      { status: 503, headers: { "Cache-Control": "no-store" } }
    );
  }

  const wsBaseUrl = resolveWebSocketBaseUrl();
  if (!wsBaseUrl) {
    return NextResponse.json(
      { detail: "Set MARKET_TERMINAL_WS_BASE_URL to the backend's public WSS origin (for example, wss://your-backend.example.com)." },
      { status: 503, headers: { "Cache-Control": "no-store" } }
    );
  }

  const ticket = createWebSocketTicket();
  if (process.env.NODE_ENV === "production" && !ticket) {
    return NextResponse.json(
      { detail: "Unable to issue the live-stream ticket. Check TERMINAL_WS_SECRET." },
      { status: 503, headers: { "Cache-Control": "no-store" } }
    );
  }

  return NextResponse.json(
    { ticket, wsBaseUrl },
    { headers: { "Cache-Control": "no-store" } }
  );
}

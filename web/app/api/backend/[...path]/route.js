import { NextResponse } from "next/server";
import { hasValidSession } from "@/lib/auth";
export const runtime = "nodejs";
export const dynamic = "force-dynamic";
function isAllowed(parts) {
    if (parts.some((part) => !part || part === "." || part === ".." || part.includes("\\")))
        return false;
    const path = parts.join("/");
    if (path === "health" || path === "health/providers")
        return true;
    if (path === "market/quotes" || path === "market/movers" || path === "market/india/screener")
        return true;
    if (path === "instruments/search" || path === "instruments/india")
        return true;
    if (/^market\/(quote|candles|indicators|news)\/[A-Za-z0-9.^=_-]{1,32}(\/staleness)?$/.test(path))
        return true;
    return false;
}
export async function GET(request, context) {
    if (!(await hasValidSession()))
        return NextResponse.json({ detail: "Unauthorized" }, { status: 401 });
    const { path } = await context.params;
    if (!isAllowed(path))
        return NextResponse.json({ detail: "Endpoint is not available through the web terminal." }, { status: 403 });
    const backend = process.env.MARKET_TERMINAL_API_BASE_URL;
    if (!backend)
        return NextResponse.json({ detail: "MARKET_TERMINAL_API_BASE_URL is not configured." }, { status: 503 });
    const backendToken = process.env.TERMINAL_BACKEND_TOKEN || "";
    if (process.env.NODE_ENV === "production" && (backendToken.length < 32 || /^(replace-with-|change-this-)/i.test(backendToken))) {
        return NextResponse.json({ detail: "A unique TERMINAL_BACKEND_TOKEN of at least 32 characters is required in production." }, { status: 503 });
    }
    const target = new URL(`/api/${path.map(encodeURIComponent).join("/")}`, backend);
    request.nextUrl.searchParams.forEach((value, key) => target.searchParams.append(key, value));
    try {
        const upstream = await fetch(target, {
            method: "GET",
            headers: backendToken
                ? { "X-Terminal-Server-Token": backendToken }
                : undefined,
            cache: "no-store",
            signal: AbortSignal.timeout(path.includes("screener") ? 95000 : 12000)
        });
        const body = await upstream.text();
        return new NextResponse(body, {
            status: upstream.status,
            headers: {
                "Content-Type": upstream.headers.get("content-type") || "application/json",
                "Cache-Control": "no-store"
            }
        });
    }
    catch {
        return NextResponse.json({ detail: "Market-data backend is unreachable. Check that the backend is running." }, { status: 502 });
    }
}

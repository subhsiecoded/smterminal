import "server-only";
import { createHmac, timingSafeEqual } from "node:crypto";
import { cookies } from "next/headers";
export const SESSION_COOKIE = "smterminal_session";
const SESSION_SECONDS = 60 * 60 * 12;
function secret() {
    const value = process.env.TERMINAL_SESSION_SECRET;
    if (!value || value.length < 32 || /^(replace-with-|change-this-)/i.test(value)) {
        throw new Error("TERMINAL_SESSION_SECRET must be a unique random value of at least 32 characters");
    }
    return value;
}
function signature(payload) {
    return createHmac("sha256", secret()).update(payload).digest("base64url");
}
export function createSessionCookieValue() {
    const payload = Buffer.from(JSON.stringify({ exp: Math.floor(Date.now() / 1000) + SESSION_SECONDS }), "utf8").toString("base64url");
    return `${payload}.${signature(payload)}`;
}
export function verifySessionValue(value) {
    if (!value)
        return false;
    const [payload, supplied, extra] = value.split(".");
    if (!payload || !supplied || extra)
        return false;
    let expected;
    try {
        expected = signature(payload);
    }
    catch {
        return false;
    }
    const a = Buffer.from(supplied);
    const b = Buffer.from(expected);
    if (a.length !== b.length || !timingSafeEqual(a, b))
        return false;
    try {
        const parsed = JSON.parse(Buffer.from(payload, "base64url").toString("utf8"));
        return typeof parsed.exp === "number" && parsed.exp > Math.floor(Date.now() / 1000);
    }
    catch {
        return false;
    }
}
export async function hasValidSession() {
    const jar = await cookies();
    return verifySessionValue(jar.get(SESSION_COOKIE)?.value);
}
export function sessionMaxAge() {
    return SESSION_SECONDS;
}

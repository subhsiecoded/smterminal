import "server-only";
import { createHmac } from "node:crypto";
function base64url(input) {
    return Buffer.from(input, "utf8").toString("base64url");
}
export function createWebSocketTicket() {
    const secret = process.env.TERMINAL_WS_SECRET;
    if (!secret)
        return null;
    const now = Math.floor(Date.now() / 1000);
    const header = base64url(JSON.stringify({ alg: "HS256", typ: "JWT" }));
    const payload = base64url(JSON.stringify({ scope: "market_ticks", sub: "web-terminal", iat: now, exp: now + 300 }));
    const input = `${header}.${payload}`;
    const sig = createHmac("sha256", secret).update(input).digest("base64url");
    return `${input}.${sig}`;
}

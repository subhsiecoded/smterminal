"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import MarketChart from "./market-chart";
const DEFAULT_SYMBOLS = ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "^NSEI", "^NSEBANK", "BTC-USD", "AAPL"];
const INTERVALS = ["1m", "5m", "15m", "1h", "1d", "1w"];
const CATEGORIES = ["gainers", "losers", "active", "turnover", "unusual-volume", "all"];
const RESERVED = new Set(["INDIA-MOVERS", "INDIA", "SCREENER", "NSE", "MOVERS", "GAINERS", "LOSERS", "ACTIVE", "TURNOVER", "UNUSUAL-VOLUME"]);
const SYMBOL_ALIASES = { NVIDIA: "NVDA", "NVIDIA CORP": "NVDA", "NVIDIA CORPORATION": "NVDA" };
const SYMBOL_RE = /^[A-Z0-9^][A-Z0-9.^=_-]{0,31}$/;
const BLOCKS = " ▁▂▃▄▅▆▇█";
async function api(path, init) {
    const endpoint = `/api/backend/${path.replace(/^\//, "")}`;
    let response;
    try {
        response = await fetch(endpoint, {
            ...init,
            cache: "no-store",
            headers: { ...(init?.headers || {}) },
        });
    } catch (error) {
        const message = error instanceof Error ? error.message : "Network request failed";
        throw new Error(message || "Market-data backend is unreachable");
    }

    let payload;
    try {
        payload = await response.json();
    } catch {
        payload = null;
    }
    if (!response.ok) {
        const detail = payload && typeof payload === "object" && "detail" in payload
            ? String(payload.detail)
            : `Request failed (${response.status})`;
        throw new Error(detail);
    }
    return payload;
}
function cleanSymbols(values) {
    const cleaned = [];
    for (const value of values) {
        const raw = value.trim().toUpperCase();
        const symbol = SYMBOL_ALIASES[raw] || raw;
        if (symbol && !RESERVED.has(symbol) && SYMBOL_RE.test(symbol) && !cleaned.includes(symbol))
            cleaned.push(symbol);
    }
    return cleaned;
}
function resample(values, width) {
    if (!values.length)
        return Array(width).fill(0);
    if (width <= 1)
        return [values[values.length - 1]];
    if (values.length >= width) {
        return Array.from({ length: width }, (_, i) => values[Math.round(i * (values.length - 1) / (width - 1))]);
    }
    return Array.from({ length: width }, (_, i) => values[Math.min(Math.floor(i * values.length / width), values.length - 1)]);
}
function renderChart(prices, width, height) {
    if (!prices.length)
        return { lines: [], directions: [], lo: 0, hi: 0 };
    const sampled = resample(prices, width);
    if (!sampled.length)
        return { lines: [], directions: [], lo: 0, hi: 0 };
    const lo = Math.min(...sampled);
    const hi = Math.max(...sampled);
    const range = (hi - lo) || 1;
    const levels = sampled.map((price) => Math.min(Math.max(Math.round((price - lo) / range * height * 8), 0), height * 8));
    const lines = [];
    for (let row = 0; row < height; row += 1) {
        const fromBottom = height - 1 - row;
        const base = fromBottom * 8;
        lines.push(levels.map((level) => BLOCKS[Math.min(Math.max(level - base, 0), 8)]));
    }
    const directions = sampled.map((price, index) => index === 0 || price >= sampled[index - 1]);
    return { lines, directions, lo, hi };
}
function number(value, decimals = 2, fallback = "—") {
    if (value === null || value === undefined || value === "")
        return fallback;
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed.toLocaleString("en-IN", { minimumFractionDigits: decimals, maximumFractionDigits: decimals }) : fallback;
}
function compact(value) {
    const parsed = Number(value);
    if (!Number.isFinite(parsed))
        return "—";
    for (const [unit, divisor] of [["Cr", 10000000], ["L", 100000], ["K", 1000]]) {
        if (Math.abs(parsed) >= divisor)
            return `${(parsed / divisor).toFixed(2)}${unit}`;
    }
    return parsed.toLocaleString("en-IN", { maximumFractionDigits: 0 });
}
function parseCommand(raw) {
    const parts = raw.trim().split(/\s+/).filter(Boolean);
    if (!parts.length)
        return { verb: "", args: [] };
    const verb = parts[0].toLowerCase();
    const known = new Set(["add", "watch", "rm", "remove", "unwatch", "select", "sel", "search", "find", "india", "movers", "india-movers", "screener", "nse", "news", "interval", "int", "quit", "exit", "help", "?"]);
    if (!known.has(verb))
        return { verb: "select", args: [parts[0].toUpperCase()] };
    return { verb, args: parts.slice(1).map((value) => ["search", "find", "india"].includes(verb) ? value : value.toUpperCase()) };
}
function calculateIndicators(candles) {
    const closes = Array.isArray(candles)
        ? candles.map((row) => Number(row?.close)).filter(Number.isFinite)
        : [];
    if (!closes.length) return {};
    const average = (values) => values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null;
    const ema = (period) => {
        const multiplier = 2 / (period + 1);
        let value = closes[0];
        for (let index = 1; index < closes.length; index += 1) value = closes[index] * multiplier + value * (1 - multiplier);
        return value;
    };
    let rsi14 = null;
    if (closes.length >= 15) {
        const changes = closes.slice(-15).slice(1).map((value, index) => value - closes.slice(-15)[index]);
        const gains = changes.map((value) => Math.max(value, 0));
        const losses = changes.map((value) => Math.max(-value, 0));
        const avgGain = average(gains);
        const avgLoss = average(losses);
        rsi14 = avgGain === 0 && avgLoss === 0 ? 50 : avgLoss === 0 ? 100 : 100 - (100 / (1 + avgGain / avgLoss));
    }
    return {
        sma20: closes.length >= 20 ? average(closes.slice(-20)) : null,
        ema12: ema(12),
        ema26: ema(26),
        rsi14,
    };
}

function formatUtcTime(date) {
    return `${date.toISOString().slice(0, 19).replace("T", " ")} UTC`;
}
function formatMarketDate(value) {
    if (value === null || value === undefined || value === "") return "—";
    const numeric = Number(value);
    const date = new Date(Number.isFinite(numeric) && Math.abs(numeric) < 1e12 ? numeric * 1000 : value);
    return Number.isNaN(date.getTime()) ? "—" : date.toLocaleDateString();
}
export default function Terminal() {
    const [watchlist, setWatchlist] = useState(DEFAULT_SYMBOLS);
    const [selected, setSelected] = useState("RELIANCE.NS");
    const [quotes, setQuotes] = useState({});
    const [candles, setCandles] = useState([]);
    const [indicators, setIndicators] = useState({});
    const [interval, setIntervalValue] = useState("1d");
    const [status, setStatus] = useState("connecting");
    const [clock, setClock] = useState(null);
    const [command, setCommand] = useState("");
    const [feedback, setFeedback] = useState("type help for commands · / to focus command bar");
    const [busy, setBusy] = useState(false);
    const [sideMode, setSideMode] = useState("topbook");
    const [sideTitle, setSideTitle] = useState("TOP OF BOOK");
    const [sideData, setSideData] = useState(null);
    const [activeSideTab, setActiveSideTab] = useState("topbook");
    const [lastSearchQuery, setLastSearchQuery] = useState("");
    const [sideLoading, setSideLoading] = useState(false);
    const [sideError, setSideError] = useState("");
    const [notices, setNotices] = useState([]);
    const [screenerOpen, setScreenerOpen] = useState(false);
    const [screener, setScreener] = useState(null);
    const [screenerCategory, setScreenerCategory] = useState("gainers");
    const [screenerFilter, setScreenerFilter] = useState("");
    const [screenerLive, setScreenerLive] = useState(true);
    const [screenerBusy, setScreenerBusy] = useState(false);
    const [detailRow, setDetailRow] = useState(null);
    const [showHelp, setShowHelp] = useState(false);
    const commandInput = useRef(null);
    const chartViewport = useRef(null);
    const [chartWidth, setChartWidth] = useState(96);
    const wsRef = useRef(null);
    const chartRequestId = useRef(0);
    const sideRequestId = useRef(0);
    const wantedSymbols = useRef([...DEFAULT_SYMBOLS]);
    const previousSymbols = useRef([...DEFAULT_SYMBOLS]);
    const mounted = useRef(false);
    const manualDisconnect = useRef(false);
    const selectedQuote = quotes[selected];
    const safeCandles = useMemo(
        () => Array.isArray(candles)
            ? candles.filter((row) => row && typeof row === "object" && row.close !== null && row.close !== undefined && Number.isFinite(Number(row.close)))
                .map((row) => ({ ...row, close: Number(row.close) }))
            : [],
        [candles]
    );
    const chart = useMemo(() => renderChart(safeCandles.map((row) => row.close), chartWidth, 15), [safeCandles, chartWidth]);
    const chartLast = safeCandles.at(-1)?.close ?? selectedQuote?.ltp;
    const visibleScreenerRows = useMemo(() => {
        const rows = screener?.results || [];
        const query = screenerFilter.trim().toLowerCase();
        return rows.filter((row) => !query || `${row.symbol} ${row.name || ""}`.toLowerCase().includes(query));
    }, [screener, screenerFilter]);
    useEffect(() => {
        const stored = localStorage.getItem("smterminal.watchlist.v1");
        if (stored) {
            try {
                const parsed = JSON.parse(stored);
                if (Array.isArray(parsed)) {
                    const cleaned = cleanSymbols(parsed.filter((item) => typeof item === "string"));
                    if (cleaned.length)
                        setWatchlist(cleaned);
                }
            }
            catch {
                localStorage.removeItem("smterminal.watchlist.v1");
            }
        }
        mounted.current = true;
    }, []);
    useEffect(() => {
        if (mounted.current)
            localStorage.setItem("smterminal.watchlist.v1", JSON.stringify(watchlist));
        wantedSymbols.current = cleanSymbols([...watchlist, selected]);
        const ws = wsRef.current;
        if (ws?.readyState === WebSocket.OPEN) {
            const next = wantedSymbols.current;
            try {
                ws.send(JSON.stringify({
                    subscribe: next.filter((symbol) => !previousSymbols.current.includes(symbol)),
                    unsubscribe: previousSymbols.current.filter((symbol) => !next.includes(symbol))
                }));
            } catch {
                ws.close(4000, "subscription update failed");
            }
        }
        previousSymbols.current = [...wantedSymbols.current];
    }, [watchlist, selected]);
    useEffect(() => {
        setClock(new Date());
        const id = window.setInterval(() => setClock(new Date()), 1000);
        return () => window.clearInterval(id);
    }, []);
    useEffect(() => {
        const addNotice = (detail) => {
            const normalized = {
                id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
                createdAt: Date.now(),
                level: detail?.level || "error",
                title: detail?.title || "Application error",
                message: detail?.message || "Something went wrong.",
                detail: detail?.detail || "",
                source: detail?.source || "APPLICATION",
            };
            setNotices((current) => {
                const duplicate = current.some((item) => item.title === normalized.title && item.message === normalized.message && Date.now() - item.createdAt < 300000);
                if (duplicate) return current;
                return [...current, normalized].slice(-4);
            });
        };
        const onNotice = (event) => addNotice(event.detail || {});
        const onWindowError = (event) => addNotice({
            title: "Unexpected application error",
            message: "A frontend component encountered an unexpected error. You can continue using other terminal panels.",
            detail: `${event.message || "Unknown error"}${event.filename ? ` · ${event.filename}:${event.lineno || 0}` : ""}`,
            source: "BROWSER RUNTIME",
            level: "error",
        });
        const onUnhandledRejection = (event) => addNotice({
            title: "Background task failed",
            message: "A background operation did not complete successfully.",
            detail: event.reason instanceof Error ? event.reason.message : String(event.reason || "Unknown rejection"),
            source: "ASYNC RUNTIME",
            level: "error",
        });
        window.addEventListener("smterminal:notice", onNotice);
        window.addEventListener("error", onWindowError);
        window.addEventListener("unhandledrejection", onUnhandledRejection);
        return () => {
            window.removeEventListener("smterminal:notice", onNotice);
            window.removeEventListener("error", onWindowError);
            window.removeEventListener("unhandledrejection", onUnhandledRejection);
        };
    }, []);
    useEffect(() => {
        if (!notices.length) return undefined;
        const timers = notices.map((notice) => window.setTimeout(() => {
            setNotices((current) => current.filter((item) => item.id !== notice.id));
        }, notice.level === "error" ? 12000 : 8000));
        return () => timers.forEach((timer) => window.clearTimeout(timer));
    }, [notices]);
    useEffect(() => {
        const element = chartViewport.current;
        if (!element)
            return;
        const observer = new ResizeObserver((entries) => {
            const width = entries[0]?.contentRect.width || element.clientWidth;
            setChartWidth(Math.max(36, Math.min(180, Math.floor(width / 8.7))));
        });
        observer.observe(element);
        return () => observer.disconnect();
    }, []);
    const refreshQuotes = useCallback(async () => {
        const symbols = cleanSymbols([...watchlist, selected]);
        if (!symbols.length)
            return;
        try {
            const payload = await api(`market/quotes?symbols=${encodeURIComponent(symbols.join(","))}`);
            if (!Array.isArray(payload)) throw new Error("The market API returned an invalid quotes payload");
            setQuotes((current) => {
                const next = { ...current };
                for (const quote of payload) {
                    if (!quote || typeof quote.symbol !== "string") continue;
                    next[quote.symbol] = { ...next[quote.symbol], ...quote };
                }
                return next;
            });
        }
        catch (error) {
            setFeedback(`[seed] ${error instanceof Error ? error.message : "Could not load quotes"}`);
        }
    }, [watchlist, selected]);
    const refreshChart = useCallback(async () => {
        const requestId = ++chartRequestId.current;
        setBusy(true);
        try {
            // Only fetch OHLC once. All four indicators are deterministic
            // calculations over the same candles and do not need a second Yahoo request.
            const history = await api(`market/candles/${encodeURIComponent(selected)}?interval=${interval}`);
            if (requestId !== chartRequestId.current) return;
            if (!Array.isArray(history)) throw new Error("The market API returned an invalid candle payload");
            const rows = history.filter((row) => row && typeof row === "object");
            setCandles(rows);
            setIndicators(calculateIndicators(rows));
            setFeedback(`chart refreshed · ${selected} · ${interval}`);
        }
        catch (error) {
            if (requestId !== chartRequestId.current) return;
            // Keep the last valid chart on intermittent provider failures.
            // The header status/inline feedback is less disruptive than a toast on every poll.
            const message = error instanceof Error ? error.message : "Unable to load chart";
            setFeedback(`[chart] showing last available snapshot · ${message}`);
        }
        finally {
            if (requestId === chartRequestId.current) setBusy(false);
        }
    }, [selected, interval]);
    useEffect(() => {
        void refreshQuotes();
        const id = window.setInterval(() => void refreshQuotes(), 60000);
        return () => window.clearInterval(id);
    }, [refreshQuotes]);
    useEffect(() => {
        void refreshChart();
        const id = window.setInterval(() => void refreshChart(), 60000);
        return () => window.clearInterval(id);
    }, [refreshChart]);
    useEffect(() => {
        let cancelled = false;
        manualDisconnect.current = false;
        let socket = null;
        let retryTimer = null;
        let heartbeatTimer = null;
        let connectionTimer = null;
        let backoff = 1000;
        let lastHeartbeat = Date.now();
        let ticketInFlight = false;
        let permanentlyBlocked = false;

        const clearHeartbeat = () => {
            if (heartbeatTimer !== null) {
                window.clearInterval(heartbeatTimer);
                heartbeatTimer = null;
            }
        };
        const clearConnectionTimer = () => {
            if (connectionTimer !== null) {
                window.clearTimeout(connectionTimer);
                connectionTimer = null;
            }
        };
        const scheduleReconnect = (minimumDelay = 0) => {
            if (cancelled || manualDisconnect.current || retryTimer !== null) return;
            if (typeof navigator !== "undefined" && !navigator.onLine) {
                setStatus("offline");
                return;
            }
            setStatus("reconnecting");
            const jitter = Math.floor(Math.random() * Math.min(1800, backoff * 0.2));
            const delay = Math.max(minimumDelay, backoff + jitter);
            retryTimer = window.setTimeout(() => {
                retryTimer = null;
                backoff = Math.min(Math.round(backoff * 1.8), 60000);
                void connect();
            }, delay);
        };

        const connect = async () => {
            if (cancelled || manualDisconnect.current || permanentlyBlocked || ticketInFlight) return;
            if (typeof navigator !== "undefined" && !navigator.onLine) {
                setStatus("offline");
                return;
            }
            if (socket && [WebSocket.CONNECTING, WebSocket.OPEN].includes(socket.readyState)) return;
            ticketInFlight = true;
            setStatus(backoff > 1000 ? "reconnecting" : "connecting");
            try {
                const response = await fetch("/api/ws-ticket", {
                    cache: "no-store",
                    signal: AbortSignal.timeout(12000),
                });
                const config = await response.json().catch(() => ({}));
                if (cancelled) return;

                if (response.status === 401) {
                    window.location.assign("/login");
                    return;
                }
                if (!response.ok) {
                    const message = typeof config.detail === "string" ? config.detail : `Live-stream setup failed (${response.status})`;
                    setStatus("error");
                    setFeedback(`[live stream] ${message}`);
                    // 4xx/503 from the ticket route indicate an auth or deployment
                    // configuration problem. Repeating the same request cannot fix it.
                    if (response.status < 500 || response.status === 503) {
                        permanentlyBlocked = true;
                        return;
                    }
                    scheduleReconnect(response.status === 429 ? 30000 : 15000);
                    return;
                }

                if (typeof config.wsBaseUrl !== "string" || !config.wsBaseUrl.trim()) {
                    setStatus("error");
                    const message = "Backend WSS URL is missing. Configure MARKET_TERMINAL_WS_BASE_URL on the web deployment.";
                    setFeedback(`[live stream] ${message}`);
                    permanentlyBlocked = true;
                    return;
                }

                let baseUrl;
                try {
                    baseUrl = new URL(config.wsBaseUrl);
                } catch {
                    const message = "The configured backend WebSocket URL is invalid.";
                    setStatus("error");
                    setFeedback(`[live stream] ${message}`);
                    permanentlyBlocked = true;
                    return;
                }
                const securePage = window.location.protocol === "https:";
                if (!( ["ws:", "wss:"].includes(baseUrl.protocol) ) || (securePage && baseUrl.protocol !== "wss:") || baseUrl.username || baseUrl.password) {
                    const message = "An HTTPS website requires a valid public WSS backend URL.";
                    setStatus("error");
                    setFeedback(`[live stream] ${message}`);
                    permanentlyBlocked = true;
                    return;
                }

                const url = new URL("/ws/ticks", baseUrl.origin);
                if (typeof config.ticket === "string" && config.ticket) url.searchParams.set("ticket", config.ticket);
                const candidate = new WebSocket(url.toString());
                socket = candidate;
                wsRef.current = candidate;
                clearConnectionTimer();
                connectionTimer = window.setTimeout(() => {
                    if (candidate.readyState === WebSocket.CONNECTING) candidate.close(4000, "connection handshake timeout");
                }, 12000);

                candidate.onopen = () => {
                    clearConnectionTimer();
                    if (cancelled || wsRef.current !== candidate) {
                        candidate.close(1000, "stale connection");
                        return;
                    }
                    backoff = 1000;
                    lastHeartbeat = Date.now();
                    setStatus("live");
                    try {
                        candidate.send(JSON.stringify({ subscribe: wantedSymbols.current }));
                    } catch {
                        candidate.close(4000, "subscription send failed");
                    }
                };
                candidate.onmessage = (event) => {
                    if (cancelled || wsRef.current !== candidate) return;
                    try {
                        const message = JSON.parse(String(event.data));
                        if (message.type === "heartbeat") {
                            lastHeartbeat = Date.now();
                            return;
                        }
                        if (typeof message.symbol === "string" && message.symbol.length <= 32) {
                            setQuotes((current) => ({
                                ...current,
                                [message.symbol]: { ...current[message.symbol], ...message },
                            }));
                        }
                    } catch {
                        // Invalid provider frames are isolated from the React render cycle.
                    }
                };
                candidate.onerror = () => {
                    if (!cancelled && wsRef.current === candidate) setStatus("reconnecting");
                };
                candidate.onclose = (event) => {
                    clearConnectionTimer();
                    clearHeartbeat();
                    if (wsRef.current === candidate) wsRef.current = null;
                    if (cancelled || manualDisconnect.current) return;

                    if ([1002, 1003, 1007, 1008].includes(event.code)) {
                        // A policy close is permanent until backend configuration is
                        // corrected. Stop reconnecting and keep the UI in a quiet
                        // degraded state instead of generating repeated popups.
                        permanentlyBlocked = true;
                        setStatus("error");
                        const reason = event.reason || "The backend rejected this WebSocket handshake.";
                        setFeedback(`[live stream disabled] ${reason} · reload after backend configuration is fixed`);
                        return;
                    }
                    scheduleReconnect();
                };

                clearHeartbeat();
                heartbeatTimer = window.setInterval(() => {
                    if (wsRef.current === candidate && candidate.readyState === WebSocket.OPEN && Date.now() - lastHeartbeat > 35000) {
                        setStatus("stale");
                        candidate.close(4000, "heartbeat timeout");
                    }
                }, 5000);
            } catch (error) {
                if (cancelled || manualDisconnect.current) return;
                setStatus("reconnecting");
                const message = error instanceof Error ? error.message : "Could not obtain a live connection ticket";
                setFeedback(`[live stream] ${message}`);
                scheduleReconnect();
            } finally {
                ticketInFlight = false;
            }
        };

        const onOnline = () => {
            if (retryTimer !== null) window.clearTimeout(retryTimer);
            retryTimer = null;
            backoff = 1000;
            window.setTimeout(() => {
                if (!cancelled && (!socket || socket.readyState === WebSocket.CLOSED)) void connect();
            }, 250);
        };
        const onOffline = () => {
            setStatus("offline");
            socket?.close(1001, "browser offline");
        };
        const onVisibility = () => {
            if (document.visibilityState === "visible" && (!socket || socket.readyState === WebSocket.CLOSED)) void connect();
        };
        window.addEventListener("online", onOnline);
        window.addEventListener("offline", onOffline);
        document.addEventListener("visibilitychange", onVisibility);
        void connect();
        return () => {
            cancelled = true;
            window.removeEventListener("online", onOnline);
            window.removeEventListener("offline", onOffline);
            document.removeEventListener("visibilitychange", onVisibility);
            if (retryTimer !== null) window.clearTimeout(retryTimer);
            clearHeartbeat();
            clearConnectionTimer();
            socket?.close(1000, "component unmounted");
            if (wsRef.current === socket) wsRef.current = null;
        };
    }, []);
    useEffect(() => {
        const onKey = (event) => {
            if (event.key === "/" && !(event.target instanceof HTMLInputElement) && !(event.target instanceof HTMLTextAreaElement)) {
                event.preventDefault();
                commandInput.current?.focus();
            }
            if (event.key === "Escape" && screenerOpen) {
                setScreenerOpen(false);
                setDetailRow(null);
            }
        };
        window.addEventListener("keydown", onKey);
        return () => window.removeEventListener("keydown", onKey);
    }, [screenerOpen]);
    async function selectSymbol(raw) {
        sideRequestId.current += 1;
        setSideLoading(false);
        setSideError("");
        const symbol = cleanSymbols([raw])[0];
        if (!symbol) {
            setFeedback(`'${raw}' is not a valid ticker symbol`);
            return;
        }
        setSelected(symbol);
        setSideMode("topbook");
        setActiveSideTab("topbook");
        setSideTitle("TOP OF BOOK");
        setFeedback(`→ ${symbol}`);
        if (!watchlist.includes(symbol)) {
            try {
                const quote = await api(`market/quote/${encodeURIComponent(symbol)}`);
                setQuotes((current) => ({ ...current, [symbol]: quote }));
            }
            catch {
                // The chart request provides the visible error when the symbol is invalid.
            }
        }
    }
    function addWatchlist(rawSymbols) {
        const valid = cleanSymbols(rawSymbols);
        const added = valid.filter((symbol) => !watchlist.includes(symbol));
        if (!added.length) {
            setFeedback("all requested symbols are already in the watchlist, or were invalid");
            return;
        }
        setWatchlist((current) => [...current, ...added]);
        setFeedback(`watching: ${added.join(", ")}`);
        void api(`market/quotes?symbols=${encodeURIComponent([...added, selected].join(","))}`)
            .then((payload) => {
                if (!Array.isArray(payload)) throw new Error("The market API returned an invalid quotes payload");
                setQuotes((current) => {
                    const next = { ...current };
                    for (const quote of payload) {
                        if (!quote || typeof quote.symbol !== "string") continue;
                        next[quote.symbol] = { ...next[quote.symbol], ...quote };
                    }
                    return next;
                });
            })
            .catch((error) => setFeedback(`[watchlist] ${error instanceof Error ? error.message : "Unable to seed added symbols"}`));
    }
    function removeWatchlist(rawSymbols) {
        const remove = new Set(rawSymbols.map((symbol) => symbol.toUpperCase()));
        const next = watchlist.filter((symbol) => !remove.has(symbol));
        setWatchlist(next);
        setFeedback(`removed: ${[...remove].join(", ")}`);
    }
    async function openIndiaScreener(category, args) {
        setScreenerFilter("");
        const aliases = {
            "top-gainers": "gainers", "top-losers": "losers", volume: "active", "most-active": "active",
            "volume-spike": "unusual-volume", unusual: "unusual-volume"
        };
        const normalized = aliases[category] || category;
        if (!CATEGORIES.includes(normalized)) {
            setFeedback("usage: india-movers gainers|losers|active|turnover|unusual-volume|all [key=value ...]");
            return;
        }
        const params = new URLSearchParams({ category: normalized, series: "EQ", limit: "50", offset: "0" });
        const paramAliases = {
            min_change: "min_change_pct", max_change: "max_change_pct", min_rvol: "min_relative_volume", sort: "sort_by"
        };
        const integerKeys = new Set(["limit", "offset", "min_volume"]);
        const floatKeys = new Set(["min_price", "max_price", "min_change_pct", "max_change_pct", "min_turnover", "min_relative_volume"]);
        try {
            for (const token of args) {
                if (!token.includes("="))
                    continue;
                const [rawKey, rawValue] = token.split("=", 2);
                const key = paramAliases[rawKey.toLowerCase()] || rawKey.toLowerCase();
                if (integerKeys.has(key)) {
                    const parsed = Number(rawValue);
                    if (!Number.isInteger(parsed))
                        throw new Error("invalid integer filter");
                    params.set(key, String(parsed));
                }
                else if (floatKeys.has(key)) {
                    const parsed = Number(rawValue);
                    if (!Number.isFinite(parsed))
                        throw new Error("invalid numeric filter");
                    params.set(key, String(parsed));
                }
                else if (key === "min_turnover_cr") {
                    const parsed = Number(rawValue);
                    if (!Number.isFinite(parsed))
                        throw new Error("invalid turnover filter");
                    params.set("min_turnover", String(parsed * 10000000));
                }
                else if (key === "series") {
                    params.set(key, rawValue.toUpperCase());
                }
                else if (key === "sort_by" || key === "order") {
                    params.set(key, rawValue.toLowerCase());
                }
            }
        }
        catch {
            setFeedback("invalid filter value - use numbers, e.g. min_change=2 min_volume=100000");
            return;
        }
        if (normalized === "unusual-volume" && !params.has("min_relative_volume"))
            params.set("min_relative_volume", "1.5");
        await loadScreener(normalized, params);
    }
    async function loadScreener(category, params) {
        setScreenerBusy(true);
        setFeedback(`[NSE] scanning listed equities and ranking available quotes…`);
        setScreenerCategory(category);
        const query = params || new URLSearchParams({ category, series: "EQ", limit: "50", offset: "0" });
        try {
            const payload = await api(`market/india/screener?${query.toString()}`);
            setScreener(payload);
            setScreenerOpen(true);
            const meta = payload.meta || {};
            setFeedback(`NSE screener: ${payload.total} matches · ${meta.coverage_pct ?? 0}% quote coverage · use the table controls`);
        }
        catch (error) {
            setFeedback(`[NSE screener] ${error instanceof Error ? error.message : "Unable to load screener"}`);
        }
        finally {
            setScreenerBusy(false);
        }
    }
    async function runCommand(event) {
        event.preventDefault();
        const raw = command.trim();
        if (!raw)
            return;
        setCommand("");
        const { verb, args } = parseCommand(raw);
        const commandRequestId = ++sideRequestId.current;
        setSideLoading(false);
        setSideError("");
        if (["add", "watch"].includes(verb)) {
            if (!args.length)
                return setFeedback("usage: add SYMBOL");
            addWatchlist(args);
        }
        else if (["rm", "remove", "unwatch"].includes(verb)) {
            if (!args.length)
                return setFeedback("usage: rm SYMBOL");
            removeWatchlist(args);
        }
        else if (["select", "sel"].includes(verb)) {
            if (!args.length)
                return setFeedback("usage: select SYMBOL");
            await selectSymbol(args[0]);
        }
        else if (["search", "find"].includes(verb)) {
            const query = args.join(" ");
            if (!query)
                return setFeedback("usage: search QUERY");
            setLastSearchQuery(query);
            try {
                const results = await api(`instruments/search?q=${encodeURIComponent(query)}`);
                if (commandRequestId !== sideRequestId.current) return;
                setSideMode("search");
                setActiveSideTab("search");
                setLastSearchQuery(query);
                setSideTitle(`SEARCH · ${query.toUpperCase()}`);
                setSideData(results);
                setFeedback(results.length ? `${results.length} search matches · select a result to open chart` : `no matches for '${query}'`);
            }
            catch (error) {
                setFeedback(`[search] ${error instanceof Error ? error.message : "Search failed"}`);
            }
        }
        else if (verb === "india") {
            const query = args.join(" ");
            try {
                const suffix = query ? `?q=${encodeURIComponent(query)}&limit=50` : "?limit=50&offset=0";
                const payload = await api(`instruments/india${suffix}`);
                if (commandRequestId !== sideRequestId.current) return;
                setSideMode("india");
                setActiveSideTab("nse");
                setSideTitle(query ? `NSE INDIA · ${query.toUpperCase()}` : "NSE INDIA · BROWSE");
                setSideData(payload);
                setFeedback(`browsing NSE (${payload.total} listed) · select a symbol to view chart`);
            }
            catch (error) {
                setFeedback(`[india] ${error instanceof Error ? error.message : "NSE list unavailable"}`);
            }
        }
        else if (verb === "movers") {
            const category = (args[0] || "gainers").toLowerCase();
            if (!["gainers", "losers", "active"].includes(category))
                return setFeedback("usage: movers gainers|losers|active");
            try {
                const payload = await api(`market/movers?category=${category}`);
                if (commandRequestId !== sideRequestId.current) return;
                setSideMode("movers");
                setActiveSideTab(category);
                setSideTitle(`MOVERS · ${category.toUpperCase()}`);
                setSideData(payload);
                setFeedback(`showing ${category} · select a symbol to switch back to top-of-book`);
            }
            catch (error) {
                setFeedback(`[movers] ${error instanceof Error ? error.message : "Mover list unavailable"}`);
            }
        }
        else if (["india-movers", "screener", "nse"].includes(verb)) {
            await openIndiaScreener((args[0] || "gainers").toLowerCase(), args.slice(1));
        }
        else if (verb === "news") {
            try {
                const payload = await api(`market/news/${encodeURIComponent(selected)}`);
                if (commandRequestId !== sideRequestId.current) return;
                setSideMode("news");
                setActiveSideTab("news");
                setSideTitle(`NEWS · ${selected}`);
                setSideData(payload);
                setFeedback(`news for ${selected}`);
            }
            catch (error) {
                setFeedback(`[news] ${error instanceof Error ? error.message : "News unavailable"}`);
            }
        }
        else if (["interval", "int"].includes(verb)) {
            const value = (args[0] || "").toLowerCase();
            if (!INTERVALS.includes(value))
                return setFeedback(`usage: interval one of ${INTERVALS.join(" | ")}`);
            setIntervalValue(value);
            setFeedback(`interval → ${value}`);
        }
        else if (["help", "?"].includes(verb)) {
            setShowHelp(true);
            setFeedback("command reference opened");
        }
        else if (["quit", "exit"].includes(verb)) {
            manualDisconnect.current = true;
            wsRef.current?.close();
            setStatus("closed");
            setFeedback("live stream disconnected · reload the page to reconnect");
        }
        else {
            setFeedback(`unknown command '${verb}' · try help`);
        }
    }
    function clickResult(symbol) {
        void selectSymbol(symbol);
    }
    async function activateSideTab(tab) {
        const requestId = ++sideRequestId.current;
        setActiveSideTab(tab);
        setSideError("");
        if (tab === "topbook") {
            setSideLoading(false);
            setSideMode("topbook");
            setSideTitle("TOP OF BOOK");
            return;
        }
        if (tab === "search" && !lastSearchQuery.trim()) {
            setSideLoading(false);
            setSideMode("search");
            setSideTitle("SEARCH · NO QUERY");
            setSideData([]);
            setFeedback("enter `search COMPANY OR SYMBOL` in the command bar to populate Search results");
            return;
        }
        setSideLoading(true);
        try {
            if (tab === "search") {
                const payload = await api(`instruments/search?q=${encodeURIComponent(lastSearchQuery)}`);
                if (requestId !== sideRequestId.current) return;
                setSideMode("search");
                setSideTitle(`SEARCH · ${lastSearchQuery.toUpperCase()}`);
                setSideData(Array.isArray(payload) ? payload : []);
            } else if (["gainers", "losers", "active"].includes(tab)) {
                const payload = await api(`market/movers?category=${tab}`);
                if (requestId !== sideRequestId.current) return;
                setSideMode("movers");
                setSideTitle(`MOVERS · ${tab.toUpperCase()}`);
                setSideData(Array.isArray(payload) ? payload : []);
            } else if (tab === "nse") {
                const payload = await api("instruments/india?limit=50&offset=0");
                if (requestId !== sideRequestId.current) return;
                setSideMode("india");
                setSideTitle("NSE INDIA · BROWSE");
                setSideData(payload);
            } else if (tab === "news") {
                const payload = await api(`market/news/${encodeURIComponent(selected)}`);
                if (requestId !== sideRequestId.current) return;
                setSideMode("news");
                setSideTitle(`NEWS · ${selected}`);
                setSideData(payload);
            }
        } catch (error) {
            if (requestId === sideRequestId.current) {
                const message = error instanceof Error ? error.message : "Unable to load results";
                setSideError(message);
                setFeedback(`[${tab}] ${message}`);
            }
        } finally {
            if (requestId === sideRequestId.current) setSideLoading(false);
        }
    }

    async function refreshScreener() {
        const params = new URLSearchParams({ category: screenerCategory, series: "EQ", limit: "50", offset: "0", refresh: "true" });
        await loadScreener(screenerCategory, params);
    }
    async function signOut() {
        await fetch("/api/logout", { method: "POST" });
        window.location.assign("/login");
    }
    function handleCommandKey(event) {
        if (event.key === "ArrowUp" && commandInput.current) {
            event.preventDefault();
            commandInput.current.select();
        }
    }
    return (<main className="terminal-shell">
      <header className="terminal-header">
        <div className="brand-lockup"><span className="brand-glyph">SM</span><span className="brand-name">MARKET TERMINAL</span><span className="brand-tag">RESEARCH / MARKET DATA</span></div>
        <div className="header-right"><span className={`status-dot ${status}`}/> <span className={`status-label ${status}`}>{status.toUpperCase()}</span><span className="header-clock">{clock ? formatUtcTime(clock) : "---- UTC"}</span><button className="logout-button" onClick={signOut}>SIGN OUT ↗</button></div>
      </header>

      <section className="terminal-body">
        <aside className="watchlist-panel">
          <div className="panel-heading"><span>WATCHLIST</span><span className="panel-count">{watchlist.length.toString().padStart(2, "0")}</span></div>
          <div className="watchlist-scroll">
            {watchlist.map((symbol) => {
            const quote = quotes[symbol];
            const positive = (quote?.change_pct || 0) >= 0;
            return (<button key={symbol} className={`watch-row ${selected === symbol ? "active" : ""}`} onClick={() => void selectSymbol(symbol)}>
                  <span className="watch-symbol">{symbol}</span>
                  <span className="watch-numbers"><span>{quote ? number(quote.ltp, 2) : "—"}</span><span className={quote ? (positive ? "positive" : "negative") : "dim"}>{quote ? `${positive ? "+" : ""}${number(quote.change_pct, 2)}%` : "WAIT"}</span></span>
                </button>);
        })}
            {!watchlist.length && <div className="empty-hint">Watchlist empty.<br />Use add SYMBOL.</div>}
          </div>
          <div className="watchlist-foot"><span>LOCAL WATCHLIST</span><span>⌘ /</span></div>
        </aside>

        <section className="chart-panel">
          <div className="chart-topline">
            <div><span className="ticker-selected">{selected}</span><span className="chart-interval">[{interval}]</span></div>
            <div className="chart-range">{chartLast !== undefined ? `LAST ${number(chartLast)}` : "LAST —"}<span>HI {number(chart.hi)}</span><span>LO {number(chart.lo)}</span></div>
          </div>
          <div className="chart-toolbar">
            <span className="section-kicker">PRICE HISTORY / OHLCV</span>
            <div className="interval-tabs">
              {INTERVALS.map((value) => <button key={value} className={interval === value ? "selected" : ""} onClick={() => setIntervalValue(value)}>{value}</button>)}
              <button className="refresh-chart" onClick={() => void refreshChart()} title="Refresh chart">↻</button>
            </div>
          </div>
          <div className="chart-viewport" ref={chartViewport}>
            <MarketChart
              candles={safeCandles}
              symbol={selected}
              interval={interval}
              loading={busy}
              livePrice={selectedQuote?.ltp}
            />
          </div>
          <div className="chart-axis"><span>{formatMarketDate(safeCandles[0]?.ts)}</span><span>{safeCandles.length ? `${safeCandles.length} BARS · ${interval.toUpperCase()}` : "WAITING FOR DATA"}</span><span>{formatMarketDate(safeCandles.at(-1)?.ts)}</span></div>
          <div className="indicator-row">
            <span>SMA20 <b>{number(indicators.sma20)}</b></span><span>EMA12 <b>{number(indicators.ema12)}</b></span><span>EMA26 <b>{number(indicators.ema26)}</b></span><span>RSI14 <b>{number(indicators.rsi14)}</b></span>
          </div>
          <div className="chart-note">INDICATORS COMPUTED FROM PRICE HISTORY · PROVIDER-SUPPLIED DATA · NOT AN EXECUTION FEED</div>
        </section>

        <aside className="side-panel" aria-label="Market results">
          <div className="panel-heading"><span>{sideTitle}</span><button className="panel-reset" title="Reset panel" aria-label="Show top of book" onClick={() => void activateSideTab("topbook")}>↺</button></div>
          <nav className="side-tabs" role="tablist" aria-label="Market result tabs">
            {[["topbook", "BOOK"], ["search", "SEARCH"], ["gainers", "GAINERS"], ["losers", "LOSERS"], ["active", "ACTIVE"], ["nse", "NSE"], ["news", "NEWS"]].map(([key, label]) => <button key={key} type="button" role="tab" aria-selected={activeSideTab === key} className={activeSideTab === key ? "active" : ""} onClick={() => void activateSideTab(key)}>{label}</button>)}
          </nav>
          <div className="side-panel-content" role="tabpanel">
            {sideLoading && <div className="side-empty side-loading"><span className="loading-pulse"/> LOADING {activeSideTab.toUpperCase()} RESULTS…</div>}
            {!sideLoading && sideError && <div className="side-empty side-error-state"><strong>RESULTS UNAVAILABLE</strong><span>{sideError}</span><button type="button" onClick={() => void activateSideTab(activeSideTab)}>RETRY ↻</button></div>}
            {!sideLoading && !sideError && sideMode === "topbook" && <TopBook quote={selectedQuote} symbol={selected}/>}
            {!sideLoading && !sideError && sideMode === "search" && <InstrumentList items={sideData || []} onSelect={clickResult}/>}
            {!sideLoading && !sideError && sideMode === "india" && <IndiaList payload={sideData} onSelect={clickResult}/>}
            {!sideLoading && !sideError && sideMode === "movers" && <MoversList items={sideData || []} onSelect={clickResult}/>}
            {!sideLoading && !sideError && sideMode === "news" && <NewsList payload={sideData}/>}
          </div>
        </aside>
      </section>

      <div className="ticker-tape" aria-label="Live watchlist ticker">
        <span className="ticker-label">LIVE FEED</span>
        <div className="ticker-items">
          {cleanSymbols([...watchlist, selected]).map((symbol) => {
            const quote = quotes[symbol];
            const positive = (quote?.change_pct || 0) >= 0;
            return <button key={symbol} onClick={() => void selectSymbol(symbol)}><b>{symbol}</b><span>{quote ? number(quote.ltp) : "—"}</span><em className={quote ? (positive ? "positive" : "negative") : "dim"}>{quote ? `${positive ? "+" : ""}${number(quote.change_pct)}%` : "WAIT"}</em></button>;
        })}
        </div>
      </div>

      <form className="command-area" onSubmit={runCommand}>
        <div className="command-input-line"><span className="prompt">›</span><input ref={commandInput} value={command} onChange={(event) => setCommand(event.target.value)} onKeyDown={handleCommandKey} placeholder="add AAPL · select TSLA · search tesla · india · india-movers gainers · news · help" aria-label="Terminal command"/><button type="submit" disabled={!command.trim()}>RUN ↵</button></div>
        <div className="command-feedback"><span className="feedback-prefix">OUTPUT</span><span>{feedback}</span><button type="button" onClick={() => setShowHelp((value) => !value)}>HELP ?</button></div>
      </form>

      {showHelp && <HelpOverlay onClose={() => setShowHelp(false)}/>}
      {screenerOpen && screener && (<ScreenerOverlay payload={screener} category={screenerCategory} rows={visibleScreenerRows} filter={screenerFilter} live={screenerLive} busy={screenerBusy} onFilter={setScreenerFilter} onCategory={(value) => { setScreenerFilter(""); void loadScreener(value); }} onRefresh={() => void refreshScreener()} onLive={() => setScreenerLive((value) => !value)} onSelect={(row) => { setScreenerOpen(false); void selectSymbol(row.symbol); }} onWatch={(row) => addWatchlist([row.symbol])} onDetails={setDetailRow} onClose={() => { setScreenerOpen(false); setDetailRow(null); }}/>)}
      {detailRow && <DetailOverlay row={detailRow} onClose={() => setDetailRow(null)} onSelect={() => { setScreenerOpen(false); setDetailRow(null); void selectSymbol(detailRow.symbol); }} onWatch={() => addWatchlist([detailRow.symbol])}/>}
      <NotificationCenter notices={notices} onDismiss={(id) => setNotices((current) => current.filter((notice) => notice.id !== id))}/>
    </main>);
}
function NotificationCenter({ notices, onDismiss }) {
    if (!notices.length) return null;
    return <div className="notification-stack" aria-live="assertive" aria-relevant="additions">
      {notices.map((notice) => <article className={`app-notice ${notice.level || "error"}`} role={notice.level === "warning" ? "status" : "alert"} key={notice.id}>
        <div className="notice-mark" aria-hidden="true">{notice.level === "warning" ? "!" : "×"}</div>
        <div className="notice-content">
          <div className="notice-heading"><strong>{notice.title}</strong><span>{(notice.level || "error").toUpperCase()}</span></div>
          <p>{notice.message}</p>
          {notice.detail && <details><summary>DIAGNOSTIC DETAILS</summary><code>{notice.detail}</code></details>}
          <small>{notice.source} · {new Date(notice.createdAt).toLocaleTimeString()}</small>
        </div>
        <button type="button" className="notice-close" onClick={() => onDismiss(notice.id)} aria-label="Dismiss notification">×</button>
      </article>)}
    </div>;
}

function TopBook({ quote, symbol }) {
    if (!quote)
        return <div className="side-empty">WAITING FOR A QUOTE…</div>;
    if (quote.bid == null || quote.ask == null)
        return <div className="side-empty">TOP OF BOOK DATA NOT AVAILABLE FOR THIS SYMBOL VIA THE CURRENT FEED.</div>;
    return <div className="topbook-grid"><div><span>BID</span><strong className="positive">{number(quote.bid)}</strong>{quote.bid_size != null && <small>SIZE {quote.bid_size}</small>}</div><div><span>ASK</span><strong className="negative">{number(quote.ask)}</strong>{quote.ask_size != null && <small>SIZE {quote.ask_size}</small>}</div><p>{symbol} · {quote.exchange || "MARKET"} · {quote.source || "POLL"}</p></div>;
}
function InstrumentList({ items, onSelect }) {
    if (!items.length)
        return <div className="side-empty">NO SEARCH RESULTS. TRY `search RELIANCE` OR ANOTHER COMPANY / TICKER.</div>;
    return <div className="side-list">{items.slice(0, 20).map((item) => <button key={`${item.symbol}-${item.exchange || ""}`} onClick={() => onSelect(item.symbol)}><b>{item.symbol}</b><span>{item.name || item.exchange || ""}</span><small>{item.exchange || item.type || "INSTRUMENT"}</small></button>)}</div>;
}
function IndiaList({ payload, onSelect }) {
    const items = payload?.results || [];
    if (!items.length)
        return <div className="side-empty">NO MATCHES. TRY `INDIA RELIANCE`.</div>;
    return <div className="side-list"><div className="side-meta">{payload?.total || 0} NSE EQUITIES · FIRST {items.length}</div>{items.map((item) => <button key={item.symbol} onClick={() => onSelect(item.yahoo_symbol || item.symbol)}><b>{item.symbol}</b><span>{item.name || ""}</span><small>{item.yahoo_symbol || item.series || "NSE"}</small></button>)}</div>;
}
function MoversList({ items, onSelect }) {
    if (!items.length)
        return <div className="side-empty">NO DATA — PROVIDER UNREACHABLE OR EMPTY.</div>;
    return <div className="side-list movers-list">{items.slice(0, 18).map((item, index) => {
            const symbol = String(item.symbol || item.ticker || "");
            const change = Number(item.change_pct || 0);
            return <button key={`${symbol}-${index}`} onClick={() => onSelect(symbol)}><b>{symbol}</b><span>{number(item.price ?? item.ltp)}</span><small className={change >= 0 ? "positive" : "negative"}>{change >= 0 ? "+" : ""}{number(change)}%</small></button>;
        })}</div>;
}
function NewsList({ payload }) {
    if (payload?.configured === false)
        return <div className="side-empty">SET FINNHUB_API_KEY ON THE BACKEND TO ENABLE COMPANY NEWS.</div>;
    const items = payload?.items || [];
    if (!items.length)
        return <div className="side-empty">NO RECENT NEWS FOUND.</div>;
    return <div className="side-news">{items.slice(0, 12).map((item, index) => {
            const rawUrl = typeof item.url === "string" ? item.url : "";
            const safeUrl = /^https?:\/\//i.test(rawUrl) ? rawUrl : "";
            return <article key={String(item.id || index)}><b>{String(item.headline || "Untitled headline")}</b><span>{String(item.source || "")}</span>{safeUrl && <a href={safeUrl} target="_blank" rel="noopener noreferrer">OPEN STORY ↗</a>}</article>;
        })}</div>;
}
function HelpOverlay({ onClose }) {
    const commands = [
        ["AAPL / select AAPL", "Select a ticker and load its chart and top-of-book"],
        ["add AAPL / rm AAPL", "Add or remove symbols from your browser-local watchlist"],
        ["search tesla", "Search global equities, ETFs, indices and crypto"],
        ["india / india reliance", "Browse or search the NSE's published equity list"],
        ["movers gainers|losers|active", "Show global/US market movers in the side panel"],
        ["india-movers gainers", "Open the NSE-wide screener; categories include losers, active, turnover, unusual-volume and all"],
        ["news", "Show company news when Finnhub is configured on the backend"],
        ["interval 1m|5m|15m|1h|1d|1w", "Change chart resolution"],
        ["help / ?", "Show this command reference"]
    ];
    return <div className="overlay-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget)
        onClose(); }}><section className="help-window"><div className="overlay-title"><b>COMMAND REFERENCE</b><button onClick={onClose}>ESC ✕</button></div>{commands.map(([command, description]) => <div className="help-row" key={command}><code>{command}</code><span>{description}</span></div>)}<p className="overlay-footnote">WEB VERSION · WATCHLIST IS STORED IN THIS BROWSER · LIVE ORDER ROUTING IS NOT AVAILABLE</p></section></div>;
}
function ScreenerOverlay({ payload, category, rows, filter, live, busy, onFilter, onCategory, onRefresh, onLive, onSelect, onWatch, onDetails, onClose }) {
    const refreshRef = useRef(onRefresh);
    useEffect(() => { refreshRef.current = onRefresh; }, [onRefresh]);
    useEffect(() => {
        if (!live)
            return;
        const id = window.setInterval(() => refreshRef.current(), 60000);
        return () => window.clearInterval(id);
    }, [live]);
    const meta = payload.meta || {};
    const scanned = meta.scanned_at ? new Date(meta.scanned_at * 1000).toISOString().slice(11, 19) : "—";
    const names = { gainers: "TOP GAINERS", losers: "TOP LOSERS", active: "MOST ACTIVE · VOLUME", turnover: "HIGHEST TURNOVER", "unusual-volume": "UNUSUAL VOLUME", all: "ALL QUOTED NSE EQUITIES" };
    return <div className="overlay-backdrop screener-backdrop"><section className="screener-window">
    <div className="overlay-title"><b>INDIA / NSE · {names[category]}</b><button onClick={onClose}>ESC ✕</button></div>
    <div className="screener-meta"><span>{meta.quote_count || 0}/{meta.universe_total || 0} SYMBOLS</span><span>{meta.coverage_pct ?? 0}% QUOTE COVERAGE</span><span>SCAN {scanned} UTC</span><span>ADV {meta.advancers ?? 0} / DEC {meta.decliners ?? 0} / FLAT {meta.unchanged ?? 0}</span><span>YAHOO SNAPSHOT · NOT EXCHANGE-CERTIFIED LIVE DATA</span></div>
    <div className="screener-tools"><input value={filter} onChange={(event) => onFilter(event.target.value)} placeholder="Filter visible results by symbol or company…"/><div className="screener-actions">{CATEGORIES.map((value) => <button key={value} className={value === category ? "active" : ""} onClick={() => onCategory(value)}>{value === "unusual-volume" ? "UNUSUAL" : value.toUpperCase()}</button>)}<button onClick={onRefresh} disabled={busy}>{busy ? "SCANNING…" : "↻ REFRESH"}</button><button onClick={onLive}>{live ? "Ⅱ PAUSE" : "▶ LIVE"}</button></div></div>
    <div className="screener-table-wrap"><table className="screener-table"><thead><tr><th>#</th><th>SYMBOL</th><th>COMPANY</th><th>LTP ₹</th><th>CHG %</th><th>VOLUME</th><th>TURNOVER ₹</th><th>RVOL</th><th>ACTIONS</th></tr></thead><tbody>
      {rows.map((row, index) => <tr key={`${row.symbol}-${index}`}><td data-label="#">{index + 1}</td><td data-label="SYMBOL"><button className="table-symbol" onClick={() => onSelect(row)}>{row.nse_symbol || row.symbol}</button></td><td data-label="COMPANY" className="company-cell">{row.name || "—"}</td><td data-label="LTP ₹">{number(row.ltp)}</td><td data-label="CHG %" className={Number(row.change_pct || 0) >= 0 ? "positive" : "negative"}>{Number(row.change_pct || 0) >= 0 ? "+" : ""}{number(row.change_pct)}%</td><td data-label="VOLUME">{compact(row.volume)}</td><td data-label="TURNOVER ₹">{compact(row.turnover)}</td><td data-label="RVOL">{number(row.relative_volume)}</td><td data-label="ACTIONS" className="row-actions"><button onClick={() => onDetails(row)}>DETAIL</button><button onClick={() => onWatch(row)}>+ WATCH</button></td></tr>)}
      {!rows.length && <tr><td colSpan={9} className="no-rows">NO ROWS MATCH THIS FILTER.</td></tr>}
    </tbody></table></div>
    <div className="screener-footer"><span>{rows.length} DISPLAYED / {payload.total} MATCHES</span><span>{meta.failed_batches ? `${meta.failed_batches} QUOTE BATCHES FAILED · ` : ""}{live ? "AUTO-REFRESH ON · 60S" : "AUTO-REFRESH PAUSED"}</span><span>SELECT SYMBOL TO OPEN CHART · DETAIL FOR QUOTE SNAPSHOT · ESC TO CLOSE</span></div>
  </section></div>;
}
function DetailOverlay({ row, onClose, onSelect, onWatch }) {
    const up = Number(row.change_pct || 0) >= 0;
    return <div className="overlay-backdrop detail-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget)
        onClose(); }}><section className="detail-window"><div className="overlay-title"><b>QUOTE SNAPSHOT · {row.symbol}</b><button onClick={onClose}>ESC ✕</button></div><h2>{row.name || row.symbol}</h2><div className="detail-price">₹{number(row.ltp)} <span className={up ? "positive" : "negative"}>{up ? "+" : ""}{number(row.change_pct)}%</span></div><div className="detail-stats"><div><small>VOLUME</small><b>{compact(row.volume)}</b></div><div><small>TURNOVER · INDICATIVE</small><b>₹{compact(row.turnover)}</b></div><div><small>RELATIVE VOLUME</small><b>{number(row.relative_volume)}×</b></div><div><small>NSE SERIES</small><b>{row.series || "EQ"}</b></div></div><p className="detail-disclaimer">Market data is a Yahoo Finance snapshot. Turnover and relative volume are indicative screening metrics, not exchange-certified figures or trading signals.</p><div className="detail-actions"><button onClick={onWatch}>+ ADD TO WATCHLIST</button><button className="primary" onClick={onSelect}>OPEN IN CHART →</button></div></section></div>;
}

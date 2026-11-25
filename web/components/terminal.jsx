"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
const DEFAULT_SYMBOLS = ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "^NSEI", "^NSEBANK", "BTC-USD", "AAPL"];
const INTERVALS = ["1m", "5m", "15m", "1h", "1d", "1w"];
const CATEGORIES = ["gainers", "losers", "active", "turnover", "unusual-volume", "all"];
const RESERVED = new Set(["INDIA-MOVERS", "INDIA", "SCREENER", "NSE", "MOVERS", "GAINERS", "LOSERS", "ACTIVE", "TURNOVER", "UNUSUAL-VOLUME"]);
const SYMBOL_RE = /^[A-Z0-9^][A-Z0-9.^=_-]{0,31}$/;
const BLOCKS = " ▁▂▃▄▅▆▇█";
async function api(path, init) {
    const response = await fetch(`/api/backend/${path.replace(/^\//, "")}`, {
        ...init,
        cache: "no-store",
        headers: { ...(init?.headers || {}) }
    });
    let payload;
    try {
        payload = await response.json();
    }
    catch {
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
        const symbol = value.trim().toUpperCase();
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
function formatUtcTime(date) {
    return `${date.toISOString().slice(0, 19).replace("T", " ")} UTC`;
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
    const wantedSymbols = useRef([...DEFAULT_SYMBOLS]);
    const previousSymbols = useRef([...DEFAULT_SYMBOLS]);
    const mounted = useRef(false);
    const manualDisconnect = useRef(false);
    const selectedQuote = quotes[selected];
    const chart = useMemo(() => renderChart(candles.map((row) => row.close), chartWidth, 15), [candles, chartWidth]);
    const chartLast = candles.length ? candles[candles.length - 1].close : selectedQuote?.ltp;
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
            ws.send(JSON.stringify({
                subscribe: next.filter((symbol) => !previousSymbols.current.includes(symbol)),
                unsubscribe: previousSymbols.current.filter((symbol) => !next.includes(symbol))
            }));
        }
        previousSymbols.current = [...wantedSymbols.current];
    }, [watchlist, selected]);
    useEffect(() => {
        setClock(new Date());
        const id = window.setInterval(() => setClock(new Date()), 1000);
        return () => window.clearInterval(id);
    }, []);
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
            setQuotes((current) => {
                const next = { ...current };
                for (const quote of payload)
                    next[quote.symbol] = { ...next[quote.symbol], ...quote };
                return next;
            });
        }
        catch (error) {
            setFeedback(`[seed] ${error instanceof Error ? error.message : "Could not load quotes"}`);
        }
    }, [watchlist, selected]);
    const refreshChart = useCallback(async () => {
        setBusy(true);
        try {
            const [history, technicals] = await Promise.all([
                api(`market/candles/${encodeURIComponent(selected)}?interval=${interval}`),
                api(`market/indicators/${encodeURIComponent(selected)}?interval=${interval}`)
            ]);
            setCandles(history);
            setIndicators(technicals);
            setFeedback(`chart refreshed · ${selected} · ${interval}`);
        }
        catch (error) {
            setCandles([]);
            setIndicators({});
            setFeedback(`[chart] ${error instanceof Error ? error.message : "Unable to load chart"}`);
        }
        finally {
            setBusy(false);
        }
    }, [selected, interval]);
    useEffect(() => {
        void refreshQuotes();
        const id = window.setInterval(() => void refreshQuotes(), 60000);
        return () => window.clearInterval(id);
    }, [refreshQuotes]);
    useEffect(() => {
        void refreshChart();
        const id = window.setInterval(() => void refreshChart(), 15000);
        return () => window.clearInterval(id);
    }, [refreshChart]);
    useEffect(() => {
        let cancelled = false;
        manualDisconnect.current = false;
        let socket = null;
        let retryTimer;
        let heartbeatTimer;
        let backoff = 1000;
        let lastHeartbeat = Date.now();
        const connect = async () => {
            if (cancelled)
                return;
            setStatus(backoff > 1000 ? "reconnecting" : "connecting");
            try {
                const response = await fetch("/api/ws-ticket", { cache: "no-store" });
                if (!response.ok)
                    throw new Error("Could not obtain live-stream ticket");
                const config = await response.json();
                if (cancelled)
                    return;
                const url = new URL(`${config.wsBaseUrl.replace(/\/$/, "")}/ws/ticks`);
                if (config.ticket)
                    url.searchParams.set("ticket", config.ticket);
                socket = new WebSocket(url.toString());
                wsRef.current = socket;
                socket.onopen = () => {
                    if (cancelled)
                        return socket?.close();
                    backoff = 1000;
                    lastHeartbeat = Date.now();
                    setStatus("live");
                    socket?.send(JSON.stringify({ subscribe: wantedSymbols.current }));
                };
                socket.onmessage = (event) => {
                    try {
                        const message = JSON.parse(String(event.data));
                        if (message.type === "heartbeat") {
                            lastHeartbeat = Date.now();
                            return;
                        }
                        if (message.symbol) {
                            setQuotes((current) => ({
                                ...current,
                                [message.symbol]: { ...current[message.symbol], ...message }
                            }));
                        }
                    }
                    catch {
                        // Ignore malformed provider messages without dropping the connection.
                    }
                };
                socket.onerror = () => setStatus("reconnecting");
                socket.onclose = () => {
                    if (heartbeatTimer)
                        window.clearInterval(heartbeatTimer);
                    if (cancelled || manualDisconnect.current)
                        return;
                    setStatus("reconnecting");
                    retryTimer = window.setTimeout(() => {
                        backoff = Math.min(backoff * 2, 15000);
                        void connect();
                    }, backoff);
                };
                heartbeatTimer = window.setInterval(() => {
                    if (socket?.readyState === WebSocket.OPEN && Date.now() - lastHeartbeat > 30000)
                        socket.close();
                }, 5000);
            }
            catch {
                if (!cancelled) {
                    setStatus("reconnecting");
                    retryTimer = window.setTimeout(() => {
                        backoff = Math.min(backoff * 2, 15000);
                        void connect();
                    }, backoff);
                }
            }
        };
        void connect();
        return () => {
            cancelled = true;
            if (retryTimer)
                window.clearTimeout(retryTimer);
            if (heartbeatTimer)
                window.clearInterval(heartbeatTimer);
            socket?.close();
            wsRef.current = null;
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
        const symbol = cleanSymbols([raw])[0];
        if (!symbol) {
            setFeedback(`'${raw}' is not a valid ticker symbol`);
            return;
        }
        setSelected(symbol);
        setSideMode("topbook");
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
            .then((payload) => setQuotes((current) => {
            const next = { ...current };
            for (const quote of payload)
                next[quote.symbol] = { ...next[quote.symbol], ...quote };
            return next;
        }))
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
            try {
                const results = await api(`instruments/search?q=${encodeURIComponent(query)}`);
                setSideMode("search");
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
                setSideMode("india");
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
                setSideMode("movers");
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
                setSideMode("news");
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
            {chart.lines.length ? (<pre className="ascii-chart" aria-label={`${selected} historical price chart`}>
                {chart.lines.map((line, row) => <span className="chart-line" key={row}>{line.map((char, column) => <span key={column} className={chart.directions[column] ? "chart-up" : "chart-down"}>{char}</span>)}</span>)}
              </pre>) : <div className="chart-empty">{busy ? "FETCHING MARKET HISTORY…" : "NO CANDLE DATA · SELECT A SYMBOL OR CHECK API CONNECTION"}</div>}
          </div>
          <div className="chart-axis"><span>{candles[0]?.ts ? new Date(candles[0].ts).toLocaleDateString() : "—"}</span><span>{candles.length ? `${candles.length} BARS · ${interval.toUpperCase()}` : "WAITING FOR DATA"}</span><span>{candles[candles.length - 1]?.ts ? new Date(candles[candles.length - 1].ts).toLocaleDateString() : "—"}</span></div>
          <div className="indicator-row">
            <span>SMA20 <b>{number(indicators.sma20)}</b></span><span>EMA12 <b>{number(indicators.ema12)}</b></span><span>EMA26 <b>{number(indicators.ema26)}</b></span><span>RSI14 <b>{number(indicators.rsi14)}</b></span>
          </div>
          <div className="chart-note">INDICATORS COMPUTED SERVER-SIDE · PRICE DATA IS PROVIDER-SUPPLIED · NOT AN EXECUTION FEED</div>
        </section>

        <aside className="side-panel">
          <div className="panel-heading"><span>{sideTitle}</span><button className="panel-reset" onClick={() => { setSideMode("topbook"); setSideTitle("TOP OF BOOK"); }}>↺</button></div>
          {sideMode === "topbook" && <TopBook quote={selectedQuote} symbol={selected}/>}
          {sideMode === "search" && <InstrumentList items={sideData || []} onSelect={clickResult}/>}
          {sideMode === "india" && <IndiaList payload={sideData} onSelect={clickResult}/>}
          {sideMode === "movers" && <MoversList items={sideData || []} onSelect={clickResult}/>}
          {sideMode === "news" && <NewsList payload={sideData}/>}
          <div className="side-quick-actions"><button onClick={() => void runCommandFromButton("news")}>NEWS</button><button onClick={() => void runCommandFromButton("movers gainers")}>GAINERS</button><button onClick={() => void runCommandFromButton("india")}>NSE LIST</button></div>
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
    </main>);
    async function runCommandFromButton(raw) {
        setCommand(raw);
        const { verb, args } = parseCommand(raw);
        if (verb === "news") {
            try {
                const payload = await api(`market/news/${encodeURIComponent(selected)}`);
                setSideMode("news");
                setSideTitle(`NEWS · ${selected}`);
                setSideData(payload);
                setFeedback(`news for ${selected}`);
            }
            catch (error) {
                setFeedback(`[news] ${error instanceof Error ? error.message : "News unavailable"}`);
            }
        }
        else if (verb === "movers") {
            try {
                const payload = await api(`market/movers?category=${args[0] || "gainers"}`);
                setSideMode("movers");
                setSideTitle(`MOVERS · ${(args[0] || "gainers").toUpperCase()}`);
                setSideData(payload);
            }
            catch (error) {
                setFeedback(`[movers] ${error instanceof Error ? error.message : "Mover list unavailable"}`);
            }
        }
        else if (verb === "india") {
            try {
                const payload = await api("instruments/india?limit=50&offset=0");
                setSideMode("india");
                setSideTitle("NSE INDIA · BROWSE");
                setSideData(payload);
            }
            catch (error) {
                setFeedback(`[india] ${error instanceof Error ? error.message : "NSE list unavailable"}`);
            }
        }
        setCommand("");
    }
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
        return <div className="side-empty">NO MATCHES FOUND.</div>;
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
      {rows.map((row, index) => <tr key={`${row.symbol}-${index}`}><td>{index + 1}</td><td><button className="table-symbol" onClick={() => onSelect(row)}>{row.nse_symbol || row.symbol}</button></td><td className="company-cell">{row.name || "—"}</td><td>{number(row.ltp)}</td><td className={Number(row.change_pct || 0) >= 0 ? "positive" : "negative"}>{Number(row.change_pct || 0) >= 0 ? "+" : ""}{number(row.change_pct)}%</td><td>{compact(row.volume)}</td><td>{compact(row.turnover)}</td><td>{number(row.relative_volume)}</td><td className="row-actions"><button onClick={() => onDetails(row)}>DETAIL</button><button onClick={() => onWatch(row)}>+ WATCH</button></td></tr>)}
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

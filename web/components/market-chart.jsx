"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

const GREEN = "#00ff41";
const GREEN_SOFT = "#00b83a";
const RED = "#ff4141";
const GRID = "rgba(0, 255, 65, 0.10)";
const MUTED = "#398b56";
const MIN_BARS = 18;
const MAX_BARS = 320;

function asNumber(value, fallback = 0) {
  const result = Number(value);
  return Number.isFinite(result) ? result : fallback;
}

function formatPrice(value) {
  return asNumber(value).toLocaleString("en-IN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function formatVolume(value) {
  const n = asNumber(value);
  if (Math.abs(n) >= 1e7) return `${(n / 1e7).toFixed(2)}Cr`;
  if (Math.abs(n) >= 1e5) return `${(n / 1e5).toFixed(2)}L`;
  if (Math.abs(n) >= 1e3) return `${(n / 1e3).toFixed(1)}K`;
  return Math.round(n).toLocaleString("en-IN");
}

function timeLabel(value, interval) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  if (["1m", "5m", "15m", "1h"].includes(interval)) {
    return date.toLocaleString("en-IN", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
  }
  return date.toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "2-digit" });
}

function movingAverage(rows, period) {
  const output = Array(rows.length).fill(null);
  let sum = 0;
  for (let index = 0; index < rows.length; index += 1) {
    sum += asNumber(rows[index].close);
    if (index >= period) sum -= asNumber(rows[index - period].close);
    if (index >= period - 1) output[index] = sum / period;
  }
  return output;
}

function exponentialAverage(rows, period) {
  const output = Array(rows.length).fill(null);
  if (!rows.length) return output;
  const multiplier = 2 / (period + 1);
  let previous = asNumber(rows[0].close);
  output[0] = previous;
  for (let index = 1; index < rows.length; index += 1) {
    previous = asNumber(rows[index].close) * multiplier + previous * (1 - multiplier);
    output[index] = previous;
  }
  return output;
}

function drawLine(ctx, values, start, end, xFor, yFor, color, width = 1.35) {
  ctx.beginPath();
  let started = false;
  for (let index = start; index < end; index += 1) {
    const value = values[index];
    if (value === null || value === undefined || !Number.isFinite(value)) continue;
    const x = xFor(index);
    const y = yFor(value);
    if (!started) {
      ctx.moveTo(x, y);
      started = true;
    } else {
      ctx.lineTo(x, y);
    }
  }
  if (started) {
    ctx.strokeStyle = color;
    ctx.lineWidth = width;
    ctx.shadowColor = color;
    ctx.shadowBlur = 3;
    ctx.stroke();
    ctx.shadowBlur = 0;
  }
}

function drawChart(canvas, rows, options) {
  const rect = canvas.getBoundingClientRect();
  const width = Math.max(320, Math.floor(rect.width));
  const height = Math.max(220, Math.floor(rect.height));
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  canvas.width = Math.floor(width * dpr);
  canvas.height = Math.floor(height * dpr);
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = "#000";
  ctx.fillRect(0, 0, width, height);

  if (!rows.length) return;

  const left = 14;
  const right = 76;
  const top = 24;
  const bottom = 24;
  const volumeHeight = options.showVolume ? Math.max(35, Math.min(58, height * 0.17)) : 0;
  const volumeGap = options.showVolume ? 13 : 0;
  const priceBottom = height - bottom - volumeHeight - volumeGap;
  const plotWidth = Math.max(80, width - left - right);
  const plotHeight = Math.max(80, priceBottom - top);
  const volumeTop = priceBottom + volumeGap;
  const volumeBottom = height - bottom;
  const count = options.end - options.start;
  const visible = rows.slice(options.start, options.end);
  const highs = visible.map((row) => asNumber(row.high, asNumber(row.close)));
  const lows = visible.map((row) => asNumber(row.low, asNumber(row.close)));
  const minRaw = Math.min(...lows);
  const maxRaw = Math.max(...highs);
  const rawRange = Math.max(maxRaw - minRaw, Math.abs(maxRaw) * 0.001, 0.01);
  const minPrice = minRaw - rawRange * 0.055;
  const maxPrice = maxRaw + rawRange * 0.055;
  const priceRange = Math.max(maxPrice - minPrice, 0.01);
  const maxVolume = Math.max(1, ...visible.map((row) => asNumber(row.volume)));
  const xFor = (index) => left + ((index - options.start + 0.5) / Math.max(count, 1)) * plotWidth;
  const yFor = (price) => top + ((maxPrice - price) / priceRange) * plotHeight;

  // Price grid and right-hand axis.
  ctx.font = "10px monospace";
  ctx.textAlign = "left";
  ctx.textBaseline = "middle";
  for (let tick = 0; tick <= 5; tick += 1) {
    const y = top + (plotHeight * tick) / 5;
    const value = maxPrice - (priceRange * tick) / 5;
    ctx.strokeStyle = GRID;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(left, y);
    ctx.lineTo(left + plotWidth, y);
    ctx.stroke();
    ctx.fillStyle = MUTED;
    ctx.fillText(formatPrice(value), left + plotWidth + 9, y);
  }

  // Volume panel.
  if (options.showVolume) {
    ctx.strokeStyle = "rgba(0, 255, 65, .18)";
    ctx.beginPath();
    ctx.moveTo(left, volumeTop - 5);
    ctx.lineTo(left + plotWidth, volumeTop - 5);
    ctx.stroke();
    ctx.fillStyle = MUTED;
    ctx.textAlign = "left";
    ctx.textBaseline = "top";
    ctx.fillText("VOLUME", left + 2, volumeTop + 1);
  }

  const step = plotWidth / Math.max(count, 1);
  const bodyWidth = Math.max(1.2, Math.min(12, step * 0.64));

  if (options.type === "line" || options.type === "area") {
    const values = rows.map((row) => asNumber(row.close));
    const points = [];
    for (let index = options.start; index < options.end; index += 1) {
      points.push({ x: xFor(index), y: yFor(values[index]) });
    }
    if (points.length) {
      ctx.beginPath();
      points.forEach((point, index) => index === 0 ? ctx.moveTo(point.x, point.y) : ctx.lineTo(point.x, point.y));
      if (options.type === "area") {
        const gradient = ctx.createLinearGradient(0, top, 0, priceBottom);
        gradient.addColorStop(0, "rgba(0,255,65,.22)");
        gradient.addColorStop(1, "rgba(0,255,65,0)");
        ctx.lineTo(points[points.length - 1].x, priceBottom);
        ctx.lineTo(points[0].x, priceBottom);
        ctx.closePath();
        ctx.fillStyle = gradient;
        ctx.fill();
      }
      ctx.beginPath();
      points.forEach((point, index) => index === 0 ? ctx.moveTo(point.x, point.y) : ctx.lineTo(point.x, point.y));
      ctx.strokeStyle = GREEN;
      ctx.lineWidth = 1.8;
      ctx.shadowColor = GREEN;
      ctx.shadowBlur = 7;
      ctx.stroke();
      ctx.shadowBlur = 0;
    }
  } else {
    for (let index = options.start; index < options.end; index += 1) {
      const row = rows[index];
      const x = xFor(index);
      const open = asNumber(row.open, asNumber(row.close));
      const close = asNumber(row.close);
      const high = asNumber(row.high, Math.max(open, close));
      const low = asNumber(row.low, Math.min(open, close));
      const color = close >= open ? GREEN : RED;
      const yOpen = yFor(open);
      const yClose = yFor(close);
      const yHigh = yFor(high);
      const yLow = yFor(low);
      ctx.strokeStyle = color;
      ctx.lineWidth = Math.max(1, Math.min(1.8, bodyWidth * 0.24));
      ctx.beginPath();
      ctx.moveTo(x, yHigh);
      ctx.lineTo(x, yLow);
      ctx.stroke();
      const bodyTop = Math.min(yOpen, yClose);
      const bodyHeight = Math.max(1.2, Math.abs(yClose - yOpen));
      ctx.fillStyle = color;
      ctx.shadowColor = color;
      ctx.shadowBlur = index === options.hoverIndex ? 10 : 2;
      ctx.fillRect(x - bodyWidth / 2, bodyTop, bodyWidth, bodyHeight);
      ctx.shadowBlur = 0;
    }
  }

  // Latest quote reference line, when it is inside the visible price range.
  const livePrice = Number(options.livePrice);
  if (Number.isFinite(livePrice) && livePrice >= minPrice && livePrice <= maxPrice) {
    const liveY = yFor(livePrice);
    ctx.save();
    ctx.setLineDash([5, 4]);
    ctx.strokeStyle = "rgba(0,255,65,.78)";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(left, liveY);
    ctx.lineTo(left + plotWidth, liveY);
    ctx.stroke();
    ctx.restore();
    ctx.fillStyle = "#003b16";
    ctx.fillRect(left + plotWidth + 5, liveY - 9, right - 10, 18);
    ctx.fillStyle = GREEN;
    ctx.textAlign = "left";
    ctx.textBaseline = "middle";
    ctx.fillText(formatPrice(livePrice), left + plotWidth + 9, liveY);
  }

  if (options.showSma) drawLine(ctx, options.sma, options.start, options.end, xFor, yFor, "#e6c84f", 1.25);
  if (options.showEma12) drawLine(ctx, options.ema12, options.start, options.end, xFor, yFor, "#48c8ff", 1.25);
  if (options.showEma26) drawLine(ctx, options.ema26, options.start, options.end, xFor, yFor, "#c084fc", 1.25);

  // Volume bars share candle direction colors.
  if (options.showVolume) {
    for (let index = options.start; index < options.end; index += 1) {
      const row = rows[index];
      const x = xFor(index);
      const volume = Math.max(0, asNumber(row.volume));
      const barHeight = (volume / maxVolume) * Math.max(8, volumeBottom - volumeTop - 13);
      ctx.fillStyle = asNumber(row.close) >= asNumber(row.open) ? "rgba(0,255,65,.42)" : "rgba(255,65,65,.42)";
      ctx.fillRect(x - bodyWidth / 2, volumeBottom - barHeight, bodyWidth, barHeight);
    }
  }

  // Bottom time axis.
  ctx.font = "9px monospace";
  ctx.fillStyle = MUTED;
  ctx.textAlign = "center";
  ctx.textBaseline = "bottom";
  const labels = Math.min(5, count);
  for (let index = 0; index < labels; index += 1) {
    const rowIndex = options.start + Math.round((index * (count - 1)) / Math.max(labels - 1, 1));
    const x = xFor(rowIndex);
    ctx.fillText(timeLabel(rows[rowIndex].ts, options.interval), x, height - 3);
  }

  // Crosshair and price guide.
  if (options.hoverIndex >= options.start && options.hoverIndex < options.end) {
    const x = xFor(options.hoverIndex);
    const y = Math.max(top, Math.min(priceBottom, options.hoverY ?? priceBottom / 2));
    ctx.save();
    ctx.setLineDash([3, 4]);
    ctx.strokeStyle = "rgba(0,255,65,.65)";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(x, top);
    ctx.lineTo(x, volumeBottom);
    ctx.moveTo(left, y);
    ctx.lineTo(left + plotWidth, y);
    ctx.stroke();
    ctx.restore();
    ctx.fillStyle = "#003b16";
    ctx.fillRect(left + plotWidth + 5, y - 9, right - 10, 18);
    ctx.fillStyle = GREEN;
    ctx.textAlign = "left";
    ctx.textBaseline = "middle";
    const priceAtCursor = maxPrice - ((y - top) / plotHeight) * priceRange;
    ctx.fillText(formatPrice(priceAtCursor), left + plotWidth + 9, y);
  }

  // Small legend with the visible window bounds.
  ctx.textAlign = "left";
  ctx.textBaseline = "top";
  ctx.fillStyle = MUTED;
  ctx.fillText(`${visible.length} BARS  ·  ${timeLabel(visible[0]?.ts, options.interval)} — ${timeLabel(visible[visible.length - 1]?.ts, options.interval)}`, left, 5);
}

export default function MarketChart({ candles = [], symbol, interval, loading = false, livePrice }) {
  const canvasRef = useRef(null);
  const stageRef = useRef(null);
  const dragRef = useRef(null);
  const [type, setType] = useState("candles");
  const [showVolume, setShowVolume] = useState(true);
  const [showSma, setShowSma] = useState(true);
  const [showEma12, setShowEma12] = useState(false);
  const [showEma26, setShowEma26] = useState(false);
  const [hover, setHover] = useState(null);
  const [dragging, setDragging] = useState(false);
  const [view, setView] = useState({ bars: 90, offset: 0 });
  const validCandles = useMemo(() => candles.filter((row) => row && Number.isFinite(Number(row.close)) && Number.isFinite(Number(row.open))), [candles]);
  const sma = useMemo(() => movingAverage(validCandles, 20), [validCandles]);
  const ema12 = useMemo(() => exponentialAverage(validCandles, 12), [validCandles]);
  const ema26 = useMemo(() => exponentialAverage(validCandles, 26), [validCandles]);
  const keyRef = useRef(`${symbol}:${interval}`);

  useEffect(() => {
    const key = `${symbol}:${interval}`;
    if (keyRef.current !== key) {
      keyRef.current = key;
      setView({ bars: Math.min(90, Math.max(MIN_BARS, validCandles.length || 90)), offset: 0 });
      setHover(null);
    }
  }, [symbol, interval, validCandles.length]);

  const windowRange = useMemo(() => {
    const bars = Math.max(MIN_BARS, Math.min(MAX_BARS, view.bars, Math.max(validCandles.length, MIN_BARS)));
    const maxOffset = Math.max(0, validCandles.length - bars);
    const offset = Math.max(0, Math.min(maxOffset, view.offset));
    const end = Math.max(0, validCandles.length - offset);
    return { bars, offset, start: Math.max(0, end - bars), end };
  }, [validCandles.length, view]);

  const render = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    drawChart(canvas, validCandles, {
      ...windowRange,
      type,
      showVolume,
      showSma,
      showEma12,
      showEma26,
      sma,
      ema12,
      ema26,
      hoverIndex: hover?.index ?? -1,
      hoverY: hover?.y,
      interval,
      loading,
      livePrice,
    });
  }, [validCandles, windowRange, type, showVolume, showSma, showEma12, showEma26, sma, ema12, ema26, hover, interval, loading, livePrice]);

  const renderRef = useRef(render);
  const frameRef = useRef(null);
  const requestDraw = useCallback(() => {
    if (frameRef.current !== null) return;
    frameRef.current = window.requestAnimationFrame(() => {
      frameRef.current = null;
      renderRef.current?.();
    });
  }, []);

  useEffect(() => {
    renderRef.current = render;
    requestDraw();
  }, [render, requestDraw]);

  useEffect(() => {
    const stage = stageRef.current;
    if (!stage) return undefined;
    const observer = new ResizeObserver(requestDraw);
    observer.observe(stage);
    return () => {
      observer.disconnect();
      if (frameRef.current !== null) window.cancelAnimationFrame(frameRef.current);
    };
  }, [requestDraw]);

  const handlePointerMove = (event) => {
    const rect = event.currentTarget.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;
    if (dragRef.current) {
      const dx = event.clientX - dragRef.current.x;
      const plotWidth = Math.max(80, rect.width - 90);
      const barsMoved = Math.round((dx / plotWidth) * windowRange.bars);
      setView((current) => ({ ...current, offset: Math.max(0, Math.min(validCandles.length - windowRange.bars, dragRef.current.offset + barsMoved)) }));
    }
    const plotWidth = Math.max(80, rect.width - 90);
    const ratio = Math.max(0, Math.min(0.9999, (x - 14) / plotWidth));
    const index = Math.min(windowRange.end - 1, windowRange.start + Math.floor(ratio * windowRange.bars));
    setHover(index >= 0 && index < validCandles.length ? { index, x, y } : null);
  };

  const handleWheel = (event) => {
    if (!validCandles.length) return;
    event.preventDefault();
    const rect = event.currentTarget.getBoundingClientRect();
    const ratio = Math.max(0, Math.min(1, (event.clientX - rect.left - 14) / Math.max(80, rect.width - 90)));
    setView((current) => {
      const oldBars = Math.max(MIN_BARS, Math.min(validCandles.length, current.bars));
      const oldEnd = validCandles.length - current.offset;
      const anchor = Math.max(0, oldEnd - oldBars + ratio * oldBars);
      const nextBars = Math.max(MIN_BARS, Math.min(Math.min(MAX_BARS, validCandles.length), Math.round(oldBars * (event.deltaY < 0 ? 0.82 : 1.22))));
      const nextStart = Math.max(0, Math.min(validCandles.length - nextBars, anchor - ratio * nextBars));
      return { bars: nextBars, offset: Math.max(0, validCandles.length - nextBars - nextStart) };
    });
  };

  const hovered = hover && validCandles[hover.index] ? validCandles[hover.index] : null;
  const zoom = (factor) => setView((current) => ({ ...current, bars: Math.max(MIN_BARS, Math.min(Math.min(MAX_BARS, Math.max(validCandles.length, MIN_BARS)), Math.round(current.bars * factor))) }));
  const fit = () => {
    setView({ bars: Math.min(MAX_BARS, Math.max(MIN_BARS, Math.min(validCandles.length || 90, 90))), offset: 0 });
    setHover(null);
  };

  return (
    <div className="market-chart">
      <div className="market-chart-controls">
        <div className="chart-control-group chart-type-controls" aria-label="Chart type">
          {[ ["candles", "CANDLE"], ["line", "LINE"], ["area", "AREA"] ].map(([value, label]) => (
            <button key={value} type="button" className={type === value ? "active" : ""} onClick={() => setType(value)}>{label}</button>
          ))}
        </div>
        <div className="chart-control-group chart-indicator-controls" aria-label="Chart overlays">
          <button type="button" className={showVolume ? "active" : ""} onClick={() => setShowVolume((value) => !value)}>VOL</button>
          <button type="button" className={showSma ? "active sma-key" : ""} onClick={() => setShowSma((value) => !value)}>SMA20</button>
          <button type="button" className={showEma12 ? "active ema12-key" : ""} onClick={() => setShowEma12((value) => !value)}>EMA12</button>
          <button type="button" className={showEma26 ? "active ema26-key" : ""} onClick={() => setShowEma26((value) => !value)}>EMA26</button>
        </div>
        <div className="chart-control-group chart-zoom-controls" aria-label="Chart navigation">
          <button type="button" onClick={() => zoom(0.8)} title="Zoom in">＋</button>
          <button type="button" onClick={() => zoom(1.25)} title="Zoom out">－</button>
          <button type="button" onClick={fit} title="Fit latest candles">FIT</button>
        </div>
      </div>
      <div
        className={`market-chart-stage ${dragging ? "is-dragging" : ""}`}
        ref={stageRef}
        onPointerDown={(event) => {
          if (event.button !== 0) return;
          dragRef.current = { x: event.clientX, offset: view.offset };
          setDragging(true);
          event.currentTarget.setPointerCapture?.(event.pointerId);
        }}
        onPointerMove={handlePointerMove}
        onPointerUp={() => { dragRef.current = null; setDragging(false); }}
        onPointerCancel={() => { dragRef.current = null; setDragging(false); }}
        onPointerLeave={() => { if (!dragRef.current) setHover(null); }}
        onWheel={handleWheel}
        onDoubleClick={fit}
        role="img"
        aria-label={`${symbol} interactive ${type} chart. Drag to pan, scroll to zoom, double-click to fit.`}
      >
        <canvas ref={canvasRef} className="market-chart-canvas" />
        {hovered && (
          <div className="market-chart-tooltip" style={{ left: 12, top: 10 }}>
            <div className="tooltip-head"><b>{symbol}</b><span>{timeLabel(hovered.ts, interval)}</span></div>
            <div className="tooltip-grid">
              <span>O <b>{formatPrice(hovered.open)}</b></span>
              <span>H <b>{formatPrice(hovered.high)}</b></span>
              <span>L <b>{formatPrice(hovered.low)}</b></span>
              <span>C <b className={asNumber(hovered.close) >= asNumber(hovered.open) ? "positive" : "negative"}>{formatPrice(hovered.close)}</b></span>
              <span className="tooltip-volume">VOL <b>{formatVolume(hovered.volume)}</b></span>
            </div>
          </div>
        )}
        {!validCandles.length && (
          <div className="chart-empty-overlay">{loading ? "FETCHING OHLCV HISTORY…" : "NO CANDLE DATA · CHECK THE MARKET DATA API"}</div>
        )}
        <div className="chart-interaction-hint">DRAG TO PAN&nbsp; · &nbsp;SCROLL TO ZOOM&nbsp; · &nbsp;DOUBLE-CLICK TO FIT</div>
      </div>
    </div>
  );
}

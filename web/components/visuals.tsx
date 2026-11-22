"use client";

import { useEffect, useRef, useState } from "react";

export function Ticker({ value, format }: { value: number; format: (value: number) => string }) {
  const [shown, setShown] = useState(value);
  const from = useRef(value);

  useEffect(() => {
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce) {
      from.current = value;
      setShown(value);
      return;
    }
    const startValue = from.current;
    const start = performance.now();
    let frame = 0;
    const step = (now: number) => {
      const t = Math.min(1, (now - start) / 650);
      const eased = 1 - (1 - t) ** 3;
      setShown(startValue + (value - startValue) * eased);
      if (t < 1) frame = requestAnimationFrame(step);
      else from.current = value;
    };
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [value]);

  return <>{format(shown)}</>;
}

export function Sparkline({
  values,
  startLabel,
  endLabel,
}: {
  values: Array<number | null>;
  startLabel?: string;
  endLabel?: string;
}) {
  const width = 320;
  const height = 72;
  const known = values.filter((value): value is number => value != null);
  if (known.length < 2) {
    return <p className="mt-4 text-xs text-ink-700/60">Ainda sem histórico semanal.</p>;
  }

  const max = Math.max(...known);
  const min = Math.min(...known);
  const span = max - min || 1;
  const segments: string[] = [];
  let current = "";
  const points: Array<{ x: number; y: number } | null> = values.map((value, index) => {
    if (value == null) return null;
    const x = values.length === 1 ? width / 2 : (index / (values.length - 1)) * width;
    const y = height - ((value - min) / span) * (height - 10) - 5;
    return { x, y };
  });

  points.forEach((point) => {
    if (!point) {
      if (current) segments.push(current);
      current = "";
      return;
    }
    current += current ? ` L${point.x},${point.y}` : `M${point.x},${point.y}`;
  });
  if (current) segments.push(current);
  const last = [...points].reverse().find((point) => point != null);

  return (
    <div className="mt-4">
      <svg viewBox={`0 0 ${width} ${height}`} className="h-16 w-full text-brand-700" role="img" aria-label="Série semanal">
        {segments.map((segment) => (
          <path key={segment} d={segment} fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
        ))}
        {last ? <circle cx={last.x} cy={last.y} r="3.5" fill="currentColor" /> : null}
      </svg>
      {startLabel || endLabel ? (
        <div className="mt-1 flex justify-between text-[10px] font-mono uppercase tracking-[0.04em] text-ink-700/50">
          <span>{startLabel}</span>
          <span>{endLabel}</span>
        </div>
      ) : null}
    </div>
  );
}

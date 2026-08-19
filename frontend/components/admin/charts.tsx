"use client";

import { useMemo, useState } from "react";

/** 관리자 통계 화면 공용: 기간 선택 + 외부 라이브러리 없는 SVG 차트. */

export type RangeKey = "7d" | "30d" | "90d" | "custom";

export function rangeParams(range: RangeKey, from: string, to: string): { date_from?: string; date_to?: string } {
  const iso = (d: Date) => {
    // 로컬(KST) 날짜 문자열
    const tz = d.getTimezoneOffset() * 60000;
    return new Date(d.getTime() - tz).toISOString().slice(0, 10);
  };
  const today = new Date();
  if (range === "custom") return { date_from: from || undefined, date_to: to || undefined };
  const days = range === "7d" ? 6 : range === "30d" ? 29 : 89;
  const start = new Date(today);
  start.setDate(today.getDate() - days);
  return { date_from: iso(start), date_to: iso(today) };
}

export function RangePicker({ range, from, to, onChange }: {
  range: RangeKey; from: string; to: string;
  onChange: (r: RangeKey, from: string, to: string) => void;
}) {
  return (
    <div className="rp">
      <div className="seg">
        {([["7d", "최근 7일"], ["30d", "최근 30일"], ["90d", "최근 90일"], ["custom", "직접 지정"]] as [RangeKey, string][]).map(([k, label]) => (
          <button key={k} className={range === k ? "on" : ""} onClick={() => onChange(k, from, to)}>{label}</button>
        ))}
      </div>
      {range === "custom" && (
        <div className="lg-dates">
          <input className="input" type="date" value={from} onChange={(e) => onChange(range, e.target.value, to)} />
          <span className="muted">~</span>
          <input className="input" type="date" value={to} onChange={(e) => onChange(range, from, e.target.value)} />
        </div>
      )}
    </div>
  );
}

export const fmtN = (n: number | null | undefined, suffix = "") => (n === null || n === undefined ? "-" : `${n.toLocaleString()}${suffix}`);
export const fmtPct = (n: number | null | undefined) => (n === null || n === undefined ? "-" : `${n.toFixed(1)}%`);
export const fmtSecOf = (ms: number | null | undefined) => (ms === null || ms === undefined ? "-" : `${(ms / 1000).toFixed(1)}초`);
export const mmdd = (d: string) => d.slice(5).replace("-", "/");

/** 단일 시리즈 세로 막대 차트 (일별 추이). 값 라벨은 hover 툴팁 + 최댓값만 직접 표기. */
export function BarChart({ data, color = "var(--primary)", height = 220, valueLabel = "건", accent }: {
  data: { label: string; value: number; extra?: string }[];
  color?: string; height?: number; valueLabel?: string;
  accent?: (i: number) => string | undefined;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const W = 600, H = height, padL = 36, padR = 8, padT = 16, padB = 26;
  const max = Math.max(1, ...data.map((d) => d.value));
  const niceMax = useMemo(() => {
    const p = Math.pow(10, Math.floor(Math.log10(max)));
    const m = max / p;
    const step = m <= 1 ? 1 : m <= 2 ? 2 : m <= 5 ? 5 : 10;
    return step * p;
  }, [max]);
  const n = data.length;
  const innerW = W - padL - padR, innerH = H - padT - padB;
  const bw = Math.max(2, Math.min(28, (innerW / Math.max(n, 1)) * 0.62));
  const x = (i: number) => padL + (innerW / Math.max(n, 1)) * (i + 0.5);
  const y = (v: number) => padT + innerH - (v / niceMax) * innerH;
  const ticks = niceMax <= 5
    ? Array.from({ length: niceMax + 1 }, (_, i) => i)
    : Array.from(new Set([0, 0.25, 0.5, 0.75, 1].map((t) => Math.round(t * niceMax))));
  const labelEvery = n > 14 ? Math.ceil(n / 10) : 1;
  const maxIdx = data.findIndex((d) => d.value === max);
  return (
    <div className="chart-wrap">
      <svg viewBox={`0 0 ${W} ${H}`} className="chart" role="img" aria-label="일별 추이 막대 차트">
        {ticks.map((t) => (
          <g key={t}>
            <line x1={padL} x2={W - padR} y1={y(t)} y2={y(t)} stroke="#e9ecf2" strokeDasharray={t === 0 ? undefined : "3 3"} />
            <text x={padL - 6} y={y(t) + 4} textAnchor="end" fontSize="10" fill="#8a94a6">{t >= 1000 ? `${(t / 1000).toFixed(t % 1000 ? 1 : 0)}K` : t}</text>
          </g>
        ))}
        {data.map((d, i) => {
          const h = Math.max(0, y(0) - y(d.value));
          const fill = accent?.(i) ?? color;
          return (
            <g key={d.label} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
              <rect x={x(i) - (innerW / n) / 2} y={padT} width={innerW / n} height={innerH} fill="transparent" />
              <rect x={x(i) - bw / 2} y={y(d.value)} width={bw} height={h} rx={h > 4 ? 4 : 0} fill={fill} opacity={hover === null || hover === i ? 1 : 0.45} />
              {i % labelEvery === 0 && <text x={x(i)} y={H - 8} textAnchor="middle" fontSize="10.5" fill="#6b7487">{d.label}</text>}
              {(i === maxIdx && d.value > 0 && hover === null) && <text x={x(i)} y={y(d.value) - 5} textAnchor="middle" fontSize="11" fontWeight="600" fill="#2b3445">{d.value.toLocaleString()}</text>}
            </g>
          );
        })}
        {hover !== null && data[hover] && (() => {
          const d = data[hover];
          const tx = Math.min(W - 150, Math.max(padL, x(hover) - 70));
          const ty = Math.max(0, y(d.value) - 50);
          return (
            <g pointerEvents="none">
              <rect x={tx} y={ty} width={140} height={d.extra ? 40 : 26} rx={6} fill="#1b2b4b" />
              <text x={tx + 8} y={ty + 17} fontSize="11" fill="#fff" fontWeight="600">{d.label} · {d.value.toLocaleString()}{valueLabel}</text>
              {d.extra && <text x={tx + 8} y={ty + 32} fontSize="10.5" fill="#c9d2e8">{d.extra}</text>}
            </g>
          );
        })()}
      </svg>
    </div>
  );
}

/** 가로 막대 순위 차트 (카테고리 TOP N). 직접 라벨: 이름 + 값(+비율). */
export function HBarList({ items, color = "var(--primary)", valueSuffix = "건" }: {
  items: { label: string; value: number; share?: number | null }[]; color?: string; valueSuffix?: string;
}) {
  const max = Math.max(1, ...items.map((i) => i.value));
  if (items.length === 0) return <div className="empty-state" style={{ padding: "28px 0" }}>데이터가 없습니다.</div>;
  return (
    <div className="hbars">
      {items.map((it) => (
        <div className="hbar" key={it.label}>
          <div className="hbar-l" title={it.label}>{it.label}</div>
          <div className="hbar-track"><div className="hbar-fill" style={{ width: `${(it.value / max) * 100}%`, background: color }} /></div>
          <div className="hbar-v">{it.value.toLocaleString()}{valueSuffix}{it.share !== undefined && it.share !== null ? <span className="muted"> ({it.share.toFixed(1)}%)</span> : null}</div>
        </div>
      ))}
    </div>
  );
}

/** 구성비 스택 막대 + 범례(항상 표시, 수치 직접 표기). */
export function StackBar({ parts }: { parts: { label: string; value: number; color: string }[] }) {
  const total = parts.reduce((a, p) => a + p.value, 0);
  return (
    <div className="stack">
      <div className="stack-bar">
        {total === 0 ? <div className="stack-seg" style={{ width: "100%", background: "#e6e9f0" }} /> :
          parts.filter((p) => p.value > 0).map((p) => (
            <div key={p.label} className="stack-seg" style={{ width: `${(p.value / total) * 100}%`, background: p.color }} title={`${p.label} ${p.value}`} />
          ))}
      </div>
      <div className="stack-legend">
        {parts.map((p) => (
          <div key={p.label} className="lg-item">
            <i style={{ background: p.color }} />
            <span>{p.label}</span>
            <b>{p.value.toLocaleString()}건</b>
            <span className="muted">({total ? ((p.value / total) * 100).toFixed(1) : "0.0"}%)</span>
          </div>
        ))}
      </div>
    </div>
  );
}

/** 증감 표시: good = 증가가 좋은 지표인지 */
export function Delta({ value, unit = "%p", goodWhenUp = true, baseline = "지난 기간" }: { value: number | null | undefined; unit?: string; goodWhenUp?: boolean; baseline?: string }) {
  if (value === null || value === undefined) return <div className="trend muted">{baseline} 데이터 없음</div>;
  const up = value > 0, flat = value === 0;
  const good = flat ? null : up === goodWhenUp;
  return (
    <div className="trend">
      <b className={flat ? "flat" : good ? "good" : "bad"}>{flat ? "—" : up ? "▲" : "▼"} {Math.abs(value).toLocaleString()}{unit}</b> vs {baseline}
    </div>
  );
}

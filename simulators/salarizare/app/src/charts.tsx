/**
 * Hand-rolled SVG marks. No chart library: the page must stay self-contained and the
 * forms here are simple enough that a library would add weight without adding clarity.
 *
 * Conventions from the project's viz method: thin marks, 4px rounded data-ends anchored
 * to the baseline, a 2px surface gap between adjacent fills, recessive grid and axes,
 * selective direct labels rather than a number on every mark, and a hover layer on every
 * plot. Colour is sequential or emphasis throughout — only two hues appear anywhere, and
 * identity is never carried by colour alone.
 */
import { useState } from 'react';

export interface Bar {
  label: string;
  value: number;
  /** Draw in the accent hue: this is emphasis, not a second category. */
  emphasis?: boolean;
  tooltip?: React.ReactNode;
}

function useTooltip() {
  const [tip, setTip] = useState<{ x: number; y: number; body: React.ReactNode } | null>(null);
  const handlers = (body: React.ReactNode) => ({
    onMouseEnter: (e: React.MouseEvent) => setTip({ x: e.clientX, y: e.clientY, body }),
    onMouseMove: (e: React.MouseEvent) => setTip({ x: e.clientX, y: e.clientY, body }),
    onMouseLeave: () => setTip(null),
  });
  const node = tip ? (
    <div
      className="hovertip"
      style={{
        left: Math.min(tip.x + 14, window.innerWidth - 300),
        top: Math.max(tip.y - 12, 8),
      }}
    >
      {tip.body}
    </div>
  ) : null;
  return { handlers, node };
}

/** Rounded only at the data end, anchored flat on the baseline. */
function barPath(x: number, y: number, w: number, h: number, r = 4): string {
  const radius = Math.min(r, w / 2, Math.max(h, 0));
  if (h <= 0.5) return `M${x} ${y + h} h${w}`;
  return [
    `M${x} ${y + h}`,
    `V${y + radius}`,
    `Q${x} ${y} ${x + radius} ${y}`,
    `H${x + w - radius}`,
    `Q${x + w} ${y} ${x + w} ${y + radius}`,
    `V${y + h}`,
    'Z',
  ].join(' ');
}

export function ColumnChart({
  bars,
  height = 240,
  yLabel,
  labelEvery = 1,
  directLabel = () => false,
}: {
  bars: Bar[];
  height?: number;
  yLabel?: string;
  labelEvery?: number;
  directLabel?: (bar: Bar, index: number) => boolean;
}) {
  const { handlers, node } = useTooltip();
  const padL = 46;
  const padR = 12;
  const padT = 18;
  const padB = 34;
  const slot = 34;
  const width = padL + padR + bars.length * slot;
  const plotH = height - padT - padB;
  const max = Math.max(...bars.map((b) => b.value), 1);
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((t) => Math.round(t * max));
  const uniqueTicks = [...new Set(ticks)];

  return (
    <div className="chart-scroll">
      <svg width={width} height={height} role="img" aria-label={yLabel ?? 'column chart'}>
        {uniqueTicks.map((t) => {
          const y = padT + plotH - (t / max) * plotH;
          return (
            <g key={t}>
              <line x1={padL} x2={width - padR} y1={y} y2={y} stroke="var(--grid)" strokeWidth={1} />
              <text className="tick" x={padL - 8} y={y + 4} textAnchor="end">
                {t.toLocaleString('ro-RO')}
              </text>
            </g>
          );
        })}
        {bars.map((bar, i) => {
          // 2px of surface between adjacent fills, so bars never touch.
          const w = slot - 8;
          const x = padL + i * slot + 4;
          const h = (bar.value / max) * plotH;
          const y = padT + plotH - h;
          const fill = bar.emphasis ? 'var(--accent)' : 'var(--series-1)';
          return (
            <g key={bar.label} {...handlers(bar.tooltip ?? `${bar.label}: ${bar.value}`)}>
              {/* Hit target larger than the mark. */}
              <rect x={padL + i * slot} y={padT} width={slot} height={plotH} fill="transparent" />
              <path d={barPath(x, y, w, h)} fill={fill} />
              {directLabel(bar, i) && h > 14 && (
                <text className="mark-label" x={x + w / 2} y={y - 5} textAnchor="middle">
                  {bar.value.toLocaleString('ro-RO')}
                </text>
              )}
              {i % labelEvery === 0 && (
                <text className="tick" x={x + w / 2} y={height - padB + 15} textAnchor="middle">
                  {bar.label}
                </text>
              )}
            </g>
          );
        })}
        <line
          x1={padL}
          x2={width - padR}
          y1={padT + plotH}
          y2={padT + plotH}
          stroke="var(--border)"
          strokeWidth={1}
        />
        {yLabel && (
          <text className="axis-label" x={2} y={padT - 6} textAnchor="start">
            {yLabel}
          </text>
        )}
      </svg>
      {node}
    </div>
  );
}

export interface SpanPointView {
  period: string;
  min: number;
  max: number;
  ratio: number;
}

/**
 * The span in force per year, against the ratio the statute declares.
 *
 * One series plus a reference line — emphasis, not categorical — so no legend box is
 * needed; the title names the series and the reference line is labelled in place.
 */
export function SpanChart({
  points,
  declared,
  height = 250,
}: {
  points: SpanPointView[];
  declared: number | null;
  height?: number;
}) {
  const { handlers, node } = useTooltip();
  const padL = 46;
  const padR = 74;
  const padT = 20;
  const padB = 36;
  const width = Math.max(360, padL + padR + points.length * 96);
  const plotH = height - padT - padB;
  // The whole series sits between 7,4 and 8,0. Against a zero baseline the escalator
  // is a flat line pinned under the reference — the reader learns nothing. A line
  // chart may start away from zero provided the axis says so, and it does: every
  // gridline is labelled and the caption states the window.
  const values = [...points.map((p) => p.ratio), ...(declared !== null ? [declared] : [])];
  const lo = Math.floor(Math.min(...values) * 5 - 1) / 5;
  const top = Math.max(...values) + 0.12;
  const y = (v: number) => padT + plotH - ((v - lo) / (top - lo)) * plotH;
  const gridlines = [];
  for (let t = Math.ceil(lo * 5) / 5; t <= top; t += 0.2) gridlines.push(Number(t.toFixed(1)));
  const x = (i: number) => padL + 42 + i * ((width - padL - padR - 42) / Math.max(points.length - 1, 1));

  const fmt = (v: number, d = 2) => v.toLocaleString('ro-RO', { minimumFractionDigits: d, maximumFractionDigits: d });

  const line = points.map((p, i) => `${i === 0 ? 'M' : 'L'}${x(i)} ${y(p.ratio)}`).join(' ');

  return (
    <div className="chart-scroll">
      <svg width={width} height={height} role="img" aria-label="raportul dintre cel mai mare si cel mai mic coeficient, pe ani">
        {gridlines.map((t) => (
          <g key={t}>
            <line x1={padL} x2={width - padR} y1={y(t)} y2={y(t)} stroke="var(--grid)" strokeWidth={1} />
            <text className="tick" x={padL - 8} y={y(t) + 4} textAnchor="end">
              1:{fmt(t, 1)}
            </text>
          </g>
        ))}

        {declared !== null && (
          <g>
            <line
              x1={padL}
              x2={width - padR}
              y1={y(declared)}
              y2={y(declared)}
              stroke="var(--accent)"
              strokeWidth={2}
              strokeDasharray="5 4"
            />
            <text className="mark-label" x={padL + 6} y={y(declared) - 7} fill="var(--accent)">
              pragul din Art. 5 — 1:{declared}
            </text>
          </g>
        )}

        <path d={line} fill="none" stroke="var(--series-1)" strokeWidth={2} strokeLinejoin="round" />

        {points.map((p, i) => (
          <g key={p.period} {...handlers(
            <>
              <strong>{p.period}</strong>
              <div className="muted">
                cel mai mic {fmt(p.min)} · cel mai mare {fmt(p.max, 4)}
              </div>
              <div>raport 1:{fmt(p.ratio)}</div>
            </>,
          )}>
            <rect x={x(i) - 26} y={padT} width={52} height={plotH} fill="transparent" />
            {/* 2px surface ring so the marker reads over the line. */}
            <circle cx={x(i)} cy={y(p.ratio)} r={5.5} fill="var(--series-1)" stroke="var(--surface-1)" strokeWidth={2} />
            <text className="tick" x={x(i)} y={height - padB + 16} textAnchor="middle">
              {p.period}
            </text>
            {(i === 0 || i === points.length - 1) && (
              <text className="mark-label" x={x(i)} y={y(p.ratio) - 12} textAnchor="middle">
                1:{fmt(p.ratio)}
              </text>
            )}
          </g>
        ))}
        <line x1={padL} x2={width - padR} y1={padT + plotH} y2={padT + plotH} stroke="var(--border)" strokeWidth={1} />
      </svg>
      {node}
    </div>
  );
}

export interface GradeBarView {
  gradeId: string;
  label: string;
  min: number;
  max: number;
  variants: number;
}

export interface GapView {
  belowGradeId: string;
  from: number;
  to: number;
  variants: number;
}

/**
 * Occupancy per salary grade, with the coefficients that fall between the bands drawn
 * in the space between the bars — where they actually sit. Putting them in their own
 * chart would lose the point: they are not a category, they are a gap.
 */
export function GradeChart({ grades, gaps, height = 260 }: { grades: GradeBarView[]; gaps: GapView[]; height?: number }) {
  const { handlers, node } = useTooltip();
  const padL = 46;
  const padR = 14;
  const padT = 20;
  // The gaps hold 1-18 variants against grades holding up to 365. On one scale they
  // vanish, and "invisible" is the wrong reading of a defect. They get their own strip
  // under the axis, on its own scale, with the count printed — separated and labelled
  // rather than silently rescaled inside the same plot.
  const gapStrip = 46;
  const padB = 40 + gapStrip;
  const slot = 56;
  const width = padL + padR + grades.length * slot;
  const plotH = height - padT - padB;
  const max = Math.max(...grades.map((g) => g.variants), 1);
  const gapByBelow = new Map(gaps.map((g) => [g.belowGradeId, g]));
  const gapMax = Math.max(...gaps.map((g) => g.variants), 1);

  return (
    <div className="chart-scroll">
      <svg width={width} height={height} role="img" aria-label="numarul de variante pe grad salarial si intre grade">
        {[0, 0.5, 1].map((t) => {
          const v = Math.round(t * max);
          const yy = padT + plotH - t * plotH;
          return (
            <g key={t}>
              <line x1={padL} x2={width - padR} y1={yy} y2={yy} stroke="var(--grid)" strokeWidth={1} />
              <text className="tick" x={padL - 8} y={yy + 4} textAnchor="end">{v}</text>
            </g>
          );
        })}

        {grades.map((g, i) => {
          const w = slot - 16;
          const x = padL + i * slot + 8;
          const h = (g.variants / max) * plotH;
          const y = padT + plotH - h;
          const gap = gapByBelow.get(g.gradeId);
          return (
            <g key={g.gradeId}>
              <g {...handlers(
                <>
                  <strong>{g.label}</strong>
                  <div className="muted">coeficienți {g.min}–{g.max}</div>
                  <div>{g.variants} variante</div>
                </>,
              )}>
                <rect x={padL + i * slot} y={padT} width={slot - 8} height={plotH} fill="transparent" />
                <path d={barPath(x, y, w, h)} fill="var(--series-1)" />
              </g>

              <text className="tick" x={x + w / 2} y={padT + plotH + 15} textAnchor="middle">
                {g.gradeId.replace('g', '')}
              </text>

              {gap && gap.variants > 0 && (
                <g {...handlers(
                  <>
                    <strong>Între gradul {g.gradeId.replace('g', '')} și următorul</strong>
                    <div className="muted">
                      peste {gap.from} și sub {gap.to} — niciun grad salarial
                    </div>
                    <div>{gap.variants} variante</div>
                  </>,
                )}>
                  <rect x={x + w - 6} y={padT + plotH + 22} width={24} height={gapStrip - 12} fill="transparent" />
                  <path
                    d={barPath(
                      x + w - 1,
                      padT + plotH + 34 - (gap.variants / gapMax) * 18,
                      12,
                      (gap.variants / gapMax) * 18,
                      3,
                    )}
                    fill="var(--accent)"
                  />
                  <text
                    className="mark-label"
                    x={x + w + 5}
                    y={padT + plotH + 46}
                    textAnchor="middle"
                    fill="var(--accent)"
                  >
                    {gap.variants}
                  </text>
                </g>
              )}
            </g>
          );
        })}
        <line x1={padL} x2={width - padR} y1={padT + plotH} y2={padT + plotH} stroke="var(--border)" strokeWidth={1} />
        <text className="axis-label" x={2} y={padT + plotH + 34}>
          între grade
        </text>
      </svg>
      {node}
    </div>
  );
}

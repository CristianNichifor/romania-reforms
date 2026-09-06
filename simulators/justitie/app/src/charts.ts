/**
 * The chart primitives, and the tooltip that explains them.
 *
 * Still no chart library and still no SVG: a horizontal bar is a div with a width, and a
 * dependency that draws rectangles would cost more bytes than the page it is drawn on. What
 * changed is that the rectangles now sit against a scale.
 *
 * Three things were wrong with drawing them bare, and each is fixed here rather than footnoted:
 *
 *   * **No axis.** A bar 40% as long as the longest bar told a reader that one row is smaller
 *     than another and nothing else. Every chart now carries nice ticks and gridlines through
 *     the track, so a length can be read as a quantity.
 *   * **Truncated labels.** Court names and charge descriptions are longer than any label
 *     column, and the ellipsis was the end of the story — `title` on the span gave the browser's
 *     tooltip after a second of stillness, which is not a way to read a chart. Hovering or
 *     focusing a row now shows the whole label with the exact figure beside it.
 *   * **Nothing to hover.** Shares, counts and the denominator they are shares of were spread
 *     across three places. The tooltip states all three together, because "25,8%" without
 *     "of 10.696.521 termene" is the kind of number that gets quoted wrongly.
 *
 * The tooltip is one element for the whole document, driven by a `data-tip` attribute and a
 * delegated listener. Rows carrying a tip are focusable, so it is reachable from the keyboard —
 * the alternative is a chart whose detail exists only for a mouse.
 */

const ro = new Intl.NumberFormat('ro-RO');

/** HTML-escape. Every string below arrives from a data file, and a court named `S.C. "X" & Co`
 *  must not be able to close an attribute. */
export function esc(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

export const count = (value: number): string => ro.format(value);

export const share = (value: number): string => `${(value * 100).toFixed(1).replace('.', ',')}%`;

/**
 * A rounded axis top and its ticks.
 *
 * Ticks land on 1, 2 or 5 times a power of ten, which is what makes them readable without a
 * label on every gridline. The thresholds are Heckbert's — 1,5, 3 and 7 rather than 1, 2 and 5 —
 * so a rough step of 1,16 rounds down to 1 instead of up to 2, which is the difference between
 * five intervals and three. The top is rounded *up* past the largest bar: rounding to the
 * nearest would let a bar overflow its own track, and clipping the longest bar in a chart is
 * exactly the wrong bar to get wrong.
 */
export function niceScale(max: number, targetTicks = 4): { max: number; ticks: number[] } {
  if (!Number.isFinite(max) || max <= 0) return { max: 1, ticks: [0, 1] };
  const rough = max / targetTicks;
  const magnitude = 10 ** Math.floor(Math.log10(rough));
  const normalised = rough / magnitude;
  const step = (normalised < 1.5 ? 1 : normalised < 3 ? 2 : normalised < 7 ? 5 : 10) * magnitude;
  const top = Math.ceil(max / step) * step;
  // Binary floating point has no exact 0,2, so both accumulating and multiplying land on
  // 0,6000000000000001 for the third tick of a share scale. Rounded back to the step's own
  // precision, because a gridline labelled with sixteen digits is a bug a reader can see.
  const decimals = Math.max(0, -Math.floor(Math.log10(step))) + 2;
  const ticks: number[] = [];
  for (let index = 0; index * step <= top + step / 1e6; index += 1) {
    ticks.push(Number((index * step).toFixed(decimals)));
  }
  return { max: Number(top.toFixed(decimals)), ticks };
}

export interface Row {
  label: string;
  value: number;
  /** The small grey line under the bar. Shown in the chart and repeated in the tooltip. */
  note?: string;
  /** Extra `term: value` lines for the tooltip only, where the chart has no room for them. */
  detail?: [string, string][];
  /** Drawn faded, for rows the data does not vouch for. */
  muted?: boolean;
}

export interface BarOptions {
  /** How a bar's own value is written. Defaults to a grouped integer. */
  format?: (value: number) => string;
  /** How an axis tick is written. Defaults to `format`, then to a grouped integer. */
  tickFormat?: (value: number) => string;
  /** What the values are, for the tooltip: "dosare", "termene", "identități". */
  unit?: string;
  /** Suppress the axis where the values are not a quantity anyone reads off a scale. */
  axis?: boolean;
  /** Roughly how many intervals to aim for. Two side-by-side charts get a track half as wide
   *  and five tick labels collide into a grey smear, so they ask for fewer. */
  targetTicks?: number;
}

function tipAttribute(title: string, lines: [string, string][]): string {
  const body = lines
    .filter(([, value]) => value !== '')
    .map(([term, value]) => `<dt>${esc(term)}</dt><dd>${esc(value)}</dd>`)
    .join('');
  return esc(`<strong>${esc(title)}</strong><dl>${body}</dl>`);
}

/** A row that can be hovered or focused carries the tip and the label a screen reader gets. */
function interactive(title: string, lines: [string, string][]): string {
  const flat = lines
    .filter(([, value]) => value !== '')
    .map(([term, value]) => `${term}: ${value}`)
    .join(', ');
  return `tabindex="0" data-tip="${tipAttribute(title, lines)}" aria-label="${esc(`${title}. ${flat}`)}"`;
}

function axisRow(ticks: number[], top: number, format: (value: number) => string): string {
  const marks = ticks
    .map((tick) => `<span style="left:${(tick / top) * 100}%">${esc(format(tick))}</span>`)
    .join('');
  return `<div class="chart-axis" aria-hidden="true">
    <span></span><span class="axis-track">${marks}</span><span></span>
  </div>`;
}

/** Gridlines drawn inside the track itself, so they line up with the bar by construction
 *  rather than by two elements agreeing about a margin. */
function gridStyle(ticks: number[], top: number): string {
  const stops = ticks
    .slice(1, -1)
    .map((tick) => `${((tick / top) * 100).toFixed(4)}%`)
    .map((at) => `transparent calc(${at} - 1px), var(--grid) ${at}, transparent calc(${at} + 1px)`)
    .join(',');
  return stops ? `background-image:linear-gradient(90deg,${stops});` : '';
}

export function bars(into: HTMLElement, rows: Row[], options: BarOptions = {}): void {
  const format = options.format ?? count;
  const tickFormat = options.tickFormat ?? format;
  const withAxis = options.axis !== false;
  if (!rows.length) {
    into.innerHTML = '<p class="empty">Nu există observații pentru această selecție.</p>';
    return;
  }
  const { max: top, ticks } = niceScale(
    Math.max(...rows.map((row) => row.value), 0),
    options.targetTicks,
  );
  const grid = withAxis ? gridStyle(ticks, top) : '';

  const body = rows
    .map((row) => {
      const lines: [string, string][] = [
        [options.unit ?? 'valoare', format(row.value)],
        ...(row.note ? ([['', row.note]] as [string, string][]) : []),
        ...(row.detail ?? []),
      ];
      return `
      <div class="bar${row.muted ? ' muted' : ''}" ${interactive(row.label, lines)}>
        <span class="bar-label">${esc(row.label)}</span>
        <span class="bar-track" style="${grid}">
          <span class="bar-fill" style="width:${((row.value / top) * 100).toFixed(3)}%"></span>
        </span>
        <span class="bar-value num">${esc(format(row.value))}</span>
        ${row.note ? `<span class="bar-note">${esc(row.note)}</span>` : ''}
      </div>`;
    })
    .join('');

  into.innerHTML = `<div class="chart">${body}${withAxis ? axisRow(ticks, top, tickFormat) : ''}</div>`;
}

export interface QuartileRow {
  label: string;
  n: number;
  p25?: number | undefined;
  p50?: number | undefined;
  p75?: number | undefined;
}

/**
 * A quartile strip per row: the box is the middle half, the line is the median.
 *
 * Drawn on a shared scale with an axis, because the point of these is that the middle half of
 * one court's intervals sits somewhere else than another's, and two boxes scaled to their own
 * rows would hide exactly that.
 */
export function quartiles(
  into: HTMLElement,
  rows: QuartileRow[],
  options: { format: (value: number) => string; unit: string; targetTicks?: number },
): void {
  const observed = rows.filter((row) => row.p50 !== undefined);
  if (!observed.length) {
    into.innerHTML = '<p class="empty">Prea puține observații pentru această selecție.</p>';
    return;
  }
  const { max: top, ticks } = niceScale(
    Math.max(...observed.map((row) => row.p75 ?? 0), 1),
    options.targetTicks,
  );
  const grid = gridStyle(ticks, top);

  const body = rows
    .map((row) => {
      if (row.p50 === undefined) {
        return `<div class="quart"><span class="bar-label">${esc(row.label)}</span>
          <span class="empty">prea puține observații</span><span></span></div>`;
      }
      const p25 = row.p25 ?? row.p50;
      const p75 = row.p75 ?? row.p50;
      const left = (p25 / top) * 100;
      const width = Math.max(((p75 - p25) / top) * 100, 0.5);
      const lines: [string, string][] = [
        ['un sfert sub', options.format(p25)],
        ['mediana', options.format(row.p50)],
        ['un sfert peste', options.format(p75)],
        [options.unit, count(row.n)],
      ];
      return `
        <div class="quart" ${interactive(row.label, lines)}>
          <span class="bar-label">${esc(row.label)}</span>
          <span class="quart-track" style="${grid}">
            <span class="quart-box" style="left:${left.toFixed(3)}%;width:${width.toFixed(3)}%"></span>
            <span class="quart-mid" style="left:${((row.p50 / top) * 100).toFixed(3)}%"></span>
          </span>
          <span class="bar-value num">${esc(options.format(row.p50))}</span>
          <span class="bar-note">${esc(count(row.n))} obs.</span>
        </div>`;
    })
    .join('');

  into.innerHTML = `<div class="chart">${body}${axisRow(ticks, top, options.format)}</div>`;
}

/** The tooltip. One per document, created on first use. */
let bubble: HTMLElement | null = null;

function ensureBubble(): HTMLElement {
  if (bubble) return bubble;
  bubble = document.createElement('div');
  bubble.className = 'tip';
  bubble.setAttribute('role', 'tooltip');
  bubble.hidden = true;
  document.body.append(bubble);
  return bubble;
}

function place(node: HTMLElement, x: number, y: number): void {
  const tip = ensureBubble();
  const box = tip.getBoundingClientRect();
  const margin = 12;
  // Flip rather than clamp when there is no room to the right: a tooltip pinned to the viewport
  // edge covers the row it is describing, which is the one thing it must never do.
  const left = x + margin + box.width > window.innerWidth ? x - margin - box.width : x + margin;
  let topEdge = y + margin;
  if (topEdge + box.height > window.innerHeight) topEdge = y - margin - box.height;
  tip.style.left = `${Math.max(4, left)}px`;
  tip.style.top = `${Math.max(4, topEdge)}px`;
  node.setAttribute('data-tipped', '');
}

function show(node: HTMLElement, x: number, y: number): void {
  const tip = ensureBubble();
  const html = node.getAttribute('data-tip');
  if (!html) return;
  tip.innerHTML = html;
  tip.hidden = false;
  place(node, x, y);
}

function hide(): void {
  if (!bubble) return;
  bubble.hidden = true;
  document.querySelectorAll('[data-tipped]').forEach((node) => node.removeAttribute('data-tipped'));
}

/**
 * Wire the tooltip once, for the whole page.
 *
 * Delegated rather than per-row, because the charts are re-rendered whenever the filter moves
 * and a listener attached to a row would be attached to a row that no longer exists. The cost
 * of getting this wrong is not a leak, it is a tooltip that stops working after the first
 * filter change — which reads as a broken page rather than as a bug.
 */
export function wireTooltips(): void {
  const target = (event: Event): HTMLElement | null => {
    const node = event.target;
    return node instanceof Element ? node.closest<HTMLElement>('[data-tip]') : null;
  };

  document.addEventListener('pointerover', (event) => {
    const node = target(event);
    if (node) show(node, event.clientX, event.clientY);
  });
  document.addEventListener('pointermove', (event) => {
    const node = target(event);
    if (node && bubble && !bubble.hidden) place(node, event.clientX, event.clientY);
  });
  // Moving from a row's label to its own bar fires `pointerout` on the label. Hiding on that
  // would make the tooltip flicker across every internal boundary, so the row only loses the
  // tooltip when the pointer has actually left it.
  document.addEventListener('pointerout', (event) => {
    const node = target(event);
    if (!node) return;
    const to = event.relatedTarget;
    if (to instanceof Node && node.contains(to)) return;
    hide();
  });
  // Focus has no coordinates, so the tooltip is placed against the row's own box instead.
  document.addEventListener('focusin', (event) => {
    const node = target(event);
    if (!node) return hide();
    const box = node.getBoundingClientRect();
    show(node, box.left + Math.min(box.width, 240), box.bottom);
  });
  document.addEventListener('focusout', hide);
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') hide();
  });
  window.addEventListener('scroll', hide, { passive: true });
}

/**
 * Application wiring.
 *
 * Slider input is debounced to animation frames rather than timers, so the recompute rate
 * follows the display instead of an arbitrary interval, and a stale result from an earlier
 * drag position is discarded rather than painted.
 */

import './style.css';
import './native-ui.css';

import { buildChain, edgeKey, indexShard } from './app/chain';
import {
  healthAccessPayloadAligned,
  healthAccessPeriodLabel,
  healthAccessTotals,
  type HealthAccessPayload,
} from './app/health-access';
import { budgetUrlFor } from './app/links';
import {
  localFinancePayloadAligned,
  localFinancePeriodLabel,
  localFinanceTotals,
  type LocalFinancePayload,
} from './app/local-finance';
import { createPanel } from './app/panels';
import {
  publicEnterpriseFootprintPayloadAligned,
  publicEnterpriseFootprintPeriodLabel,
  publicEnterpriseFootprintTotals,
  type PublicEnterpriseFootprintPayload,
} from './app/public-enterprise-footprint';
import { REFERENCE, sameMap } from './app/reference';
import { decode as decodeScenario, encode as encodeScenario, writeHash, type Scenario } from './app/scenario';
import {
  STORAGE_KEY,
  exportFilename,
  mergeImported,
  parseImport,
  parseVersions,
  removeVersion,
  serialiseVersions,
  toExportFile,
  upsertVersion,
  type SavedVersion,
} from './app/versions';
import {
  STRINGS,
  detectLang,
  formatMoney,
  formatNumber,
  formatPercent,
  formatPercentagePoints,
  type Lang,
  type Strings,
} from './i18n';
import {
  createMap,
  CAPITAL_COLOUR,
  COST_RAMP,
  COUNTY_LINE_COLOUR,
  REGION_LINE_COLOUR,
  ORPHAN_SEAT_COLOUR,
  ROAD_COLOUR,
  SEAT_COLOUR,
  SEAT_KIND,
  UNCHANGED_SEAT_COLOUR,
  UNCHANGED_COLOUR,
  type ChainFeature,
  type Overlay,
} from './map/map';
import { PALETTE } from './model/colour';
import { regionOfCounty } from './model/regions';
import { allocateSeats, representationShift, type VoteList } from './model/allocation';
import {
  BUCHAREST_COUNCIL,
  councillorsFor,
  danishBandFor,
  representationAfter,
  representationBefore,
} from './model/representation';
import { CANDIDACY, DEFAULT_PARAMS, REASON, type Params, type ViewMode } from './model/types';
import type { Outgoing, ReadyMessage, ResultMessage } from './model/worker';

const DATA_BASE = `${import.meta.env.BASE_URL}data/`;

const RADIUS_GRID = [5000, 7500, 10000, 12500, 15000, 17500, 20000, 22500, 25000, 27500, 30000];

interface SliderSpec {
  key: keyof Params;
  labelKey: keyof Strings;
  helpKey: keyof Strings;
  min: number;
  max: number;
  step: number;
  format: (value: number, lang: Lang, s: Strings) => string;
}

const KM = (v: number): string => `${(v / 1000).toFixed(1).replace(/\.0$/, '')} km`;

const SLIDERS: SliderSpec[] = [
  {
    key: 'x', labelKey: 'x', helpKey: 'xHelp',
    min: 5000, max: 50000, step: 500,
    format: (v, l) => formatNumber(v, l),
  },
  {
    key: 'rNationalM', labelKey: 'rNational', helpKey: 'rNationalHelp',
    min: 0, max: RADIUS_GRID.length - 1, step: 1,
    format: (v) => KM(v),
  },
  {
    key: 'rCapM', labelKey: 'rCap', helpKey: 'rCapHelp',
    min: 0, max: RADIUS_GRID.length - 1, step: 1,
    format: (v) => KM(v),
  },
  {
    key: 'rTownM', labelKey: 'rTown', helpKey: 'rTownHelp',
    min: 0, max: RADIUS_GRID.length - 1, step: 1,
    format: (v) => KM(v),
  },
  {
    key: 'nMin', labelKey: 'nMin', helpKey: 'nMinHelp',
    min: 1, max: 10, step: 1,
    format: (v) => String(v),
  },
  {
    key: 'rSepM', labelKey: 'rSep', helpKey: 'rSepHelp',
    min: 0, max: 30000, step: 1000,
    format: (v) => KM(v),
  },
  {
    key: 'minOverlap', labelKey: 'minOverlap', helpKey: 'minOverlapHelp',
    min: 0, max: 0.5, step: 0.01,
    format: (v) => `${Math.round(v * 100)}%`,
  },
  {
    key: 'pOrphan', labelKey: 'pOrphan', helpKey: 'pOrphanHelp',
    min: 0, max: 15000, step: 500,
    format: (v, l, s) => (v === 0 ? s.pOrphanOff : formatNumber(v, l)),
  },
  {
    key: 'maxRoadM', labelKey: 'maxRoad', helpKey: 'maxRoadHelp',
    min: 0, max: 80000, step: 5000,
    format: (v, _l, s) => (v === 0 ? s.pTargetOff : KM(v)),
  },
  {
    key: 'pTarget', labelKey: 'pTarget', helpKey: 'pTargetHelp',
    min: 0, max: 100000, step: 2500,
    format: (v, l, s) => (v === 0 ? s.pTargetOff : formatNumber(v, l)),
  },
  {
    key: 'minCompactness', labelKey: 'minCompactness', helpKey: 'minCompactnessHelp',
    min: 0, max: 0.35, step: 0.05,
    format: (v, _l, s) => (v === 0 ? s.pTargetOff : v.toFixed(2)),
  },
];

const isRadius = (key: keyof Params): boolean =>
  key === 'rCapM' || key === 'rTownM' || key === 'rNationalM';

/**
 * What to call a unit, as opposed to a UAT.
 *
 * The six sectors merge into one city and the lowest-numbered one stands for it, since the
 * UAT set has no "Municipiul Bucuresti" row. Naming the resulting unit "Sectorul 1" would
 * describe the merge as an annexation by one sector, which is not what it is.
 */
/** "Tulcea", not "TL". The payload carries the code; the manifest carries the name. */
function countyName(data: ReadyMessage, index: number): string {
  const code = data.attributes.county[index] ?? '';
  return data.countyNames[code] ?? code;
}

function unitName(data: ReadyMessage, seat: number): string {
  if (data.attributes.county[seat] === 'B') return 'MUNICIPIUL BUCUREȘTI';
  return data.attributes.name[seat]!;
}

function el<T extends HTMLElement>(selector: string): T {
  const node = document.querySelector<T>(selector);
  if (!node) throw new Error(`missing element: ${selector}`);
  return node;
}

async function boot(): Promise<void> {
  const initialLang = detectLang();
  // A bare URL gets the published map, where there is one. A URL carrying a scenario is the
  // reader's own and is never overridden — including a link somebody shared with them.
  const arrivedBare = location.hash.replace(/^#/, '').trim() === '';
  const scenario: Scenario = decodeScenario(
    arrivedBare && REFERENCE.published ? REFERENCE.hash : location.hash,
    initialLang,
  );
  const referenceScenario = REFERENCE.published
    ? decodeScenario(REFERENCE.hash, initialLang)
    : null;
  let strings = STRINGS[scenario.lang];

  let ready: ReadyMessage | null = null;
  let latest: ResultMessage | null = null;
  let isOrphanRegion = new Uint8Array(0);
  let costPerResident = new Float32Array(0);
  let costBreaks: number[] = [];
  let token = 0;
  let pending = false;

  const worker = new Worker(new URL('./model/worker.ts', import.meta.url), { type: 'module' });
  const mapHandle = await createMap(el('#map'), DATA_BASE);

  const controlsPanel = createPanel({
    element: el('#controls'),
    handle: el('#controls-handle'),
    storageKey: 'administrativ:width:controls',
    defaultWidth: 340,
    edge: 'right',
  });
  const detailPanel = createPanel({
    element: el('#detail'),
    handle: el('#detail-handle'),
    storageKey: 'administrativ:width:detail',
    defaultWidth: 360,
    edge: 'left',
  });

  /**
   * How tall the disclaimer is, published to CSS.
   *
   * On a phone the sheets stack up from the bottom of the screen and the disclaimer is
   * already there — and it is the one piece of text on this page that must not be covered,
   * since it is what stops the map being read as an official proposal. Its height is not a
   * constant to hard-code: it wraps to two lines in Romanian and three in English on a
   * narrow screen. Measured, so the sheets sit on top of it rather than under it.
   */
  const disclaimer = el<HTMLElement>('.disclaimer');
  const publishDisclaimerHeight = (): void => {
    document.documentElement.style.setProperty(
      '--disclaimer-h',
      `${Math.round(disclaimer.getBoundingClientRect().height)}px`,
    );
  };
  new ResizeObserver(publishDisclaimerHeight).observe(disclaimer);
  publishDisclaimerHeight();

  /**
   * Whether this is a touchscreen.
   *
   * The hovercard has no dismiss control because a pointer leaving is its dismiss. A finger
   * never leaves, so on a touchscreen the card strands over the map with no way to shift it.
   * Rather than bolt a close button onto it — which would make it a dialog, and there would
   * then be two dialogs saying overlapping things — the card is suppressed here and a tap
   * opens the detail panel instead, which is a real panel with a real close control.
   */
  const coarsePointer = window.matchMedia('(pointer: coarse)');

  // --- rendering ---------------------------------------------------------------------

  const applyStaticText = (): void => {
    strings = STRINGS[scenario.lang];
    document.documentElement.lang = scenario.lang;
    document.title = strings.title;
    for (const node of document.querySelectorAll<HTMLElement>('[data-i18n]')) {
      const key = node.dataset.i18n as keyof Strings;
      node.textContent = strings[key];
    }
    for (const button of document.querySelectorAll<HTMLButtonElement>('.lang button')) {
      button.setAttribute('aria-pressed', String(button.dataset.lang === scenario.lang));
    }
    el('#sources').innerHTML =
      'ANCPI · INS (Recensământ 2021) · Ministerul Finanțelor · OpenStreetMap · ' +
      '<a href="https://www.transparenta.eu" target="_blank" rel="noopener">Transparenta.eu</a> · ' +
      '<a href="https://companiidestat.ro/date/" target="_blank" rel="noopener">companiidestat.ro</a> · ' +
      '<a href="https://geo-spatial.org" target="_blank" rel="noopener">geo-spatial.org</a>';
    controlsPanel.setLabels(strings.panelResize, strings.panelResizeHelp);
    detailPanel.setLabels(strings.panelResize, strings.panelResizeHelp);
    el('#detail-close').setAttribute('aria-label', strings.panelClose);
    el('#detail-close').setAttribute('title', strings.panelClose);
    renderModes();
    renderLegend();
    renderSliders();
    renderLayers();
    renderSummary();
    renderDetail();
    renderHoverOptions();
    renderBadge();
    renderVersions();
    renderForced();
    renderPins();
    renderCandidates();
    renderAudit();
  };

  const overlayState: Record<Overlay, boolean> = {
    counties: true,
    regions: false,
    seats: false,
    capitals: true,
    roads: false,
    countyRoads: false,
  };

  const renderLayers = (): void => {
    const rows: [Overlay, string, string, boolean, string][] = [
      ['counties', strings.layerCounties, COUNTY_LINE_COLOUR, false, ''],
      ['regions', strings.layerRegions, REGION_LINE_COLOUR, false, ''],
      ['capitals', strings.layerCapitals, CAPITAL_COLOUR, true, ''],
      ['seats', strings.layerSeats, SEAT_COLOUR, true, ''],
      ['roads', strings.layerRoads, ROAD_COLOUR, false, strings.layersRoadsNote],
      [
        'countyRoads',
        strings.layerCountyRoads,
        ROAD_COLOUR,
        false,
        strings.layersCountyRoadsNote,
      ],
    ];
    el('#layers').innerHTML = rows
      .map(
        ([key, label, colour, dot, note]) => `
        <label class="layer-row civic-choice">
          <input type="checkbox" data-overlay="${key}" ${overlayState[key] ? 'checked' : ''} />
          <span class="swatch${dot ? ' dot' : ''}" style="background:${colour}"></span>
          <span>${label}${note ? ` <span class="note">— ${note}</span>` : ''}</span>
        </label>`,
      )
      .join('');
    for (const input of document.querySelectorAll<HTMLInputElement>('#layers input')) {
      input.addEventListener('change', () => {
        const key = input.dataset.overlay as Overlay;
        overlayState[key] = input.checked;
        void mapHandle.setOverlay(key, input.checked).then((shown) => {
          // The road payloads are fetched from a release rather than committed, so they can
          // legitimately be absent from a build. Say so and un-tick the box: leaving it ticked
          // over an empty map reads as "there are no roads here" rather than "this build does
          // not have them".
          if (input.checked && !shown) {
            overlayState[key] = false;
            input.checked = false;
            input.disabled = true;
            const note = input.parentElement?.querySelector('.note');
            if (note) note.textContent = `— ${strings.layersRoadsUnavailable}`;
          }
        });
      });
    }
  };

  /**
   * Repaint from the latest result, in whatever mode is selected.
   *
   * "Today" is not a different computation, only a different thing to draw: the 3,186
   * communes as they are, each its own unit and its own seat. Keeping it here rather than in
   * the worker means switching between before and after is instant.
   */
  const paint = (): void => {
    if (!latest || !ready) return;
    const showingToday = scenario.mode === 'current';
    const identity = new Uint16Array(latest.regionOf.length);
    for (let i = 0; i < identity.length; i += 1) identity[i] = i;

    mapHandle.applyAssignment(
      showingToday ? identity : latest.regionOf,
      showingToday ? ready.currentColourOf : latest.colourOf,
      latest.tierOf,
      scenario.mode,
      costPerResident,
      costBreaks,
    );

    const kindOf = new Int8Array(latest.regionOf.length).fill(-1);
    if (!showingToday) {
      for (let i = 0; i < latest.regionOf.length; i += 1) {
        if (latest.regionOf[i] !== i) continue;
        kindOf[i] =
          latest.tierOf[i] !== -1
            ? ready.attributes.isCapital[i]
              ? SEAT_KIND.CAPITAL
              : SEAT_KIND.CENTRE
            : isOrphanRegion[i] === 1
              ? SEAT_KIND.ORPHAN
              : SEAT_KIND.UNCHANGED;
      }
    }
    mapHandle.setCentres(kindOf);
    renderLabels();
  };

  const renderModes = (): void => {
    const modes: [ViewMode, string][] = [
      ['current', strings.viewCurrent],
      ['regions', strings.viewRegions],
      ['cost', strings.viewCost],
    ];
    el('#modes').innerHTML = modes
      .map(
        ([mode, label]) =>
          `<button data-mode="${mode}" aria-pressed="${mode === scenario.mode}">${label}</button>`,
      )
      .join('');
    for (const button of document.querySelectorAll<HTMLButtonElement>('#modes button')) {
      button.addEventListener('click', () => {
        scenario.mode = button.dataset.mode as ViewMode;
        writeHash(scenario);
        renderModes();
        renderLegend();
        renderSummary();
        renderDetail();
        paint();
      });
    }
  };

  const renderLegend = (): void => {
    if (scenario.mode === 'cost') {
      const breaks = costBreaks
        .map((b) => formatNumber(b, scenario.lang))
        .join(' · ');
      el('#legend').innerHTML =
        `<h4>${strings.costPerResident}</h4>` +
        `<div class="ramp">${COST_RAMP.map((c) => `<span style="background:${c}"></span>`).join('')}</div>` +
        `<div class="ramp-labels"><span>${strings.costLegendLow}</span><span>${strings.costLegendHigh}</span></div>` +
        `<div class="ramp-labels" style="margin-top:4px"><span>RON: ${breaks}</span></div>`;
      return;
    }
    const rows: [string, string, boolean?][] = [
      [CAPITAL_COLOUR, strings.legendCapital, true],
      [SEAT_COLOUR, strings.legendAbsorber, true],
      [ORPHAN_SEAT_COLOUR, strings.legendOrphanSeat, true],
      [UNCHANGED_SEAT_COLOUR, strings.legendUnchangedSeat, true],
      [PALETTE[6]!, strings.legendAbsorbed],
      [PALETTE[0]!, strings.legendOrphan],
      [UNCHANGED_COLOUR, strings.legendUnchanged],
    ];
    el('#legend').innerHTML =
      `<h4>${strings.legend}</h4>` +
      rows
        .map(
          ([colour, label, isDot]) =>
            `<div class="row"><span class="swatch${isDot ? ' dot' : ''}" style="background:${colour}"></span>${label}</div>`,
        )
        .join('');
  };

  const renderSliders = (): void => {
    const host = el('#sliders');
    host.innerHTML = SLIDERS.map((spec) => {
      const raw = scenario.params[spec.key];
      const value = isRadius(spec.key) ? RADIUS_GRID.indexOf(raw) : raw;
      return `
        <div class="slider" data-key="${spec.key}">
          <div class="slider-head">
            <label for="s-${spec.key}">${strings[spec.labelKey]}</label>
            <span class="readout" data-readout>${spec.format(raw, scenario.lang, strings)}</span>
          </div>
          <input id="s-${spec.key}" type="range" min="${spec.min}" max="${spec.max}"
                 step="${spec.step}" value="${value}" />
          <p class="help">${strings[spec.helpKey]}</p>
        </div>`;
    }).join('');

    for (const spec of SLIDERS) {
      const input = host.querySelector<HTMLInputElement>(`#s-${spec.key}`)!;
      input.addEventListener('input', () => {
        const n = Number(input.value);
        // Radius sliders move over grid positions, not metres, so the handle always lands
        // on a precomputed radius instead of snapping visibly after the fact.
        const next = isRadius(spec.key) ? RADIUS_GRID[n]! : n;
        scenario.params = { ...scenario.params, [spec.key]: next };
        host
          .querySelector<HTMLElement>(`.slider[data-key="${spec.key}"] [data-readout]`)!
          .textContent = spec.format(next, scenario.lang, strings);
        schedule();
      });
    }
  };

  const renderSummary = (): void => {
    if (!latest || !ready) {
      el('#summary').innerHTML = `<div class="stat"><span class="value">—</span></div>`;
      return;
    }
    if (scenario.mode === 'current') {
      el('#summary').innerHTML =
        `<div class="stat"><span class="value">${formatNumber(ready.uatCount, scenario.lang)}</span>` +
        `<span class="label">${strings.viewCurrent}</span></div>` +
        `<div class="stat"><span class="value accent">${formatNumber(latest.regions, scenario.lang)}</span>` +
        `<span class="label">${strings.viewRegions}</span></div>`;
      return;
    }
    const reduction = 100 * (1 - latest.regions / ready.uatCount);
    const stat = (value: string, label: string, accent = false, title = ''): string =>
      `<div class="stat" ${title ? `title="${title}"` : ''}>
         <span class="value${accent ? ' accent' : ''}">${value}</span>
         <span class="label">${label}</span>
       </div>`;

    el('#summary').innerHTML = [
      stat(
        `${formatNumber(latest.regions, scenario.lang)}`,
        `${strings.regions} / ${formatNumber(ready.uatCount, scenario.lang)}`,
      ),
      stat(`${reduction.toFixed(1)}%`, strings.reduction, true),
      stat(
        formatMoney(latest.savingsAdminRon, scenario.lang),
        strings.savings,
        true,
        strings.savingsHelp,
      ),
      stat(formatNumber(latest.seeds, scenario.lang), strings.seeds),
      stat(formatNumber(latest.orphanRegions, scenario.lang), strings.orphanRegions),
      ...(scenario.params.pTarget > 0
        ? [
            stat(
              formatNumber(latest.belowTarget, scenario.lang),
              strings.belowTarget,
              false,
              strings.belowTargetHelp,
            ),
          ]
        : []),
      `<div class="stat"><span class="recompute">${strings.recomputeTime} ${latest.elapsedMs.toFixed(0)} ms</span>
       <span class="label">${strings.upperBound}: ${formatMoney(latest.savingsOperatingRon, scenario.lang)}</span></div>`,
    ].join('');
  };

  /** Plain-language reason a commune ended up where it did. */
  const explain = (index: number): string => {
    if (!latest || !ready) return '';
    const reason = latest.reasonOf[index]!;
    const region = latest.regionOf[index]!;
    const centre = unitName(ready, region);
    const radius =
      latest.tierOf[region] === 0
        ? `${scenario.params.rCapM / 1000} km`
        : `${scenario.params.rTownM / 1000} km`;

    switch (reason) {
      case REASON.CENTRE_CAPITAL:
        return strings.whyCapital;
      case REASON.CENTRE_THRESHOLD:
        return strings.whyThreshold
          .replace('{pop}', formatNumber(ready.population[index]!, scenario.lang))
          .replace('{x}', formatNumber(scenario.params.x, scenario.lang));
      case REASON.CENTRE_PROMOTED:
        return strings.whyPromoted.replace('{n}', String(scenario.params.nMin));
      case REASON.ABSORBED_OVERLAP:
        return strings.whyAbsorbedOverlap
          .replace('{centre}', centre)
          .replace('{pct}', `${latest.overlapOf[index]}%`)
          .replace('{radius}', radius);
      case REASON.ABSORBED_SEAT:
        return strings.whyAbsorbedSeat.replace('{centre}', centre).replace('{radius}', radius);
      case REASON.ORPHAN_SEAT:
        return strings.whyOrphanSeat;
      case REASON.ORPHAN_MEMBER:
        return strings.whyOrphanMember;
      case REASON.MANUAL_PIN:
        return strings.pinWhy;
      case REASON.TARGET_MERGED:
        return strings.whyTargetMerge.replace(
          '{target}',
          formatNumber(scenario.params.pTarget, scenario.lang),
        );
      default:
        return '';
    }
  };

  /** Units a given UAT could legally be pinned to: existing seats it may join. */
  const pinTargets = (index: number): number[] => {
    const info = ready;
    const result = latest;
    if (!info || !result) return [];
    const here = result.regionOf[index]!;
    const seats = new Set<number>();
    for (let i = 0; i < result.regionOf.length; i += 1) seats.add(result.regionOf[i]!);
    const county = info.attributes.county[index];
    return [...seats]
      .filter((seat) => {
        if (seat === here) return false;
        const seatCounty = info.attributes.county[seat];
        if (seatCounty === county) return true;
        // The one county line the model allows, in the one direction it allows it.
        return seatCounty === 'B' && county === 'IF';
      })
      .sort((a, b) => unitName(info, a).localeCompare(unitName(info, b), scenario.lang));
  };

  const setPin = (uat: number, seat: number | null): void => {
    scenario.pins = scenario.pins.filter((p) => p.uat !== uat);
    if (seat !== null) scenario.pins.push({ uat, seat });
    schedule();
  };

  // --- the published map, and the reader's own -----------------------------------------

  /** Saved versions, read once and kept in step with storage from here on. */
  let versions: SavedVersion[] = (() => {
    try {
      return parseVersions(window.localStorage.getItem(STORAGE_KEY));
    } catch {
      return [];
    }
  })();

  const persistVersions = (): void => {
    try {
      window.localStorage.setItem(STORAGE_KEY, serialiseVersions(versions));
    } catch {
      // Private browsing or a full quota. The list still works for this session; it just
      // does not survive the tab, which is better than refusing to save at all.
    }
  };

  const onReference = (): boolean =>
    referenceScenario !== null && sameMap(scenario, referenceScenario);

  const renderBadge = (): void => {
    const badge = el<HTMLElement>('#version-badge');
    if (!REFERENCE.published) { badge.hidden = true; return; }
    badge.hidden = false;
    badge.dataset.state = onReference() ? 'reference' : 'yours';
    badge.textContent = onReference()
      ? `${strings.refBadge} · ${REFERENCE.version}${REFERENCE.date ? ` · ${REFERENCE.date}` : ''}`
      : `${strings.refYours} · ${strings.refYoursUnsaved}`;
  };

  const loadHash = (hash: string): void => {
    const next = decodeScenario(hash, scenario.lang);
    scenario.params = next.params;
    scenario.pins = next.pins;
    scenario.forced = next.forced;
    scenario.mode = next.mode;
    scenario.selected = next.selected;
    renderModes();
    renderSliders();
    mapHandle.setSelected(scenario.selected);
    schedule();
  };

  const renderVersions = (): void => {
    const box = el<HTMLElement>('#versions');
    const rows = versions
      .map(
        (v) => `<li>
          <div class="version-row">
            <button class="link" data-open-version="${encodeURIComponent(v.name)}">${v.name}</button>
            <span>${
              v.units === null ? '' : `${formatNumber(v.units, scenario.lang)} ${strings.versionsUnits}`
            }</span>
          </div>
          <div class="version-meta">
            <span>${v.savedAt.slice(0, 10)}</span>
            <button data-drop-version="${encodeURIComponent(v.name)}" title="${strings.versionsDelete}">×</button>
          </div>
        </li>`,
      )
      .join('');

    box.innerHTML = `
      <h2>${strings.versionsHeading}</h2>
      ${
        REFERENCE.published && !onReference()
          ? `<button class="link" data-restore-reference>${strings.refRestore}</button>`
          : ''
      }
      ${versions.length === 0 ? `<p class="muted">${strings.versionsNone}</p>` : `<ul class="version-list">${rows}</ul>`}
      <button id="save-version" class="ghost small wide civic-button">${strings.versionsSave}</button>
      <div class="version-actions">
        <button class="link" id="export-versions">${strings.versionsExport}</button>
        <button class="link" id="import-versions">${strings.versionsImport}</button>
      </div>
      <div class="version-actions">
        <button class="link" id="export-png">${strings.exportPng}</button>
        <button class="link" id="print-sheet">${strings.printSheet}</button>
      </div>`;

    box.querySelector<HTMLButtonElement>('[data-restore-reference]')?.addEventListener('click', () => {
      loadHash(REFERENCE.hash);
    });

    box.querySelectorAll<HTMLButtonElement>('[data-open-version]').forEach((button) => {
      button.addEventListener('click', () => {
        const name = decodeURIComponent(button.dataset.openVersion!);
        const found = versions.find((v) => v.name === name);
        if (found) loadHash(found.hash);
      });
    });

    box.querySelectorAll<HTMLButtonElement>('[data-drop-version]').forEach((button) => {
      button.addEventListener('click', () => {
        versions = removeVersion(versions, decodeURIComponent(button.dataset.dropVersion!));
        persistVersions();
        renderVersions();
      });
    });

    el<HTMLButtonElement>('#save-version').addEventListener('click', () => {
      const name = window.prompt(strings.versionsNamePrompt, '')?.trim();
      if (!name) return;
      versions = upsertVersion(versions, {
        name,
        savedAt: new Date().toISOString(),
        hash: encodeScenario(scenario),
        units: latest?.regions ?? null,
      });
      persistVersions();
      renderVersions();
    });

    el<HTMLButtonElement>('#export-versions').addEventListener('click', () => {
      const now = new Date().toISOString();
      const blob = new Blob([JSON.stringify(toExportFile(versions, now), null, 2)], {
        type: 'application/json',
      });
      download(URL.createObjectURL(blob), exportFilename(now));
    });

    el<HTMLButtonElement>('#import-versions').addEventListener('click', () => {
      el<HTMLInputElement>('#versions-file').click();
    });

    el<HTMLButtonElement>('#export-png').addEventListener('click', () => {
      void exportPng();
    });

    el<HTMLButtonElement>('#print-sheet').addEventListener('click', () => window.print());
  };

  const download = (href: string, filename: string): void => {
    const link = document.createElement('a');
    link.href = href;
    link.download = filename;
    link.click();
    // Revoking immediately can beat the download on some browsers; a frame is enough.
    requestAnimationFrame(() => URL.revokeObjectURL(href));
  };

  el<HTMLInputElement>('#versions-file').addEventListener('change', async (event) => {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;
    const imported = parseImport(await file.text());
    // Reset first, so choosing the same file twice fires a change event both times.
    input.value = '';
    if (imported === null) {
      window.alert(strings.versionsImportFailed);
      return;
    }
    versions = mergeImported(versions, imported);
    persistVersions();
    renderVersions();
    window.alert(strings.versionsImported.replace('{n}', String(imported.length)));
  });

  /**
   * The map as a PNG, names included.
   *
   * Drawn from MapLibre's own canvas, which is why the map is created with
   * `preserveDrawingBuffer` — without it the browser is free to discard the buffer after
   * compositing and the read comes back blank. It costs a little memory on every frame,
   * which is the price of the export working at all.
   *
   * The names are the awkward part, and were simply missing before. They are HTML rather than
   * a MapLibre symbol layer — which is what avoids depending on a font server or shipping
   * glyph atlases — so they are not on that canvas at all, and an export of Romania with no
   * place names on it is a picture of a colour scheme. They are composited on afterwards: the
   * map bitmap first, then each label where its span already sits, with a stroke standing in
   * for the CSS text-shadow that keeps it legible over the choropleth.
   */
  const exportPng = async (): Promise<void> => {
    const button = el<HTMLButtonElement>('#export-png');
    const label = button.textContent;
    button.textContent = strings.exportPngBusy;
    try {
      await new Promise<void>((resolve) => mapHandle.map.once('idle', () => resolve()));
      const source = mapHandle.map.getCanvas();
      const out = document.createElement('canvas');
      out.width = source.width;
      out.height = source.height;
      const ctx = out.getContext('2d');
      if (!ctx) return;
      ctx.drawImage(source, 0, 0);

      // The canvas is in device pixels; the labels are positioned in CSS pixels.
      const scale = source.width / Math.max(source.clientWidth, 1);
      ctx.textAlign = 'center';
      ctx.lineJoin = 'round';
      for (const node of labels.children) {
        const span = node as HTMLElement;
        const text = span.textContent ?? '';
        if (!text) continue;
        const centre = span.classList.contains('centre');
        const size = centre ? 12 : 11;
        ctx.font = `600 ${size * scale}px ui-sans-serif, system-ui, sans-serif`;
        // Mirrors the span's own transform: translate(-50%, -140%).
        const x = parseFloat(span.style.left || '0') * scale;
        const y = (parseFloat(span.style.top || '0') - size * 1.4) * scale;
        ctx.strokeStyle = '#0f1216';
        ctx.lineWidth = 3 * scale;
        ctx.strokeText(text, x, y);
        ctx.fillStyle = centre ? '#ffffff' : '#f2f4f7';
        ctx.fillText(text, x, y);
      }

      download(
        out.toDataURL('image/png'),
        `administrativ-${new Date().toISOString().slice(0, 10)}.png`,
      );
    } finally {
      button.textContent = label;
    }
  };

  // --- the route a commune was absorbed along -------------------------------------------

  /**
   * County shards of routed geometry, fetched the first time a route in that county is shown.
   *
   * 31 KB each, so a hover pays for one county and nothing else. `null` records a county
   * whose shard is not in this build — the geometry is published as a release asset like the
   * road layers, so its absence is a normal state and must cost the route its shape, not its
   * existence.
   */
  const shards = new Map<string, Map<string, [number, number][]> | null>();
  const shardLoads = new Map<string, Promise<void>>();

  const loadShard = (county: string): Promise<void> => {
    let pending = shardLoads.get(county);
    if (!pending) {
      pending = fetch(`${DATA_BASE}edge-paths/${county}.geojson`)
        .then((response) => (response.ok ? response.json() : null))
        .then((raw) => {
          shards.set(county, raw === null ? null : indexShard(raw));
        })
        .catch(() => {
          shards.set(county, null);
        });
      shardLoads.set(county, pending);
    }
    return pending;
  };

  let chainFor: number | null = null;

  /** Draw the route, and say in the card which legs are real roads and which are stand-ins. */
  const drawChain = (
    uat: number,
    legs: { from: number; to: number; metres: number; seconds: number }[],
  ): void => {
    if (!ready || chainFor !== uat) return;
    const county = ready.attributes.county[uat] ?? '';
    const shard = shards.get(county);
    const siruta = ready.attributes.siruta;

    void mapHandle.seatPoints().then((seats) => {
      if (chainFor !== uat) return;
      const route = [uat, ...legs.map((leg) => leg.to)];
      const metresOf = (a: number, b: number): number =>
        legs.find((leg) => leg.from === a && leg.to === b)?.metres ?? Infinity;
      const geometryFor = (a: number, b: number): [number, number][] | null =>
        shard?.get(edgeKey(siruta[a] ?? '', siruta[b] ?? '')) ?? null;

      const { features, legs: drawn, totalMetres } = buildChain(
        route,
        metresOf,
        geometryFor,
        (i) => seats.get(i),
      );
      mapHandle.setChain(features);

      const slot = hovercard.querySelector<HTMLElement>('.chain');
      if (!slot || slot.dataset.uat !== String(uat)) return;
      const anySchematic = drawn.some((leg) => !leg.real);
      // Minutes as well as kilometres. The distance cap is the least legible rule in the
      // model — "21.5 km against a 50 km cap" asks a reader to hold a distance in their head
      // and judge it, and a time does not. Absent where the build has no edge-time payload,
      // and where no drivable route exists.
      const secondsOf = new Map(legs.map((leg) => [`${leg.from}:${leg.to}`, leg.seconds]));
      const minutes = (secs: number | undefined): string =>
        secs === undefined || secs <= 0 || secs >= 65_535
          ? ''
          : ` · ${Math.round(secs / 60)} ${strings.chainMinutes}`;
      const totalSeconds = legs.reduce(
        (sum, leg) => (leg.seconds > 0 && leg.seconds < 65_535 ? sum + leg.seconds : sum),
        0,
      );
      slot.innerHTML =
        `<div class="sd-title">${strings.chainTitle}</div>` +
        drawn
          .map(
            (leg) =>
              `<div class="line${leg.real ? '' : ' schematic'}">` +
              `<span>${ready!.attributes.name[leg.to]}</span>` +
              `<span>${(leg.metres / 1000).toFixed(1)} km${minutes(
                secondsOf.get(`${leg.from}:${leg.to}`),
              )}</span></div>`,
          )
          .join('') +
        `<div class="line total"><span>${strings.chainTotal}</span>` +
        `<span>${(totalMetres / 1000).toFixed(1)} km${minutes(totalSeconds)}</span></div>` +
        (shard === undefined ? `<div class="chain-note">${strings.chainLoading}</div>` : '') +
        (anySchematic && shard !== undefined
          ? `<div class="chain-note">${strings.chainSchematic}</div>`
          : '');
    });
  };

  /** Every member's route to the centre, drawn as one set of legs. */
  const requestUnitChains = (seat: number): void => {
    if (!ready) return;
    chainFor = seat;
    const county = ready.attributes.county[seat] ?? '';
    if (!shards.has(county)) {
      void loadShard(county).then(() => worker.postMessage({ type: 'unitChains', seat }));
    }
    worker.postMessage({ type: 'unitChains', seat });
  };

  /** Ask for a route, and fetch the county's geometry alongside so the two arrive together. */
  const requestChain = (uat: number | null): void => {
    if (uat === null || !ready || !latest) {
      chainFor = null;
      mapHandle.setChain([]);
      return;
    }
    // No route was measured for this one; the panel says which rule placed it instead.
    if (latest.parentOf[uat]! < 0) {
      chainFor = null;
      mapHandle.setChain([]);
      return;
    }
    chainFor = uat;
    const county = ready.attributes.county[uat] ?? '';
    if (!shards.has(county)) void loadShard(county).then(() => worker.postMessage({ type: 'chain', uat }));
    worker.postMessage({ type: 'chain', uat });
  };

  // --- what the pointer emphasises -------------------------------------------------------

  /**
   * Hover behaviour is a reading preference, not part of the scenario.
   *
   * Deliberately not in the URL hash: a shared link is an argument about a map, and two people
   * comparing the same scenario should not find they disagree because one of them had a
   * different highlight switched on.
   */
  type HoverBounds = 'none' | 'county' | 'region' | 'unit' | 'all';
  type HoverRoads = 'none' | 'chain' | 'unit';
  let hoverBounds: HoverBounds = 'county';
  let hoverRoads: HoverRoads = 'chain';

  const renderHoverOptions = (): void => {
    const bounds: [HoverBounds, string][] = [
      ['none', strings.hoverNone],
      ['county', strings.hoverCounty],
      ['region', strings.hoverRegion],
      ['unit', strings.hoverUnit],
      ['all', strings.hoverAll],
    ];
    const roads: [HoverRoads, string][] = [
      ['none', strings.hoverNone],
      ['chain', strings.hoverRoadsChain],
      ['unit', strings.hoverRoadsUnit],
    ];
    el('#hover-options').innerHTML = `
      <p class="hover-label">${strings.hoverBoundsHeading}</p>
      <div class="chip-row" id="hover-bounds">
        ${bounds
          .map(
            ([key, text]) =>
              `<button data-bounds="${key}" aria-pressed="${key === hoverBounds}">${text}</button>`,
          )
          .join('')}
      </div>
      <p class="hover-label">${strings.hoverRoadsHeading}</p>
      <div class="chip-row" id="hover-roads">
        ${roads
          .map(
            ([key, text]) =>
              `<button data-roads="${key}" aria-pressed="${key === hoverRoads}">${text}</button>`,
          )
          .join('')}
      </div>
      <p class="help">${strings.hoverHelp}</p>`;

    for (const button of document.querySelectorAll<HTMLButtonElement>('#hover-bounds button')) {
      button.addEventListener('click', () => {
        hoverBounds = button.dataset.bounds as HoverBounds;
        renderHoverOptions();
        applyHover(lastHovered);
      });
    }
    for (const button of document.querySelectorAll<HTMLButtonElement>('#hover-roads button')) {
      button.addEventListener('click', () => {
        hoverRoads = button.dataset.roads as HoverRoads;
        renderHoverOptions();
        applyHover(lastHovered);
      });
    }
  };

  /** The commune the pointer is over, so a change of option redraws without waiting for a move. */
  let lastHovered: number | null = null;

  const applyHover = (index: number | null): void => {
    lastHovered = index;
    if (!ready || !latest || index === null) {
      mapHandle.setCountyFocus(null);
      mapHandle.setRegionFocus(null);
      mapHandle.setUnitFocus([]);
      requestChain(null);
      return;
    }

    const county = ready.attributes.county[index] ?? null;
    const wantCounty = hoverBounds === 'county' || hoverBounds === 'all';
    const wantRegion = hoverBounds === 'region' || hoverBounds === 'all';
    const wantUnit = hoverBounds === 'unit' || hoverBounds === 'all';

    mapHandle.setCountyFocus(wantCounty ? county : null);
    mapHandle.setRegionFocus(wantRegion ? regionOfCounty(county ?? undefined) : null);

    const seat = latest.regionOf[index]!;
    if (wantUnit) {
      const members: number[] = [];
      for (let i = 0; i < latest.regionOf.length; i += 1) {
        if (latest.regionOf[i] === seat) members.push(i);
      }
      mapHandle.setUnitFocus(members);
    } else {
      mapHandle.setUnitFocus([]);
    }

    if (hoverRoads === 'none') {
      chainFor = null;
      mapHandle.setChain([]);
    } else if (hoverRoads === 'unit') {
      requestUnitChains(seat);
    } else {
      requestChain(index);
    }
  };

  const setForced = (uat: number, on: boolean): void => {
    scenario.forced = on
      ? [...new Set([...scenario.forced, uat])].sort((a, b) => a - b)
      : scenario.forced.filter((i) => i !== uat);
    schedule();
  };

  /**
   * The centres the reader put on the map themselves.
   *
   * Kept apart from the pins block because they are a different kind of override and the
   * difference matters: a pin moves one commune after the rules have run, and a forced centre
   * changes what the rules were given. A reader who confuses the two will misread the map.
   */
  const renderForced = (): void => {
    const box = el<HTMLElement>('#forced');
    if (!ready || !latest) { box.hidden = true; return; }
    box.hidden = false;

    if (scenario.forced.length === 0) {
      box.innerHTML = `<h4>${strings.forceHeading}</h4><p class="muted">${strings.forceNone}</p>`;
      return;
    }

    const refusalOf = new Map(latest.forcedRejected.map((r) => [r.uat, r.why]));
    const refusalText: Record<string, string> = {
      'capital-ring': strings.forceRefusedRing,
      bucharest: strings.forceRefusedBucharest,
      'already-a-centre': strings.forceRefusedAlready,
    };

    box.innerHTML = `
      <h4>${strings.forceHeading} <span class="count">${formatNumber(
        scenario.forced.length,
        scenario.lang,
      )}</span></h4>
      <p class="muted">${strings.forceNote}</p>
      <ul class="pin-list">
        ${scenario.forced
          .map((uat) => {
            const why = refusalOf.get(uat);
            return `<li${why ? ' class="stale"' : ''}>
              <span class="pin-uat">${ready!.attributes.name[uat]}</span>
              <span>${ready!.attributes.county[uat]}</span>
              ${why ? `<em class="pin-note">${refusalText[why] ?? why}</em>` : ''}
              <button data-unforce="${uat}" title="${strings.forceRemove}">×</button>
            </li>`;
          })
          .join('')}
      </ul>
      <button class="link" data-clear-forced>${strings.forceClearAll}</button>`;

    box.querySelectorAll<HTMLButtonElement>('[data-unforce]').forEach((button) => {
      button.addEventListener('click', () => setForced(Number(button.dataset.unforce), false));
    });
    box.querySelector<HTMLButtonElement>('[data-clear-forced]')?.addEventListener('click', () => {
      scenario.forced = [];
      schedule();
    });
  };

  const renderPins = (): void => {
    const box = el<HTMLElement>('#pins');
    if (!ready || !latest) { box.hidden = true; return; }
    box.hidden = false;
    if (scenario.pins.length === 0) {
      box.innerHTML = `<h4>${strings.pinHeading}</h4><p class="muted">${strings.pinNone}</p>`;
      return;
    }
    const stale = new Set(latest.pinsRejected.map((r) => r.pin.uat));
    box.innerHTML = `
      <h4>${strings.pinHeading} <span class="count">${scenario.pins.length}</span></h4>
      <ul class="pin-list">
        ${scenario.pins
          .map(
            (pin) => `<li${stale.has(pin.uat) ? ' class="stale"' : ''}>
              <span class="pin-uat">${ready!.attributes.name[pin.uat]}</span>
              <span class="pin-arrow">→</span>
              <span class="pin-seat">${unitName(ready!, pin.seat)}</span>
              ${stale.has(pin.uat) ? `<em class="pin-note">${strings.pinStale}</em>` : ''}
              <button data-unpin="${pin.uat}" title="${strings.pinRemove}">×</button>
            </li>`,
          )
          .join('')}
      </ul>
      <button class="link" data-clear-pins>${strings.pinClearAll}</button>`;

    box.querySelectorAll<HTMLButtonElement>('[data-unpin]').forEach((button) => {
      button.addEventListener('click', () => setPin(Number(button.dataset.unpin), null));
    });
    box.querySelector<HTMLButtonElement>('[data-clear-pins]')?.addEventListener('click', () => {
      scenario.pins = [];
      schedule();
    });
  };

  /**
   * Units worth a second look.
   *
   * Not a list of errors — the rules are deterministic and these are all legal outcomes.
   * It exists so the odd cases can be found deliberately instead of stumbled on while
   * panning the map, which is how every one of them has been found so far.
   */
  /**
   * Who could have been a centre, and what became of them.
   *
   * The list is the rules chart: the map already shows which towns became centres, and the
   * argument is about the ones that did not. Fetched from the worker when the section is
   * opened and refreshed while it stays open, because it is a function of the parameters and
   * goes stale the moment a slider moves.
   */
  let candidacyOf: Uint8Array | null = null;
  let candidacyOpen = false;
  let candidateQuery = '';
  let candidateCounty = '';
  /**
   * The counties seen in the last completed report.
   *
   * Held across recomputes so the filter bar survives them. Promoting from the list starts a
   * recompute, which drops `candidacyOf` — rebuilding the controls from scratch each time
   * would blink the search box away and take the caret with it.
   */
  let candidateCounties: string[] = [];

  /**
   * Which states the reader may promote from, measured rather than assumed.
   *
   * Forcing waives the population threshold and the separation floor — the two rules that are
   * matters of judgement — so a candidate passed over for either can be promoted. Two states
   * cannot, and each is refused for its own reason:
   *
   *  - `IN_CAPITAL_RING` is refused `capital-ring`. A capital holds its ring by right, and
   *    that is a matter of geography rather than judgement.
   *  - `STOOD_DOWN` is refused `already-a-centre`. It was a centre when the override was
   *    considered, and the capital absorbs it immediately afterwards.
   *
   * Offering a button that the model would refuse is worse than offering none, so these two
   * carry the reason instead. See tests/candidate-promotion.test.ts, which holds the model to
   * exactly this list.
   */
  const FORCEABLE: ReadonlySet<number> = new Set<number>([
    CANDIDACY.ELIGIBLE_UNUSED,
    CANDIDACY.REFUSED_SEPARATION,
  ]);

  /** The reason a state carries instead of a button. */
  const BARRED_REASON: Record<number, keyof Strings> = {
    [CANDIDACY.IN_CAPITAL_RING]: 'candBarred',
    [CANDIDACY.STOOD_DOWN]: 'candBarredStoodDown',
  };

  const requestCandidacy = (): void => {
    if (!candidacyOpen) return;
    worker.postMessage({ type: 'candidacy', params: scenario.params, forced: scenario.forced });
  };

  const CANDIDACY_LABEL: Record<number, keyof Strings> = {
    [CANDIDACY.CAPITAL]: 'candCapital',
    [CANDIDACY.THRESHOLD]: 'candThreshold',
    [CANDIDACY.PROMOTED]: 'candPromoted',
    [CANDIDACY.STOOD_DOWN]: 'candStoodDown',
    [CANDIDACY.ELIGIBLE_UNUSED]: 'candEligibleUnused',
    [CANDIDACY.REFUSED_SEPARATION]: 'candRefusedSeparation',
    [CANDIDACY.IN_CAPITAL_RING]: 'candInCapitalRing',
  };

  /** Centres first, then the near misses, then the merely eligible. */
  const CANDIDACY_ORDER = [
    CANDIDACY.CAPITAL,
    CANDIDACY.THRESHOLD,
    CANDIDACY.PROMOTED,
    CANDIDACY.STOOD_DOWN,
    CANDIDACY.IN_CAPITAL_RING,
    CANDIDACY.REFUSED_SEPARATION,
    CANDIDACY.ELIGIBLE_UNUSED,
  ] as const;

  const renderCandidates = (): void => {
    const box = el<HTMLElement>('#candidates');
    if (!ready || !latest) { box.hidden = true; return; }
    box.hidden = false;

    // Rebuilding the panel replaces the search box, which would drop the caret mid-word on
    // every keystroke. Noted before the rebuild and restored after it.
    const active = document.activeElement as HTMLInputElement | null;
    const hadFocus = active?.id === 'candidate-search';
    const caret = hadFocus ? active.selectionStart : null;

    const grouped = new Map<number, number[]>();
    const counties = new Set<string>();
    let total = 0;
    let shown = 0;

    if (candidacyOf) {
      const needle = candidateQuery.trim().toLocaleLowerCase(scenario.lang);
      for (let i = 0; i < candidacyOf.length; i += 1) {
        const state = candidacyOf[i]!;
        if (state === CANDIDACY.NONE) continue;
        total += 1;
        counties.add(ready.attributes.county[i]!);
        if (candidateCounty && ready.attributes.county[i] !== candidateCounty) continue;
        if (needle && !ready.attributes.name[i]!.toLocaleLowerCase(scenario.lang).includes(needle)) {
          continue;
        }
        shown += 1;
        let list = grouped.get(state);
        if (!list) { list = []; grouped.set(state, list); }
        list.push(i);
      }
    }

    if (candidacyOf) candidateCounties = [...counties].sort((a, b) => a.localeCompare(b, scenario.lang));
    const filtered = candidateQuery.trim() !== '' || candidateCounty !== '';

    const row = (i: number): string => {
      const state = candidacyOf![i]!;
      const isForced = scenario.forced.includes(i);
      const canForce = FORCEABLE.has(state) || isForced;
      const barred = BARRED_REASON[state];
      const action = canForce
        ? `<button class="ghost tiny" data-promote="${i}" data-on="${isForced ? '0' : '1'}">${
            isForced ? strings.candDemote : strings.candPromote
          }</button>`
        : barred
          ? `<span class="barred" title="${strings[barred]}">—</span>`
          : '';
      return `<li>
        <div class="audit-row candidate-row">
          <button class="candidate-name" data-goto-candidate="${i}">${ready!.attributes.name[i]}</button>
          <span class="candidate-meta">${ready!.attributes.county[i]} · ${formatNumber(
            ready!.population[i]!,
            scenario.lang,
          )}</span>
          ${action}
        </div>
      </li>`;
    };

    const groups = CANDIDACY_ORDER.filter((state) => (grouped.get(state)?.length ?? 0) > 0)
      .map((state) => {
        const list = grouped.get(state)!;
        return `
        <details${filtered ? ' open' : ''}>
          <summary>${strings[CANDIDACY_LABEL[state]!]}
            <span class="count">${formatNumber(list.length, scenario.lang)}</span></summary>
          <ul class="audit-list">
            ${list
              .slice()
              .sort((a, b) => ready!.population[b]! - ready!.population[a]!)
              .map(row)
              .join('')}
          </ul>
        </details>`;
      })
      .join('');

    const filterBar = `
        <div class="candidate-filters">
          <div class="civic-field">
          <input id="candidate-search" class="civic-input" type="search" placeholder="${strings.candSearch}"
                 aria-label="${strings.candSearch}" value="${candidateQuery.replace(/"/g, '&quot;')}">
          </div>
          <div class="civic-field">
          <select id="candidate-county" class="civic-select civic-select--native" aria-label="${strings.candCounty}">
            <option value="">${strings.candAllCounties}</option>
            ${candidateCounties
              .map(
                (c) =>
                  `<option value="${c}"${c === candidateCounty ? ' selected' : ''}>${c}</option>`,
              )
              .join('')}
          </select>
          </div>
        </div>`;

    const listing = `
        <p class="muted candidate-showing">${strings.candShowing
          .replace('{shown}', formatNumber(shown, scenario.lang))
          .replace('{total}', formatNumber(total, scenario.lang))}</p>
        ${groups || `<p class="muted">${strings.candNoMatch}</p>`}`;

    // The filter bar outlives the report: promoting starts a recompute that drops it, and
    // taking the controls away for those 150 ms loses whatever was being typed.
    const body = candidacyOf
      ? `${filterBar}${listing}`
      : `${candidateCounties.length > 0 ? filterBar : ''}<p class="muted">${strings.candidatesLoading}</p>`;

    box.innerHTML = `
      <details id="candidates-details"${candidacyOpen ? ' open' : ''}>
        <summary><h4>${strings.candidatesHeading}</h4></summary>
        <p class="muted">${strings.candidatesIntro}</p>
        ${body}
      </details>`;

    el<HTMLDetailsElement>('#candidates-details').addEventListener('toggle', (event) => {
      candidacyOpen = (event.target as HTMLDetailsElement).open;
      if (candidacyOpen && !candidacyOf) requestCandidacy();
    });

    box.querySelector<HTMLInputElement>('#candidate-search')?.addEventListener('input', (event) => {
      candidateQuery = (event.target as HTMLInputElement).value;
      renderCandidates();
    });

    box.querySelector<HTMLSelectElement>('#candidate-county')?.addEventListener('change', (event) => {
      candidateCounty = (event.target as HTMLSelectElement).value;
      renderCandidates();
    });

    box.querySelectorAll<HTMLButtonElement>('[data-goto-candidate]').forEach((button) => {
      button.addEventListener('click', () => {
        const index = Number(button.dataset.gotoCandidate);
        scenario.selected = index;
        writeHash(scenario);
        mapHandle.setSelected(index);
        mapHandle.flyTo(index);
        renderDetail();
      });
    });

    // Promoting from the list rather than from the map: the reader is comparing candidates
    // against each other here, and sending them to the map to act on one loses the comparison.
    box.querySelectorAll<HTMLButtonElement>('[data-promote]').forEach((button) => {
      button.addEventListener('click', () => {
        setForced(Number(button.dataset.promote), button.dataset.on === '1');
      });
    });

    if (hadFocus) {
      const input = box.querySelector<HTMLInputElement>('#candidate-search');
      input?.focus();
      if (caret !== null) input?.setSelectionRange(caret, caret);
    }
  };

  const renderAudit = (): void => {
    const box = el<HTMLElement>('#audit');
    if (!ready || !latest) { box.hidden = true; return; }
    box.hidden = false;

    const members = new Map<number, number[]>();
    for (let i = 0; i < latest.regionOf.length; i += 1) {
      const seat = latest.regionOf[i]!;
      let list = members.get(seat);
      if (!list) { list = []; members.set(seat, list); }
      list.push(i);
    }

    const single: number[] = [];
    const below: number[] = [];
    const outranked: number[] = [];
    for (const [seat, list] of members) {
      if (list.length === 1) single.push(seat);
      const pop = list.reduce((total, i) => total + ready!.population[i]!, 0);
      if (scenario.params.pTarget > 0 && pop < scenario.params.pTarget) below.push(seat);
      if (list.some((i) => ready!.attributes.adminRank[i]! < ready!.attributes.adminRank[seat]!)) {
        outranked.push(seat);
      }
    }

    const groups: [string, number[]][] = [
      [strings.auditSingle, single],
      [strings.auditBelowTarget, below],
      [strings.auditOutranked, outranked],
      [strings.auditSplit, latest.splitUnits],
    ];
    const shown = groups.filter(([, list]) => list.length > 0);

    box.innerHTML = `
      <h4>${strings.auditHeading}</h4>
      <p class="muted">${strings.auditIntro}</p>
      ${
        shown.length === 0
          ? `<p class="muted">${strings.auditClean}</p>`
          : shown
              .map(
                ([label, list]) => `
        <details>
          <summary>${label} <span class="count">${formatNumber(list.length, scenario.lang)}</span></summary>
          <ul class="audit-list">
            ${list
              .slice()
              .sort((a, b) => unitName(ready!, a).localeCompare(unitName(ready!, b), scenario.lang))
              .map(
                (seat) =>
                  `<li data-seat="${seat}">
                     <div class="audit-row">
                       <button data-goto="${seat}">${unitName(ready!, seat)}</button>
                       <span>${ready!.attributes.county[seat]}</span>
                     </div>
                     <em class="audit-why"></em>
                   </li>`,
              )
              .join('')}
          </ul>
        </details>`,
              )
              .join('')
      }`;

    // Filled in when a group is opened, not on every repaint: each answer is a Dijkstra
    // inside one county, which is cheap once and wasteful 137 times a second during a drag.
    box.querySelectorAll<HTMLDetailsElement>('details').forEach((details) => {
      details.addEventListener('toggle', () => {
        if (!details.open) return;
        const seats = [...details.querySelectorAll<HTMLElement>('li[data-seat]')]
          .filter((row) => row.querySelector('.audit-why')?.textContent === '')
          .map((row) => Number(row.dataset.seat));
        if (seats.length > 0) worker.postMessage({ type: 'explain', seats });
      });
    });

    box.querySelectorAll<HTMLButtonElement>('[data-goto]').forEach((button) => {
      button.addEventListener('click', () => {
        const seat = Number(button.dataset.goto);
        scenario.selected = seat;
        writeHash(scenario);
        mapHandle.setSelected(seat);
        mapHandle.flyTo(seat);
        renderDetail();
      });
    });
  };

  /**
   * A commune's page on transparenta.eu, or null where the payload has no id for it.
   *
   * A payload built before `uatCode` existed has no such array at all, so an older build
   * loses the link rather than the panel.
   */
  const budgetUrl = (index: number): string | null =>
    budgetUrlFor(ready?.attributes.uatCode?.[index]);

  const budgetLink = (index: number, label: string): string => {
    const url = budgetUrl(index);
    if (!url) return label;
    return `<a class="budget-link" href="${url}" target="_blank" rel="noopener"
              title="${strings.budgetLinkTitle}">${label}</a>`;
  };

  const signed = (
    value: number | null,
    formatter: (absValue: number) => string,
  ): string => {
    if (value === null) return '—';
    const sign = value > 0 ? '+' : value < 0 ? '-' : '';
    return `${sign}${formatter(Math.abs(value))}`;
  };

  /**
   * Shared health-access indicators, fetched only for the detail panel.
   *
   * This reports UAT co-location counts from packages/health_access. It deliberately leaves
   * Bucharest sector rows blank because the shared view can place Bucharest providers only at
   * municipality level, not inside individual sectors.
   */
  let healthAccess: HealthAccessPayload | null = null;
  let healthAccessLoad: Promise<void> | null = null;

  const loadHealthAccess = (): Promise<void> => {
    healthAccessLoad ??= fetch(`${DATA_BASE}health-access-uat.json`)
      .then((response) => (response.ok ? response.json() : null))
      .then((raw: HealthAccessPayload | null) => {
        healthAccess = raw && ready && healthAccessPayloadAligned(raw, ready.attributes.siruta)
          ? raw
          : null;
      })
      .catch(() => {
        healthAccess = null;
      });
    return healthAccessLoad;
  };

  /**
   * Shared local-finance indicators, fetched only for the detail panel.
   *
   * The model's own binary finance still carries administration-only spending. The shared mart
   * adds comparable revenue/own-revenue indicators, aligned to the same UAT index so a merged
   * unit can be summed without a string join in the browser.
   */
  let localFinance: LocalFinancePayload | null = null;
  let localFinanceLoad: Promise<void> | null = null;

  const loadLocalFinance = (): Promise<void> => {
    localFinanceLoad ??= fetch(`${DATA_BASE}local-finance-2024.json`)
      .then((response) => (response.ok ? response.json() : null))
      .then((raw: LocalFinancePayload | null) => {
        localFinance = raw && ready && localFinancePayloadAligned(raw, ready.attributes.siruta)
          ? raw
          : null;
      })
      .catch(() => {
        localFinance = null;
      });
    return localFinanceLoad;
  };

  /**
   * Public-enterprise footprint, aggregated by authority/UAT before it reaches the app.
   *
   * The source package may know company CUIs and names while building the aggregate; this
   * payload deliberately does not. The browser gets only numeric arrays aligned to UAT index.
   */
  let publicEnterpriseFootprint: PublicEnterpriseFootprintPayload | null = null;
  let publicEnterpriseFootprintLoad: Promise<void> | null = null;

  const loadPublicEnterpriseFootprint = (): Promise<void> => {
    publicEnterpriseFootprintLoad ??= fetch(`${DATA_BASE}public-enterprise-footprint.json`)
      .then((response) => (response.ok ? response.json() : null))
      .then((raw: PublicEnterpriseFootprintPayload | null) => {
        publicEnterpriseFootprint =
          raw && ready && publicEnterpriseFootprintPayloadAligned(raw, ready.attributes.siruta)
            ? raw
            : null;
      })
      .catch(() => {
        publicEnterpriseFootprint = null;
      });
    return publicEnterpriseFootprintLoad;
  };

  /**
   * The 2020 local-council votes, fetched the first time a unit's detail is opened.
   *
   * 153 KB, and only a reader who opens a unit ever needs it — the map itself does not. Absent
   * or unreachable it costs the party table and nothing else, which is why the panel renders
   * without waiting for it and fills the section in when it lands.
   */
  interface VotesPayload {
    mandate: string;
    parties: string[];
    partyOf: number[][];
    votesOf: number[][];
  }
  let votes: VotesPayload | null = null;
  let votesLoad: Promise<void> | null = null;

  const loadVotes = (): Promise<void> => {
    votesLoad ??= fetch(`${DATA_BASE}votes.json`)
      .then((response) => (response.ok ? response.json() : null))
      .then((raw: VotesPayload | null) => {
        votes = raw;
      })
      .catch(() => {
        votes = null;
      });
    return votesLoad;
  };

  const listsOf = (index: number): VoteList[] => {
    if (!votes) return [];
    const parties = votes.partyOf[index] ?? [];
    const counts = votes.votesOf[index] ?? [];
    return parties.map((party, k) => ({ party, votes: counts[k] ?? 0 }));
  };

  /**
   * Who would hold the seats, before and after.
   *
   * Both sides are computed the same way — the members' own votes under the same rules — so
   * the difference is attributable to pooling rather than to methodology. Using the real
   * elected roster for "today" and a computation for "after" would have mixed the two.
   */
  const partyTableHtml = (members: number[], totalPop: number): string => {
    if (!ready || !votes) return '';
    const perCommune = members
      .map((i) => ({ i, lists: listsOf(i) }))
      .filter((m) => m.lists.length > 0)
      .map((m) => allocateSeats(m.lists, councillorsFor(ready!.population[m.i]!)));
    if (perCommune.length === 0) return '';

    const pooled = new Map<number, number>();
    for (const i of members) {
      for (const list of listsOf(i)) {
        pooled.set(list.party, (pooled.get(list.party) ?? 0) + list.votes);
      }
    }
    const merged = allocateSeats(
      [...pooled].map(([party, v]) => ({ party, votes: v })),
      councillorsFor(totalPop),
    );

    const shift = representationShift(perCommune, merged);
    const lost = new Set(shift.losesAllSeats);
    const rows = [...new Set([...shift.before.keys(), ...shift.after.keys()])]
      .map((party) => ({
        party,
        before: shift.before.get(party) ?? 0,
        after: shift.after.get(party) ?? 0,
      }))
      .sort((a, b) => b.after - a.after || b.before - a.before)
      .slice(0, 10);

    return `
      <div class="party-table">
        <div class="rep-row rep-head">
          <span>${strings.repPartyHeading}</span>
          <span>${strings.repPartyToday}</span>
          <span>${strings.repPartyAfter}</span>
        </div>
        ${rows
          .map(
            (r) => `<div class="rep-row${lost.has(r.party) ? ' lost' : ''}">
              <span title="${votes!.parties[r.party] ?? ''}">${votes!.parties[r.party] ?? ''}</span>
              <span>${r.before}</span>
              <span>${r.after || '—'}</span>
            </div>`,
          )
          .join('')}
        ${
          shift.losesAllSeats.length > 0
            ? `<p class="muted lost-note">${formatNumber(shift.losesAllSeats.length, scenario.lang)} ${strings.repLoses}</p>`
            : ''
        }
        <p class="muted">${strings.repCaveat}</p>
        <p class="muted rep-source">${strings.repMandate}</p>
      </div>`;
  };

  /**
   * Which courts a merged unit would straddle.
   *
   * The Government's own circumscriptions, not nearest-court-by-road: the legal assignment is
   * a fact and the nearest court is a guess that happens to be right most of the time.
   *
   * Judecătorii rather than tribunale. There is one tribunal per county and no unit may cross
   * a county line, so no merger could ever span two — the level where a merger actually
   * straddles a boundary is the judecătorie, and 55% of the default map's units do.
   */
  interface CourtsPayload {
    period?: string;
    courts: string[];
    courtOf: number[];
  }
  let courts: CourtsPayload | null = null;
  let courtsLoad: Promise<void> | null = null;

  const loadCourts = (): Promise<void> => {
    courtsLoad ??= fetch(`${DATA_BASE}courts.json`)
      .then((response) => (response.ok ? response.json() : null))
      .then((raw: CourtsPayload | null) => {
        courts = raw;
      })
      .catch(() => {
        courts = null;
      });
    return courtsLoad;
  };

  const courtsHtml = (members: number[]): string => {
    const payload = courts;
    if (!payload) return '';
    // -1 marks a commune the 2023 decision predates; it drops out rather than reading as a court.
    const here = [...new Set(members.map((i) => payload.courtOf[i] ?? -1).filter((c) => c >= 0))];
    if (here.length === 0) return '';
    const listed = here
      .map((c) => payload.courts[c] ?? '')
      .sort((a, b) => a.localeCompare(b, scenario.lang));
    return `
      <div class="courts">
        <h4>${strings.courtHeading}</h4>
        <p class="court-count">${
          here.length === 1 ? strings.courtOne : strings.courtMany.replace('{n}', String(here.length))
        }</p>
        <p class="muted court-list">${listed.join(' · ')}</p>
        ${here.length > 1 ? `<p class="muted">${strings.courtSplitNote}</p>` : ''}
        <p class="muted rep-source">${strings.courtSource}</p>
      </div>`;
  };

  /**
   * What a merger does to the political layer.
   *
   * Statutory on both sides — Art. 112 sets the council by population band, Art. 148 the
   * mayors and vice-mayors — so this is the one consequence of consolidation that needs no
   * counterfactual and no modelling. Bucharest is carved out rather than banded, because the
   * Consiliul General is fixed at 55 by the same article and applying the top band to it
   * would report 31 and be quietly wrong.
   */
  const representationHtml = (members: number[], region: number, totalPop: number): string => {
    if (!ready) return '';
    const bucharest = ready.attributes.county[region] === 'B';
    const row = (label: string, now: string, after: string): string =>
      `<div class="rep-row"><span>${label}</span><span>${now}</span><span>${after}</span></div>`;

    if (bucharest) {
      return `
        <div class="representation">
          <h4>${strings.repHeading}</h4>
          ${row(strings.repCouncillors, '—', formatNumber(BUCHAREST_COUNCIL, scenario.lang))}
          <p class="muted">${strings.repBucharest}</p>
          <p class="muted rep-source">${strings.repSource}</p>
        </div>`;
    }

    const before = representationBefore(
      members.map((i) => ({
        population: ready!.population[i]!,
        isCountyCapital: ready!.attributes.isCapital[i] === true,
      })),
    );
    const after = representationAfter(totalPop, ready.attributes.isCapital[region] === true);
    const band = danishBandFor(totalPop);
    const n = (value: number): string => formatNumber(value, scenario.lang);

    return `
      <div class="representation">
        <h4>${strings.repHeading}</h4>
        <div class="rep-row rep-head">
          <span></span><span>${strings.repNow}</span><span>${strings.repAfter}</span>
        </div>
        ${row(strings.repMayors, n(before.mayors), n(after.mayors))}
        ${row(strings.repViceMayors, n(before.viceMayors), n(after.viceMayors))}
        ${row(strings.repCouncillors, n(before.councillors), n(after.councillors))}
        <p class="muted">${strings.repDanish
          .replace('{min}', String(band.min))
          .replace('{max}', String(band.max))}</p>
        <p class="muted rep-source">${strings.repSource}</p>
        ${partyTableHtml(members, totalPop)}
      </div>`;
  };

  const renderDetail = (): void => {
    const panel = el<HTMLElement>('#detail');
    const body = el<HTMLElement>('#detail-body');
    const index = scenario.selected;
    if (index === null || !ready || !latest) {
      panel.hidden = true;
      return;
    }
    panel.hidden = false;

    const region = latest.regionOf[index]!;
    const members: number[] = [];
    for (let i = 0; i < latest.regionOf.length; i += 1) {
      if (latest.regionOf[i] === region) members.push(i);
    }
    members.sort((a, b) => ready!.population[b]! - ready!.population[a]!);

    const currentPin = scenario.pins.find((p) => p.uat === index)?.seat ?? null;
    const targets = pinTargets(index);
    const isForced = scenario.forced.includes(index);
    const orphan = isOrphanRegion[region] === 1;
    const sum = (series: Float32Array): number =>
      members.reduce((total, i) => total + series[i]!, 0);
    const totalPop = members.reduce((total, i) => total + ready!.population[i]!, 0);
    const totalAdmin = sum(ready.administrativeRon);
    const totalOperating = sum(ready.operatingRon);
    const totalDevelopment = sum(ready.developmentRon);
    const totalPersonnel = sum(ready.personnelRon);
    const totalAdminPersonnel = sum(ready.adminPersonnelRon);
    const totalIncome = sum(ready.incomeRon);
    const sharedFinance = localFinanceTotals(localFinance, members, ready.population);
    const sharedFinanceYears = localFinance ? localFinancePeriodLabel(localFinance) : '';
    const financeTrendRows: Array<[string, string]> = [];
    if (sharedFinance && sharedFinance.spendingGrowth2023To2025 !== null) {
      financeTrendRows.push([
        strings.spendingGrowth2023To2025,
        signed(sharedFinance.spendingGrowth2023To2025, (value) =>
          formatPercent(value, scenario.lang),
        ),
      ]);
    }
    if (sharedFinance && sharedFinance.ownRevenueShareChange2023To2025 !== null) {
      financeTrendRows.push([
        strings.ownRevenueShareChange2023To2025,
        signed(sharedFinance.ownRevenueShareChange2023To2025, (value) =>
          formatPercentagePoints(value, scenario.lang),
        ),
      ]);
    }
    const financeStressRows: Array<[string, string]> = [];
    if (sharedFinance && sharedFinance.revenuePerInhabitantRon !== null) {
      financeStressRows.push([
        strings.revenuePerInhabitant,
        `${formatNumber(sharedFinance.revenuePerInhabitantRon, scenario.lang)} RON`,
      ]);
    }
    if (sharedFinance && sharedFinance.spendingPerInhabitantRon !== null) {
      financeStressRows.push([
        strings.spendingPerInhabitant,
        `${formatNumber(sharedFinance.spendingPerInhabitantRon, scenario.lang)} RON`,
      ]);
    }
    if (sharedFinance && sharedFinance.personnelSpendingShare !== null) {
      financeStressRows.push([
        strings.personnelSpendingShare,
        formatPercent(sharedFinance.personnelSpendingShare, scenario.lang),
      ]);
    }
    const financeStressHtml = financeStressRows
      .map(
        ([label, value]) =>
          `<div class="finance-share"><span>${label}</span><span>${value}</span></div>`,
      )
      .join('');
    const financeTrendHtml =
      sharedFinanceYears && financeTrendRows.length > 0
        ? `<div class="finance-trends">
             <div class="finance-trend-title">${strings.fiscalTrend.replace(
               '{years}',
               sharedFinanceYears,
             )}</div>
             ${financeTrendRows
               .map(
                 ([label, value]) =>
                   `<div class="finance-share"><span>${label}</span><span>${value}</span></div>`,
               )
               .join('')}
           </div>`
        : '';

    // The saving is the administration of everyone except the centre: the centre keeps its
    // own town hall, and the rest is what a merger removes.
    const centreAdmin = ready.administrativeRon[region]!;
    const saved = Math.max(0, totalAdmin - centreAdmin);
    const balance = totalIncome - (totalOperating + totalDevelopment);

    const scale = Math.max(
      totalIncome,
      totalOperating + totalDevelopment,
      sharedFinance?.revenueRon ?? 0,
      1,
    );
    const bar = (label: string, value: number, colour: string): string => `
      <div class="row">
        <div class="top"><span>${label}</span><span>${formatMoney(value, scenario.lang)}</span></div>
        <div class="bar"><i style="width:${Math.min(100, (value / scale) * 100).toFixed(1)}%;background:${colour}"></i></div>
      </div>`;

    // The party table needs the votes; the rest of the panel does not wait for them.
    if (!localFinance) void loadLocalFinance().then(() => { if (scenario.selected === index) renderDetail(); });
    if (!healthAccess) void loadHealthAccess().then(() => { if (scenario.selected === index) renderDetail(); });
    if (!publicEnterpriseFootprint) void loadPublicEnterpriseFootprint().then(() => { if (scenario.selected === index) renderDetail(); });
    if (!votes) void loadVotes().then(() => { if (scenario.selected === index) renderDetail(); });
    if (!courts) void loadCourts().then(() => { if (scenario.selected === index) renderDetail(); });
    const sharedHealth = healthAccessTotals(healthAccess, members);
    const healthYears = healthAccess ? healthAccessPeriodLabel(healthAccess) : '';
    const healthHtml = sharedHealth
      ? `<div class="health-access">
           <h4>${strings.healthAccessHeading}</h4>
           <dl>
             <dt>${strings.healthAccessProviders}</dt>
             <dd>${formatNumber(sharedHealth.localProviderCount, scenario.lang)}</dd>
             <dt>${strings.healthAccessUats}</dt>
             <dd>${formatNumber(sharedHealth.uatsWithLocalProvider, scenario.lang)} / ${formatNumber(
               sharedHealth.uatsWithHealthData,
               scenario.lang,
             )}</dd>
             <dt>${strings.healthAccessBeds}</dt>
             <dd>${formatNumber(Math.round(sharedHealth.localClinicalBeds), scenario.lang)}</dd>
           </dl>
           ${
             sharedHealth.sectorRowsExcluded > 0
               ? `<p class="muted">${strings.healthAccessSectorRows.replace(
                   '{n}',
                   formatNumber(sharedHealth.sectorRowsExcluded, scenario.lang),
                 )}</p>`
               : ''
           }
           <p class="muted rep-source">${strings.healthAccessSource.replace(
             '{years}',
             healthYears,
           )}</p>
         </div>`
      : '';
    const enterpriseFootprint = publicEnterpriseFootprintTotals(publicEnterpriseFootprint, members);
    const enterpriseYears = publicEnterpriseFootprint
      ? publicEnterpriseFootprintPeriodLabel(publicEnterpriseFootprint)
      : '';
    const enterpriseFootprintHtml =
      enterpriseFootprint
      && (enterpriseFootprint.companyCount > 0 || enterpriseFootprint.subsidiesRon > 0)
        ? `<div class="public-enterprise-footprint">
             <h4>${strings.publicEnterpriseHeading}</h4>
             <dl>
               <dt>${strings.publicEnterpriseCompanies}</dt>
               <dd>${formatNumber(enterpriseFootprint.companyCount, scenario.lang)}</dd>
               <dt>${strings.publicEnterpriseLossMaking}</dt>
               <dd>${formatNumber(enterpriseFootprint.lossMakingCompanyCount, scenario.lang)}</dd>
               <dt>${strings.publicEnterpriseEmployees}</dt>
               <dd>${formatNumber(enterpriseFootprint.employeeCount, scenario.lang)}</dd>
               <dt>${strings.publicEnterpriseRevenue}</dt>
               <dd>${formatMoney(enterpriseFootprint.revenueRon, scenario.lang)}</dd>
               <dt>${strings.publicEnterpriseProfitLoss}</dt>
               <dd>${signed(enterpriseFootprint.profitLossRon, (value) =>
                 formatMoney(value, scenario.lang),
               )}</dd>
               <dt>${strings.publicEnterpriseDebt}</dt>
               <dd>${formatMoney(enterpriseFootprint.debtRon, scenario.lang)}</dd>
               <dt>${strings.publicEnterpriseSubsidies}</dt>
               <dd>${formatMoney(enterpriseFootprint.subsidiesRon, scenario.lang)}</dd>
             </dl>
             <p class="muted rep-source">${strings.publicEnterpriseSource.replace(
               '{years}',
               enterpriseYears,
             )}</p>
           </div>`
        : '';
    detailPanel.setTitle(unitName(ready, region));
    el<HTMLElement>('#detail-kicker').innerHTML =
      `${strings.region}${orphan ? ` · <span class="badge orphan">${strings.legendOrphan}</span>` : ''}`;
    body.innerHTML = `
      <h3>${unitName(ready, region)}</h3>
      ${
        budgetUrl(region)
          ? `<p class="budget-row">${budgetLink(region, strings.budgetLink)}</p>`
          : ''
      }
      <dl>
        <dt>${strings.county}</dt><dd>${ready.attributes.county[region]}</dd>
        <dt>${strings.members}</dt><dd>${formatNumber(members.length, scenario.lang)}</dd>
        <dt>${strings.population}</dt><dd>${formatNumber(totalPop, scenario.lang)}</dd>
        <dt>${strings.adminCost}</dt><dd>${formatMoney(totalAdmin, scenario.lang)}</dd>
        <dt>${strings.operatingCost}</dt><dd>${formatMoney(totalOperating, scenario.lang)}</dd>
        <dt>${strings.costPerResident}</dt><dd>${
          totalPop > 0 ? formatNumber(totalAdmin / totalPop, scenario.lang) : '—'
        } RON</dd>
      </dl>
      <div class="fiscal">
        <h4>${strings.fiscalHeading}</h4>
        ${bar(strings.ownIncome, totalIncome, '#43b07a')}
        ${
          sharedFinance
            ? `${bar(strings.ownRevenue, sharedFinance.ownRevenueRon, '#2aa6a1')}
              <div class="finance-share">
                <span>${strings.ownRevenueShare}</span>
                <span>${
                  sharedFinance.ownRevenueShare === null
                    ? '—'
                    : formatPercent(sharedFinance.ownRevenueShare, scenario.lang)
                }</span>
              </div>
              ${financeStressHtml}
              ${financeTrendHtml}
              <p class="muted rep-source">${strings.localFinanceSource.replace(
                '{year}',
                sharedFinanceYears,
              )}</p>`
            : ''
        }
        ${bar(strings.adminPersonnel, totalAdminPersonnel, '#e0b13a')}
        ${bar(strings.totalPersonnel, totalPersonnel, '#e08a34')}
        ${bar(strings.operatingCost, totalOperating, '#d4544c')}
        ${bar(strings.developmentCost, totalDevelopment, '#3f8fd4')}
        <div class="balance ${balance >= 0 ? 'surplus' : 'deficit'}">
          <span>${balance >= 0 ? strings.balanceSurplus : strings.balanceDeficit}</span>
          <span>${formatMoney(Math.abs(balance), scenario.lang)}</span>
        </div>
      </div>

      ${representationHtml(members, region, totalPop)}

      ${courtsHtml(members)}

      ${enterpriseFootprintHtml}

      ${healthHtml}

      <div class="savings">
        <h4>${strings.savingsHeading}</h4>
        <dl>
          <dt>${strings.totalOperatingOfMembers}</dt><dd>${formatMoney(totalAdmin, scenario.lang)}</dd>
          <dt>${strings.centreKeeps}</dt><dd>${formatMoney(centreAdmin, scenario.lang)}</dd>
        </dl>
        <div class="headline">
          <div class="value">${formatMoney(saved, scenario.lang)}</div>
          <div class="label">${strings.savedPerYear}</div>
        </div>
      </div>

      <div class="why">
        <h4>${strings.whyTitle}</h4>
        <p>${explain(region)}</p>
        ${
          index !== region
            ? `<p><strong>${ready.attributes.name[index]}:</strong> ${explain(index)}</p>`
            : ''
        }
        <p class="county-rule">${strings.whyCountyRule.replace('{county}', ready.attributes.county[region]!)}</p>
      </div>
      ${latest.splitUnits.includes(region) ? `<p class="pin-warning">${strings.pinSplit}</p>` : ''}
      ${
        // Offered on the commune in view, not on the unit it belongs to: forcing a centre is
        // a claim about this locality, and on a unit's own seat it would be a no-op the model
        // reports back as "already a centre".
        isForced || latest.forcedApplied.includes(index) || index !== region
          ? `<div class="force-control">
               <button class="ghost small wide civic-button" data-force="${index}">${
                 isForced ? strings.forceUndo : strings.forceMake
               }</button>
               <p class="help">${strings.forceNote}</p>
             </div>`
          : ''
      }
      <div class="pin-control civic-field">
        <label for="pin-select">${strings.pinMoveTo}</label>
        <select id="pin-select" class="civic-select civic-select--native">
          <option value="">${strings.pinKeepRules}</option>
          ${
            // The assigned region is not a new target, but must still display a saved pin.
            currentPin === region && !targets.includes(currentPin)
              ? `<option value="${currentPin}" selected disabled>${unitName(ready, currentPin)}</option>`
              : ''
          }
          ${targets
            .map(
              (seat) =>
                `<option value="${seat}"${
                  currentPin === seat ? ' selected' : ''
                }>${unitName(ready!, seat)}</option>`,
            )
            .join('')}
        </select>
      </div>
      <ul class="members">
        ${members
          .map(
            (i) =>
              `<li class="${i === region ? 'is-centre' : ''}${
                 scenario.pins.some((p) => p.uat === i) ? ' is-pinned' : ''
               }">
                 <span>${budgetLink(i, ready!.attributes.name[i]!)}${
                   scenario.pins.some((p) => p.uat === i)
                     ? ` <em class="pin-badge">${strings.pinBadge}</em>`
                     : ''
                 }</span>
                 <span>${formatNumber(ready!.population[i]!, scenario.lang)}</span>
               </li>`,
          )
          .join('')}
      </ul>`;

    body.querySelector<HTMLButtonElement>('[data-force]')?.addEventListener('click', () => {
      setForced(index, !isForced);
    });

    body.querySelector<HTMLSelectElement>('#pin-select')?.addEventListener('change', (event) => {
      const value = (event.target as HTMLSelectElement).value;
      setPin(index, value === '' ? null : Number(value));
    });
  };

  // --- recompute loop ----------------------------------------------------------------

  const schedule = (): void => {
    writeHash(scenario);
    if (pending) return;
    pending = true;
    // Animation frames, not timers: the recompute rate follows the display, and a drag
    // never queues more work than the screen can show.
    requestAnimationFrame(() => {
      pending = false;
      token += 1;
      worker.postMessage({
        type: 'compute',
        params: scenario.params,
        pins: scenario.pins,
        forced: scenario.forced,
        token,
      });
    });
  };

  worker.onmessage = (event: MessageEvent<Outgoing>) => {
    const message = event.data;

    if (message.type === 'error') {
      el('#loading').innerHTML = `<span>${message.message}</span>`;
      return;
    }

    if (message.type === 'ready') {
      ready = message;
      costBreaks = message.adminCostBreaks;
      costPerResident = new Float32Array(message.uatCount);
      for (let i = 0; i < message.uatCount; i += 1) {
        const pop = message.population[i]!;
        costPerResident[i] = pop > 0 ? message.administrativeRon[i]! / pop : 0;
      }
      renderModes();
      schedule();
      return;
    }

    if (message.type === 'seat-distances') {
      const slot = hovercard.querySelector<HTMLElement>('.seat-distances');
      if (!slot || !ready || slot.dataset.uat !== String(message.uat)) return;
      slot.innerHTML =
        `<div class="sd-title">${strings.hoverSeatDistances}</div>` +
        message.seats
          .map(
            (row) =>
              `<div class="line${row.own ? ' own' : ''}">` +
              `<span>${unitName(ready!, row.seat)}</span>` +
              `<span>${(row.metres / 1000).toFixed(1)} km</span></div>`,
          )
          .join('');
      return;
    }

    if (message.type === 'explain-result') {
      for (const blocker of message.blockers) {
        const note = el<HTMLElement>('#audit').querySelector<HTMLElement>(
          `li[data-seat="${blocker.seat}"] .audit-why`,
        );
        if (!note) continue;
        note.textContent =
          blocker.kind === 'no-county-neighbour'
            ? strings.auditWhyCounty
            : blocker.kind === 'capital-only'
              ? strings.auditWhyCapitalOnly
              : blocker.kind === 'county-minimum'
                ? strings.auditWhyCountyMinimum.replace('{units}', String(blocker.units))
                : strings.auditWhyCap
                  .replace('{km}', (blocker.metres / 1000).toFixed(1))
                  .replace('{cap}', String(Math.round(scenario.params.maxRoadM / 1000)));
      }
      return;
    }

    if (message.type === 'unit-chains-result') {
      if (!ready || chainFor !== message.seat) return;
      const county = ready.attributes.county[message.seat] ?? '';
      const shard = shards.get(county);
      const siruta = ready.attributes.siruta;
      void mapHandle.seatPoints().then((seats) => {
        if (chainFor !== message.seat) return;
        const features: ChainFeature[] = [];
        for (const leg of message.legs) {
          const routed = shard?.get(edgeKey(siruta[leg.from] ?? '', siruta[leg.to] ?? '')) ?? null;
          if (routed && routed.length > 1) {
            features.push({
              type: 'Feature',
              properties: { kind: 'road' },
              geometry: { type: 'LineString', coordinates: routed },
            });
            continue;
          }
          const a = seats.get(leg.from);
          const b = seats.get(leg.to);
          if (!a || !b) continue;
          features.push({
            type: 'Feature',
            properties: { kind: 'schematic' },
            geometry: { type: 'LineString', coordinates: [a, b] },
          });
        }
        mapHandle.setChain(features);
      });
      return;
    }

    if (message.type === 'chain-result') {
      drawChain(message.uat, message.legs);
      return;
    }

    if (message.type === 'candidacy-result') {
      candidacyOf = message.candidacyOf;
      renderCandidates();
      return;
    }

    // Discard anything a later drag has already superseded.
    if (message.token !== token) return;

    latest = message;
    isOrphanRegion = new Uint8Array(message.regionOf.length);
    // A region is orphan-tier when its centre is not a seed: gravitational regions are
    // always centred on a seed, clusters never are.
    for (let i = 0; i < message.regionOf.length; i += 1) {
      const region = message.regionOf[i]!;
      if (message.tierOf[region] === -1) isOrphanRegion[region] = 1;
    }

    paint();
    renderSummary();
    renderDetail();
    renderHoverOptions();
    renderBadge();
    renderVersions();
    renderForced();
    renderPins();
    // Stale the instant the parameters change, so it is dropped and re-asked rather than
    // left on screen describing a selection that is no longer the one on the map.
    candidacyOf = null;
    renderCandidates();
    requestCandidacy();
    renderAudit();
    el<HTMLElement>('#loading').hidden = true;
  };

  // --- interaction -------------------------------------------------------------------

  /**
   * Names on the map, once zoomed in far enough to have room for them.
   *
   * Below the threshold there are 3,186 communes across the country and any labelling is an
   * unreadable pile; above it there are a few dozen on screen. In "today" every commune is
   * named, otherwise only the seats — the name of a unit belongs at its centre, and naming
   * every absorbed commune would say nothing about which unit it joined.
   */
  const LABEL_ZOOM = 8.2;
  const LABEL_LIMIT = 90;
  const labels = el<HTMLElement>('#labels');

  const renderLabels = (): void => {
    if (!ready || !latest || mapHandle.zoom() < LABEL_ZOOM) {
      labels.replaceChildren();
      return;
    }
    const showingToday = scenario.mode === 'current';
    const accept = (index: number): boolean =>
      showingToday || latest!.regionOf[index] === index;

    const fragment = document.createDocumentFragment();
    for (const point of mapHandle.visibleSeats(accept, LABEL_LIMIT)) {
      const node = document.createElement('span');
      node.textContent = showingToday
        ? ready.attributes.name[point.index]!
        : unitName(ready, point.index);
      if (!showingToday) node.className = 'centre';
      node.style.left = `${point.x}px`;
      node.style.top = `${point.y}px`;
      fragment.append(node);
    }
    labels.replaceChildren(fragment);
  };

  mapHandle.onViewChange(renderLabels);

  // Hover: the commune as it is today, and the unit it would belong to. Both at once,
  // because "what happens to my commune" is the question the map is actually asked, and
  // answering it should not require a click.
  const hovercard = el<HTMLElement>('#hovercard');
  mapHandle.onHover((index, x, y) => {
    // On a touchscreen the card would strand: there is no leave event to dismiss it. The
    // county outline still follows, because that is drawn on the map and not in a popup.
    if (coarsePointer.matches) {
      hovercard.hidden = true;
      applyHover(index);
      return;
    }
    if (index === null || !ready || !latest) {
      hovercard.hidden = true;
      // Fall back to the selected commune, so the outline does not flicker off every time the
      // pointer crosses a gap between two polygons.
      applyHover(scenario.selected);
      return;
    }
    applyHover(index);
    const unit = latest.regionOf[index]!;
    let unitPop = 0;
    let unitMembers = 0;
    let unitArea = 0;
    for (let i = 0; i < latest.regionOf.length; i += 1) {
      if (latest.regionOf[i] === unit) {
        unitPop += ready.population[i]!;
        unitArea += ready.areaKm2[i]!;
        unitMembers += 1;
      }
    }
    const unchanged = unitMembers === 1;
    hovercard.innerHTML = `
      <div class="name">${ready.attributes.name[index]}</div>
      <div class="county">${countyName(ready, index)}</div>
      <div class="line"><span>${strings.population}</span><span>${formatNumber(
        ready.population[index]!,
        scenario.lang,
      )}</span></div>
      <div class="line"><span>${strings.area}</span><span>${formatNumber(
        Math.round(ready.areaKm2[index]!),
        scenario.lang,
      )} km²</span></div>
      <div class="after">
        <div class="line">
          <span>${unchanged ? strings.legendUnchanged : strings.hoverProposed}</span>
          <span>${formatNumber(unitPop, scenario.lang)}</span>
        </div>
        <div class="line">
          <span>${strings.area}</span>
          <span>${formatNumber(Math.round(unitArea), scenario.lang)} km²</span>
        </div>
        ${
          unchanged
            ? ''
            : `<div class="unit">${unitName(ready, unit)} · ${formatNumber(
                unitMembers,
                scenario.lang,
              )} ${strings.hoverCommunes}</div>`
        }
      </div>
      <div class="seat-distances" data-uat="${index}"></div>
      <div class="chain" data-uat="${index}"></div>`;
    // Filled in when the worker answers. This is the question the map itself cannot show:
    // why is this commune under Topolog rather than Isaccea?
    worker.postMessage({ type: 'seatDistances', uat: index });
    hovercard.hidden = false;
    // Kept inside the viewport: near the right or bottom edge the card flips to the other
    // side of the cursor rather than being clipped.
    const box = hovercard.getBoundingClientRect();
    const left = x + 16 + box.width > window.innerWidth ? x - box.width - 16 : x + 16;
    const top = y + 16 + box.height > window.innerHeight ? y - box.height - 16 : y + 16;
    hovercard.style.left = `${Math.max(8, left)}px`;
    hovercard.style.top = `${Math.max(8, top)}px`;
  });

  mapHandle.onSelect((index) => {
    scenario.selected = index;
    mapHandle.setCountyFocus(index === null ? null : (ready?.attributes.county[index] ?? null));
    mapHandle.setSelected(index);
    writeHash(scenario);
    renderDetail();
    // On a phone the panel is a collapsed sheet, so selecting a commune has to open it —
    // otherwise a tap appears to do nothing but move the outline.
    if (index !== null && detailPanel.isSheet()) detailPanel.setOpen(true);
  });

  el('#detail-close').addEventListener('click', () => {
    scenario.selected = null;
    mapHandle.setSelected(null);
    mapHandle.setCountyFocus(null);
    detailPanel.setOpen(false);
    writeHash(scenario);
    renderDetail();
  });

  for (const button of document.querySelectorAll<HTMLButtonElement>('.lang button')) {
    button.addEventListener('click', () => {
      scenario.lang = button.dataset.lang as Lang;
      writeHash(scenario);
      applyStaticText();
    });
  }

  el('#reset-btn').addEventListener('click', () => {
    scenario.params = { ...DEFAULT_PARAMS };
    // Reset means the default scenario, and a scenario with overrides in it is not that.
    scenario.pins = [];
    renderSliders();
    schedule();
  });

  el('#copy-link').addEventListener('click', async () => {
    await navigator.clipboard.writeText(location.href);
    const button = el<HTMLButtonElement>('#copy-link');
    button.textContent = strings.linkCopied;
    setTimeout(() => (button.textContent = strings.copyLink), 1500);
  });

  const modal = el<HTMLDialogElement>('#methodology');
  el('#methodology-btn').addEventListener('click', () => {
    modal.innerHTML = methodologyHtml(strings);
    modal.querySelector('button')!.addEventListener('click', () => modal.close());
    modal.showModal();
  });

  applyStaticText();
  for (const [key, visible] of Object.entries(overlayState) as [Overlay, boolean][]) {
    if (visible) {
      void mapHandle.setOverlay(key, true).then((shown) => {
        if (!shown) {
          overlayState[key] = false;
          renderLayers();
        }
      });
    }
  }
  mapHandle.setSelected(scenario.selected);
  worker.postMessage({ type: 'init', baseUrl: DATA_BASE });
}

function methodologyHtml(s: Strings): string {
  const ro = document.documentElement.lang === 'ro';
  return `
    <h2>${s.methodology}</h2>
    <p>${
      ro
        ? 'Modelul este determinist: aceleași setări produc întotdeauna exact aceeași hartă. Nu folosește optimizare și nici aleatoriu.'
        : 'The model is deterministic: the same settings always produce exactly the same map. It uses no optimization and no randomness.'
    }</p>
    <h3>${ro ? 'Cum funcționează' : 'How it works'}</h3>
    <p>${
      ro
        ? 'Reședințele de județ și localitățile peste pragul de populație devin centre. Suprafața fiecărui centru este extinsă cu o rază care depinde de tipul lui. Comunele vecine care intră suficient în această rază — și care sunt legate printr-un drum ce traversează granița comună — sunt absorbite, în valuri concentrice. Regiunile nu traversează niciodată limitele de județ.'
        : 'County capitals and localities above the population threshold become centres. Each centre’s territory is buffered outward by a radius that depends on its tier. Neighbouring communes that fall far enough inside that radius — and that are linked by a road crossing the shared border — are absorbed, in concentric waves. Regions never cross county lines.'
    }</p>
    <h3>${ro ? 'Despre economie' : 'About the saving'}</h3>
    <p>${s.savingsHelp}</p>
    <h3>${ro ? 'Limitări' : 'Limitations'}</h3>
    <p>${
      ro
        ? 'Raza este o distanță în linie dreaptă, nu pe drum. Drumurile sunt folosite doar pentru a verifica dacă o graniță este traversată. Datele despre drumuri provin din OpenStreetMap și clasificarea lor nu este întotdeauna exactă — în Delta Dunării, de exemplu, unele drumuri de pământ apar ca drumuri obișnuite.'
        : 'The radius is a straight-line distance, not a road distance. Roads are used only to test whether a border is crossed. Road data comes from OpenStreetMap and its classification is not always exact — in the Danube Delta, for instance, some sand tracks are tagged as ordinary roads.'
    }</p>
    <p><a href="${import.meta.env.BASE_URL}METHODOLOGY.md" target="_blank" rel="noopener">${
      ro ? 'Metodologia completă, inclusiv sursele și deciziile contestabile' : 'Full methodology, including sources and disputable decisions'
    }</a></p>
    <button class="ghost civic-button">${s.close}</button>`;
}

void boot();

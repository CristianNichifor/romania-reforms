export interface HealthAccessPayload {
  id: string;
  sourceViewId: string;
  sourceViewSha256: string;
  periodStart: string;
  periodEnd: string;
  siruta: string[];
  hasLocalProvider: Array<boolean | null>;
  localProviderCount: Array<number | null>;
  localClinicalBedProviders: Array<number | null>;
  localClinicalBeds: Array<number | null>;
  countyEligibleProviderCount: number[];
  countyBlockedProviderCount: number[];
  sectorRowExcluded: boolean[];
  summary?: {
    uats: number;
    sourceUats: number;
    uatsWithHealthData: number;
    uatsWithLocalProvider: number;
    localProviderCount: number;
    eligibleProviders: number;
    blockedProviders: number;
    namedExclusions: number;
    sectorRowsExcluded: number;
    sourceExcludedSectorRows: number;
  };
}

export interface HealthAccessTotals {
  localProviderCount: number;
  uatsWithLocalProvider: number;
  uatsWithHealthData: number;
  sectorRowsExcluded: number;
  localClinicalBedProviders: number;
  localClinicalBeds: number;
}

const seriesAligned = (series: readonly unknown[], uatCount: number): boolean =>
  series.length === uatCount;

export function healthAccessPayloadAligned(
  payload: HealthAccessPayload,
  expectedSiruta: readonly string[],
): boolean {
  const uatCount = expectedSiruta.length;
  return (
    payload.siruta.length === uatCount
    && seriesAligned(payload.hasLocalProvider, uatCount)
    && seriesAligned(payload.localProviderCount, uatCount)
    && seriesAligned(payload.localClinicalBedProviders, uatCount)
    && seriesAligned(payload.localClinicalBeds, uatCount)
    && seriesAligned(payload.countyEligibleProviderCount, uatCount)
    && seriesAligned(payload.countyBlockedProviderCount, uatCount)
    && seriesAligned(payload.sectorRowExcluded, uatCount)
    && payload.siruta.every((siruta, index) => siruta === expectedSiruta[index])
  );
}

const nullableNumberAt = (
  series: ReadonlyArray<number | null>,
  index: number,
): number | null => {
  const value = series[index];
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
};

export function healthAccessPeriodLabel(payload: HealthAccessPayload): string {
  return payload.periodStart === payload.periodEnd
    ? payload.periodStart
    : `${payload.periodStart}-${payload.periodEnd}`;
}

export function healthAccessTotals(
  payload: HealthAccessPayload | null,
  members: readonly number[],
): HealthAccessTotals | null {
  if (!payload) return null;

  let localProviderCount = 0;
  let uatsWithLocalProvider = 0;
  let uatsWithHealthData = 0;
  let sectorRowsExcluded = 0;
  let localClinicalBedProviders = 0;
  let localClinicalBeds = 0;

  for (const index of members) {
    const providers = nullableNumberAt(payload.localProviderCount, index);
    if (providers === null) {
      if (payload.sectorRowExcluded[index] === true) sectorRowsExcluded += 1;
      continue;
    }

    uatsWithHealthData += 1;
    localProviderCount += providers;
    if (payload.hasLocalProvider[index] === true) uatsWithLocalProvider += 1;
    localClinicalBedProviders += nullableNumberAt(payload.localClinicalBedProviders, index) ?? 0;
    localClinicalBeds += nullableNumberAt(payload.localClinicalBeds, index) ?? 0;
  }

  return {
    localProviderCount,
    uatsWithLocalProvider,
    uatsWithHealthData,
    sectorRowsExcluded,
    localClinicalBedProviders,
    localClinicalBeds,
  };
}

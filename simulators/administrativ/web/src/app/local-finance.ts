export interface LocalFinancePayload {
  id: string;
  sourceMartId: string;
  sourceMartSha256: string;
  period: string;
  sourceYears?: number[];
  siruta: string[];
  revenueRon: number[];
  ownRevenueRon: number[];
  ownRevenueShare: Array<number | null>;
  spendingRon2023?: Array<number | null>;
  spendingRon2025?: Array<number | null>;
  revenueRon2023?: Array<number | null>;
  revenueRon2025?: Array<number | null>;
  ownRevenueRon2023?: Array<number | null>;
  ownRevenueRon2025?: Array<number | null>;
  spendingGrowth2023To2025?: Array<number | null>;
  ownRevenueShareChange2023To2025?: Array<number | null>;
}

export interface LocalFinanceTotals {
  revenueRon: number;
  ownRevenueRon: number;
  ownRevenueShare: number | null;
  sourceYears: number[];
  spendingGrowth2023To2025: number | null;
  ownRevenueShareChange2023To2025: number | null;
}

const optionalSeriesAligned = (
  series: readonly unknown[] | null | undefined,
  uatCount: number,
): boolean => series == null || series.length === uatCount;

export function localFinancePayloadAligned(
  payload: LocalFinancePayload,
  expectedSiruta: readonly string[],
): boolean {
  const uatCount = expectedSiruta.length;
  return (
    payload.siruta.length === uatCount
    && payload.revenueRon.length === uatCount
    && payload.ownRevenueRon.length === uatCount
    && payload.ownRevenueShare.length === uatCount
    && optionalSeriesAligned(payload.spendingRon2023, uatCount)
    && optionalSeriesAligned(payload.spendingRon2025, uatCount)
    && optionalSeriesAligned(payload.revenueRon2023, uatCount)
    && optionalSeriesAligned(payload.revenueRon2025, uatCount)
    && optionalSeriesAligned(payload.ownRevenueRon2023, uatCount)
    && optionalSeriesAligned(payload.ownRevenueRon2025, uatCount)
    && optionalSeriesAligned(payload.spendingGrowth2023To2025, uatCount)
    && optionalSeriesAligned(payload.ownRevenueShareChange2023To2025, uatCount)
    && payload.siruta.every((siruta, index) => siruta === expectedSiruta[index])
  );
}

const valueAt = (series: readonly number[], index: number): number => {
  const value = series[index] ?? 0;
  return Number.isFinite(value) ? value : 0;
};

const nullableValueAt = (
  series: ReadonlyArray<number | null> | undefined,
  index: number,
): number | null => {
  const value = series?.[index];
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
};

const averageAt = (
  series: ReadonlyArray<number | null> | undefined,
  members: readonly number[],
): number | null => {
  let total = 0;
  let count = 0;
  for (const index of members) {
    const value = nullableValueAt(series, index);
    if (value === null) continue;
    total += value;
    count += 1;
  }
  return count > 0 ? total / count : null;
};

const ratioChangeFromSums = (
  startSeries: ReadonlyArray<number | null> | undefined,
  endSeries: ReadonlyArray<number | null> | undefined,
  members: readonly number[],
): number | null => {
  if (!startSeries || !endSeries) return null;

  let startTotal = 0;
  let endTotal = 0;
  for (const index of members) {
    const start = nullableValueAt(startSeries, index);
    const end = nullableValueAt(endSeries, index);
    if (start === null || end === null || start <= 0) continue;
    startTotal += start;
    endTotal += end;
  }
  return startTotal > 0 ? (endTotal - startTotal) / startTotal : null;
};

const ownRevenueShareChangeFromSums = (
  revenueStartSeries: ReadonlyArray<number | null> | undefined,
  ownRevenueStartSeries: ReadonlyArray<number | null> | undefined,
  revenueEndSeries: ReadonlyArray<number | null> | undefined,
  ownRevenueEndSeries: ReadonlyArray<number | null> | undefined,
  members: readonly number[],
): number | null => {
  if (
    !revenueStartSeries
    || !ownRevenueStartSeries
    || !revenueEndSeries
    || !ownRevenueEndSeries
  ) {
    return null;
  }

  let revenueStartTotal = 0;
  let ownRevenueStartTotal = 0;
  let revenueEndTotal = 0;
  let ownRevenueEndTotal = 0;
  for (const index of members) {
    const revenueStart = nullableValueAt(revenueStartSeries, index);
    const ownRevenueStart = nullableValueAt(ownRevenueStartSeries, index);
    const revenueEnd = nullableValueAt(revenueEndSeries, index);
    const ownRevenueEnd = nullableValueAt(ownRevenueEndSeries, index);
    if (
      revenueStart === null
      || ownRevenueStart === null
      || revenueEnd === null
      || ownRevenueEnd === null
      || revenueStart <= 0
      || revenueEnd <= 0
    ) {
      continue;
    }

    revenueStartTotal += revenueStart;
    ownRevenueStartTotal += ownRevenueStart;
    revenueEndTotal += revenueEnd;
    ownRevenueEndTotal += ownRevenueEnd;
  }

  if (revenueStartTotal <= 0 || revenueEndTotal <= 0) return null;
  return ownRevenueEndTotal / revenueEndTotal - ownRevenueStartTotal / revenueStartTotal;
};

export function localFinancePeriodLabel(payload: LocalFinancePayload): string {
  const years = [...(payload.sourceYears ?? [])]
    .filter((year) => Number.isInteger(year))
    .sort((a, b) => a - b);
  if (years.length === 0) return payload.period;
  return years.length === 1 ? String(years[0]!) : `${years[0]!}-${years[years.length - 1]!}`;
}

export function localFinanceTotals(
  payload: LocalFinancePayload | null,
  members: readonly number[],
): LocalFinanceTotals | null {
  if (!payload) return null;

  let revenueRon = 0;
  let ownRevenueRon = 0;
  for (const index of members) {
    revenueRon += valueAt(payload.revenueRon, index);
    ownRevenueRon += valueAt(payload.ownRevenueRon, index);
  }

  const hasSpendingBases = Boolean(payload.spendingRon2023 && payload.spendingRon2025);
  const spendingGrowth2023To2025 = hasSpendingBases
    ? ratioChangeFromSums(payload.spendingRon2023, payload.spendingRon2025, members)
    : averageAt(payload.spendingGrowth2023To2025, members);
  const hasOwnRevenueBases = Boolean(
    payload.revenueRon2023
      && payload.ownRevenueRon2023
      && payload.revenueRon2025
      && payload.ownRevenueRon2025,
  );
  const ownRevenueShareChange2023To2025 = hasOwnRevenueBases
    ? ownRevenueShareChangeFromSums(
        payload.revenueRon2023,
        payload.ownRevenueRon2023,
        payload.revenueRon2025,
        payload.ownRevenueRon2025,
        members,
      )
    : averageAt(payload.ownRevenueShareChange2023To2025, members);

  return {
    revenueRon,
    ownRevenueRon,
    ownRevenueShare: revenueRon > 0 ? ownRevenueRon / revenueRon : null,
    sourceYears: [...(payload.sourceYears ?? [])],
    spendingGrowth2023To2025,
    ownRevenueShareChange2023To2025,
  };
}

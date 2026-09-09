export interface LocalFinancePayload {
  id: string;
  sourceMartId: string;
  sourceMartSha256: string;
  period: string;
  siruta: string[];
  revenueRon: number[];
  ownRevenueRon: number[];
  ownRevenueShare: Array<number | null>;
}

export interface LocalFinanceTotals {
  revenueRon: number;
  ownRevenueRon: number;
  ownRevenueShare: number | null;
}

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
    && payload.siruta.every((siruta, index) => siruta === expectedSiruta[index])
  );
}

const valueAt = (series: readonly number[], index: number): number => {
  const value = series[index] ?? 0;
  return Number.isFinite(value) ? value : 0;
};

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

  return {
    revenueRon,
    ownRevenueRon,
    ownRevenueShare: revenueRon > 0 ? ownRevenueRon / revenueRon : null,
  };
}

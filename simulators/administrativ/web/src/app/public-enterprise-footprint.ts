export interface PublicEnterpriseFootprintPayload {
  id: string;
  sourceViewId: string;
  sourceViewSha256: string;
  periodStart: string;
  periodEnd: string;
  publisher: string;
  license: string;
  attribution: string;
  siruta: string[];
  authorityCount: number[];
  companyCount: number[];
  activeCompanyCount: number[];
  companiesWithFinancials: number[];
  lossMakingCompanyCount: number[];
  employeeCount: number[];
  revenueRon: number[];
  profitLossRon: number[];
  debtRon: number[];
  subsidiesRon: number[];
  summary?: {
    uats: number;
    sourceUats: number;
    matchedSourceUats: number;
    excludedSourceUats: number;
    companyCount: number;
    activeCompanyCount: number;
    lossMakingCompanyCount: number;
    companiesWithFinancials: number;
    employeeCount: number;
    revenueRon: number;
    profitLossRon: number;
    debtRon: number;
    subsidiesRon: number;
  };
}

export interface PublicEnterpriseFootprintTotals {
  authorityCount: number;
  companyCount: number;
  activeCompanyCount: number;
  companiesWithFinancials: number;
  lossMakingCompanyCount: number;
  employeeCount: number;
  revenueRon: number;
  profitLossRon: number;
  debtRon: number;
  subsidiesRon: number;
}

const seriesAligned = (series: readonly unknown[], uatCount: number): boolean =>
  series.length === uatCount;

export function publicEnterpriseFootprintPayloadAligned(
  payload: PublicEnterpriseFootprintPayload,
  expectedSiruta: readonly string[],
): boolean {
  const uatCount = expectedSiruta.length;
  return (
    payload.siruta.length === uatCount
    && seriesAligned(payload.authorityCount, uatCount)
    && seriesAligned(payload.companyCount, uatCount)
    && seriesAligned(payload.activeCompanyCount, uatCount)
    && seriesAligned(payload.companiesWithFinancials, uatCount)
    && seriesAligned(payload.lossMakingCompanyCount, uatCount)
    && seriesAligned(payload.employeeCount, uatCount)
    && seriesAligned(payload.revenueRon, uatCount)
    && seriesAligned(payload.profitLossRon, uatCount)
    && seriesAligned(payload.debtRon, uatCount)
    && seriesAligned(payload.subsidiesRon, uatCount)
    && payload.siruta.every((siruta, index) => siruta === expectedSiruta[index])
  );
}

const valueAt = (series: readonly number[], index: number): number => {
  const value = series[index] ?? 0;
  return Number.isFinite(value) ? value : 0;
};

export function publicEnterpriseFootprintPeriodLabel(
  payload: PublicEnterpriseFootprintPayload,
): string {
  return payload.periodStart === payload.periodEnd
    ? payload.periodStart
    : `${payload.periodStart}-${payload.periodEnd}`;
}

export function publicEnterpriseFootprintTotals(
  payload: PublicEnterpriseFootprintPayload | null,
  members: readonly number[],
): PublicEnterpriseFootprintTotals | null {
  if (!payload) return null;
  const totals: PublicEnterpriseFootprintTotals = {
    authorityCount: 0,
    companyCount: 0,
    activeCompanyCount: 0,
    companiesWithFinancials: 0,
    lossMakingCompanyCount: 0,
    employeeCount: 0,
    revenueRon: 0,
    profitLossRon: 0,
    debtRon: 0,
    subsidiesRon: 0,
  };

  for (const index of members) {
    totals.authorityCount += valueAt(payload.authorityCount, index);
    totals.companyCount += valueAt(payload.companyCount, index);
    totals.activeCompanyCount += valueAt(payload.activeCompanyCount, index);
    totals.companiesWithFinancials += valueAt(payload.companiesWithFinancials, index);
    totals.lossMakingCompanyCount += valueAt(payload.lossMakingCompanyCount, index);
    totals.employeeCount += valueAt(payload.employeeCount, index);
    totals.revenueRon += valueAt(payload.revenueRon, index);
    totals.profitLossRon += valueAt(payload.profitLossRon, index);
    totals.debtRon += valueAt(payload.debtRon, index);
    totals.subsidiesRon += valueAt(payload.subsidiesRon, index);
  }

  return totals;
}

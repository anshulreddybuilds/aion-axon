export const DEFAULT_SUPERVISION_THRESHOLD = 40;

export function autonomyLedgerRow(
  capability,
  threshold = DEFAULT_SUPERVISION_THRESHOLD
) {
  const pct =
    capability?.effective_autonomy_pct ??
    capability?.autonomy_pct ??
    null;

  const numericPct = pct == null ? null : Number(pct);
  const validPct = Number.isFinite(numericPct) ? numericPct : null;

  return {
    name: capability?.name ?? "",
    pct: validPct,
    belowThreshold:
      validPct != null && validPct < Number(threshold),
    widthPct:
      validPct == null
        ? null
        : Math.min(100, Math.max(0, validPct)),
  };
}

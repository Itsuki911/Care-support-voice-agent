export function formatUsd(amount: number | null) {
  return amount === null ? "N/A" : `$${amount.toFixed(4)}`;
}

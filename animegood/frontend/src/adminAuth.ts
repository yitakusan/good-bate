const STORAGE_KEY = "animegood:admin_token";

export function loadAdminToken(): string {
  try {
    return localStorage.getItem(STORAGE_KEY) ?? "";
  } catch {
    return "";
  }
}

export function saveAdminToken(token: string) {
  try {
    if (token.trim()) {
      localStorage.setItem(STORAGE_KEY, token.trim());
    } else {
      localStorage.removeItem(STORAGE_KEY);
    }
  } catch {
    // ignore
  }
}

export function adminHeaders(token: string): HeadersInit {
  const trimmed = token.trim();
  if (!trimmed) {
    return {};
  }
  return { "X-Admin-Token": trimmed };
}

export function formatCnyEstimate(priceJpy: number | null, cnyPer100Jpy: number | null): string | null {
  if (priceJpy === null || cnyPer100Jpy === null || priceJpy <= 0) {
    return null;
  }
  const cny = (priceJpy * cnyPer100Jpy) / 100;
  return `约 ¥${cny.toFixed(2)}`;
}

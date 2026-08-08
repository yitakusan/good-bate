const GENERAL_DELAY_MS = 350;
const HMV_OR_BIC_DELAY_MS = 1_500;
const FAILURE_EXTRA_DELAY_MS = 1_000;

function isRateLimitedRetailer(url: string): boolean {
  try {
    const host = new URL(url).hostname.toLowerCase();
    return (
      host === "hmv.co.jp" ||
      host.endsWith(".hmv.co.jp") ||
      host === "biccamera.com" ||
      host.endsWith(".biccamera.com")
    );
  } catch {
    return false;
  }
}

export function batchScrapeDelayMs(
  previousUrl: string,
  nextUrl: string,
  previousFailed: boolean,
): number {
  const retailerDelay =
    isRateLimitedRetailer(previousUrl) || isRateLimitedRetailer(nextUrl)
      ? HMV_OR_BIC_DELAY_MS
      : GENERAL_DELAY_MS;
  return retailerDelay + (previousFailed ? FAILURE_EXTRA_DELAY_MS : 0);
}

export function waitForBatchScrape(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

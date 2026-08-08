import { useEffect, useState } from "react";

type ExchangeRate = {
  display: string;
  cny_per_100_jpy: number;
  updated_at: string | null;
  source_url: string;
};

type LoadState = "loading" | "ready" | "error";

export function ExchangeRateWidget() {
  const [state, setState] = useState<LoadState>("loading");
  const [rate, setRate] = useState<ExchangeRate | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function loadRate() {
      try {
        const response = await fetch("/api/exchange-rate", { cache: "no-store" });
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        const payload = (await response.json()) as ExchangeRate;
        if (!cancelled) {
          setRate(payload);
          setState("ready");
        }
      } catch {
        if (!cancelled) {
          setRate(null);
          setState("error");
        }
      }
    }

    void loadRate();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <aside className="exchange-rate-widget" aria-label="日元汇率">
      {state === "loading" ? <span className="exchange-rate-muted">汇率加载中…</span> : null}
      {state === "error" ? <span className="exchange-rate-muted">汇率暂不可用</span> : null}
      {state === "ready" && rate ? (
        <>
          <span className="exchange-rate-value">{rate.display}</span>
          {rate.updated_at ? (
            <span className="exchange-rate-meta">更新 {rate.updated_at}</span>
          ) : null}
          <a
            className="exchange-rate-link"
            href={rate.source_url}
            target="_blank"
            rel="noreferrer"
          >
            来源
          </a>
        </>
      ) : null}
    </aside>
  );
}

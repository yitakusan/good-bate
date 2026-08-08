import { useState } from "react";

export type HeroEvent = {
  id: number;
  title: string;
  summary: string;
  ip: string;
  shop: string;
  source_url: string;
  image_url: string | null;
  published_at: string | null;
  ends_at: string | null;
  first_seen: string;
  source_platform: string;
};

type HeroEventsProps = {
  events: HeroEvent[];
  showShopLabels?: boolean;
};

function formatEndsAt(endsAt: string | null): string | null {
  if (!endsAt) {
    return null;
  }
  const day = endsAt.slice(0, 10);
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(day);
  if (!match) {
    return `至 ${day}`;
  }
  return `至 ${Number(match[1])}年${Number(match[2])}月${Number(match[3])}日`;
}

export function HeroEvents({ events, showShopLabels = false }: HeroEventsProps) {
  if (events.length === 0) {
    return null;
  }

  return <HeroEventsCarousel events={events} showShopLabels={showShopLabels} />;
}

function HeroEventsCarousel({ events, showShopLabels = false }: HeroEventsProps) {
  const [index, setIndex] = useState(0);
  const event = events[index];
  const hasMultiple = events.length > 1;
  const endsLabel = formatEndsAt(event.ends_at ?? null);

  function goPrev() {
    setIndex((current) => (current - 1 + events.length) % events.length);
  }

  function goNext() {
    setIndex((current) => (current + 1) % events.length);
  }

  return (
    <section className="hero-events" aria-label="活动资讯">
      <div className="hero-events-header">
        <p className="hero-events-label">活动资讯</p>
        {hasMultiple ? (
          <p className="hero-events-count">
            {index + 1} / {events.length}
          </p>
        ) : null}
      </div>

      <div className="hero-events-slide">
        {hasMultiple ? (
          <button type="button" className="hero-events-nav prev" onClick={goPrev} aria-label="上一条活动">
            ‹
          </button>
        ) : null}

        <article className="hero-events-card">
          {event.image_url ? (
            <a
              className="hero-events-image-link"
              href={event.source_url}
              target="_blank"
              rel="noreferrer"
            >
              <img className="hero-events-image" src={event.image_url} alt="" loading="lazy" />
            </a>
          ) : null}
          <div className="hero-events-content">
            <div className="hero-events-meta">
              <span>{event.ip}</span>
              {showShopLabels ? <span className="meta-shop">{event.shop}</span> : null}
              {endsLabel ? <span className="hero-events-ends">{endsLabel}</span> : null}
            </div>
            <h2 className="hero-events-title">
              <a href={event.source_url} target="_blank" rel="noreferrer">
                {event.title}
              </a>
            </h2>
            {event.summary ? <p className="hero-events-summary">{event.summary}</p> : null}
            <a className="hero-events-link" href={event.source_url} target="_blank" rel="noreferrer">
              查看详情
            </a>
          </div>
        </article>

        {hasMultiple ? (
          <button type="button" className="hero-events-nav next" onClick={goNext} aria-label="下一条活动">
            ›
          </button>
        ) : null}
      </div>

      {hasMultiple ? (
        <div className="hero-events-dots" role="tablist" aria-label="活动资讯切换">
          {events.map((item, dotIndex) => (
            <button
              key={item.id}
              type="button"
              role="tab"
              aria-selected={dotIndex === index}
              aria-label={`第 ${dotIndex + 1} 条活动`}
              className={dotIndex === index ? "active" : ""}
              onClick={() => setIndex(dotIndex)}
            />
          ))}
        </div>
      ) : null}
    </section>
  );
}

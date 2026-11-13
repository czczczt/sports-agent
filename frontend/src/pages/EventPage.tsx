// Карточка старта (/events-view/:id). Перенос event_detail.html.
import { Link, useParams } from 'react-router-dom';
import { eventsApi } from '@/api/endpoints';
import type { EventItem } from '@/api/types';
import { BackLink, Icon, NotFound, PageState } from '@/components/ui';
import { useApi } from '@/hooks/useApi';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';
import { dateRu, plural, sourceName } from '@/lib/format';

/** «21.12.2025 — 22.12.2025 · Москва» */
export function eventDates(ev: EventItem): string {
  let s = dateRu(ev.date_begin);
  if (ev.date_end && ev.date_end.slice(0, 10) !== (ev.date_begin || '').slice(0, 10)) s += ` — ${dateRu(ev.date_end)}`;
  return s;
}

export function EventPage() {
  const eventId = Number(useParams().eventId);
  const { data: event, error, loading, reload } = useApi((signal) => eventsApi.get(eventId, signal), [eventId]);
  useDocumentTitle(event ? `${event.title} — Старты` : undefined);

  return (
    <PageState loading={loading} error={error} hasData={!!event} onRetry={reload}
      notFound={<NotFound title="Старт не найден" backTo="/events-view" backLabel="Старты" />}>
      {() => <EventDetail event={event!} />}
    </PageState>
  );
}

function EventDetail({ event }: { event: EventItem }) {
  const place = event.place || event.address;
  const finishers = event.races.reduce((sum, r) => sum + (r.total_count || 0), 0);

  return (
    <>
      <BackLink to="/events-view">Старты</BackLink>

      <section className="card card--clip">
        <div className="finish-flag" />
        <div className="card--pad" style={{ display: 'flex', flexDirection: 'column', gap: 12, padding: 20 }}>
          <div className="chips">
            <span className="chip chip--run"><Icon name="run" className="icon-sm" />Бег</span>
            <span className="chip">{sourceName(event.source_name)}</span>
          </div>
          <h1 className="h1 h1-sm">{event.title}</h1>
          <div className="muted num">{eventDates(event)}{place && ` · ${place}`}</div>
          <div className="grid-2" style={{ maxWidth: 420 }}>
            <div className="tile">
              <div className="tile__value num">{event.races.length}</div>
              <div className="tile__label">{plural(event.races.length, 'дистанция', 'дистанции', 'дистанций')}</div>
            </div>
            <div className="tile">
              <div className="tile__value num">{finishers || '—'}</div>
              <div className="tile__label">
                {finishers ? `${plural(finishers, 'участник', 'участника', 'участников')} в протоколах` : 'участников в протоколах'}
              </div>
            </div>
          </div>
        </div>
      </section>

      <div className="track-divider" />

      <section className="card card--clip">
        <div className="card__head">
          <h2 className="h2">Дистанции и протоколы</h2>
        </div>
        {event.races.length ? event.races.map((r) => (
          <Link key={r.id} to={`/races-view/${r.id}`} className="list-row" style={{ padding: '14px 20px' }}>
            <div style={{ minWidth: 0 }}>
              <div className="list-row__title strong">{r.name_raw}</div>
            </div>
            <div className="row" style={{ flexWrap: 'nowrap', color: 'var(--text-muted)' }}>
              {!!r.total_count && <><span className="num strong" style={{ color: 'var(--text-primary)' }}>{r.total_count}</span><span className="small">уч.</span></>}
              <Icon name="chevron" />
            </div>
          </Link>
        )) : (
          <div className="empty"><p className="small muted">Дистанций у старта пока нет.</p></div>
        )}
      </section>
    </>
  );
}

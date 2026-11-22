import type { EventItem } from '@/shared/api';
import { paths } from '@/shared/config';
import { dateRu, plural, sourceName } from '@/shared/lib';
import { BackLink, Icon } from '@/shared/ui';
import { Link } from 'react-router-dom';
import styles from './EventDetail.module.css';

export function eventDates(ev: EventItem): string {
  let s = dateRu(ev.date_begin);
  if (ev.date_end && ev.date_end.slice(0, 10) !== (ev.date_begin || '').slice(0, 10))
    s += ` — ${dateRu(ev.date_end)}`;
  return s;
}

interface EventDetailProps {
  event: EventItem;
}

export function EventDetail({ event }: EventDetailProps): React.JSX.Element {
  const place = event.place || event.address;
  const finishers = event.races.reduce((sum, r) => sum + (r.total_count || 0), 0);

  return (
    <>
      <BackLink to={paths.events}>Старты</BackLink>

      <section className="card card--clip">
        <div className="finish-flag" />
        <div className={['card--pad', styles.header].join(' ')}>
          <div className="chips">
            <span className="chip chip--run">
              <Icon name="run" className="icon-sm" />
              {event.sport === 'ski'
                ? 'Лыжи'
                : event.sport === 'triathlon'
                  ? 'Триатлон'
                  : event.sport === 'trail'
                    ? 'Трейл'
                    : 'Бег'}
            </span>
            <span className="chip">{sourceName(event.source_name)}</span>
            {event.status === 'planned' && (
              <span className="chip chip--primary">Запланирован</span>
            )}
            {Boolean(event.possible_duplicate_id) && (
              <span className="chip chip--warning">Возможный дубль</span>
            )}
            {Boolean(event.series_name) && (
              <span className="chip">Серия: {event.series_name}</span>
            )}
          </div>
          <h1 className="h1 h1-sm">{event.title}</h1>
          <div className="muted num">
            {eventDates(event)}
            {place && ` · ${place}`}
          </div>
          <div className={['grid-2', styles.location].join(' ')}>
            <div className="tile">
              <div className="tile__value num">{event.races.length}</div>
              <div className="tile__label">
                {plural(event.races.length, 'дистанция', 'дистанции', 'дистанций')}
              </div>
            </div>
            <div className="tile">
              <div className="tile__value num">{finishers || '—'}</div>
              <div className="tile__label">
                {finishers
                  ? `${plural(finishers, 'участник', 'участника', 'участников')} в протоколах`
                  : 'участников в протоколах'}
              </div>
            </div>
          </div>
        </div>
      </section>

      <div className="track-divider" />

      {Boolean(event.past_edition) && (
        <section className="card card--clip">
          <div className="card__head">
            <h2 className="h2">Прошлый выпуск ({event.past_edition?.edition_year || 'ранее'})</h2>
          </div>
          <div className="card--pad">
            <div className="muted small">{event.past_edition?.edition_title}</div>
            <div className="tile" style={{ margin: '0.75rem 0' }}>
              <div className="tile__value num">{event.past_edition?.employees_total}</div>
              <div className="tile__label">сотрудников финишировало в прошлом выпуске</div>
            </div>
            {Boolean(event.past_edition?.distance_counts?.length) && (
              <div className="chips">
                {(event.past_edition?.distance_counts ?? []).map((dc) => (
                  <span key={dc.distance_name} className="chip chip--sm">
                    {dc.distance_name}: <strong className="num">{dc.count}</strong> сотр.
                  </span>
                ))}
              </div>
            )}
          </div>
        </section>
      )}

      <div className="track-divider" />

      <section className="card card--clip">
        <div className="card__head">
          <h2 className="h2">Дистанции и протоколы</h2>
        </div>
        {event.races.length ? (
          event.races.map((r) => (
            <Link key={r.id} to={paths.race(r.id)} className={['list-row', styles.distance].join(' ')}>
              <div className={styles.name}>
                <div className="list-row__title strong">{r.name_raw}</div>
              </div>
              <div className={['row', styles.count].join(' ')}>
                {!!r.total_count && (
                  <>
                    <span className={['num strong', styles.participants].join(' ')}>{r.total_count}</span>
                    <span className="small">уч.</span>
                  </>
                )}
                <Icon name="chevron" />
              </div>
            </Link>
          ))
        ) : (
          <div className="empty">
            <p className="small muted">Дистанций у старта пока нет.</p>
          </div>
        )}
      </section>
    </>
  );
}

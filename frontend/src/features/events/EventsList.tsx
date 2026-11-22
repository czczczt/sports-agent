import type { EventItem } from '@/shared/api';
import { paths } from '@/shared/config';
import { dateRu, monthTitle, plural, sourceName } from '@/shared/lib';
import { Fragment } from 'react';
import { Link } from 'react-router-dom';
import styles from './EventsList.module.css';

const monthKey = (ev?: EventItem) => (ev?.date_begin || '').slice(0, 7);

interface EventsListProps {
  events: EventItem[];
}

export function EventsList({ events }: EventsListProps): React.JSX.Element {
  const isNewMonth = (i: number) => i === 0 || monthKey(events[i]) !== monthKey(events[i - 1]);

  return (
    <>
      <section className="card card--clip only-desktop">
        <div className="table-wrap">
          <table className={['table', styles.table].join(' ')}>
            <thead>
              <tr>
                <th scope="col" className={styles.dateColumn}>
                  Дата
                </th>
                <th scope="col">Старт</th>
                <th scope="col">Площадка</th>
                <th scope="col">Место</th>
                <th scope="col" className="right">
                  Дистанций
                </th>
              </tr>
            </thead>
            <tbody>
              {events.map((ev, i) => (
                <Fragment key={ev.id}>
                  {isNewMonth(i) && (
                    <tr className="group-row">
                      <th scope="rowgroup" colSpan={5} className="muted">
                        {monthTitle(ev.date_begin)}
                      </th>
                    </tr>
                  )}
                  <tr>
                    <td className="num muted nowrap">{dateRu(ev.date_begin)}</td>
                    <td>
                      <Link to={paths.event(ev.id)} className="cell-title">
                        {ev.title}
                      </Link>
                      {ev.status === 'planned' && (
                        <span className="chip chip--sm chip--primary" style={{ marginLeft: 6 }}>
                          Запланирован
                        </span>
                      )}
                      {Boolean(ev.possible_duplicate_id) && (
                        <span className="chip chip--sm chip--warning" style={{ marginLeft: 6 }}>
                          Возможный дубль
                        </span>
                      )}
                      {Boolean(ev.series_name) && (
                        <span className="chip chip--sm" style={{ marginLeft: 6 }}>
                          {ev.series_name}
                        </span>
                      )}
                      {Boolean(ev.past_edition?.employees_total) && (
                        <span className="chip chip--sm" style={{ marginLeft: 6 }} title="Участников компании в прошлом выпуске">
                          В прошлом: {ev.past_edition?.employees_total} сотр.
                        </span>
                      )}
                      {ev.races.length > 0 && (
                        <div className={['chips', styles.chips].join(' ')}>
                          {ev.races.map((r) => (
                            <Link key={r.id} to={paths.race(r.id)} className="chip chip--sm">
                              {r.name_raw}
                              {!!r.total_count && (
                                <>
                                  {' '}
                                  <span className="chip__count num">{r.total_count}</span>
                                </>
                              )}
                            </Link>
                          ))}
                        </div>
                      )}
                    </td>
                    <td>
                      <span className="chip chip--sm">{sourceName(ev.source_name)}</span>
                    </td>
                    <td className="muted">{ev.place || ev.address || '—'}</td>
                    <td className="num right strong">{ev.races.length}</td>
                  </tr>
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="card card--clip only-mobile">
        {events.map((ev, i) => (
          <Fragment key={ev.id}>
            {isNewMonth(i) && (
              <div className={`small muted strong month-label${i > 0 ? ' month-label--sep' : ''}`}>
                {monthTitle(ev.date_begin)}
              </div>
            )}
            <Link to={paths.event(ev.id)} className="list-row">
              <div className={styles.description}>
                <div className="list-row__title">
                  {ev.title}
                  {ev.status === 'planned' && (
                    <span className="chip chip--sm chip--primary" style={{ marginLeft: 6 }}>
                      Запланирован
                    </span>
                  )}
                  {Boolean(ev.possible_duplicate_id) && (
                    <span className="chip chip--sm chip--warning" style={{ marginLeft: 6 }}>
                      Дубль
                    </span>
                  )}
                </div>
                <div className="list-row__meta num">
                  {dateRu(ev.date_begin)}
                  {(ev.place || ev.address) && ` · ${ev.place || ev.address}`}
                </div>
              </div>
              <div className="list-row__end">
                <span className="chip chip--sm">{sourceName(ev.source_name)}</span>
                <div className="list-row__meta num">
                  {ev.races.length} {plural(ev.races.length, 'дистанция', 'дистанции', 'дистанций')}
                </div>
              </div>
            </Link>
          </Fragment>
        ))}
      </section>
    </>
  );
}

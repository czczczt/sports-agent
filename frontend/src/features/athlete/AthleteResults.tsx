import type { AthleteResultItem } from '@/shared/api';
import { paths } from '@/shared/config';
import { dateRu, fixed1, hms, sourceName } from '@/shared/lib';
import { Link } from 'react-router-dom';
import styles from './AthleteProfile.module.css';

function placeCell(r: AthleteResultItem) {
  if (r.place_abs && r.total_participants) {
    return (
      <>
        <span className="strong">{r.place_abs}</span> <span className="muted">/ {r.total_participants}</span>
      </>
    );
  }
  return <span className="strong">{r.place_abs || '—'}</span>;
}

interface AthleteResultsProps {
  results: AthleteResultItem[];
  athleteId: number;
}
export function AthleteResults({ results, athleteId }: AthleteResultsProps): React.JSX.Element {
  return (
    <section className="card card--clip">
      <div className="card__head">
        <h2 className="h2">Результаты</h2>
        <span className="chip chip--sm chip--brand">{results.length} · Бег</span>
      </div>

      {results.length ? (
        <>
          <div className="table-wrap only-desktop">
            <table className={['table table--legacy-metrics', styles.results].join(' ')}>
              <thead>
                <tr>
                  <th scope="col">Дата</th>
                  <th scope="col">Старт</th>
                  <th scope="col" className="right">
                    Время
                  </th>
                  <th scope="col" className="right">
                    Темп
                  </th>
                  <th scope="col" className="right">
                    Баллы
                  </th>
                  <th scope="col" className="center">
                    Место
                  </th>
                </tr>
              </thead>
              <tbody>
                {results.map((r) => (
                  <tr key={r.result_id}>
                    <td className="num muted nowrap">{dateRu(r.event_date)}</td>
                    <td>
                      <Link to={paths.race(r.race_id, athleteId)} className="cell-title">
                        {r.event_title}
                      </Link>
                      <div className="cell-sub">
                        {r.distance_name} · {sourceName(r.source_name)}
                      </div>
                    </td>
                    <td className="num right strong nowrap">
                      {r.time_formatted}
                      {!!r.gun_time_s && <div className="cell-sub">пист. {hms(r.gun_time_s)}</div>}
                    </td>
                    <td className="num right nowrap">{r.pace_formatted}</td>
                    <td className="num right nowrap">
                      {r.rating_points != null ? (
                        <span className="strong">{fixed1(r.rating_points)}</span>
                      ) : (
                        <span className="muted" title={r.rating_reason || 'не в зачёте'}>
                          —
                        </span>
                      )}
                    </td>
                    <td className="num center nowrap">{placeCell(r)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="only-mobile">
            {results.map((r) => (
              <Link key={r.result_id} to={paths.race(r.race_id, athleteId)} className="list-row">
                <div className={styles.name}>
                  <div className="list-row__title">{r.event_title}</div>
                  <div className="list-row__meta num">
                    {dateRu(r.event_date)} · {r.distance_name} ·{' '}
                    {r.place_abs && r.total_participants
                      ? `${r.place_abs} из ${r.total_participants}`
                      : `${r.place_abs || '—'} место`}
                  </div>
                </div>
                <div className="list-row__end">
                  <div className="num strong">{r.time_formatted}</div>
                  <div className="list-row__meta num">
                    {r.pace_formatted}
                    {r.rating_points != null && ` · ${fixed1(r.rating_points)} б.`}
                  </div>
                </div>
              </Link>
            ))}
          </div>
        </>
      ) : (
        <div className="empty">
          <p className="small muted">Недостаточно данных.</p>
        </div>
      )}
    </section>
  );
}

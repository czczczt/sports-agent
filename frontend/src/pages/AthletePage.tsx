// Профиль спортсмена (/athletes-view/:id). Перенос athlete_profile.html.
import { Link, useParams } from 'react-router-dom';
import { athletesApi } from '@/api/endpoints';
import type { AthleteResultItem, AthleteSummary } from '@/api/types';
import { PaceChart } from '@/components/charts/PaceChart';
import { AssessmentCard } from '@/components/athlete/AssessmentCard';
import { BackLink, Icon, NotFound, PageState } from '@/components/ui';
import { useApi } from '@/hooks/useApi';
import { SITE_TITLE, useDocumentTitle } from '@/hooks/useDocumentTitle';
import { athleteMeta, dateRu, fixed1, hms, initials, plural, sourceName } from '@/lib/format';

export function AthletePage() {
  const athleteId = Number(useParams().athleteId);
  const { data, error, loading, reload } = useApi(
    (signal) => Promise.all([athletesApi.summary(athleteId, signal), athletesApi.results(athleteId, signal)]),
    [athleteId],
  );
  useDocumentTitle(data ? `${data[0].athlete.display_name} — ${SITE_TITLE}` : undefined);

  return (
    <PageState loading={loading} error={error} hasData={!!data} onRetry={reload}
      notFound={<NotFound title="Спортсмен не найден" />}>
      {() => <AthleteProfile summary={data![0]} results={data![1]} />}
    </PageState>
  );
}

function placeCell(r: AthleteResultItem) {
  if (r.place_abs && r.total_participants) {
    return <><span className="strong">{r.place_abs}</span> <span className="muted">/ {r.total_participants}</span></>;
  }
  return <span className="strong">{r.place_abs || '—'}</span>;
}

function AthleteProfile({ summary, results }: { summary: AthleteSummary; results: AthleteResultItem[] }) {
  const a = summary.athlete;
  const pbCount = summary.personal_bests.length;

  return (
    <>
      <BackLink to="/">Найти себя</BackLink>

      <section className="card profile-head">
        <div className="row" style={{ flexWrap: 'nowrap', gap: 20, minWidth: 0 }}>
          <span className="avatar avatar--lg" aria-hidden="true">{initials(a.display_name)}</span>
          <div style={{ minWidth: 0 }}>
            <h1 className="h1 h1-sm">{a.display_name}</h1>
            <div className="muted num" style={{ marginTop: 6 }}>{athleteMeta(a, false)}</div>
            {a.club && <div className="small muted" style={{ marginTop: 2 }}>{a.club}</div>}
          </div>
        </div>
      </section>

      <div className="cols">
        <div className="cols__side">
          <div className="grid-2">
            <div className="card card--accent stat">
              <span className="stat__label stat__label--run"><Icon name="run" className="icon-sm" />Бег</span>
              <span className="display-num num">{summary.total_starts}</span>
              <span className="small muted">{plural(summary.total_starts, 'финиш', 'финиша', 'финишей')}</span>
            </div>
            <div className="card stat">
              <span className="stat__label stat__label--brand"><Icon name="trophy" className="icon-sm" />Рекорды</span>
              <span className="display-num num">{pbCount}</span>
              <span className="small muted">{plural(pbCount, 'личный рекорд', 'личных рекорда', 'личных рекордов')}</span>
            </div>
          </div>

          <section className={`card card--pad${summary.rating.status === 'no_data' ? ' card--pending' : ''}`}>
            {summary.rating.rank ? (
              <div className="grid-2" style={{ gap: 16 }}>
                <div>
                  <Link to={`/rating-view?athlete_id=${a.id}`} className="rating-profile-link" title="Открыть в общем рейтинге">
                    <h2 className="h2 rating-hover-target" style={{ lineHeight: 1.25 }}>Место</h2>
                    <div className="display-num num rating-hover-target rating-big-num">{summary.rating.rank}</div>
                  </Link>
                </div>
                <div>
                  <Link to="/rating-formula" className="points-profile-link" title="Как рассчитываются баллы">
                    <h2 className="h2 rating-hover-target-points" style={{ lineHeight: 1.25 }}>Баллы</h2>
                    <div className="display-num num rating-hover-target-points rating-big-num">
                      {summary.rating.points != null ? fixed1(summary.rating.points) : '—'}
                    </div>
                  </Link>
                </div>
              </div>
            ) : (
              <>
                <div className="row row--between">
                  <h2 className="h2">Место</h2>
                  <span className="chip chip--sm chip--pending">нет данных</span>
                </div>
                <p className="small" style={{ marginTop: 12 }}>Недостаточно данных для рейтинга за последние 365 дней.</p>
              </>
            )}
          </section>

          <section className="card card--clip">
            <div className="card__head"><h2 className="h2">Личные рекорды</h2></div>
            {pbCount ? summary.personal_bests.map((pb) => (
              <div key={pb.norm_distance} className="list-row">
                <div style={{ minWidth: 0 }}>
                  <div className="list-row__title strong">{pb.distance_title}</div>
                  <div className="list-row__meta" title={pb.event_title}>{dateRu(pb.event_date)} · {pb.event_title}</div>
                </div>
                <div className="list-row__end">
                  <div className="num strong" style={{ fontSize: 16 }}>{pb.time_formatted}</div>
                  <div className="list-row__meta num">{pb.pace_formatted}</div>
                </div>
              </div>
            )) : (
              <div style={{ padding: '16px 20px' }}><p className="small muted">Недостаточно данных.</p></div>
            )}
          </section>

          <section className="card card--pad">
            <h2 className="h2" style={{ marginBottom: summary.dynamics.length ? 2 : 12 }}>Темп по стартам</h2>
            {summary.dynamics.length ? (
              <div className="chart-box chart-box--sm" style={{ height: 165 }}><PaceChart data={summary.dynamics} /></div>
            ) : (
              <p className="small muted">Недостаточно данных для графика.</p>
            )}
          </section>
        </div>

        <div className="cols__main">
          <AssessmentCard athleteId={a.id} />

          <section className="card card--clip">
            <div className="card__head">
              <h2 className="h2">Результаты</h2>
              <span className="chip chip--sm chip--brand">{results.length} · Бег</span>
            </div>

            {results.length ? (
              <>
                <div className="table-wrap only-desktop">
                  <table className="table table--legacy-metrics" style={{ minWidth: 680 }}>
                    <thead>
                      <tr>
                        <th scope="col">Дата</th>
                        <th scope="col">Старт</th>
                        <th scope="col" className="right">Время</th>
                        <th scope="col" className="right">Темп</th>
                        <th scope="col" className="right">Баллы</th>
                        <th scope="col" className="center">Место</th>
                      </tr>
                    </thead>
                    <tbody>
                      {results.map((r) => (
                        <tr key={r.result_id}>
                          <td className="num muted nowrap">{dateRu(r.event_date)}</td>
                          <td>
                            <Link to={`/races-view/${r.race_id}?athlete_id=${a.id}`} className="cell-title">{r.event_title}</Link>
                            <div className="cell-sub">{r.distance_name} · {sourceName(r.source_name)}</div>
                          </td>
                          <td className="num right strong nowrap">
                            {r.time_formatted}
                            {!!r.gun_time_s && <div className="cell-sub">пист. {hms(r.gun_time_s)}</div>}
                          </td>
                          <td className="num right nowrap">{r.pace_formatted}</td>
                          <td className="num right nowrap">
                            {r.rating_points != null
                              ? <span className="strong">{fixed1(r.rating_points)}</span>
                              : <span className="muted" title={r.rating_reason || 'не в зачёте'}>—</span>}
                          </td>
                          <td className="num center nowrap">{placeCell(r)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                <div className="only-mobile">
                  {results.map((r) => (
                    <Link key={r.result_id} to={`/races-view/${r.race_id}?athlete_id=${a.id}`} className="list-row">
                      <div style={{ minWidth: 0 }}>
                        <div className="list-row__title">{r.event_title}</div>
                        <div className="list-row__meta num">
                          {dateRu(r.event_date)} · {r.distance_name} · {r.place_abs && r.total_participants
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
              <div className="empty"><p className="small muted">Недостаточно данных.</p></div>
            )}
          </section>
        </div>
      </div>
    </>
  );
}

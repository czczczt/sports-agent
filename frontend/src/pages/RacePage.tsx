// Дистанция и протокол (/races-view/:id?athlete_id=…&search=…). Перенос race_detail.html.
import { useState, type FormEvent } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { racesApi } from '@/api/endpoints';
import type { RacePage as RacePageData, RaceProtocolItem } from '@/api/types';
import { DistributionChart } from '@/components/charts/DistributionChart';
import { BackLink, EmptyState, Icon, NotFound, PageState, StatusChip } from '@/components/ui';
import { DistancePills } from '@/components/ui/DistancePills';
import { useApi } from '@/hooks/useApi';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';
import { dateRu, fixed1, genderLabel, hms, plural } from '@/lib/format';

export function RacePage() {
  const raceId = Number(useParams().raceId);
  const [params, setParams] = useSearchParams();
  const search = params.get('search') || '';
  const athleteId = Number(params.get('athlete_id')) || null;

  const { data, error, loading, reload } = useApi(
    (signal) => racesApi.page(raceId, { search, athlete_id: athleteId }, signal),
    [raceId, search, athleteId],
  );
  useDocumentTitle(data ? `${data.race.name_raw} — ${data.event?.title ?? 'Старты'}` : undefined);

  const setSearch = (value: string) => {
    const q: Record<string, string> = {};
    if (athleteId) q.athlete_id = String(athleteId);
    if (value) q.search = value;
    setParams(q);
  };

  return (
    <PageState loading={loading} error={error} hasData={!!data} onRetry={reload}
      notFound={<NotFound title="Дистанция не найдена" backTo="/events-view" backLabel="Старты" />}>
      {() => <RaceDetail data={data!} athleteId={athleteId} search={search} onSearch={setSearch} />}
    </PageState>
  );
}

/** «М · 34» для таблицы; возраст 0 и год рождения 2026 показываем как 1 (как в прежнем шаблоне). */
function ageText(r: RaceProtocolItem): string {
  if (r.age != null && r.age > 0) return String(r.age);
  if (r.age === 0 || r.birth_year === 2026) return '1';
  return '';
}

function AthleteName({ r, className }: { r: RaceProtocolItem; className: string }) {
  return r.athlete_id
    ? <Link to={`/athletes-view/${r.athlete_id}`} className={className}>{r.full_name_raw}</Link>
    : <span className={className}>{r.full_name_raw}</span>;
}

function ProtocolTableRow({ r, isMe }: { r: RaceProtocolItem; isMe: boolean }) {
  const age = ageText(r);
  return (
    <tr className={isMe ? 'me-row' : undefined}>
      <td className="num strong">{r.place_abs || '—'}</td>
      <td>
        <AthleteName r={r} className="cell-title" />
        {isMe && <>{' '}<span className="small strong" style={{ color: 'var(--brand-text)', marginLeft: 6 }}>это вы</span></>}
        <div className="cell-sub num">{r.bib ? `№ ${r.bib}` : ''}{r.bib && r.club_raw ? ' · ' : ''}{r.club_raw || ''}</div>
      </td>
      <td className="muted num nowrap">{genderLabel(r.gender) || '—'}{age && ` · ${age}`}</td>
      <td className="num strong nowrap">{r.time_formatted}</td>
      <td className="num muted nowrap">{hms(r.gun_time_s)}</td>
      <td className="num nowrap">{r.pace_formatted}</td>
      <td><StatusChip status={r.status} /></td>
    </tr>
  );
}

function ProtocolListRow({ r, isMe }: { r: RaceProtocolItem; isMe: boolean }) {
  const age = ageText(r);
  return (
    <div className={`list-row list-row--place${isMe ? ' me-row' : ''}`}>
      <span className="num strong muted">{r.place_abs || '—'}</span>
      <div style={{ minWidth: 0 }}>
        <div className="row" style={{ gap: 8 }}>
          <AthleteName r={r} className="list-row__title" />
          {isMe && <span className="small strong" style={{ color: 'var(--brand-text)' }}>это вы</span>}
        </div>
        <div className="list-row__meta num">
          {r.pace_formatted}{r.gender && ` · ${genderLabel(r.gender)}`}{age && ` ${age}`}{r.club_raw && ` · ${r.club_raw}`}
        </div>
      </div>
      <div className="list-row__end">
        <div className="num strong">{r.time_formatted}</div>
        {r.status !== 'FIN' && <StatusChip status={r.status} />}
      </div>
    </div>
  );
}

function RaceDetail({ data, athleteId, search, onSearch }: {
  data: RacePageData;
  athleteId: number | null;
  search: string;
  onSearch: (value: string) => void;
}) {
  const { race, event, results, competition, rating_leaders: leaders } = data;
  const pinned = data.pinned_athlete_result;
  const me = competition?.athlete_result ?? null;
  const athleteQuery = athleteId ? `?athlete_id=${athleteId}` : '';
  const isMe = (r: RaceProtocolItem) => !!athleteId && r.athlete_id === athleteId;
  const finCount = competition ? competition.total_finishers : results.length;
  const place = event?.place || event?.address;

  return (
    <>
      {event && <BackLink to={`/events-view/${event.id}`}>{event.title}</BackLink>}

      <section className="card card--clip">
        <div className="finish-flag" />
        <div style={{ padding: 20, display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div className="chips">
            <span className="chip chip--run"><Icon name="run" className="icon-sm" />Бег</span>
          </div>
          <h1 className="h1 h1-sm">{race.name_raw}</h1>
          {event && (
            <div className="muted num">
              <Link to={`/events-view/${event.id}`} style={{ textDecoration: 'none' }}>{event.title}</Link> · {dateRu(event.date_begin)}{place && ` · ${place}`}
            </div>
          )}
          <div className="grid-2" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))' }}>
            <div className="tile"><div className="tile__value num">{finCount}</div><div className="tile__label">{plural(finCount, 'финишёр', 'финишёра', 'финишёров')}</div></div>
            {competition && (
              <>
                <div className="tile"><div className="tile__value num">{hms(competition.median_time_s)}</div><div className="tile__label">медиана</div></div>
                <div className="tile"><div className="tile__value num">{hms(competition.p25_time_s)}</div><div className="tile__label">граница топ-25%</div></div>
              </>
            )}
            {!!race.distance_m && (
              <div className="tile"><div className="tile__value num">{race.distance_m} м</div><div className="tile__label">длина</div></div>
            )}
          </div>
        </div>
      </section>

      {event && event.races.length > 1 && (
        <DistancePills
          label="Дистанции старта"
          activeId={race.id}
          items={event.races.map((r) => ({ id: r.id, label: r.name_raw, to: `/races-view/${r.id}${athleteQuery}` }))}
        />
      )}

      <div className="track-divider" />

      <div className="cols">
        <div className="cols__side">
          {me && competition && (
            <section className="card card--pad me-row" style={{ borderColor: 'transparent' }}>
              <div className="row row--between">
                <h2 className="h2">Ваш результат</h2>
                {!!me.top_percent && <span className="chip chip--brand">топ {me.top_percent}%</span>}
              </div>
              <div className="row" style={{ alignItems: 'baseline', gap: 8 }}>
                <span className="display-num num">{me.place_abs || '—'}</span>
                <span className="muted">место из {competition.total_finishers}</span>
              </div>
              <div className="grid-2">
                <div className="tile" style={{ background: 'var(--surface)' }}><div className="tile__value num">{me.time_formatted}</div><div className="tile__label">чистое время</div></div>
                <div className="tile" style={{ background: 'var(--surface)' }}><div className="tile__value num">{me.pace_formatted}</div><div className="tile__label">темп</div></div>
              </div>
            </section>
          )}

          {!search && leaders.length > 0 && (
            <section className="card card--clip">
              <div className="card__head">
                <h2 className="h2">Топ по рейтингу</h2>
                <span className="chip chip--sm chip--brand">365 дней</span>
              </div>
              {leaders.map((r, i) => (
                <div key={r.result_id} className="list-row list-row--place">
                  <span className={`medal medal--${i + 1} num`}>{i + 1}</span>
                  <span style={{ minWidth: 0 }}>
                    <Link to={`/athletes-view/${r.athlete_id}`} className="list-row__title">{r.full_name_raw}</Link>
                    {' '}<span className="list-row__meta">место в общем рейтинге: {r.rating_rank} · {r.rating_starts} {plural(r.rating_starts, 'старт', 'старта', 'стартов')}</span>
                  </span>
                  <span className="list-row__end">
                    <span className="num strong">{fixed1(r.rating_points)}</span>
                    {' '}<span className="list-row__meta">баллов</span>
                  </span>
                </div>
              ))}
            </section>
          )}

          {competition && (
            <section className="card card--pad">
              <div>
                <h2 className="h2">Конкуренция</h2>
                <p className="small muted" style={{ marginTop: 4 }}>Распределение финишных времён{me && ' · ваш интервал выделен'}</p>
              </div>
              <div className="chart-box chart-box--sm"><DistributionChart competition={competition} /></div>
            </section>
          )}
        </div>

        <section className="cols__main card card--clip" style={{ gap: 0 }}>
          <div className="card__head">
            <h2 className="h2">Протокол</h2>
            <ProtocolSearch key={search} initial={search} onSearch={onSearch} resetTo={`/races-view/${race.id}${athleteQuery}`} />
          </div>

          {results.length || pinned ? (
            <>
              {/* Десктоп: полная таблица */}
              <div className="table-wrap only-desktop">
                <table className="table" style={{ minWidth: 760 }}>
                  <thead>
                    <tr>
                      <th scope="col">Место</th>
                      <th scope="col">Участник</th>
                      <th scope="col">Пол / возраст</th>
                      <th scope="col">Чистое</th>
                      <th scope="col">Пистолетное</th>
                      <th scope="col">Темп</th>
                      <th scope="col">Статус</th>
                    </tr>
                  </thead>
                  <tbody>
                    {pinned && (
                      <>
                        <ProtocolTableRow r={pinned} isMe />
                        <tr className="gap-row">
                          <td className="muted gap-row__dots">&bull;<br />&bull;<br />&bull;</td>
                          <td colSpan={6} className="gap-row__rest" />
                        </tr>
                      </>
                    )}
                    {results.map((r) => <ProtocolTableRow key={r.result_id} r={r} isMe={isMe(r)} />)}
                  </tbody>
                </table>
              </div>

              {/* Телефон: компактные строки */}
              <div className="only-mobile">
                {pinned && (
                  <>
                    <ProtocolListRow r={pinned} isMe />
                    <div className="list-row list-row--place list-row--gap">
                      <span className="muted">&bull;<br />&bull;<br />&bull;</span>
                      <div />
                    </div>
                  </>
                )}
                {results.map((r) => <ProtocolListRow key={r.result_id} r={r} isMe={isMe(r)} />)}
              </div>
            </>
          ) : (
            <EmptyState inCard={false} text={search ? `По запросу «${search}» никого нет.` : 'Протокол пуст.'} />
          )}
        </section>
      </div>
    </>
  );
}

function ProtocolSearch({ initial, onSearch, resetTo }: { initial: string; onSearch: (value: string) => void; resetTo: string }) {
  const [value, setValue] = useState(initial);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    onSearch(value.trim());
  };
  return (
    <form className="form-inline" role="search" style={{ flex: '1 1 280px', justifyContent: 'flex-end' }} onSubmit={submit}>
      <label className="sr-only" htmlFor="protocol-search">Поиск в протоколе</label>
      <input id="protocol-search" className="input input--sm" type="search" name="search" value={value}
        onChange={(e) => setValue(e.target.value)} placeholder="Фамилия или номер" />
      <button type="submit" className="btn btn--primary" style={{ minHeight: 40 }}>Найти</button>
      {initial && (
        <Link to={resetTo} className="btn btn--ghost" style={{ minHeight: 40 }}>Сбросить</Link>
      )}
    </form>
  );
}

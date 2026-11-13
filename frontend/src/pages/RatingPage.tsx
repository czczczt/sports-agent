// Рейтинг (/rating-view?gender=M|F&athlete_id=…). Перенос rating.html.
import { useEffect, useRef } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { ratingApi } from '@/api/endpoints';
import type { RatingPage as RatingPageData, RatingRow } from '@/api/types';
import { ErrorState, Icon, Loader } from '@/components/ui';
import { useApi } from '@/hooks/useApi';
import { SITE_TITLE, useDocumentTitle } from '@/hooks/useDocumentTitle';
import { dateRu, fixed1 } from '@/lib/format';

const GENDERS: { value: string | null; label: string }[] = [
  { value: null, label: 'Все' },
  { value: 'M', label: 'Мужчины' },
  { value: 'F', label: 'Женщины' },
];

export function RatingPage() {
  useDocumentTitle(`Рейтинг — ${SITE_TITLE}`);
  const [params] = useSearchParams();
  const rawGender = params.get('gender');
  const gender = rawGender === 'M' || rawGender === 'F' ? rawGender : null;
  const athleteId = Number(params.get('athlete_id')) || null;

  const { data, error, loading, reload } = useApi(
    (signal) => ratingApi.page({ gender, athlete_id: athleteId }, signal),
    [gender, athleteId],
  );

  const genderLink = (g: string | null) => {
    const q = new URLSearchParams();
    if (g) q.set('gender', g);
    if (athleteId) q.set('athlete_id', String(athleteId));
    const s = q.toString();
    return `/rating-view${s ? `?${s}` : ''}`;
  };

  return (
    <div className="rating-page">
      <header className="rating-page__head">
        <div>
          <h1 className="rating-page__title">Рейтинг</h1>
          <p className="rating-page__subtitle">Последние 365 дней · обновлён {data ? dateRu(data.period_end) : '…'}</p>
        </div>
        <nav className="rating-sports" aria-label="Виды спорта">
          <Link className="rating-sport rating-sport--active" to="/rating-view">Бег</Link>
          <span className="rating-sport rating-sport--disabled">Лыжи</span>
          <span className="rating-sport rating-sport--disabled">Триатлон</span>
          <span className="rating-sport rating-sport--disabled">Трейл</span>
        </nav>
      </header>

      <div className="rating-filters">
        <div className="rating-filter">
          <span>Пол</span>
          <div className="rating-segment">
            {GENDERS.map((g) => (
              <Link key={g.label} to={genderLink(g.value)} preventScrollReset className={gender === g.value ? 'is-active' : undefined}>{g.label}</Link>
            ))}
          </div>
        </div>
      </div>

      {error && !data ? <ErrorState error={error} onRetry={reload} />
        : !data ? <Loader />
        : <RatingBoard data={data} athleteId={athleteId} loading={loading} />}
    </div>
  );
}

function RatingTableRow({ row, isMe, plainPlace = false }: { row: RatingRow; isMe: boolean; plainPlace?: boolean }) {
  const medal = !plainPlace && row.rank <= 3 ? row.rank : 'plain';
  return (
    <tr className={isMe ? 'me-row' : undefined} id={isMe ? 'me-row' : undefined}>
      <td><span className={`rating-place rating-place--${medal}`}>{row.rank}</span></td>
      <td>
        <Link to={`/athletes-view/${row.athlete_id}`} className="rating-athlete">{row.display_name}</Link>
        <span className="rating-birth">{row.birth_year || 'год не указан'}</span>
      </td>
      <td className="right strong num">{fixed1(row.points)}</td>
      <td className="right muted num">{row.starts_count}</td>
    </tr>
  );
}

function RatingBoard({ data, athleteId, loading }: { data: RatingPageData; athleteId: number | null; loading: boolean }) {
  const me = data.me_row;
  const meInRows = !!me && data.rows.some((r) => r.athlete_id === athleteId);
  const scrolledFor = useRef<string | null>(null);

  // Как раньше: при переходе «Место» из профиля прокручиваем к строке спортсмена.
  useEffect(() => {
    const key = `${athleteId}`;
    if (!athleteId || loading || scrolledFor.current === key) return;
    scrolledFor.current = key;
    const t = setTimeout(() => document.getElementById('me-row')?.scrollIntoView({ behavior: 'smooth', block: 'center' }), 150);
    return () => clearTimeout(t);
  }, [athleteId, loading]);

  return (
    <div className="rating-layout">
      <section className="rating-board">
        {data.rows.length ? (
          <>
            {/* Пьедестал топ-3 убран: он дублировал первые строки таблицы (там уже есть медали 1–3). */}
            <div className="rating-table-wrap">
              <table className="rating-table">
                <thead>
                  <tr>
                    <th>Место</th>
                    <th>Спортсмен</th>
                    <th className="right">Баллы</th>
                    <th className="right">Стартов</th>
                  </tr>
                </thead>
                <tbody>
                  {me && !meInRows && (
                    <>
                      <RatingTableRow row={me} isMe plainPlace />
                      <tr className="gap-row">
                        <td className="muted gap-row__dots">&bull;<br />&bull;<br />&bull;</td>
                        <td colSpan={3} className="gap-row__rest" />
                      </tr>
                    </>
                  )}
                  {data.rows.map((row) => (
                    <RatingTableRow key={row.athlete_id} row={row} isMe={!!athleteId && row.athlete_id === athleteId} />
                  ))}
                </tbody>
              </table>
            </div>
            <div className="rating-board__footer">1–{data.rows.length} из {data.total}</div>
          </>
        ) : (
          <div className="empty"><span className="empty__icon"><Icon name="trophy" /></span><div className="strong">Рейтинг пока пуст</div></div>
        )}
      </section>

      <aside className="rating-sidebar">
        {me && (
          <section className="rating-side-card">
            <strong className="rating-side-card__rank">{me.rank}</strong>
            <p className="rating-side-card__muted">{me.display_name} · {fixed1(me.points)} балла</p>
            <Link to={`/athletes-view/${me.athlete_id}`} className="rating-side-card__link">В профиль →</Link>
          </section>
        )}
        <section className="rating-side-card">
          <Link to="/rating-formula" className="rating-side-card__title-link">Как считается беговой рейтинг</Link>
        </section>
      </aside>
    </div>
  );
}

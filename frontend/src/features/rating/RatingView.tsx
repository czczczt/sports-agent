import { paths } from '@/shared/config';
import { dateRu, parseId } from '@/shared/lib';
import { useAuth } from '@/shared/session';
import { AsyncView } from '@/shared/ui';
import { Link, useSearchParams } from 'react-router-dom';
import { z } from 'zod';
import { RatingBoard } from './RatingBoard';
import layout from './RatingView.module.css';
import { useRating } from './useRating';

const GENDERS: { value: string | null; label: string }[] = [
  { value: null, label: 'Все' },
  { value: 'M', label: 'Мужчины' },
  { value: 'F', label: 'Женщины' },
];

const SPORTS = [
  { id: 'run', label: 'Бег' },
  { id: 'ski', label: 'Лыжи' },
  { id: 'triathlon', label: 'Триатлон' },
  { id: 'trail', label: 'Трейл' },
];

export function RatingView(): React.JSX.Element {
  const [params, setParams] = useSearchParams();
  const { user } = useAuth();
  const isCaptainOrAdmin = user?.role === 'admin' || user?.role === 'captain';

  const sportParam = params.get('sport')?.toLowerCase() || 'run';
  const sport = ['run', 'ski', 'triathlon', 'trail'].includes(sportParam) ? sportParam : 'run';
  const asOf = isCaptainOrAdmin ? params.get('as_of') : null;
  const gender = z.enum(['M', 'F']).nullable().catch(null).parse(params.get('gender'));
  const athleteId = parseId(params.get('athlete_id'));

  const query = useRating(sport, asOf, gender, athleteId);
  const data = query.data;

  const updateParam = (key: string, value: string | null) => {
    const next = new URLSearchParams(params);
    if (value) {
      next.set(key, value);
    } else {
      next.delete(key);
    }
    setParams(next);
  };

  const sportLink = (sp: string) => {
    const q = new URLSearchParams(params);
    q.set('sport', sp);
    const s = q.toString();
    return `${paths.rating}${s ? `?${s}` : ''}`;
  };

  const genderLink = (g: string | null) => {
    const q = new URLSearchParams(params);
    if (g) {
      q.set('gender', g);
    } else {
      q.delete('gender');
    }
    const s = q.toString();
    return `${paths.rating}${s ? `?${s}` : ''}`;
  };

  return (
    <div className={layout.ratingPage}>
      <header className={layout.ratingPageHead}>
        <div>
          <h1 className={layout.ratingPageTitle}>Рейтинг</h1>
          <p className={layout.ratingPageSubtitle}>
            {asOf ? (
              <>
                Срез на дату {dateRu(asOf)} · период {data ? `${dateRu(data.period_start)} — ${dateRu(data.period_end)}` : '…'}
              </>
            ) : (
              <>Последние 365 дней · обновлён {data ? dateRu(data.period_end) : '…'}</>
            )}
          </p>
        </div>
        <nav className={layout.ratingSports} aria-label="Виды спорта">
          {SPORTS.map((s) => (
            <Link
              key={s.id}
              className={[layout.ratingSport, sport === s.id ? layout.ratingSportActive : ''].join(' ')}
              to={sportLink(s.id)}
            >
              {s.label}
            </Link>
          ))}
        </nav>
      </header>

      <div className={layout.ratingFilters}>
        <div className={layout.ratingFilter}>
          <span>Пол</span>
          <div className="rating-segment">
            {GENDERS.map((g) => (
              <Link
                key={g.label}
                to={genderLink(g.value)}
                preventScrollReset
                aria-current={gender === g.value ? 'page' : undefined}
                className={gender === g.value ? 'is-active' : undefined}
              >
                {g.label}
              </Link>
            ))}
          </div>
        </div>

        {isCaptainOrAdmin && (
          <div className={layout.asOfFilter}>
            <label htmlFor="as-of-input">Срез на дату:</label>
            <input
              id="as-of-input"
              type="date"
              className={layout.asOfInput}
              value={asOf || ''}
              onChange={(e) => updateParam('as_of', e.target.value || null)}
            />
            {asOf && (
              <button
                type="button"
                className="btn-link"
                style={{ fontSize: '12px', cursor: 'pointer' }}
                onClick={() => updateParam('as_of', null)}
              >
                Сбросить
              </button>
            )}
          </div>
        )}
      </div>

      <AsyncView query={query}>
        {(rows) => <RatingBoard data={rows} athleteId={athleteId} loading={query.isFetching} />}
      </AsyncView>
    </div>
  );
}

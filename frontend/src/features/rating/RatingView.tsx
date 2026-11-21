import { paths } from '@/shared/config';
import { dateRu, parseId } from '@/shared/lib';
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

export function RatingView(): React.JSX.Element {
  const [params] = useSearchParams();
  const gender = z.enum(['M', 'F']).nullable().catch(null).parse(params.get('gender'));
  const athleteId = parseId(params.get('athlete_id'));

  const query = useRating(gender, athleteId);
  const data = query.data;

  const genderLink = (g: string | null) => {
    const q = new URLSearchParams();
    if (g) q.set('gender', g);
    if (athleteId) q.set('athlete_id', String(athleteId));
    const s = q.toString();
    return `${paths.rating}${s ? `?${s}` : ''}`;
  };

  return (
    <div className={layout.ratingPage}>
      <header className={layout.ratingPageHead}>
        <div>
          <h1 className={layout.ratingPageTitle}>Рейтинг</h1>
          <p className={layout.ratingPageSubtitle}>
            Последние 365 дней · обновлён {data ? dateRu(data.period_end) : '…'}
          </p>
        </div>
        <nav className={layout.ratingSports} aria-label="Виды спорта">
          <Link className={[layout.ratingSport, layout.ratingSportActive].join(' ')} to={paths.rating}>
            Бег
          </Link>
          <span className={[layout.ratingSport, layout.ratingSportDisabled].join(' ')}>Лыжи</span>
          <span className={[layout.ratingSport, layout.ratingSportDisabled].join(' ')}>Триатлон</span>
          <span className={[layout.ratingSport, layout.ratingSportDisabled].join(' ')}>Трейл</span>
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
      </div>

      <AsyncView query={query}>
        {(rows) => <RatingBoard data={rows} athleteId={athleteId} loading={query.isFetching} />}
      </AsyncView>
    </div>
  );
}

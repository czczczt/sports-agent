import type { RacePage as RacePageData } from '@/shared/api';
import { paths } from '@/shared/config';
import { fixed1, plural } from '@/shared/lib';
import { Link } from 'react-router-dom';
import { DistributionChart } from './DistributionChart';
import styles from './RaceDetail.module.css';

interface RaceStatisticsProps {
  data: RacePageData;
  search: string;
}
export function RaceStatistics({ data, search }: RaceStatisticsProps): React.JSX.Element {
  const { competition, rating_leaders: leaders } = data;
  const me = competition?.athlete_result ?? null;
  return (
    <div className="cols__side">
      {me && competition && (
        <section className={['card card--pad me-row', styles.personalResult].join(' ')}>
          <div className="row row--between">
            <h2 className="h2">Ваш результат</h2>
            {!!me.top_percent && <span className="chip chip--brand">топ {me.top_percent}%</span>}
          </div>
          <div className={['row', styles.performance].join(' ')}>
            <span className="display-num num">{me.place_abs || '—'}</span>
            <span className="muted">место из {competition.total_finishers}</span>
          </div>
          <div className="grid-2">
            <div className={['tile', styles.tile].join(' ')}>
              <div className="tile__value num">{me.time_formatted}</div>
              <div className="tile__label">время в протоколе</div>
            </div>
            <div className={['tile', styles.tile].join(' ')}>
              <div className="tile__value num">{me.pace_formatted}</div>
              <div className="tile__label">темп</div>
            </div>
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
              <span className={styles.leader}>
                <Link to={paths.athlete(r.athlete_id)} className="list-row__title">
                  {r.full_name_raw}
                </Link>{' '}
                <span className="list-row__meta">
                  место в общем рейтинге: {r.rating_rank} · {r.rating_starts}{' '}
                  {plural(r.rating_starts, 'старт', 'старта', 'стартов')}
                </span>
              </span>
              <span className="list-row__end">
                <span className="num strong">{fixed1(r.rating_points)}</span>{' '}
                <span className="list-row__meta">баллов</span>
              </span>
            </div>
          ))}
        </section>
      )}

      {competition && (
        <section className="card card--pad">
          <div>
            <h2 className="h2">Конкуренция</h2>
            <p className={['small muted', styles.chartCaption].join(' ')}>
              Распределение финишных времён{me && ' · ваш интервал выделен'}
            </p>
          </div>
          <div className="chart-box chart-box--sm">
            <DistributionChart competition={competition} />
          </div>
        </section>
      )}
    </div>
  );
}

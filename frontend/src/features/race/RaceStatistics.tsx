import type { RacePage as RacePageData } from '@/shared/api';
import { formatFullName } from '@/shared/lib';
import { useAuth } from '@/shared/session';
import { DistributionChart } from './DistributionChart';
import styles from './RaceDetail.module.css';

interface RaceStatisticsProps {
  data: RacePageData;
  athleteId: number | null;
}

export function RaceStatistics({ data, athleteId }: RaceStatisticsProps): React.JSX.Element {
  const { competition, results, pinned_athlete_result: pinned } = data;
  const me = competition?.athlete_result ?? null;
  const { user } = useAuth();
  const isOwnProfile = Boolean(
    user?.athlete_id != null && athleteId != null && user.athlete_id === athleteId,
  );
  const athleteName =
    pinned?.full_name_raw ||
    results.find((r) => athleteId != null && r.athlete_id === athleteId)?.full_name_raw;

  return (
    <div className="cols__side">
      {me && competition && (
        <section className={['card card--pad me-row', styles.personalResult].join(' ')}>
          <div className="row row--between">
            <h2 className="h2">
              {isOwnProfile
                ? 'Ваш результат'
                : athleteName
                  ? formatFullName(athleteName)
                  : 'Спортсмен'}
            </h2>
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

      {competition && (
        <section className="card card--pad">
          <div>
            <h2 className="h2">Конкуренция</h2>
            <p className={['small muted', styles.chartCaption].join(' ')}>
              Распределение финишных времён
              {me && (isOwnProfile ? ' · ваш интервал выделен' : ' · интервал спортсмена выделен')}
            </p>
          </div>
          <div className="chart-box chart-box--sm">
            <DistributionChart competition={competition} isOwnProfile={isOwnProfile} />
          </div>
        </section>
      )}
    </div>
  );
}

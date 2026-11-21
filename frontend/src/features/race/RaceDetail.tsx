import type { RacePage as RacePageData } from '@/shared/api';
import { paths } from '@/shared/config';
import { dateRu, hms, plural } from '@/shared/lib';
import { BackLink, DistancePills, Icon } from '@/shared/ui';
import { Link } from 'react-router-dom';
import styles from './RaceDetail.module.css';
import { RaceProtocol } from './RaceProtocol';
import { RaceStatistics } from './RaceStatistics';

interface RaceDetailProps {
  data: RacePageData;
  athleteId: number | null;
  search: string;
  onSearch: (value: string) => void;
}

export function RaceDetail({ data, athleteId, search, onSearch }: RaceDetailProps): React.JSX.Element {
  const { race, event, results, competition } = data;
  const finCount = competition ? competition.total_finishers : results.length;
  const place = event?.place || event?.address;

  return (
    <>
      {event && <BackLink to={paths.event(event.id)}>{event.title}</BackLink>}

      <section className="card card--clip">
        <div className="finish-flag" />
        <div className={styles.header}>
          <div className="chips">
            <span className="chip chip--run">
              <Icon name="run" className="icon-sm" />
              Бег
            </span>
          </div>
          <h1 className="h1 h1-sm">{race.name_raw}</h1>
          {event && (
            <div className="muted num">
              <Link to={paths.event(event.id)} className={styles.event}>
                {event.title}
              </Link>{' '}
              · {dateRu(event.date_begin)}
              {place && ` · ${place}`}
            </div>
          )}
          <div className={['grid-2', styles.metrics].join(' ')}>
            <div className="tile">
              <div className="tile__value num">{finCount}</div>
              <div className="tile__label">{plural(finCount, 'финишёр', 'финишёра', 'финишёров')}</div>
            </div>
            {competition && (
              <>
                <div className="tile">
                  <div className="tile__value num">{hms(competition.median_time_s)}</div>
                  <div className="tile__label">медиана</div>
                </div>
                <div className="tile">
                  <div className="tile__value num">{hms(competition.p25_time_s)}</div>
                  <div className="tile__label">граница топ-25%</div>
                </div>
              </>
            )}
            {!!race.distance_m && (
              <div className="tile">
                <div className="tile__value num">{race.distance_m} м</div>
                <div className="tile__label">длина</div>
              </div>
            )}
          </div>
        </div>
      </section>

      {event && event.races.length > 1 && (
        <DistancePills
          label="Дистанции старта"
          activeId={race.id}
          items={event.races.map((r) => ({ id: r.id, label: r.name_raw, to: paths.race(r.id, athleteId) }))}
        />
      )}

      <div className="track-divider" />

      <div className="cols">
        <RaceStatistics data={data} search={search} />
        <RaceProtocol data={data} athleteId={athleteId} search={search} onSearch={onSearch} />
      </div>
    </>
  );
}

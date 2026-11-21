import type { AthleteResultItem, AthleteSummary } from '@/shared/api';
import { paths } from '@/shared/config';
import { athleteMeta, dateRu, fixed1, initials, plural } from '@/shared/lib';
import { BackLink, Icon } from '@/shared/ui';
import { Link } from 'react-router-dom';
import { AssessmentCard } from './AssessmentCard';
import styles from './AthleteProfile.module.css';
import { AthleteResults } from './AthleteResults';
import { PaceChart } from './PaceChart';

interface AthleteProfileProps {
  summary: AthleteSummary;
  results: AthleteResultItem[];
}

export function AthleteProfile({ summary, results }: AthleteProfileProps): React.JSX.Element {
  const a = summary.athlete;
  const pbCount = summary.personal_bests.length;

  return (
    <>
      <BackLink to={paths.search}>Найти себя</BackLink>

      <section className="card profile-head">
        <div className={['row', styles.identity].join(' ')}>
          <span className="avatar avatar--lg" aria-hidden="true">
            {initials(a.display_name)}
          </span>
          <div className={styles.name}>
            <h1 className="h1 h1-sm">{a.display_name}</h1>
            <div className={['muted num', styles.meta].join(' ')}>{athleteMeta(a)}</div>
          </div>
        </div>
      </section>

      <div className="cols">
        <div className="cols__side">
          <div className="grid-2">
            <div className="card card--accent stat">
              <span className="stat__label stat__label--run">
                <Icon name="run" className="icon-sm" />
                Бег
              </span>
              <span className="display-num num">{summary.total_starts}</span>
              <span className="small muted">
                {plural(summary.total_starts, 'финиш', 'финиша', 'финишей')}
              </span>
            </div>
            <div className="card stat">
              <span className="stat__label stat__label--brand">
                <Icon name="trophy" className="icon-sm" />
                Рекорды
              </span>
              <span className="display-num num">{pbCount}</span>
              <span className="small muted">
                {plural(pbCount, 'личный рекорд', 'личных рекорда', 'личных рекордов')}
              </span>
            </div>
          </div>

          <section className={`card card--pad${summary.rating.status === 'no_data' ? ' card--pending' : ''}`}>
            {summary.rating.rank ? (
              <div className={['grid-2', styles.stats].join(' ')}>
                <div>
                  <Link
                    to={paths.ratingFor(a.id)}
                    className="rating-profile-link"
                    title="Открыть в общем рейтинге"
                  >
                    <h2 className={['h2 rating-hover-target', styles.statTitle].join(' ')}>Место</h2>
                    <div className="display-num num rating-hover-target rating-big-num">
                      {summary.rating.rank}
                    </div>
                  </Link>
                </div>
                <div>
                  <Link
                    to={paths.ratingFormula}
                    className="points-profile-link"
                    title="Как рассчитываются баллы"
                  >
                    <h2 className={['h2 rating-hover-target-points', styles.statTitle].join(' ')}>Баллы</h2>
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
                <p className={['small', styles.period].join(' ')}>
                  Недостаточно данных для рейтинга за последние 365 дней.
                </p>
              </>
            )}
          </section>

          <section className="card card--clip">
            <div className="card__head">
              <h2 className="h2">Личные рекорды</h2>
            </div>
            {pbCount ? (
              summary.personal_bests.map((pb) => (
                <div key={pb.norm_distance} className="list-row">
                  <div className={styles.name}>
                    <div className="list-row__title strong">{pb.distance_title}</div>
                    <div className="list-row__meta" title={pb.event_title}>
                      {dateRu(pb.event_date)} · {pb.event_title}
                    </div>
                  </div>
                  <div className="list-row__end">
                    <div className={['num strong', styles.subtitle].join(' ')}>{pb.time_formatted}</div>
                    <div className="list-row__meta num">{pb.pace_formatted}</div>
                  </div>
                </div>
              ))
            ) : (
              <div className={styles.empty}>
                <p className="small muted">Недостаточно данных.</p>
              </div>
            )}
          </section>

          <section className="card card--pad">
            <h2
              className={['h2', styles.chartTitle].join(' ')}
              data-populated={summary.dynamics.length || undefined}
            >
              Темп по стартам
            </h2>
            {summary.dynamics.length ? (
              <div className={['chart-box chart-box--sm', styles.chart].join(' ')}>
                <PaceChart data={summary.dynamics} />
              </div>
            ) : (
              <p className="small muted">Недостаточно данных для графика.</p>
            )}
          </section>
        </div>

        <div className="cols__main">
          <AssessmentCard athleteId={a.id} />

          <AthleteResults results={results} athleteId={a.id} />
        </div>
      </div>
    </>
  );
}

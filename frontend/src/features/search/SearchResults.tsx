import { paths } from '@/shared/config';
import { athleteMeta, initials, plural } from '@/shared/lib';
import { AsyncView, EmptyState, Icon } from '@/shared/ui';
import { Link } from 'react-router-dom';
import styles from './SearchResults.module.css';
import { useCandidates } from './useCandidates';

interface SearchResultsProps {
  lastName: string;
  birthYear: number;
}

export function SearchResults({ lastName, birthYear }: SearchResultsProps): React.JSX.Element {
  const query = useCandidates(lastName, birthYear);

  return (
    <AsyncView query={query} loadingText="Ищем спортсменов…">
      {(candidates) => (
        <>
          <div className="row row--between">
            <h2 className={['strong', styles.heading].join(' ')}>
              {candidates.length
                ? `Нашли ${candidates.length} ${plural(candidates.length, 'спортсмена', 'спортсмена', 'спортсменов')}`
                : 'Никого не нашли'}
            </h2>
          </div>

          {candidates.length ? (
            <div className="grid-cards">
              {candidates.map((cand) => {
                const meta = athleteMeta(cand);
                const fullName =
                  cand.middle_name && !cand.display_name.includes(cand.middle_name)
                    ? `${cand.display_name} ${cand.middle_name}`
                    : cand.display_name;
                return (
                  <div key={cand.id} className="card card--pad candidate-card">
                    <div className="row candidate-card__head">
                      <span className="avatar" aria-hidden="true">
                        {initials(cand.display_name)}
                      </span>
                      <div className={styles.identity}>
                        <div className="strong candidate-card__name">{fullName}</div>
                        <div className="small muted num candidate-card__meta" title={meta}>
                          {meta}
                        </div>
                      </div>
                    </div>
                    <div className={['chips', styles.chips].join(' ')}>
                      <Link
                        to={paths.athlete(cand.id)}
                        className="chip chip--run"
                        title="Открыть результаты в беге"
                      >
                        <Icon name="run" className="icon-sm" />
                        Бег · {cand.starts_count} {plural(cand.starts_count, 'старт', 'старта', 'стартов')}
                      </Link>
                      {cand.employee_status === 'confirmed' && (
                        <span className="chip chip--sm chip--brand">Сотрудник Сбера</span>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <EmptyState
              title="Спортсмен не найден"
              text="Проверьте написание фамилии или уберите год рождения."
            />
          )}
        </>
      )}
    </AsyncView>
  );
}

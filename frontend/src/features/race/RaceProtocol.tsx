import type { RacePage as RacePageData, RaceProtocolItem } from '@/shared/api';
import { paths } from '@/shared/config';
import { EmptyState } from '@/shared/ui';
import { ProtocolListRow } from './ProtocolListRow';
import { ProtocolSearch } from './ProtocolSearch';
import { ProtocolTableRow } from './ProtocolTableRow';
import styles from './RaceDetail.module.css';

interface RaceProtocolProps {
  data: RacePageData;
  athleteId: number | null;
  search: string;
  onSearch: (value: string) => void;
}
export function RaceProtocol({ data, athleteId, search, onSearch }: RaceProtocolProps): React.JSX.Element {
  const { race, results, pinned_athlete_result: pinned } = data;
  const isMe = (r: RaceProtocolItem) => !!athleteId && r.athlete_id === athleteId;
  return (
    <section className={['cols__main card card--clip', styles.protocol].join(' ')}>
      <div className="card__head">
        <h2 className="h2">Протокол</h2>
        <ProtocolSearch
          key={`${race.id}:${search}`}
          initial={search}
          onSearch={onSearch}
          resetTo={paths.race(race.id, athleteId)}
        />
      </div>

      {results.length || pinned ? (
        <>
          <div className="table-wrap only-desktop">
            <table className={['table', styles.table].join(' ')}>
              <thead>
                <tr>
                  <th scope="col">Место</th>
                  <th scope="col">Участник</th>
                  <th scope="col">Пол / возраст</th>
                  <th scope="col">Время в протоколе</th>
                  <th scope="col">Пистолетное</th>
                  <th scope="col">Темп</th>
                  <th scope="col">Баллы</th>
                  <th scope="col">Статус</th>
                </tr>
              </thead>
              <tbody>
                {pinned && (
                  <>
                    <ProtocolTableRow r={pinned} isMe />
                    <tr className="gap-row">
                      <td className="muted gap-row__dots">
                        &bull;
                        <br />
                        &bull;
                        <br />
                        &bull;
                      </td>
                      <td colSpan={7} className="gap-row__rest" />
                    </tr>
                  </>
                )}
                {results.map((r) => (
                  <ProtocolTableRow key={r.result_id} r={r} isMe={isMe(r)} />
                ))}
              </tbody>
            </table>
          </div>

          <div className="only-mobile">
            {pinned && (
              <>
                <ProtocolListRow r={pinned} isMe />
                <div className="list-row list-row--place list-row--gap">
                  <span className="muted">
                    &bull;
                    <br />
                    &bull;
                    <br />
                    &bull;
                  </span>
                  <div />
                </div>
              </>
            )}
            {results.map((r) => (
              <ProtocolListRow key={r.result_id} r={r} isMe={isMe(r)} />
            ))}
          </div>
        </>
      ) : (
        <EmptyState inCard={false} text={search ? `По запросу «${search}» никого нет.` : 'Протокол пуст.'} />
      )}
    </section>
  );
}

import type { RatingPage as RatingPageData } from '@/shared/api';
import { paths } from '@/shared/config';
import { fixed1 } from '@/shared/lib';
import { Icon } from '@/shared/ui';
import { useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import { RatingTableRow } from './RatingTableRow';
import layout from './RatingView.module.css';

interface RatingBoardProps {
  data: RatingPageData;
  athleteId: number | null;
  loading: boolean;
}

export function RatingBoard({ data, athleteId, loading }: RatingBoardProps): React.JSX.Element {
  const me = data.me_row;
  const meInRows = !!me && data.rows.some((r) => r.athlete_id === athleteId);
  const scrolledFor = useRef<string | null>(null);

  useEffect(() => {
    const key = `${athleteId}`;
    if (!athleteId || loading || scrolledFor.current === key) return;
    const t = setTimeout(() => {
      const row = document.getElementById('me-row');
      if (!row) return;
      scrolledFor.current = key;
      row.scrollIntoView({
        behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth',
        block: 'center',
      });
    }, 150);
    return () => clearTimeout(t);
  }, [athleteId, loading]);

  return (
    <div className={layout.ratingLayout}>
      <section className={layout.ratingBoard}>
        {data.rows.length ? (
          <>
            <div className="rating-table-wrap">
              <table className={layout.ratingTable}>
                <thead>
                  <tr>
                    <th scope="col">Место</th>
                    <th scope="col">Спортсмен</th>
                    <th scope="col" className="right">
                      Баллы
                    </th>
                    <th scope="col" className="right">
                      Стартов
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {me && !meInRows && (
                    <>
                      <RatingTableRow row={me} isMe plainPlace />
                      <tr className="gap-row">
                        <td className="muted gap-row__dots">
                          &bull;
                          <br />
                          &bull;
                          <br />
                          &bull;
                        </td>
                        <td colSpan={3} className="gap-row__rest" />
                      </tr>
                    </>
                  )}
                  {data.rows.map((row) => (
                    <RatingTableRow
                      key={row.athlete_id}
                      row={row}
                      isMe={!!athleteId && row.athlete_id === athleteId}
                    />
                  ))}
                </tbody>
              </table>
            </div>
            <div className={layout.ratingBoardFooter}>
              1–{data.rows.length} из {data.total}
            </div>
          </>
        ) : (
          <div className="empty">
            <span className="empty__icon">
              <Icon name="trophy" />
            </span>
            <div className="strong">Рейтинг пока пуст</div>
          </div>
        )}
      </section>

      <aside className={layout.ratingSidebar}>
        {me && (
          <section className={layout.ratingSideCard}>
            <strong className={layout.ratingSideCardRank}>{me.rank}</strong>
            <p className={layout.ratingSideCardMuted}>
              {me.display_name} · {fixed1(me.points)} балла
            </p>
            <Link to={paths.athlete(me.athlete_id)} className={layout.ratingSideCardLink}>
              В профиль →
            </Link>
          </section>
        )}
        <section className={layout.ratingSideCard}>
          <Link to={paths.ratingFormula} className={layout.ratingSideCardTitleLink}>
            Как считается беговой рейтинг
          </Link>
        </section>
      </aside>
    </div>
  );
}

import type { RatingRow } from '@/shared/api';
import { paths } from '@/shared/config';
import { fixed1, formatFullName } from '@/shared/lib';
import { Link } from 'react-router-dom';
import layout from './RatingView.module.css';

interface RatingTableRowProps {
  row: RatingRow;
  isMe: boolean;
  plainPlace?: boolean;
}

export function RatingTableRow({ row, isMe, plainPlace = false }: RatingTableRowProps): React.JSX.Element {
  const medal = !plainPlace && row.rank <= 3 ? row.rank : 'plain';
  return (
    <tr className={isMe ? 'me-row' : undefined} id={isMe ? 'me-row' : undefined}>
      <td>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <span className={`rating-place rating-place--${medal}`}>{row.rank}</span>
          {row.rank_delta !== null && row.rank_delta !== undefined && (
            <span
              className={
                row.rank_delta > 0
                  ? layout.rankDeltaUp
                  : row.rank_delta < 0
                  ? layout.rankDeltaDown
                  : layout.rankDeltaNeutral
              }
              title={`Динамика за месяц: ${row.rank_delta > 0 ? `+${row.rank_delta}` : row.rank_delta}`}
            >
              {row.rank_delta > 0 ? `▲${row.rank_delta}` : row.rank_delta < 0 ? `▼${Math.abs(row.rank_delta)}` : '—'}
            </span>
          )}
        </div>
      </td>
      <td>
        <Link to={paths.athlete(row.athlete_id)} className={layout.ratingAthlete}>
          {formatFullName(row.display_name)}
        </Link>
        <span className={layout.ratingBirth}>{row.birth_year || 'год не указан'}</span>
      </td>
      <td className="right strong num">{fixed1(row.points)}</td>
      <td className="right muted num">{row.starts_count}</td>
    </tr>
  );
}

import type { RaceProtocolItem } from '@/shared/api';
import { fixed1, genderLabel } from '@/shared/lib';
import { StatusChip } from '@/shared/ui';
import { ageText } from './ageText';
import { AthleteName } from './AthleteName';
import styles from './ProtocolListRow.module.css';

interface ProtocolListRowProps {
  r: RaceProtocolItem;
  isMe: boolean;
}

export function ProtocolListRow({ r, isMe }: ProtocolListRowProps): React.JSX.Element {
  const age = ageText(r);
  return (
    <div className={`list-row list-row--place${isMe ? ' me-row' : ''}`}>
      <span className="num strong muted">{r.place_abs || '—'}</span>
      <div className={styles.name}>
        <div className={['row', styles.identity].join(' ')}>
          <AthleteName r={r} className="list-row__title" />
          {isMe && <span className={['small strong', styles.currentAthlete].join(' ')}>это вы</span>}
        </div>
        <div className="list-row__meta num">
          {r.pace_formatted}
          {r.gender && ` · ${genderLabel(r.gender)}`}
          {age && ` ${age}`}
          {r.club_raw && ` · ${r.club_raw}`}
        </div>
      </div>
      <div className="list-row__end">
        <div className="num strong">{r.time_formatted}</div>
        {r.points != null && (
          <div className="small num" style={{ color: 'var(--brand-text)' }}>
            {fixed1(r.points)} б.
          </div>
        )}
        {r.status !== 'FIN' && <StatusChip status={r.status} />}
      </div>
    </div>
  );
}

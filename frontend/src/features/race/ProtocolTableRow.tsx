import type { RaceProtocolItem } from '@/shared/api';
import { genderLabel, hms } from '@/shared/lib';
import { StatusChip } from '@/shared/ui';
import { ageText } from './ageText';
import { AthleteName } from './AthleteName';
import styles from './ProtocolTableRow.module.css';

interface ProtocolTableRowProps {
  r: RaceProtocolItem;
  isMe: boolean;
}

export function ProtocolTableRow({ r, isMe }: ProtocolTableRowProps): React.JSX.Element {
  const age = ageText(r);
  return (
    <tr className={isMe ? 'me-row' : undefined}>
      <td className="num strong">{r.place_abs || '—'}</td>
      <td>
        <AthleteName r={r} className="cell-title" />
        {isMe && (
          <>
            {' '}
            <span className={['small strong', styles.currentAthlete].join(' ')}>это вы</span>
          </>
        )}
        <div className="cell-sub num">
          {r.bib ? `№ ${r.bib}` : ''}
          {r.bib && r.club_raw ? ' · ' : ''}
          {r.club_raw || ''}
        </div>
      </td>
      <td className="muted num nowrap">
        {genderLabel(r.gender) || '—'}
        {age && ` · ${age}`}
      </td>
      <td className="num strong nowrap">{r.time_formatted}</td>
      <td className="num muted nowrap">{hms(r.gun_time_s)}</td>
      <td className="num nowrap">{r.pace_formatted}</td>
      <td>
        <StatusChip status={r.status} />
      </td>
    </tr>
  );
}

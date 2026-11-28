import type { RaceProtocolItem } from '@/shared/api';
import { paths } from '@/shared/config';
import { formatFullName } from '@/shared/lib';
import { Link } from 'react-router-dom';

interface AthleteNameProps {
  r: RaceProtocolItem;
  className: string;
}

export function AthleteName({ r, className }: AthleteNameProps): React.JSX.Element {
  const displayName = formatFullName(r.full_name_raw);
  return r.athlete_id ? (
    <Link to={paths.athlete(r.athlete_id)} className={className}>
      {displayName}
    </Link>
  ) : (
    <span className={className}>{displayName}</span>
  );
}

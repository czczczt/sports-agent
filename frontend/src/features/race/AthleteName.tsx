import type { RaceProtocolItem } from '@/shared/api';
import { paths } from '@/shared/config';
import { Link } from 'react-router-dom';

interface AthleteNameProps {
  r: RaceProtocolItem;
  className: string;
}

export function AthleteName({ r, className }: AthleteNameProps): React.JSX.Element {
  return r.athlete_id ? (
    <Link to={paths.athlete(r.athlete_id)} className={className}>
      {r.full_name_raw}
    </Link>
  ) : (
    <span className={className}>{r.full_name_raw}</span>
  );
}

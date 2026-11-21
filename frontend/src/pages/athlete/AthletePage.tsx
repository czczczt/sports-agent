import { AthleteView } from '@/features/athlete';
import { parseId } from '@/shared/lib';
import { NotFound } from '@/shared/ui';
import { useParams } from 'react-router-dom';

export function AthletePage(): React.JSX.Element {
  const athleteId = parseId(useParams().athleteId);
  if (athleteId === null) return <NotFound title="Спортсмен не найден" />;
  return <AthleteView athleteId={athleteId} />;
}

import { RaceView } from '@/features/race';
import { paths } from '@/shared/config';
import { parseId } from '@/shared/lib';
import { NotFound } from '@/shared/ui';
import { useParams } from 'react-router-dom';

export function RacePage(): React.JSX.Element {
  const raceId = parseId(useParams().raceId);
  if (raceId === null)
    return <NotFound title="Дистанция не найдена" backTo={paths.events} backLabel="Старты" />;
  return <RaceView raceId={raceId} />;
}

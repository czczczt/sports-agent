import { paths } from '@/shared/config';
import { KEEP_SCROLL, useDocumentTitle } from '@/shared/hooks';
import { parseId } from '@/shared/lib';
import { AsyncView, NotFound } from '@/shared/ui';
import { useSearchParams } from 'react-router-dom';
import { RaceDetail } from './RaceDetail';
import { useRace } from './useRace';

interface RaceViewProps {
  raceId: number;
}

export function RaceView({ raceId }: RaceViewProps): React.JSX.Element {
  const [params, setParams] = useSearchParams();
  const search = params.get('search') || '';
  const athleteId = parseId(params.get('athlete_id'));

  const query = useRace(raceId, search, athleteId);
  const data = query.data;
  useDocumentTitle(data ? `${data.race.name_raw} — ${data.event?.title ?? 'Старты'}` : undefined);

  const setSearch = (value: string) => {
    const q: Record<string, string> = {};
    if (athleteId) q.athlete_id = String(athleteId);
    if (value) q.search = value;
    setParams(q, KEEP_SCROLL);
  };

  return (
    <AsyncView
      query={query}
      notFound={<NotFound title="Дистанция не найдена" backTo={paths.events} backLabel="Старты" />}
    >
      {(data) => (
        <RaceDetail key={raceId} data={data} athleteId={athleteId} search={search} onSearch={setSearch} />
      )}
    </AsyncView>
  );
}

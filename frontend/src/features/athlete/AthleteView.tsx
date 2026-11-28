import { SITE_TITLE, useDocumentTitle } from '@/shared/hooks';
import { formatFullName } from '@/shared/lib';
import { AsyncView, NotFound } from '@/shared/ui';
import { AthleteProfile } from './AthleteProfile';
import { useAthlete } from './useAthlete';

interface AthleteViewProps {
  athleteId: number;
}

export function AthleteView({ athleteId }: AthleteViewProps): React.JSX.Element {
  const query = useAthlete(athleteId);
  const data = query.data;
  useDocumentTitle(data ? `${formatFullName(data[0].athlete.display_name)} — ${SITE_TITLE}` : undefined);

  return (
    <AsyncView query={query} notFound={<NotFound title="Спортсмен не найден" />}>
      {(data) => <AthleteProfile key={athleteId} summary={data[0]} results={data[1]} />}
    </AsyncView>
  );
}

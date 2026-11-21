import { EventView } from '@/features/event';
import { paths } from '@/shared/config';
import { parseId } from '@/shared/lib';
import { NotFound } from '@/shared/ui';
import { useParams } from 'react-router-dom';

export function EventPage(): React.JSX.Element {
  const eventId = parseId(useParams().eventId);
  if (eventId === null) return <NotFound title="Старт не найден" backTo={paths.events} backLabel="Старты" />;
  return <EventView eventId={eventId} />;
}

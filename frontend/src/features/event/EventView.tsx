import { paths } from '@/shared/config';
import { useDocumentTitle } from '@/shared/hooks';
import { AsyncView, NotFound } from '@/shared/ui';
import { EventDetail } from './EventDetail';
import { useEvent } from './useEvent';

interface EventViewProps {
  eventId: number;
}

export function EventView({ eventId }: EventViewProps): React.JSX.Element {
  const query = useEvent(eventId);
  const event = query.data;
  useDocumentTitle(event ? `${event.title} — Старты` : undefined);

  return (
    <AsyncView
      query={query}
      notFound={<NotFound title="Старт не найден" backTo={paths.events} backLabel="Старты" />}
    >
      {(event) => <EventDetail event={event} />}
    </AsyncView>
  );
}

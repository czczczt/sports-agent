import type { EventFilters } from '@/features/events';
import { eventFilters, EventsView } from '@/features/events';
import { KEEP_SCROLL, SITE_TITLE, useDocumentTitle } from '@/shared/hooks';
import { useSearchParams } from 'react-router-dom';

const FILTER_KEYS = ['query', 'date_from', 'date_to', 'city', 'source'] as const;

function readFilters(params: URLSearchParams): EventFilters {
  return eventFilters.parse({
    query: params.get('query') || params.get('title') || '',
    date_from: params.get('date_from') || '',
    date_to: params.get('date_to') || '',
    city: params.get('city') || '',
    source: params.get('source') || '',
  });
}

export function EventsPage(): React.JSX.Element {
  useDocumentTitle('Старты — ' + SITE_TITLE);
  const [params, setParams] = useSearchParams();
  const filters = readFilters(params);
  const apply = (next: EventFilters) => {
    const q: Record<string, string> = {};
    for (const k of FILTER_KEYS) if (next[k]) q[k] = next[k];
    setParams(q, KEEP_SCROLL);
  };
  return <EventsView filters={filters} onApply={apply} onReset={() => setParams({}, KEEP_SCROLL)} />;
}

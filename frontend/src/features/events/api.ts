import { client, responseData } from '@/shared/api';

import type { EventFilters } from './filters';

export const eventsApi = {
  list: (filters: EventFilters, signal?: AbortSignal) =>
    responseData(client.GET('/api/events', { params: { query: { ...filters, limit: 60 } }, signal })),
};

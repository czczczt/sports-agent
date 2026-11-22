import type { components } from '@/shared/api';
import { client, responseData } from '@/shared/api';

import type { EventFilters } from './filters';

export const eventsApi = {
  list: (filters: EventFilters, signal?: AbortSignal) =>
    responseData(client.GET('/api/events', { params: { query: { ...filters, limit: 60 } }, signal })),
  createPlanned: (body: components['schemas']['PlannedEventCreate']) =>
    responseData(client.POST('/api/admin/events/planned', { body })),
};

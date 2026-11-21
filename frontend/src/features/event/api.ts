import { client, responseData } from '@/shared/api';

export const eventsApi = {
  get: (id: number, signal?: AbortSignal) =>
    responseData(client.GET('/api/events/{event_id}', { params: { path: { event_id: id } }, signal })),
};

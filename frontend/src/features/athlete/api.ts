import { client, responseData } from '@/shared/api';

export const athletesApi = {
  summary: (id: number, signal?: AbortSignal) =>
    responseData(
      client.GET('/api/athletes/{athlete_id}/summary', { params: { path: { athlete_id: id } }, signal }),
    ),
  results: (id: number, signal?: AbortSignal) =>
    responseData(
      client.GET('/api/athletes/{athlete_id}/results', { params: { path: { athlete_id: id } }, signal }),
    ),
  assessment: (id: number) =>
    responseData(
      client.POST('/api/athletes/{athlete_id}/assessment', { params: { path: { athlete_id: id } } }),
    ),
};

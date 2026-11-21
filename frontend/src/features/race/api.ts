import { client, responseData } from '@/shared/api';

export const racesApi = {
  page: (id: number, params: { search?: string; athlete_id?: number | null }, signal?: AbortSignal) =>
    responseData(
      client.GET('/api/races/{race_id}', { params: { path: { race_id: id }, query: params }, signal }),
    ),
};

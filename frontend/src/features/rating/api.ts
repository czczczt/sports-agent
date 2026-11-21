import { client, responseData } from '@/shared/api';

export const ratingApi = {
  page: (params: { gender?: string | null; athlete_id?: number | null }, signal?: AbortSignal) =>
    responseData(client.GET('/api/rating', { params: { query: params }, signal })),
};

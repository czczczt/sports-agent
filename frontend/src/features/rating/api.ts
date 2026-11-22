import { client, responseData } from '@/shared/api';

export const ratingApi = {
  page: (
    params: {
      sport?: string;
      as_of?: string | null;
      gender?: string | null;
      athlete_id?: number | null;
      search?: string | null;
    },
    signal?: AbortSignal
  ) =>
    responseData(client.GET('/api/rating', { params: { query: params }, signal })),
};

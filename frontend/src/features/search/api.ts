import { client, responseData } from '@/shared/api';

export const athletesApi = {
  search: (lastName: string, birthYear: number, signal?: AbortSignal) =>
    responseData(
      client.GET('/api/athletes/search', {
        params: { query: { last_name: lastName, birth_year: birthYear, limit: 50 } },
        signal,
      }),
    ),
};

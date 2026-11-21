import { client, responseData } from '@/shared/api';

export const ratingApi = {
  formula: (signal?: AbortSignal) => responseData(client.GET('/api/rating/formula', { signal })),
};

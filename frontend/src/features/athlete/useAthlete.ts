import { useQuery } from '@tanstack/react-query';
import { athletesApi } from './api';

export const athleteKey = (athleteId: number) => ['athlete', athleteId] as const;

export function useAthlete(athleteId: number) {
  return useQuery({
    queryKey: athleteKey(athleteId),
    queryFn: ({ signal }) =>
      Promise.all([athletesApi.summary(athleteId, signal), athletesApi.results(athleteId, signal)]),
  });
}

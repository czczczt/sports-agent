import { useQuery } from '@tanstack/react-query';
import { ratingApi } from './api';

export const ratingKey = (
  sport: string,
  asOf: string | null,
  gender: string | null,
  athleteId: number | null
) => ['rating', sport, asOf, gender, athleteId] as const;

export function useRating(
  sport: string = 'run',
  asOf: string | null = null,
  gender: string | null = null,
  athleteId: number | null = null
) {
  return useQuery({
    queryKey: ratingKey(sport, asOf, gender, athleteId),
    queryFn: ({ signal }) =>
      ratingApi.page({ sport, as_of: asOf, gender, athlete_id: athleteId }, signal),
  });
}

import { useQuery } from '@tanstack/react-query';
import { ratingApi } from './api';

export const ratingKey = (gender: string | null, athleteId: number | null) =>
  ['rating', gender, athleteId] as const;

export function useRating(gender: string | null, athleteId: number | null) {
  return useQuery({
    queryKey: ratingKey(gender, athleteId),
    queryFn: ({ signal }) => ratingApi.page({ gender, athlete_id: athleteId }, signal),
  });
}

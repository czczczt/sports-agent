import { useQuery } from '@tanstack/react-query';
import { racesApi } from './api';

export const raceKey = (raceId: number, search: string, athleteId: number | null) =>
  ['race', raceId, search, athleteId] as const;

export function useRace(raceId: number, search: string, athleteId: number | null) {
  return useQuery({
    queryKey: raceKey(raceId, search, athleteId),
    queryFn: ({ signal }) => racesApi.page(raceId, { search, athlete_id: athleteId }, signal),
  });
}

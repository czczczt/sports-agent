import { useQuery } from '@tanstack/react-query';
import { racesApi } from './api';

export const raceKey = (
  raceId: number,
  search: string,
  athleteId: number | null,
  employeesOnly: boolean = true,
) => ['race', raceId, search, athleteId, employeesOnly] as const;

export function useRace(
  raceId: number,
  search: string,
  athleteId: number | null,
  employeesOnly: boolean = true,
) {
  return useQuery({
    queryKey: raceKey(raceId, search, athleteId, employeesOnly),
    queryFn: ({ signal }) =>
      racesApi.page(raceId, { search, athlete_id: athleteId, employees_only: employeesOnly }, signal),
  });
}

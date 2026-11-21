import { useQuery } from '@tanstack/react-query';
import { athletesApi } from './api';

export const candidatesKey = (lastName: string, birthYear: number) =>
  ['search', lastName, birthYear] as const;

export function useCandidates(lastName: string, birthYear: number) {
  return useQuery({
    queryKey: candidatesKey(lastName, birthYear),
    queryFn: ({ signal }) => athletesApi.search(lastName, birthYear, signal),
  });
}

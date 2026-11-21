import { useQuery } from '@tanstack/react-query';
import { eventsApi } from './api';
import type { EventFilters } from './filters';

export const eventsKey = (filters: EventFilters) => ['events', filters] as const;

export function useEvents(filters: EventFilters) {
  return useQuery({ queryKey: eventsKey(filters), queryFn: ({ signal }) => eventsApi.list(filters, signal) });
}

import { useQuery } from '@tanstack/react-query';
import { eventsApi } from './api';

export const eventKey = (eventId: number) => ['event', eventId] as const;

export function useEvent(eventId: number) {
  return useQuery({ queryKey: eventKey(eventId), queryFn: ({ signal }) => eventsApi.get(eventId, signal) });
}

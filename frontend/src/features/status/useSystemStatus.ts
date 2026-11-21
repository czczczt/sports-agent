import { client, responseData } from '@/shared/api';
import { useQuery } from '@tanstack/react-query';

export const systemStatusKey = () => ['status'] as const;

export function useSystemStatus() {
  return useQuery({
    queryKey: systemStatusKey(),
    queryFn: ({ signal }) => responseData(client.GET('/api/status', { signal })),
  });
}

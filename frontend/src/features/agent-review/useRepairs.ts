import type { ReviewDecision } from '@/shared/api';
import { client, responseData } from '@/shared/api';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

export const repairsKey = () => ['agent-review', 'recipes'] as const;

export function useRepairs() {
  return useQuery({
    queryKey: repairsKey(),
    queryFn: ({ signal }) => responseData(client.GET('/api/agent-review/recipes', { signal })),
    refetchInterval: (query) =>
      query.state.data?.some((repair) => repair.status === 'running') ? 5000 : false,
  });
}
export function useRepairDecision(id: number) {
  const cache = useQueryClient();
  return useMutation({
    mutationFn: (body: ReviewDecision) =>
      responseData(
        client.POST('/api/agent-review/recipes/{repair_id}/decision', {
          params: { path: { repair_id: id } },
          body,
        }),
      ),
    onSuccess: () => cache.invalidateQueries({ queryKey: repairsKey() }),
  });
}

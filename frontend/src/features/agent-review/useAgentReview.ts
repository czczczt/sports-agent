import { useQuery } from '@tanstack/react-query';
import { agentReviewApi } from './api';

export const agentReviewKey = (status: string, source: string) => ['agent-review', status, source] as const;

export function useAgentReview(status: string, source: string, enabled: boolean) {
  return useQuery({
    queryKey: agentReviewKey(status, source),
    queryFn: ({ signal }) => agentReviewApi.page({ status, source }, signal),
    enabled,
  });
}

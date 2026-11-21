import type { ReviewAction } from '@/shared/api';
import { client, responseData } from '@/shared/api';

export const agentReviewApi = {
  page: (params: { status: string; source?: string }, signal?: AbortSignal) =>
    responseData(client.GET('/api/agent-review/page', { params: { query: params }, signal })),
  decide: (id: number, body: ReviewAction) =>
    responseData(
      client.POST('/api/agent-review/{issue_id}/decide', { params: { path: { issue_id: id } }, body: body }),
    ),
  reset: (id: number) =>
    responseData(client.POST('/api/agent-review/{issue_id}/reset', { params: { path: { issue_id: id } } })),
  apply: (id: number, push: boolean) =>
    responseData(
      client.POST('/api/agent-review/{issue_id}/apply', {
        params: { path: { issue_id: id } },
        body: { push },
      }),
    ),
  remove: (id: number) =>
    responseData(client.DELETE('/api/agent-review/{issue_id}', { params: { path: { issue_id: id } } })),
};

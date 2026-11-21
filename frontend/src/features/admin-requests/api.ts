import type { AccessRequestDecisionPayload, ReportDecisionPayload } from '@/shared/api';
import { client, responseData } from '@/shared/api';

export const adminApi = {
  accessRequests: (statusFilter?: string, signal?: AbortSignal) =>
    responseData(
      client.GET('/api/admin/access-requests', {
        params: { query: { status_filter: statusFilter || undefined } },
        signal,
      }),
    ),
  decideAccessRequest: (userId: number, body: AccessRequestDecisionPayload) =>
    responseData(
      client.POST('/api/admin/access-requests/{user_id}/decision', {
        params: { path: { user_id: userId } },
        body: body,
      }),
    ),
  reports: (statusFilter?: string, signal?: AbortSignal) =>
    responseData(
      client.GET('/api/reports', { params: { query: { status_filter: statusFilter || undefined } }, signal }),
    ),
  decideReport: (reportId: number, body: ReportDecisionPayload) =>
    responseData(
      client.POST('/api/reports/{report_id}/decision', {
        params: { path: { report_id: reportId } },
        body: body,
      }),
    ),
};

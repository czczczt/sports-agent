import type { AccessRequestDecisionPayload, ReportDecisionPayload } from '@/shared/api';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { adminApi } from './api';

const keys = {
  access: ['moderation', 'access'] as const,
  reports: ['moderation', 'reports'] as const,
};

export function useModeration(
  tab: 'access' | 'reports',
  accessFilter: string,
  reportFilter: string,
  enabled: boolean,
) {
  const access = useQuery({
    queryKey: [...keys.access, accessFilter],
    queryFn: ({ signal }) =>
      adminApi.accessRequests(accessFilter === 'all' ? undefined : accessFilter, signal),
    enabled: enabled && tab === 'access',
  });
  const reports = useQuery({
    queryKey: [...keys.reports, reportFilter],
    queryFn: ({ signal }) => adminApi.reports(reportFilter === 'all' ? undefined : reportFilter, signal),
    enabled: enabled && tab === 'reports',
  });
  return {
    accessItems: access.data ?? [],
    reportItems: reports.data ?? [],
    active: tab === 'access' ? access : reports,
  };
}

export function useAccessDecision() {
  const cache = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: AccessRequestDecisionPayload }) =>
      adminApi.decideAccessRequest(id, body),
    onSuccess: () => cache.invalidateQueries({ queryKey: keys.access }),
  });
}

export function useReportDecision() {
  const cache = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: ReportDecisionPayload }) =>
      adminApi.decideReport(id, body),
    onSuccess: () => cache.invalidateQueries({ queryKey: keys.reports }),
  });
}

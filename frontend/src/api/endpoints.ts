import { api } from './client';
import type {
  AgentApplyResult, AgentReviewPage, Assessment, AthleteCandidate, AthleteResultItem, AthleteSummary,
  AuthResponse, EventItem, LoginRequest, PasswordResetConfirm, PasswordResetRequest, RacePage, RatingFormula, RatingPage, RegisterRequest, RegisterResponse, User,
} from './types';

export const authApi = {
  login: (body: LoginRequest) => api.post<AuthResponse>('/api/auth/login', body),
  logout: () => api.post<{ status: string }>('/api/auth/logout'),
  me: (signal?: AbortSignal) => api.get<User>('/api/auth/me', undefined, signal),
  register: (body: RegisterRequest) => api.post<RegisterResponse>('/api/auth/register', body),
  passwordResetRequest: (body: PasswordResetRequest) =>
    api.post<{ status: string; message: string }>('/api/auth/password-reset-request', body),
  passwordReset: (body: PasswordResetConfirm) =>
    api.post<{ status: string; message: string }>('/api/auth/password-reset', body),
};

export const athletesApi = {
  search: (lastName: string, birthYear: number, signal?: AbortSignal) =>
    api.get<AthleteCandidate[]>('/api/athletes/search', { last_name: lastName, birth_year: birthYear, limit: 50 }, signal),
  summary: (id: number, signal?: AbortSignal) => api.get<AthleteSummary>(`/api/athletes/${id}/summary`, undefined, signal),
  results: (id: number, signal?: AbortSignal) => api.get<AthleteResultItem[]>(`/api/athletes/${id}/results`, undefined, signal),
  assessment: (id: number) => api.post<Assessment>(`/api/athletes/${id}/assessment`),
};

export interface EventFilters {
  query?: string;
  date_from?: string;
  date_to?: string;
  city?: string;
  source?: string;
}

export const eventsApi = {
  list: (filters: EventFilters, signal?: AbortSignal) =>
    api.get<EventItem[]>('/api/events', { ...filters, limit: 60 }, signal),
  get: (id: number, signal?: AbortSignal) => api.get<EventItem>(`/api/events/${id}`, undefined, signal),
};

export const racesApi = {
  page: (id: number, params: { search?: string; athlete_id?: number | null }, signal?: AbortSignal) =>
    api.get<RacePage>(`/api/races/${id}`, params, signal),
};

export const ratingApi = {
  page: (params: { gender?: string | null; athlete_id?: number | null }, signal?: AbortSignal) =>
    api.get<RatingPage>('/api/rating', params, signal),
  formula: (signal?: AbortSignal) => api.get<RatingFormula>('/api/rating/formula', undefined, signal),
};

export const agentReviewApi = {
  page: (params: { status: string; source?: string }, signal?: AbortSignal) =>
    api.get<AgentReviewPage>('/api/agent-review/page', params, signal),
  decide: (id: number, body: { decision: 'approve' | 'reject'; author: string; comment: string; retry: boolean }) =>
    api.post<unknown>(`/api/agent-review/${id}/decide`, body),
  reset: (id: number) => api.post<unknown>(`/api/agent-review/${id}/reset`),
  apply: (id: number, push: boolean) => api.post<AgentApplyResult>(`/api/agent-review/${id}/apply`, { push }),
  remove: (id: number) => api.delete<unknown>(`/api/agent-review/${id}`),
};

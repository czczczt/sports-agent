import type { LoginRequest, PasswordResetConfirm, PasswordResetRequest, RegisterRequest } from '@/shared/api';
import { client, responseData } from '@/shared/api';

export const authApi = {
  login: (body: LoginRequest) => responseData(client.POST('/api/auth/login', { body: body })),
  logout: () => responseData(client.POST('/api/auth/logout')),
  me: (signal?: AbortSignal) => responseData(client.GET('/api/auth/me', { signal })),
  register: (body: RegisterRequest) => responseData(client.POST('/api/auth/register', { body: body })),
  passwordResetRequest: (body: PasswordResetRequest) =>
    responseData(client.POST('/api/auth/password-reset-request', { body: body })),
  passwordReset: (body: PasswordResetConfirm) =>
    responseData(client.POST('/api/auth/password-reset', { body: body })),
};

import createClient from 'openapi-fetch';
import { z } from 'zod';
import type { paths } from './schema';

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
  ) {
    super(detail);
    this.name = 'ApiError';
  }
}

const validationIssue = z.object({ loc: z.array(z.union([z.string(), z.number()])), msg: z.string() });
const errorBody = z.object({ detail: z.union([z.string(), z.array(validationIssue)]) });
const tokenSchema = z.string().min(1).nullable();

export function readToken(): string | null {
  return tokenSchema.catch(null).parse(localStorage.getItem('auth_token'));
}

export const client = createClient<paths>({
  baseUrl: import.meta.env.VITE_API_URL || window.location.origin,
  credentials: 'same-origin',
  querySerializer(params) {
    const search = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) {
      if (value != null && value !== '') search.set(key, String(value));
    }
    return search.toString();
  },
});

client.use({
  onRequest({ request }) {
    const token = readToken();
    if (token) request.headers.set('Authorization', 'Bearer ' + token);
    request.headers.set('Accept', 'application/json');
    return request;
  },
  async onResponse({ response }) {
    if (response.ok) return response;
    const payload: unknown = await response.json().catch(() => null);
    const parsed = errorBody.safeParse(payload);
    const detail = parsed.success ? parsed.data.detail : response.statusText;
    const message =
      typeof detail === 'string'
        ? detail
        : detail
            .map((issue) =>
              [issue.loc.filter((part) => part !== 'body').join('.'), issue.msg].filter(Boolean).join(': '),
            )
            .join(', ');
    throw new ApiError(response.status, message || 'Ошибка ' + response.status);
  },
});

export async function responseData<T>(request: Promise<{ data?: T; response: Response }>): Promise<T> {
  const { data, response } = await request;
  if (data === undefined) throw new ApiError(response.status, 'Пустой ответ сервера');
  return data;
}

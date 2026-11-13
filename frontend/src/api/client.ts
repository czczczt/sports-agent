// Тонкая обёртка над fetch для JSON API бэкенда (FastAPI, префикс /api).

export class ApiError extends Error {
  constructor(public status: number, public detail: string) {
    super(detail);
    this.name = 'ApiError';
  }
}

export type QueryValue = string | number | boolean | null | undefined;
export type Query = Record<string, QueryValue>;

/** Собирает query-строку, пропуская пустые значения. */
export function buildQuery(params?: Query): string {
  if (!params) return '';
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === null || v === undefined || v === '') continue;
    qs.set(k, String(v));
  }
  const s = qs.toString();
  return s ? `?${s}` : '';
}

async function request<T>(method: string, path: string, opts: { query?: Query; body?: unknown; signal?: AbortSignal } = {}): Promise<T> {
  const init: RequestInit = { method, signal: opts.signal, headers: { Accept: 'application/json' } };
  if (opts.body !== undefined) {
    init.headers = { ...init.headers, 'Content-Type': 'application/json' };
    init.body = JSON.stringify(opts.body);
  }
  const res = await fetch(path + buildQuery(opts.query), init);
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const detail = data && typeof data.detail === 'string' ? data.detail : `ошибка ${res.status}`;
    throw new ApiError(res.status, detail);
  }
  return data as T;
}

export const api = {
  get: <T>(path: string, query?: Query, signal?: AbortSignal) => request<T>('GET', path, { query, signal }),
  post: <T>(path: string, body?: unknown) => request<T>('POST', path, { body }),
  delete: <T>(path: string) => request<T>('DELETE', path),
};

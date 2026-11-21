import { useCallback, useEffect, useRef, useState, type DependencyList } from 'react';
import { ApiError } from '@/api/client';

export interface ApiState<T> {
  data: T | undefined;
  error: ApiError | Error | null;
  /** Идёт запрос (в том числе повторный — прежние data при этом остаются на экране). */
  loading: boolean;
  /** Перезапросить с теми же параметрами. */
  reload: () => void;
}

/**
 * Загрузка данных для страницы. fetcher получает AbortSignal: при смене deps
 * или уходе со страницы прежний запрос отменяется, и устаревший ответ не перетрёт новый.
 * Если fetcher вернул undefined вместо промиса — запрос не нужен (например, форма пуста).
 */
export function useApi<T>(fetcher: (signal: AbortSignal) => Promise<T> | undefined, deps: DependencyList): ApiState<T> {
  const [data, setData] = useState<T | undefined>(undefined);
  const [error, setError] = useState<ApiError | Error | null>(null);
  const [loading, setLoading] = useState(true);
  const [nonce, setNonce] = useState(0);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  useEffect(() => {
    const ctrl = new AbortController();
    const promise = fetcherRef.current(ctrl.signal);
    if (!promise) {
      setData(undefined);
      setError(null);
      setLoading(false);
      return () => ctrl.abort();
    }
    setLoading(true);
    promise
      .then((d) => {
        if (ctrl.signal.aborted) return;
        setData(d);
        setError(null);
      })
      .catch((e: unknown) => {
        if (ctrl.signal.aborted || (e instanceof DOMException && e.name === 'AbortError')) return;
        setError(e instanceof Error ? e : new Error(String(e)));
      })
      .finally(() => {
        if (!ctrl.signal.aborted) setLoading(false);
      });
    return () => ctrl.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);
  return { data, error, loading, reload };
}

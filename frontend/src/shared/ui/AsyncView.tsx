import { ApiError } from '@/shared/api';
import type { UseQueryResult } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { ErrorState } from './ErrorState';
import { Loader } from './Loader';
import { NotFound } from './NotFound';

interface AsyncViewProps<T> {
  query: UseQueryResult<T, Error>;
  notFound?: ReactNode;
  loadingText?: string;
  children: (data: T) => ReactNode;
}

export function AsyncView<T>({ query, notFound, loadingText, children }: AsyncViewProps<T>) {
  if (query.error instanceof ApiError && query.error.status === 404) return <>{notFound ?? <NotFound />}</>;
  if (query.data === undefined)
    return query.error ? (
      <ErrorState error={query.error} onRetry={() => void query.refetch()} />
    ) : (
      <Loader text={loadingText} />
    );
  return (
    <>
      {query.isFetching && (
        <span className="sr-only" role="status">
          Обновление данных…
        </span>
      )}
      {query.error && <ErrorState error={query.error} onRetry={() => void query.refetch()} />}
      {children(query.data)}
    </>
  );
}

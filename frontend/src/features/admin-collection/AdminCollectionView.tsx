import { dateTimeRu, parseId, sourceName } from '@/shared/lib';
import { useAuth } from '@/shared/session';
import { EmptyState, ErrorState, Loader } from '@/shared/ui';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import { collectionApi } from './api';
import styles from './AdminCollectionView.module.css';
import { CollectionForm } from './CollectionForm';
import { CollectionPreview } from './CollectionPreview';
import { CollectionProgress } from './CollectionProgress';

const historyKey = ['admin-collection', 'history'] as const;
const batchKey = (id: number | null) => ['admin-collection', 'batch', id] as const;

function CollectionDashboard(): React.JSX.Element {
  const [search, setSearch] = useSearchParams();
  const queryClient = useQueryClient();

  const sources = useQuery({
    queryKey: ['admin-collection', 'sources'],
    queryFn: ({ signal }) => collectionApi.sources(signal),
  });
  const history = useQuery({
    queryKey: historyKey,
    queryFn: ({ signal }) => collectionApi.history(signal),
  });
  const batchId = parseId(search.get('batch')) ?? history.data?.[0]?.id ?? null;
  const batch = useQuery({
    queryKey: batchKey(batchId),
    enabled: batchId !== null,
    queryFn: ({ signal }) => collectionApi.batch(batchId ?? 0, signal),
    refetchInterval: ({ state: { data } }) =>
      data?.sources.some(({ status }) => status === 'queued' || status === 'running') ||
      data?.drafts.some(({ status }) => status === 'queued' || status === 'running')
        ? 2_000
        : false,
  });
  const start = useMutation({
    mutationFn: collectionApi.start,
    onSuccess: ({ id }) => {
      setSearch({ batch: String(id) });
      void queryClient.invalidateQueries({ queryKey: historyKey });
    },
  });
  const sourceLabel = (code: string) =>
    sources.data?.find((source) => source.code === code)?.label ?? sourceName(code);

  return (
    <>
      <div className="page-head">
        <div className="page-head__text">
          <h1 className="h1 h1-sm">Обновление данных</h1>
          <p className="lead">Собери новые и изменённые протоколы, проверь черновики и утверди публикацию.</p>
        </div>
      </div>
      {sources.isLoading && <Loader text="Загружаем площадки…" />}
      {sources.error && <ErrorState error={sources.error} onRetry={() => void sources.refetch()} />}
      {sources.data && (
        <CollectionForm
          key={start.data?.id}
          sources={sources.data}
          starting={start.isPending}
          onStart={start.mutate}
        />
      )}
      {start.error && (
        <p role="alert" className={styles.error}>
          {start.error.message}
        </p>
      )}
      <section className={`card card--pad ${styles.stack}`} aria-labelledby="collection-history">
        <div className={styles.row}>
          <h2 className="h2" id="collection-history">
            История запусков
          </h2>
          <div className={styles.row}>
            {history.data && (history.data.length > 0 || batchId !== null) && (
              <label className={`field ${styles.history}`}>
                Запуск
                <select
                  className="input input--sm"
                  value={batchId ?? ''}
                  onChange={({ target }) => setSearch({ batch: target.value })}
                >
                  {batchId !== null && !history.data.some(({ id }) => id === batchId) && (
                    <option value={batchId}>№ {batchId}</option>
                  )}
                  {history.data.map(({ id, created_at }) => (
                    <option key={id} value={id}>
                      № {id} · {dateTimeRu(created_at)}
                    </option>
                  ))}
                </select>
              </label>
            )}
            {batchId !== null && (
              <button
                type="button"
                className="btn btn--ghost"
                disabled={batch.isFetching}
                onClick={() => void batch.refetch()}
              >
                Обновить статус
              </button>
            )}
          </div>
        </div>
        {history.isLoading && <Loader text="Загружаем историю…" inCard={false} />}
        {history.error && <ErrorState error={history.error} onRetry={() => void history.refetch()} />}
        {history.data?.length === 0 && batchId === null && <p className="muted">Запусков пока нет.</p>}
      </section>
      {batch.isLoading && <Loader text="Загружаем ход сбора…" />}
      {batch.error && <ErrorState error={batch.error} onRetry={() => void batch.refetch()} />}
      {batch.data && (
        <>
          <CollectionProgress
            batch={batch.data}
            sourceLabel={sourceLabel}
            starting={start.isPending}
            onStart={start.mutate}
          />
          <CollectionPreview
            key={batch.data.id}
            batch={batch.data}
            sourceLabel={sourceLabel}
            onUpdate={() => queryClient.invalidateQueries({ queryKey: batchKey(batch.data.id) })}
          />
        </>
      )}
    </>
  );
}

export function AdminCollectionView(): React.JSX.Element {
  const { isAdmin } = useAuth();
  if (!isAdmin) {
    return (
      <EmptyState
        title="Требуются права администратора"
        text="Обновление протоколов доступно только администратору."
      />
    );
  }
  return <CollectionDashboard />;
}

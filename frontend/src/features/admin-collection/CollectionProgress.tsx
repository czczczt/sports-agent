import { useState } from 'react';
import type { CollectionBatch, CollectionStartRequest } from './api';
import styles from './AdminCollectionView.module.css';

const retryStartsLimit = 100;

const statuses: Record<string, [string, 'pending' | 'error' | 'brand' | 'muted']> = {
  queued: ['В очереди', 'pending'],
  running: ['В работе', 'pending'],
  completed: ['Сбор завершён', 'brand'],
  failed: ['Ошибка', 'error'],
  unsupported: ['Автопоиск недоступен', 'muted'],
  disabled: ['Площадка отключена', 'muted'],
  ready: ['Черновик готов', 'brand'],
  approved: ['Утверждён', 'brand'],
  unchanged: ['Без изменений', 'muted'],
};

function CollectionStatus({ status }: { status: string }) {
  const [label, tone] = statuses[status] ?? [status, 'muted'];
  return <span className={`chip chip--sm chip--${tone}`}>{label}</span>;
}

export function CollectionProgress({
  batch,
  sourceLabel,
  starting,
  onStart,
}: {
  batch: CollectionBatch;
  sourceLabel: (source: string) => string;
  starting: boolean;
  onStart: (body: CollectionStartRequest) => void;
}): React.JSX.Element {
  const [retrySelection, setRetrySelection] = useState({ batchId: batch.id, chunk: 0 });
  const failedDrafts = batch.drafts.filter(({ status }) => status === 'failed');
  const failedSources = batch.sources.filter(({ status }) => status === 'failed');
  const retryChunk = retrySelection.batchId === batch.id ? retrySelection.chunk : 0;
  const retryChunkCount = Math.ceil(failedDrafts.length / retryStartsLimit);
  const retryStart = retryChunk * retryStartsLimit;
  const retryStarts = failedDrafts
    .slice(retryStart, retryStart + retryStartsLimit)
    .map(({ source, event_code }) => ({ source, event_code }));
  const failedDraftSources = new Set(failedDrafts.map(({ source }) => source));
  const retry = {
    sources: Array.from(
      new Set([
        ...failedSources.filter(({ code }) => !failedDraftSources.has(code)).map(({ code }) => code),
        ...retryStarts.map(({ source }) => source),
      ]),
    ),
    starts: retryStarts,
  };

  return (
    <section className={`card card--pad ${styles.stack}`} aria-labelledby="collection-progress">
      <div className={styles.row}>
        <h2 className="h2" id="collection-progress">
          Ход сбора
        </h2>
        {retry.sources.length > 0 && (
          <div className={styles.row}>
            {retryChunkCount > 1 && (
              <label className="field">
                Порция стартов
                <select
                  className="input input--sm"
                  value={retryChunk}
                  disabled={starting}
                  onChange={({ target }) =>
                    setRetrySelection({ batchId: batch.id, chunk: Number(target.value) })
                  }
                >
                  {Array.from({ length: retryChunkCount }, (_, chunk) => {
                    const first = chunk * retryStartsLimit + 1;
                    const last = Math.min((chunk + 1) * retryStartsLimit, failedDrafts.length);
                    return (
                      <option value={chunk} key={chunk}>
                        {first}–{last} из {failedDrafts.length}
                      </option>
                    );
                  })}
                </select>
              </label>
            )}
            <button type="button" className="btn btn--ghost" disabled={starting} onClick={() => onStart(retry)}>
              Повторить сбор с ошибками
            </button>
          </div>
        )}
      </div>
      {retryChunkCount > 1 && (
        <p className="small muted">
          За один запуск можно повторить до {retryStartsLimit} стартов. Остальные порции можно запустить,
          вернувшись к этому сбору через историю.
        </p>
      )}
      <div className={styles.columns}>
        {batch.sources.map(({ code, status, error }) => {
          const starts = batch.drafts.filter(({ source }) => source === code);
          return (
            <article className={styles.panel} key={code}>
              <div className={styles.row}>
                <h3>{sourceLabel(code)}</h3>
                <CollectionStatus status={status} />
              </div>
              {error && <p className={`small ${styles.error}`}>{error}</p>}
              {starts.length > 0 && (
                <details className={styles.protocols}>
                  <summary>Старты ({starts.length})</summary>
                  <ul className={styles.cleanList}>
                    {starts.map((start) => (
                      <li key={start.id}>
                        <div className={styles.row}>
                          <span>{start.title || start.event_code}</span>
                          <CollectionStatus status={start.status} />
                        </div>
                        {start.error && <p className={`small ${styles.error}`}>{start.error}</p>}
                      </li>
                    ))}
                  </ul>
                </details>
              )}
            </article>
          );
        })}
      </div>
    </section>
  );
}

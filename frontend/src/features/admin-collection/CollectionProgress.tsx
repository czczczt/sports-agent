import { useState } from 'react';
import type { CollectionBatch, CollectionStartRequest } from './api';
import styles from './AdminCollectionView.module.css';

const retryStartsLimit = 100;

const knownCollectionIssues = {
  'RussiaRunning has no supported individual distances': {
    label: 'Нет поддерживаемых дистанций',
    sourceLabel: 'без поддерживаемых дистанций',
    tone: 'muted',
    description: 'В старте нет индивидуальных дистанций, которые сейчас можно импортировать.',
    retry: false,
  },
  'RussiaRunning protocols are not marked final': {
    label: 'Протокол предварительный',
    sourceLabel: 'с предварительным протоколом',
    tone: 'pending',
    description: 'RussiaRunning не пометил протокол как итоговый. Старт можно проверить повторно позже.',
    retry: true,
  },
  'No final source protocols': {
    label: 'Нет доступного итогового протокола',
    sourceLabel: 'без доступного итогового протокола',
    tone: 'muted',
    description:
      'Для этого запуска итоговый протокол не найден. Причина могла отличаться; старт можно проверить повторно.',
    retry: true,
  },
} as const;

type KnownCollectionIssue = (typeof knownCollectionIssues)[keyof typeof knownCollectionIssues];

function knownCollectionIssue(error: string | null): KnownCollectionIssue | undefined {
  if (!error || !Object.prototype.hasOwnProperty.call(knownCollectionIssues, error)) return undefined;
  return knownCollectionIssues[error as keyof typeof knownCollectionIssues];
}

function isDuplicatedSourceError(sourceError: string | null, starts: CollectionBatch['drafts']): boolean {
  return Boolean(
    sourceError &&
    starts.some((start) => start.error !== null && `${start.event_code}: ${start.error}` === sourceError),
  );
}

const statuses: Record<string, [string, 'pending' | 'error' | 'brand' | 'muted']> = {
  queued: ['В очереди', 'pending'],
  running: ['В работе', 'pending'],
  completed: ['Сбор завершён', 'brand'],
  failed: ['Ошибка', 'error'],
  unsupported: ['Нужен код старта', 'muted'],
  disabled: ['Площадка отключена', 'muted'],
  ready: ['Черновик готов', 'brand'],
  approved: ['Утверждён', 'brand'],
  unchanged: ['Без изменений', 'muted'],
};

function CollectionStatus({ status }: { status: string }) {
  const [label, tone] = statuses[status] ?? [status, 'muted'];
  return <span className={`chip chip--sm chip--${tone}`}>{label}</span>;
}

function IssueStatus({ issue, count }: { issue: KnownCollectionIssue; count?: number }) {
  const label = count === undefined ? issue.label : `${count} ${issue.sourceLabel}`;
  return <span className={`chip chip--sm chip--${issue.tone}`}>{label}</span>;
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
  const failedDrafts = batch.drafts.filter(
    ({ status, error }) => status === 'failed' && knownCollectionIssue(error)?.retry !== false,
  );
  const failedSources = batch.sources.filter(({ status }) => status === 'failed');
  const retryChunk = retrySelection.batchId === batch.id ? retrySelection.chunk : 0;
  const retryChunkCount = Math.ceil(failedDrafts.length / retryStartsLimit);
  const retryStart = retryChunk * retryStartsLimit;
  const retryStarts = failedDrafts
    .slice(retryStart, retryStart + retryStartsLimit)
    .map(({ source, event_code }) => ({ source, event_code }));
  const failedDraftSources = new Set(
    batch.drafts.filter(({ status }) => status === 'failed').map(({ source }) => source),
  );
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
            <button
              type="button"
              className="btn btn--ghost"
              disabled={starting}
              onClick={() => onStart(retry)}
            >
              Проверить старты повторно
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
          const failedStarts = starts.filter(({ status: startStatus }) => startStatus === 'failed');
          const knownIssues = failedStarts.flatMap((start) => {
            const issue = knownCollectionIssue(start.error);
            return issue ? [issue] : [];
          });
          const sourceErrorIsDuplicated = isDuplicatedSourceError(error, starts);
          const hasTechnicalFailures =
            failedStarts.some((start) => !knownCollectionIssue(start.error)) ||
            Boolean(error && !sourceErrorIsDuplicated);
          const issueCounts = Array.from(new Set(knownIssues)).map((issue) => ({
            issue,
            count: knownIssues.filter((knownIssue) => knownIssue === issue).length,
          }));
          const showKnownIssueSummary = status === 'failed' && knownIssues.length > 0;
          return (
            <article className={styles.panel} key={code}>
              <div className={styles.row}>
                <h3>{sourceLabel(code)}</h3>
                <div className={styles.row}>
                  {(!showKnownIssueSummary || hasTechnicalFailures) && <CollectionStatus status={status} />}
                  {showKnownIssueSummary &&
                    issueCounts.map(({ issue, count }) => (
                      <IssueStatus issue={issue} count={count} key={issue.label} />
                    ))}
                </div>
              </div>
              {status === 'unsupported' && (
                <p className="small muted">
                  Открой «Указать известные коды стартов», введи код для этого источника и нажми «Обновить
                  данные».
                </p>
              )}
              {error && !sourceErrorIsDuplicated && <p className={`small ${styles.error}`}>{error}</p>}
              {starts.length > 0 && (
                <details className={styles.protocols}>
                  <summary>Старты ({starts.length})</summary>
                  <ul className={styles.cleanList}>
                    {starts.map((start) => {
                      const issue = knownCollectionIssue(start.error);
                      return (
                        <li key={start.id}>
                          <div className={styles.row}>
                            <span>{start.title || start.event_code}</span>
                            {issue ? (
                              <IssueStatus issue={issue} />
                            ) : (
                              <CollectionStatus status={start.status} />
                            )}
                          </div>
                          {issue ? (
                            <p className={`small ${issue.tone === 'pending' ? styles.warning : 'muted'}`}>
                              {issue.description}
                            </p>
                          ) : (
                            start.error && <p className={`small ${styles.error}`}>{start.error}</p>
                          )}
                        </li>
                      );
                    })}
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

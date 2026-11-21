import type { AgentReviewItem } from '@/shared/api';
import { dateTimeRu, sourceName } from '@/shared/lib';
import { Icon } from '@/shared/ui';
import styles from './ReviewCard.module.css';
import { StatusBadge } from './StatusBadge';

function splitLines(text: string): string[] {
  return text ? text.replace(/\r?\n$/, '').split(/\r?\n/) : [];
}

function diffLineClass(line: string): string | undefined {
  if (line.startsWith('+++') || line.startsWith('---') || line.startsWith('@@')) return 'meta';
  if (line.startsWith('+')) return 'add';
  if (line.startsWith('-')) return 'del';
  return undefined;
}

interface ReviewDetailsProps {
  item: AgentReviewItem;
}
export function ReviewDetails({ item: it }: ReviewDetailsProps): React.JSX.Element {
  const run = it.run;
  const tokensTotal = (run?.tokens_in ?? 0) + (run?.tokens_out ?? 0);
  return (
    <>
      {' '}
      <div className={['card__head', styles.header].join(' ')}>
        <div className={['stack', styles.heading].join(' ')}>
          <div className={['row', styles.titleRow].join(' ')}>
            <h2 className={['h2', styles.title].join(' ')}>
              Задача #{it.issue_id} · {sourceName(it.source)}
            </h2>
            <a
              href={it.object_ref ?? undefined}
              target="_blank"
              rel="noopener noreferrer"
              className={['small muted', styles.source].join(' ')}
            >
              {it.object_ref} <Icon name="external" className="icon-sm" />
            </a>
          </div>
          <div className={styles.problem}>
            <span className="muted">Проблема:</span>
            <span className={styles.detail}>{it.details}</span>
          </div>
        </div>
        <div className="chips">
          <StatusBadge status={it.status} />
        </div>
      </div>
      <div className={['card--pad', styles.body].join(' ')}>
        <div className={['stack', styles.explanation].join(' ')}>
          <span className="label">Обоснование решения агента</span>
          <p className={styles.reason}>{it.reason || '—'}</p>
          <span className={['muted small num', styles.metrics].join(' ')}>
            Модель: <b>{run?.model}</b>
            {!!run?.tokens_in &&
              ` · Токены: ${run.tokens_in} вход / ${run.tokens_out} выход (всего ${tokensTotal})`}
            {run?.seconds != null && ` · Время: ${run.seconds} сек.`}
          </span>
        </div>

        <div className={['stack', styles.block].join(' ')}>
          <span className="label">Сгенерированный код</span>
          <pre className="diff">
            {splitLines(it.diff).map((line, i) => (
              <span key={i} className={diffLineClass(line)}>
                {line}
              </span>
            ))}
          </pre>
        </div>

        <div className={['stack', styles.block].join(' ')}>
          <span className="label">Результат проверки решения</span>
          <pre className="report">{it.report_text}</pre>
        </div>

        {it.reviews.length > 0 && (
          <div className={['stack', styles.decisions].join(' ')}>
            <span className="label">Решения</span>
            {it.reviews.map((rv, i) => (
              <p key={i} className="small">
                <span className="strong">{rv.decision}</span> — {rv.author}, {dateTimeRu(rv.decided_at)}
                {rv.comment && `: ${rv.comment}`}
                {rv.applied_result && <span className="muted"> · применение: {rv.applied_result}</span>}
                {rv.pr_url && rv.pr_url.startsWith('http') ? (
                  <>
                    {' '}
                    ·{' '}
                    <a href={rv.pr_url} target="_blank" rel="noopener noreferrer">
                      PR <Icon name="external" className="icon-sm" />
                    </a>
                  </>
                ) : (
                  rv.pr_url && <span className="muted"> · {rv.pr_url}</span>
                )}
              </p>
            ))}
          </div>
        )}
      </div>
    </>
  );
}

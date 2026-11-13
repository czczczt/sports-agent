// Правки агента (/agent-review?status=…&source=…). Перенос agent_review.html:
// проверка человеком решений ИИ-агента, чинящего парсеры (данные — PostgreSQL парсера).
import { useState, type FormEvent } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { agentReviewApi } from '@/api/endpoints';
import type { AgentReviewItem, AgentReviewPage as AgentReviewData } from '@/api/types';
import { EmptyState, ErrorState, Icon, Loader } from '@/components/ui';
import { useApi } from '@/hooks/useApi';
import { SITE_TITLE, useDocumentTitle } from '@/hooks/useDocumentTitle';
import { dateTimeRu, sourceName } from '@/lib/format';

export function AgentReviewPage() {
  useDocumentTitle(`Правки агента · ${SITE_TITLE}`);
  const [params, setParams] = useSearchParams();
  const status = params.get('status') || 'proposed';
  const source = params.get('source') || '';

  const { data, error, loading, reload } = useApi(
    (signal) => agentReviewApi.page({ status, source }, signal),
    [status, source],
  );

  return (
    <>
      <div className="page-head">
        <div className="page-head__text">
          <h1 className="h1 h1-sm">Правки агента</h1>
          <p className="lead">Сгенерированные ИИ-агентом решения и адаптеры для сбора протоколов соревнований, ожидающие проверки человеком.</p>
        </div>
        <ReviewFilters key={`${status}|${source}`} data={data} status={status} source={source}
          onApply={(st, src) => setParams(src ? { status: st, source: src } : { status: st })} />
      </div>

      {error && !data ? <ErrorState error={error} onRetry={reload} />
        : !data || loading ? <Loader />
        : <ReviewList data={data} status={status} onChanged={reload} />}
    </>
  );
}

function ReviewFilters({ data, status, source, onApply }: {
  data?: AgentReviewData;
  status: string;
  source: string;
  onApply: (status: string, source: string) => void;
}) {
  const [st, setSt] = useState(status);
  const [src, setSrc] = useState(source);
  const statuses = data?.statuses ?? [status];
  const submit = (e: FormEvent) => {
    e.preventDefault();
    onApply(st, src);
  };
  return (
    <form className="review-filters" onSubmit={submit}>
      <label className="field">Статус
        <select name="status" className="input input--sm" value={st} onChange={(e) => setSt(e.target.value)}>
          {statuses.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
      </label>
      <label className="field">Площадка
        <select name="source" className="input input--sm" value={src} onChange={(e) => setSrc(e.target.value)}>
          <option value="">все</option>
          {(data?.sources ?? []).map((s) => <option key={s} value={s}>{sourceName(s)}</option>)}
        </select>
      </label>
      <button className="btn btn--primary">Показать</button>
    </form>
  );
}

function ReviewList({ data, status, onChanged }: { data: AgentReviewData; status: string; onChanged: () => void }) {
  const [removed, setRemoved] = useState<number[]>([]);
  const items = data.items.filter((it) => !removed.includes(it.issue_id));

  const onRemoved = (id: number) => {
    const left = items.length - 1;
    setRemoved((r) => [...r, id]);
    if (left <= 0) onChanged();
  };

  return (
    <>
      {data.db_error && (
        <div className="card card--pending" role="alert">
          <p className="strong">Управление агентом временно недоступно</p>
          <p className="small">{data.db_error}</p>
          <p className="small muted">Для этого экрана нужна PostgreSQL-база парсера и переменная окружения <code>DATABASE_URL</code>.</p>
        </div>
      )}

      {!items.length && (
        <EmptyState
          title={`Предложений нет${status !== 'all' ? ` в статусе «${status}»` : ''}`}
          text="Все задачи проверены или находятся в других вкладках."
        />
      )}

      {items.map((it) => (
        <ReviewCard key={it.issue_id} item={it} defaultAuthor={data.default_author} onChanged={onChanged} onRemoved={onRemoved} />
      ))}
    </>
  );
}

/** Как str.splitlines(): без пустой строки в конце. */
function splitLines(text: string): string[] {
  return text ? text.replace(/\r?\n$/, '').split(/\r?\n/) : [];
}

function diffLineClass(line: string): string | undefined {
  if (line.startsWith('+++') || line.startsWith('---') || line.startsWith('@@')) return 'meta';
  if (line.startsWith('+')) return 'add';
  if (line.startsWith('-')) return 'del';
  return undefined;
}

function StatusBadge({ status }: { status: string }) {
  if (status === 'proposed') return <span className="chip chip--sm chip--pending">ждёт решения</span>;
  if (['approved', 'resolved', 'known'].includes(status)) return <span className="chip chip--sm chip--brand">{status}</span>;
  if (status === 'rejected') return <span className="chip chip--sm chip--error">rejected</span>;
  return <span className="chip chip--sm chip--muted">{status}</span>;
}

function ReviewCard({ item: it, defaultAuthor, onChanged, onRemoved }: {
  item: AgentReviewItem;
  defaultAuthor: string;
  onChanged: () => void;
  onRemoved: (id: number) => void;
}) {
  const navigate = useNavigate();
  const run = it.run ?? null;
  const [author, setAuthor] = useState(defaultAuthor);
  const [comment, setComment] = useState('');
  const [retry, setRetry] = useState(false);
  const [push, setPush] = useState(false);
  const [busy, setBusy] = useState(false);
  const [removing, setRemoving] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [msg, setMsg] = useState('');

  const run$ = async <T,>(action: () => Promise<T>): Promise<T | null> => {
    setMsg('выполняется…');
    setBusy(true);
    try {
      const res = await action();
      setMsg('');
      return res;
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
      return null;
    } finally {
      setBusy(false);
    }
  };

  const decide = async (decision: 'approve' | 'reject') => {
    if (await run$(() => agentReviewApi.decide(it.issue_id, { decision, author, comment, retry }))) onChanged();
  };

  const apply = async () => {
    const data = await run$(() => agentReviewApi.apply(it.issue_id, push));
    if (data) {
      setMsg(`${data.result} → ${data.status}${data.pr_url ? ` · ${data.pr_url}` : ''}`);
      setTimeout(onChanged, 2500);
    }
  };

  const reset = async () => {
    setBusy(true);
    setResetting(true);
    try {
      await agentReviewApi.reset(it.issue_id);
      navigate('/agent-review?status=proposed');
      onChanged();
    } catch {
      /* как и раньше: при ошибке просто снимаем блокировку кнопки */
    } finally {
      setBusy(false);
      setResetting(false);
    }
  };

  const remove = async () => {
    if (!window.confirm(`Удалить задачу #${it.issue_id} с сайта?`)) return;
    setBusy(true);
    setRemoving(true);
    try {
      await agentReviewApi.remove(it.issue_id);
      onRemoved(it.issue_id);
    } catch {
      setRemoving(false);
      window.alert('Ошибка при удалении задачи');
    } finally {
      setBusy(false);
    }
  };

  const tokensTotal = (run?.tokens_in || 0) + (run?.tokens_out || 0);
  const deleteButton = (
    <button type="button" className="btn btn--ghost btn--danger" disabled={busy} onClick={remove}>✕ Удалить</button>
  );
  const resetButton = (
    <button type="button" className="btn btn--ghost" disabled={busy} onClick={reset}>{resetting ? 'сброс…' : '↺ Сбросить решение'}</button>
  );

  return (
    <article className={`card card--clip review-card${removing ? ' review-card--removing' : ''}`} id={`issue-${it.issue_id}`}>
      <div className="card__head" style={{ alignItems: 'flex-start', paddingBottom: 4 }}>
        <div className="stack" style={{ gap: 4, flex: 1 }}>
          <div className="row" style={{ alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <h2 className="h2" style={{ margin: 0 }}>Задача #{it.issue_id} · {sourceName(it.source)}</h2>
            <a href={it.object_ref} target="_blank" rel="noopener noreferrer" className="small muted" style={{ textDecoration: 'underline' }}>
              {it.object_ref} <Icon name="external" className="icon-sm" />
            </a>
          </div>
          <div style={{ fontSize: 15, lineHeight: 1.5, marginTop: 2 }}>
            <span className="muted">Проблема:</span>
            <span style={{ color: 'var(--text-base)', marginLeft: 4 }}>{it.details}</span>
          </div>
        </div>
        <div className="chips"><StatusBadge status={it.status} /></div>
      </div>

      <div className="card--pad" style={{ paddingTop: 4 }}>
        <div className="stack" style={{ gap: 4 }}>
          <span className="label">Обоснование решения агента</span>
          <p style={{ fontSize: 15, lineHeight: 1.5, margin: 0 }}>{it.reason || '—'}</p>
          <span className="muted small num" style={{ marginTop: 4 }}>
            Модель: <b>{run?.model}</b>
            {!!run?.tokens_in && ` · Токены: ${run.tokens_in} вход / ${run.tokens_out} выход (всего ${tokensTotal})`}
            {run?.seconds != null && ` · Время: ${run.seconds} сек.`}
          </span>
        </div>

        <div className="stack" style={{ gap: 6, marginTop: 14 }}>
          <span className="label">Сгенерированный код</span>
          <pre className="diff">
            {splitLines(it.diff).map((line, i) => <span key={i} className={diffLineClass(line)}>{line}</span>)}
          </pre>
        </div>

        <div className="stack" style={{ gap: 6, marginTop: 14 }}>
          <span className="label">Результат проверки решения</span>
          <pre className="report">{it.report_text}</pre>
        </div>

        {it.reviews.length > 0 && (
          <div className="stack" style={{ gap: 6 }}>
            <span className="label">Решения</span>
            {it.reviews.map((rv, i) => (
              <p key={i} className="small">
                <span className="strong">{rv.decision}</span> — {rv.author}, {dateTimeRu(rv.decided_at)}{rv.comment && `: ${rv.comment}`}
                {rv.applied_result && <span className="muted"> · применение: {rv.applied_result}</span>}
                {rv.pr_url && rv.pr_url.startsWith('http')
                  ? <> · <a href={rv.pr_url} target="_blank" rel="noopener noreferrer">PR <Icon name="external" className="icon-sm" /></a></>
                  : rv.pr_url && <span className="muted"> · {rv.pr_url}</span>}
              </p>
            ))}
          </div>
        )}
      </div>

      {it.status === 'proposed' ? (
        <div className="card__foot">
          <div className="decide-grid">
            <label className="field">Автор
              <input className="input input--sm" value={author} onChange={(e) => setAuthor(e.target.value)} />
            </label>
            <label className="field">Комментарий (обязателен при отклонении)
              <input className="input input--sm" value={comment} onChange={(e) => setComment(e.target.value)} />
            </label>
          </div>
          <div className="row" style={{ justifyContent: 'space-between', width: '100%' }}>
            <div className="row">
              <button type="button" className="btn btn--primary" disabled={busy} onClick={() => decide('approve')}>Подтвердить</button>
              <button type="button" className="btn btn--ghost" disabled={busy} onClick={() => decide('reject')}>Отклонить</button>
              <label className="row small muted" style={{ gap: 6 }}>
                <input type="checkbox" checked={retry} onChange={(e) => setRetry(e.target.checked)} /> вернуть агенту с комментарием
              </label>
              <span className="msg-error" role="status">{msg}</span>
            </div>
            {deleteButton}
          </div>
        </div>
      ) : it.status === 'approved' ? (
        <div className="card__foot">
          <div className="row" style={{ justifyContent: 'space-between', width: '100%' }}>
            <div className="row">
              <button type="button" className="btn btn--primary" disabled={busy} onClick={apply}>Применить</button>
              <label className="row small muted" style={{ gap: 6 }}>
                <input type="checkbox" checked={push} onChange={(e) => setPush(e.target.checked)} /> push и PR (иначе только локальная ветка)
              </label>
              <span className="small" role="status">{msg}</span>
            </div>
            <div className="row">{resetButton}{deleteButton}</div>
          </div>
        </div>
      ) : (
        <div className="card__foot">
          <div className="row" style={{ justifyContent: 'space-between', width: '100%' }}>
            <span className="small muted">Статус: <b>{it.status}</b></span>
            <div className="row">{resetButton}{deleteButton}</div>
          </div>
        </div>
      )}
    </article>
  );
}

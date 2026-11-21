import { useEffect, useState, type FormEvent } from 'react';
import { api } from '@/api/client';
import { ErrorState, Loader } from '@/components/ui';
import { useApi } from '@/hooks/useApi';

const reviewPath = '/api/agent-review/recipes';
type Action = 'approve' | 'edit' | 'reject';

interface Repair {
  id: number;
  issue_id: number | null;
  source_id: number;
  source_name: string | null;
  status: 'running' | 'waiting';
  candidate: Record<string, unknown> | null;
  errors: string[];
  can_approve: boolean;
}

export function RecipeReviewPanel() {
  const { data, error, loading, reload } = useApi(
    (signal) => api.get<Repair[]>(reviewPath, undefined, signal),
    [],
  );
  const hasRunningRepair = data?.some((repair) => repair.status === 'running');
  useEffect(() => {
    if (!hasRunningRepair) return;
    const timer = window.setInterval(reload, 5000);
    return () => window.clearInterval(timer);
  }, [hasRunningRepair, reload]);

  return (
    <section aria-labelledby="recipe-review-title">
      <div className="page-head">
        <h2 className="h2" id="recipe-review-title">Рецепты извлечения</h2>
        <button type="button" className="btn" onClick={reload}>Обновить</button>
      </div>
      {error && <ErrorState error={error} onRetry={reload} />}
      {loading && !data && <Loader />}
      {!loading && data?.length === 0 && <p className="muted">Открытых ремонтов нет.</p>}
      {data?.map((repair) => <RepairCard key={repair.id} repair={repair} onDecision={reload} />)}
    </section>
  );
}

function RepairCard({ repair, onDecision }: { repair: Repair; onDecision: () => void }) {
  const [edited, setEdited] = useState<string | null>(null);
  const [comment, setComment] = useState('');
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string>();
  const proposal = JSON.stringify(repair.candidate ?? {}, null, 2);

  const decide = async (action: Action, event?: FormEvent) => {
    event?.preventDefault();
    setError(undefined);
    setPending(true);
    try {
      const candidate = action === 'edit' ? JSON.parse(edited ?? proposal) : undefined;
      await api.post(`${reviewPath}/${repair.id}/decision`, { action, candidate, comment });
      setEdited(null);
      setComment('');
      onDecision();
    } catch (exc) {
      setError(exc instanceof SyntaxError
        ? 'Исправьте синтаксис JSON'
        : exc instanceof Error ? exc.message : 'Не удалось сохранить решение');
    } finally {
      setPending(false);
    }
  };

  return (
    <article className="card">
      <h3 className="h3">{repair.source_name ?? `Источник #${repair.source_id}`} · ремонт #{repair.id}</h3>
      {repair.issue_id !== null && <p className="muted">Инцидент #{repair.issue_id}</p>}
      {repair.status === 'running' ? (
        <p role="status">В очереди или выполняется</p>
      ) : (
        <form onSubmit={(event) => void decide('edit', event)}>
          {repair.errors.length > 0 && (
            <ul>{repair.errors.map((message) => <li key={message}>{message}</li>)}</ul>
          )}
          <label className="field">
            Рецепт JSON
            <textarea className="input" rows={8} spellCheck={false}
              value={edited ?? proposal} onChange={(event) => setEdited(event.target.value)} />
          </label>
          <label className="field">
            Комментарий
            <input className="input" value={comment} maxLength={1000}
              onChange={(event) => setComment(event.target.value)} />
          </label>
          {error && <p role="alert">{error}</p>}
          <div className="actions">
            <button type="button" className="btn btn--primary" disabled={pending || !repair.can_approve}
              onClick={() => void decide('approve')}>Активировать проверенный рецепт</button>
            <button type="submit" className="btn" disabled={pending || edited === null}>Проверить правку</button>
            <button type="button" className="btn" disabled={pending}
              onClick={() => void decide('reject')}>Отклонить</button>
          </div>
        </form>
      )}
    </article>
  );
}


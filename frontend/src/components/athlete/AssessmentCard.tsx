// Блок «ИИ-оценка» в профиле: по кнопке запрашивает отчёт GigaChat (POST /api/athletes/:id/assessment),
// дальше та же кнопка показывает/скрывает уже загруженный отчёт.
import { useState } from 'react';
import { athletesApi } from '@/api/endpoints';
import { Icon } from '@/components/ui';
import { renderAssessmentMarkdown } from '@/lib/markdown';

type State =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'ready'; html: string; open: boolean }
  | { kind: 'error'; message: string };

export function AssessmentCard({ athleteId }: { athleteId: number }) {
  const [state, setState] = useState<State>({ kind: 'idle' });

  const onClick = async () => {
    if (state.kind === 'ready') {
      setState({ ...state, open: !state.open });
      return;
    }
    setState({ kind: 'loading' });
    try {
      const data = await athletesApi.assessment(athleteId);
      setState({ kind: 'ready', html: renderAssessmentMarkdown(data.assessment_text), open: true });
    } catch (err) {
      setState({ kind: 'error', message: err instanceof Error ? err.message : String(err) });
    }
  };

  const buttonText = {
    idle: 'Показать отчёт',
    loading: 'Формируем отчёт…',
    ready: state.kind === 'ready' && state.open ? 'Скрыть отчёт' : 'Показать отчёт',
    error: 'Попробовать снова',
  }[state.kind];
  const visible = state.kind === 'loading' || state.kind === 'error' || (state.kind === 'ready' && state.open);

  return (
    <section id="agent" className="card card--pad">
      <div className="row row--between" style={{ alignItems: 'center' }}>
        <div style={{ minWidth: 0, flex: '1 1 260px' }}>
          <h2 className="h2">ИИ-оценка</h2>
        </div>
        <button type="button" className="btn btn--primary btn--stretch-mobile" disabled={state.kind === 'loading'} onClick={onClick}>
          <Icon name="spark" /><span>{buttonText}</span>
        </button>
      </div>
      {visible && (
        <div>
          {state.kind === 'loading' && (
            <div className="row" style={{ padding: '12px 0' }}>
              <span className="spinner" aria-hidden="true" />
              <span className="small muted">Агент обрабатывает метрики и пишет отчёт…</span>
            </div>
          )}
          {state.kind === 'error' && (
            <div className="assessment" aria-live="polite">Не удалось сформировать оценку: {state.message}</div>
          )}
          {state.kind === 'ready' && (
            <>
              {/* HTML собран из экранированного текста (lib/markdown.ts), разметку модель вставить не может */}
              <div className="assessment" aria-live="polite" dangerouslySetInnerHTML={{ __html: state.html }} />
              <div className="row small muted" style={{ marginTop: 10, justifyContent: 'flex-end' }}>
                <span style={{ color: 'var(--status-pending)' }}>Оценка носит исключительно справочный характер</span>
              </div>
            </>
          )}
        </div>
      )}
    </section>
  );
}

import type { RepairReview as Repair, ReviewDecision } from '@/shared/api';
import { useState, type FormEvent } from 'react';
import { z } from 'zod';
import styles from './AgentReviewView.module.css';
import { useRepairDecision } from './useRepairs';

const recipeInput = z
  .object({
    baseSelector: z.string(),
    fields: z.array(
      z
        .object({
          name: z.enum([
            'full_name_raw',
            'bib',
            'gender',
            'status',
            'place_abs',
            'place_gender',
            'chip_time_s',
            'gun_time_s',
            'club_raw',
            'city',
            'age_group',
            'birth_year',
          ]),
          selector: z.string(),
          type: z.enum(['text', 'attribute', 'regex']),
          attribute: z.string().nullish(),
          pattern: z.string().nullish(),
        })
        .strict(),
    ),
  })
  .strict();

type Action = ReviewDecision['action'];

const statusMeta: Record<string, { label: string; chipClass: string }> = {
  running: { label: 'Агент работает', chipClass: 'chip chip--sm chip--pending' },
  waiting: { label: 'Ждёт решения', chipClass: 'chip chip--sm chip--pending' },
  activated: { label: 'Рецепт активирован', chipClass: 'chip chip--sm chip--brand' },
  unchanged: { label: 'Текущий рецепт актуален', chipClass: 'chip chip--sm chip--brand' },
  rejected: { label: 'Отклонён', chipClass: 'chip chip--sm chip--error' },
  stale: { label: 'Устарел', chipClass: 'chip chip--sm chip--error' },
};

const attemptLabels: Record<Repair['attempts'][number]['step'], string> = {
  trial: 'Пробное извлечение',
  sample: 'Проверка на проблемном протоколе',
  golden: 'Проверка на эталонных протоколах',
  generate: 'Первичная генерация рецепта',
  repair: 'Исправленный рецепт от агента',
  unavailable: 'Работа приостановлена',
};

interface RepairCardProps {
  repair: Repair;
  onDecide?: () => void;
}

export function RepairCard({ repair, onDecide }: RepairCardProps): React.JSX.Element {
  const [edited, setEdited] = useState<string | null>(null);
  const [comment, setComment] = useState('');
  const decision = useRepairDecision(repair.id);
  const pending = decision.isPending;
  const [error, setError] = useState<string>();
  const [feedback, setFeedback] = useState<string>();
  const proposal = JSON.stringify(repair.candidate ?? {}, null, 2);

  const badge = statusMeta[repair.status] ?? {
    label: repair.status,
    chipClass: 'chip chip--sm chip--muted',
  };

  const decide = async (action: Action, event?: FormEvent) => {
    event?.preventDefault();
    setError(undefined);
    setFeedback(undefined);
    try {
      const input: unknown = action === 'edit' ? JSON.parse(edited ?? proposal) : undefined;
      const candidate = input === undefined ? undefined : recipeInput.parse(input);
      onDecide?.();
      await decision.mutateAsync({ action, candidate, comment });
      setEdited(null);
      setComment('');
      setFeedback(
        action === 'approve'
          ? 'Рецепт отправлен на активацию и повторный сбор.'
          : action === 'edit'
            ? 'JSON отправлен на перепроверку на эталонах.'
            : 'Ремонт отклонён.',
      );
    } catch (exc) {
      setError(
        exc instanceof SyntaxError
          ? 'Исправьте синтаксис JSON'
          : exc instanceof z.ZodError
            ? 'Проверьте структуру полей рецепта'
            : exc instanceof Error
              ? exc.message
              : 'Не удалось сохранить решение',
      );
    }
  };

  const detailsContent = (
    <>
      {repair.base_selector &&
        typeof repair.candidate?.baseSelector === 'string' &&
        repair.base_selector !== repair.candidate.baseSelector && (
          <dl className={styles.selectorDiff}>
            <dt className="small muted">Исходный селектор</dt>
            <dd>
              <code>{repair.base_selector}</code>
            </dd>
            <dt className="small muted">Селектор после ремонта</dt>
            <dd>
              <code>{repair.candidate.baseSelector}</code>
            </dd>
          </dl>
        )}
      {repair.attempts.length > 0 && (
        <ol className={styles.repairTimeline} aria-label="Ход ремонта">
          {repair.attempts.map((attempt, index) => (
            <li key={index} className="small">
              {attemptLabels[attempt.step]} ·{' '}
              <span className={attempt.errors.length ? 'muted' : ''}>
                {attempt.errors.length ? 'есть ошибки' : 'успешно'}
              </span>
              {attempt.errors.length > 0 && (
                <ul>
                  {attempt.errors.map((message) => (
                    <li key={message}>{message}</li>
                  ))}
                </ul>
              )}
            </li>
          ))}
        </ol>
      )}
    </>
  );

  return (
    <article className="card card--pad">
      <div className={styles.cardHeader}>
        <div>
          <h3 className="h3">
            #{repair.id} · {repair.source_name ?? `Источник #${repair.source_id}`}
          </h3>
        </div>
        <div className={styles.cardBadges}>
          {repair.issue_id !== null && (
            <span className="chip chip--sm chip--muted">Инцидент #{repair.issue_id}</span>
          )}
          <span className={badge.chipClass} role="status">
            {badge.label}
          </span>
        </div>
      </div>

      <div className={`small muted ${styles.metaRow}`}>
        {repair.golden_total > 0 && (
          <span>
            Эталоны: {repair.golden_passed} / {repair.golden_total}
          </span>
        )}
        {repair.tokens_used > 0 && <span>Токены: {repair.tokens_used}</span>}
        {repair.status === 'activated' && (
          <span>
            Версия {repair.recipe_version ?? '—'} ·{' '}
            {repair.collection_pending
              ? 'Воркер возобновляет сбор'
              : `Сохранено строк: ${repair.saved_rows}`}
          </span>
        )}
      </div>

      {feedback && (
        <p className="small" role="status" style={{ marginBottom: '0.75rem' }}>
          <strong>{feedback}</strong>
          {repair.status === 'waiting' && repair.golden_total > 0
            ? ` Результат: эталоны ${repair.golden_passed}/${repair.golden_total}${repair.errors.length ? ` · ошибки: ${repair.errors.join('; ')}` : ' · проверка пройдена'}.`
            : repair.status === 'activated'
              ? ` Готово: версия ${repair.recipe_version ?? '—'}, сохранено строк: ${repair.saved_rows}.`
              : repair.status === 'rejected'
                ? ' Отклонён.'
                : ' Обновление статуса...'}
        </p>
      )}

      {repair.status === 'waiting' ? (
        <>
          {detailsContent}
          <form className={styles.formStack} onSubmit={(event) => void decide('edit', event)}>
            {repair.attempts.length === 0 && repair.errors.length > 0 && (
              <ul className="small">
                {repair.errors.map((message) => (
                  <li key={message}>{message}</li>
                ))}
              </ul>
            )}
            <label className="field">
              <span>Рецепт JSON</span>
              <textarea
                className="input"
                rows={8}
                spellCheck={false}
                value={edited ?? proposal}
                onChange={(event) => setEdited(event.target.value)}
              />
            </label>
            <label className="field">
              <span>Комментарий</span>
              <input
                className="input"
                value={comment}
                maxLength={1000}
                placeholder="Необязательно"
                onChange={(event) => setComment(event.target.value)}
              />
            </label>
            {error && (
              <p className="small" role="alert">
                {error}
              </p>
            )}
            <div className="actions">
              <button
                type="button"
                className="btn btn--primary"
                disabled={pending || !repair.can_approve}
                onClick={() => void decide('approve')}
              >
                Активировать рецепт
              </button>
              <button type="submit" className="btn" disabled={pending}>
                Перепроверить JSON
              </button>
              <button type="button" className="btn btn--ghost" disabled={pending} onClick={() => void decide('reject')}>
                Отклонить
              </button>
            </div>
          </form>
        </>
      ) : (
        (repair.attempts.length > 0 || repair.candidate) && (
          <details className={styles.detailsToggle}>
            <summary className="small muted">Показать ход ремонта и JSON</summary>
            {detailsContent}
            {repair.candidate && <pre className={styles.recipeCode}>{proposal}</pre>}
          </details>
        )
      )}
    </article>
  );
}

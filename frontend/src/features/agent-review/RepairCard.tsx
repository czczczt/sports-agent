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

const statusLabels: Record<string, string> = {
  running: 'Агент работает',
  waiting: 'Нужно решение оператора',
  activated: 'Рецепт активирован',
  unchanged: 'Текущий рецепт прошёл проверки',
  rejected: 'Рецепт отклонён',
  stale: 'Активный рецепт уже сменился',
};

const attemptLabels: Record<Repair['attempts'][number]['step'], string> = {
  trial: 'Агент запустил пробное извлечение',
  sample: 'Проверка на проблемном протоколе',
  golden: 'Проверка на эталонных протоколах',
  generate: 'Агент предложил первый рецепт',
  repair: 'Агент представил исправленный рецепт',
  unavailable: 'Работа приостановлена',
};

interface RepairCardProps {
  repair: Repair;
}

export function RepairCard({ repair }: RepairCardProps): React.JSX.Element {
  const [edited, setEdited] = useState<string | null>(null);
  const [comment, setComment] = useState('');
  const decision = useRepairDecision(repair.id);
  const pending = decision.isPending;
  const [error, setError] = useState<string>();
  const proposal = JSON.stringify(repair.candidate ?? {}, null, 2);

  const decide = async (action: Action, event?: FormEvent) => {
    event?.preventDefault();
    setError(undefined);
    try {
      const input: unknown = action === 'edit' ? JSON.parse(edited ?? proposal) : undefined;
      const candidate = input === undefined ? undefined : recipeInput.parse(input);
      await decision.mutateAsync({ action, candidate, comment });
      setEdited(null);
      setComment('');
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

  return (
    <article className="card">
      <h3 className="h3">
        {repair.source_name ?? `Источник #${repair.source_id}`} · ремонт #{repair.id}
      </h3>
      {repair.issue_id !== null && <p className="muted">Инцидент #{repair.issue_id}</p>}
      <p role="status">{statusLabels[repair.status] ?? repair.status}</p>
      {repair.attempts.length > 0 && (
        <ol className={styles.repairTimeline} aria-label="Ход ремонта">
          {repair.attempts.map((attempt, index) => (
            <li key={index}>
              {attemptLabels[attempt.step]} · {attempt.errors.length ? 'есть ошибки' : 'успешно'}
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
      {repair.golden_total > 0 && (
        <p>
          Эталонных протоколов совпало: {repair.golden_passed} из {repair.golden_total}
        </p>
      )}
      {repair.tokens_used > 0 && <p className="muted">Токенов использовано: {repair.tokens_used}</p>}
      {repair.status === 'activated' && (
        <p role="status">
          Версия {repair.recipe_version} ·{' '}
          {repair.collection_pending
            ? 'Воркер возобновляет сбор'
            : `Сохранено строк по этой версии: ${repair.saved_rows}`}
        </p>
      )}
      {repair.base_selector &&
        typeof repair.candidate?.baseSelector === 'string' &&
        repair.base_selector !== repair.candidate.baseSelector && (
          <dl className={styles.selectorDiff}>
            <dt>Исходный селектор</dt>
            <dd>
              <code>{repair.base_selector}</code>
            </dd>
            <dt>Селектор после ремонта</dt>
            <dd>
              <code>{repair.candidate.baseSelector}</code>
            </dd>
          </dl>
        )}
      {repair.status === 'waiting' ? (
        <form onSubmit={(event) => void decide('edit', event)}>
          {repair.attempts.length === 0 && repair.errors.length > 0 && (
            <ul>
              {repair.errors.map((message) => (
                <li key={message}>{message}</li>
              ))}
            </ul>
          )}
          <label className="field">
            Рецепт JSON
            <textarea
              className="input"
              rows={8}
              spellCheck={false}
              value={edited ?? proposal}
              onChange={(event) => setEdited(event.target.value)}
            />
          </label>
          <label className="field">
            Комментарий
            <input
              className="input"
              value={comment}
              maxLength={1000}
              onChange={(event) => setComment(event.target.value)}
            />
          </label>
          {error && <p role="alert">{error}</p>}
          <div className="actions">
            <button
              type="button"
              className="btn btn--primary"
              disabled={pending || !repair.can_approve}
              onClick={() => void decide('approve')}
            >
              Активировать проверенный рецепт
            </button>
            <button type="submit" className="btn" disabled={pending || edited === null}>
              Проверить правку
            </button>
            <button type="button" className="btn" disabled={pending} onClick={() => void decide('reject')}>
              Отклонить
            </button>
          </div>
        </form>
      ) : (
        repair.candidate && (
          <details>
            <summary>Рецепт JSON</summary>
            <pre className={styles.recipeCode}>{proposal}</pre>
          </details>
        )
      )}
    </article>
  );
}

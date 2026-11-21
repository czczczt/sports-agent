import type { AgentReviewItem } from '@/shared/api';
import { useRef } from 'react';
import styles from './ReviewCard.module.css';
import { ReviewDetails } from './ReviewDetails';
import { useReviewActions } from './useReviewActions';

interface ReviewCardProps {
  item: AgentReviewItem;
  defaultAuthor: string;
}

export function ReviewCard({ item: it, defaultAuthor }: ReviewCardProps): React.JSX.Element {
  const dialog = useRef<HTMLDialogElement>(null);
  const {
    author,
    setAuthor,
    comment,
    setComment,
    retry,
    setRetry,
    push,
    setPush,
    mutation,
    busy,
    removing,
    resetting,
    decide,
    apply,
    reset,
    msg,
  } = useReviewActions(it, defaultAuthor);
  const deleteButton = (
    <button
      type="button"
      className="btn btn--ghost btn--danger"
      disabled={busy}
      onClick={() => dialog.current?.showModal()}
    >
      ✕ Удалить
    </button>
  );
  const resetButton = (
    <button type="button" className="btn btn--ghost" disabled={busy} onClick={reset}>
      {resetting ? 'сброс…' : '↺ Сбросить решение'}
    </button>
  );

  return (
    <article
      className={`card card--clip review-card${removing ? ' review-card--removing' : ''}`}
      id={`issue-${it.issue_id}`}
    >
      <dialog ref={dialog} className="confirm-dialog" aria-label="Удаление задачи">
        <p>Удалить задачу #{it.issue_id} с сайта?</p>
        <form method="dialog" className="row">
          <button className="btn btn--ghost">Отмена</button>
          <button className="btn btn--danger" onClick={() => mutation.mutate('remove')}>
            Удалить
          </button>
        </form>
      </dialog>
      {mutation.isError && (
        <p role="alert" className="msg-error">
          {mutation.error.message}
        </p>
      )}
      <ReviewDetails item={it} />
      {it.status === 'proposed' ? (
        <div className="card__foot">
          <div className="decide-grid">
            <label className="field">
              Автор
              <input className="input input--sm" value={author} onChange={(e) => setAuthor(e.target.value)} />
            </label>
            <label className="field">
              Комментарий (обязателен при отклонении)
              <input
                className="input input--sm"
                value={comment}
                onChange={(e) => setComment(e.target.value)}
              />
            </label>
          </div>
          <div className={['row', styles.actions].join(' ')}>
            <div className="row">
              <button
                type="button"
                className="btn btn--primary"
                disabled={busy}
                onClick={() => decide('approve')}
              >
                Подтвердить
              </button>
              <button
                type="button"
                className="btn btn--ghost"
                disabled={busy}
                onClick={() => decide('reject')}
              >
                Отклонить
              </button>
              <label className={['row small muted', styles.decisions].join(' ')}>
                <input type="checkbox" checked={retry} onChange={(e) => setRetry(e.target.checked)} /> вернуть
                агенту с комментарием
              </label>
              <span className="msg-error" role="status">
                {msg}
              </span>
            </div>
            {deleteButton}
          </div>
        </div>
      ) : it.status === 'approved' ? (
        <div className="card__foot">
          <div className={['row', styles.actions].join(' ')}>
            <div className="row">
              <button type="button" className="btn btn--primary" disabled={busy} onClick={apply}>
                Применить
              </button>
              <label className={['row small muted', styles.decisions].join(' ')}>
                <input type="checkbox" checked={push} onChange={(e) => setPush(e.target.checked)} /> push и PR
                (иначе только локальная ветка)
              </label>
              <span className="small" role="status">
                {msg}
              </span>
            </div>
            <div className="row">
              {resetButton}
              {deleteButton}
            </div>
          </div>
        </div>
      ) : (
        <div className="card__foot">
          <div className={['row', styles.actions].join(' ')}>
            <span className="small muted">
              Статус: <b>{it.status}</b>
            </span>
            <div className="row">
              {resetButton}
              {deleteButton}
            </div>
          </div>
        </div>
      )}
    </article>
  );
}

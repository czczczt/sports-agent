import type { ReportItem } from '@/shared/api';
import { paths } from '@/shared/config';
import { useState } from 'react';
import { Link } from 'react-router-dom';
import styles from './AdminRequestsView.module.css';

import { useReportDecision } from './useModeration';
const REPORT_KINDS: Record<string, string> = {
  not_me: 'Это не мой результат',
  add_start: 'Добавить мой старт',
  hide_me: 'Скрыть меня из рейтинга',
  link_me: 'Привязать к профилю',
  other_club: 'Другой клуб',
  data_error: 'Ошибка в данных',
  merge_profile: 'Объединить профили',
  other: 'Обращение',
};

interface ReportCardProps {
  rep: ReportItem;
}

export function ReportCard({ rep }: ReportCardProps): React.JSX.Element {
  const [comment, setComment] = useState(rep.moderator_comment ?? '');
  const [notice, setNotice] = useState('');
  const mutation = useReportDecision();
  const decide = (decision: 'accepted' | 'resolved' | 'rejected') =>
    mutation.mutate(
      { id: rep.id, body: { decision, moderator_comment: comment || undefined } },
      { onSuccess: () => setNotice(decision === 'rejected' ? 'Обращение отклонено' : 'Решение сохранено') },
    );
  return (
    <div className={['card card--pad', styles.card].join(' ')}>
      <div className={styles.header}>
        <div>
          <div className={styles.candidates}>
            <span className="chip chip--sm chip--brand">{REPORT_KINDS[rep.kind] || rep.kind}</span>
            <span className="small muted">
              Заявка #{rep.id} · Автор ID: {rep.user_id}
            </span>
          </div>
          <div className={styles.message}>{rep.message}</div>
        </div>
        <div>
          {rep.status === 'new' && <span className="chip chip--sm chip--pending">Новая</span>}
          {rep.status === 'accepted' && <span className="chip chip--sm chip--brand">Принята</span>}
          {rep.status === 'resolved' && <span className="chip chip--sm chip--brand">Выполнена</span>}
          {rep.status === 'rejected' && <span className="chip chip--sm chip--error">Отклонена</span>}
        </div>
      </div>

      {(rep.athlete_id || rep.result_id || rep.event_id || rep.url) && (
        <div className={styles.references}>
          {rep.athlete_id && (
            <span>
              Спортсмен:{' '}
              <Link to={paths.athlete(rep.athlete_id)} target="_blank" className={styles.referenceLink}>
                ID {rep.athlete_id}
              </Link>
            </span>
          )}
          {rep.result_id && <span>Результат ID: {rep.result_id}</span>}
          {rep.event_id && (
            <span>
              Старт:{' '}
              <Link to={paths.event(rep.event_id)} target="_blank" className={styles.referenceLink}>
                ID {rep.event_id}
              </Link>
            </span>
          )}
          {rep.url && (
            <span>
              Ссылка:{' '}
              <a href={rep.url} target="_blank" rel="noreferrer" className={styles.referenceLink}>
                {rep.url}
              </a>
            </span>
          )}
        </div>
      )}

      <div className={styles.commentFields}>
        <label className={['field', styles.field].join(' ')}>
          <span className="small muted">Комментарий модератора:</span>
          <input
            type="text"
            className="input input--sm"
            placeholder="Ответ пользователю или примечание"
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            disabled={mutation.isPending}
          />
        </label>
      </div>

      {(mutation.error || notice) && (
        <div className={styles.notice} data-error={mutation.isError || undefined}>
          {mutation.error?.message ?? notice}
        </div>
      )}

      <div className={styles.reportActions}>
        <button
          type="button"
          className="btn btn--sm btn--primary"
          onClick={() => decide('accepted')}
          disabled={mutation.isPending}
        >
          Принять
        </button>
        <button
          type="button"
          className="btn btn--sm btn--primary"
          onClick={() => decide('resolved')}
          disabled={mutation.isPending}
        >
          Выполнить
        </button>
        <button
          type="button"
          className={['btn btn--sm btn--ghost', styles.reject].join(' ')}

          onClick={() => decide('rejected')}
          disabled={mutation.isPending}
        >
          Отклонить
        </button>
      </div>
    </div>
  );
}

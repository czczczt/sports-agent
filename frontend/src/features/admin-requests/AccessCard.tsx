import type { AccessRequestItem } from '@/shared/api';
import { paths } from '@/shared/config';
import { dateRu, dateTimeRu, formatFullName } from '@/shared/lib';
import { useState } from 'react';
import { Link } from 'react-router-dom';
import styles from './AdminRequestsView.module.css';

import { useAccessDecision } from './useModeration';
interface AccessCardProps {
  req: AccessRequestItem;
}

export function AccessCard({ req }: AccessCardProps): React.JSX.Element {
  const [comment, setComment] = useState('');
  const [notice, setNotice] = useState('');
  const [athlete, setAthlete] = useState(String(req.candidate_athlete_id ?? req.athlete_id ?? ''));
  const mutation = useAccessDecision();
  const decide = (decision: 'approve' | 'reject') =>
    mutation.mutate(
      {
        id: req.id,
        body: { decision, athlete_id: athlete ? Number(athlete) : null, comment: comment || undefined },
      },
      {
        onSuccess: () =>
          setNotice(
            decision === 'approve' ? 'Заявка на доступ успешно одобрена' : 'Заявка на доступ отклонена',
          ),
      },
    );
  return (
    <div className={['card card--pad', styles.card].join(' ')}>
      <div className={styles.header}>
        <div>
          <div className={styles.name}>
            {[req.last_name, req.first_name, req.middle_name].filter(Boolean).join(' ') || req.username}
          </div>
          <div className={['small muted', styles.meta].join(' ')}>
            Логин: <strong>{req.username}</strong> · Email: <strong>{req.email}</strong>
          </div>
        </div>
        <div>
          {req.status === 'pending' && <span className="chip chip--sm chip--pending">Ожидает</span>}
          {req.status === 'active' && <span className="chip chip--sm chip--brand">Активен</span>}
          {req.status === 'rejected' && <span className="chip chip--sm chip--error">Отклонён</span>}
          {req.status === 'blocked' && <span className="chip chip--sm chip--error">Заблокирован</span>}
        </div>
      </div>

      <div className={styles.details}>
        <div>
          <span className="small muted">Дата рождения:</span>{' '}
          <span className="small strong">{dateRu(req.birth_date)}</span>
        </div>
        <div>
          <span className="small muted">Город:</span> <span className="small strong">{req.city || '—'}</span>
        </div>
        <div>
          <span className="small muted">Подана:</span>{' '}
          <span className="small strong">{dateTimeRu(req.created_at)}</span>
        </div>
        <div>
          <span className="small muted">Роль:</span> <span className="small strong">{req.role}</span>
        </div>
      </div>

      <div className={styles.fields}>
        <div className={styles.candidates}>
          <span className="small strong">Привязка к спортсмену:</span>
          {req.candidate_athlete_name && req.candidate_athlete_id != null && (
            <span className="chip chip--sm chip--muted">
              Кандидат:{' '}
              <Link
                to={paths.athlete(req.candidate_athlete_id)}
                target="_blank"
                className={styles.candidateLink}
              >
                {formatFullName(req.candidate_athlete_name)}
              </Link>{' '}
              (ID: {req.candidate_athlete_id})
            </span>
          )}
          {req.athlete_id && !req.candidate_athlete_name && req.candidate_athlete_id != null && (
            <span className="chip chip--sm chip--brand">
              Привязан:{' '}
              <Link to={paths.athlete(req.athlete_id)} target="_blank" className={styles.athleteLink}>
                ID {req.athlete_id}
              </Link>
            </span>
          )}
        </div>

        <div className={styles.fieldRow}>
          <label className={['field', styles.field].join(' ')}>
            <span className="small muted">ID спортсмена:</span>
            <input
              type="number"
              className="input input--sm"
              placeholder="ID профиля"
              value={athlete}
              onChange={(e) => setAthlete(e.target.value)}
              disabled={mutation.isPending}
            />
          </label>
          <label className={['field', styles.field].join(' ')}>
            <span className="small muted">Комментарий модератора:</span>
            <input
              type="text"
              className="input input--sm"
              placeholder="Причина решения или заметка"
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              disabled={mutation.isPending}
            />
          </label>
        </div>
      </div>

      {(mutation.error || notice) && (
        <div className={styles.notice} data-error={mutation.isError || undefined}>
          {mutation.error?.message ?? notice}
        </div>
      )}

      <div className={styles.actions}>
        <button
          type="button"
          className="btn btn--sm btn--primary"
          onClick={() => decide('approve')}
          disabled={mutation.isPending}
        >
          {req.status === 'active' ? 'Сохранить привязку' : 'Одобрить доступ'}
        </button>
        {req.status !== 'rejected' && (
          <button
            type="button"
            className={['btn btn--sm btn--ghost', styles.reject].join(' ')}

            onClick={() => decide('reject')}
            disabled={mutation.isPending}
          >
            Отклонить
          </button>
        )}
      </div>
    </div>
  );
}

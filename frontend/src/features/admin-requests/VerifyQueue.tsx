import type { VerifyQueueItem } from '@/shared/api';
import { paths } from '@/shared/config';
import { dateRu } from '@/shared/lib';
import { useAuth } from '@/shared/session';
import { AsyncView, EmptyState } from '@/shared/ui';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { z } from 'zod';
import styles from './AdminRequestsView.module.css';
import { adminApi } from './api';

const sports = { all: 'Все', run: 'Бег', ski: 'Лыжи', triathlon: 'Триатлон', trail: 'Трейл' };
type Decision = 'confirmed' | 'not_employee';

function VerifyCard({
  item,
  pending,
  decide,
}: {
  item: VerifyQueueItem;
  pending: boolean;
  decide: (status: Decision, comment: string) => void;
}) {
  const [comment, setComment] = useState('');
  return (
    <article className={['card card--pad', styles.card].join(' ')}>
      <div className={styles.header}>
        <div>
          <span className="chip chip--sm chip--brand">#{item.rank}</span>{' '}
          <Link className={styles.athleteLink} to={paths.athlete(item.athlete_id)} target="_blank">
            {item.display_name}
          </Link>
          <div className="small muted">
            Вид спорта: {item.sport} · Пол: {item.gender || '—'} · Баллы: {item.points.toFixed(1)} · Стартов:{' '}
            {item.starts_count}
          </div>
        </div>
        <span className="chip chip--sm chip--pending">Не проверен</span>
      </div>
      <div className={styles.details}>
        <div>Дата рождения: {item.birth_date ? dateRu(item.birth_date) : (item.birth_year ?? '—')}</div>
        <div>
          Связанный аккаунт:{' '}
          {item.linked_username
            ? `@${item.linked_username} (${item.linked_user_email || '—'})`
            : 'Нет связки с учёткой'}
        </div>
      </div>
      <label className="field">
        <span className="small muted">Примечание проверки в «Пульсе»</span>
        <input
          className="input input--sm"
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          disabled={pending}
        />
      </label>
      <div className={styles.actions}>
        <button
          type="button"
          className="btn btn--sm btn--primary"
          disabled={pending}
          onClick={() => decide('confirmed', comment)}
        >
          Подтвердить сотрудника
        </button>
        <button
          type="button"
          className={['btn btn--sm btn--ghost', styles.reject].join(' ')}
          disabled={pending}
          onClick={() => decide('not_employee', comment)}
        >
          Не сотрудник
        </button>
      </div>
    </article>
  );
}

export function VerifyQueue() {
  const { isCaptain, captainSports } = useAuth();
  const availableSports =
    isCaptain && captainSports.length > 0
      ? Object.fromEntries(Object.entries(sports).filter(([k]) => k !== 'all' && captainSports.includes(k)))
      : sports;

  const [params, setParams] = useSearchParams();
  const topN = z.coerce.number().int().min(1).max(100).catch(10).parse(params.get('top_n'));
  const fallbackSport = captainSports[0] ?? 'run';
  const rawSport = params.get('sport') || (isCaptain && captainSports.length > 0 ? fallbackSport : 'run');
  const sport = isCaptain && captainSports.length > 0 && !captainSports.includes(rawSport)
    ? fallbackSport
    : rawSport;

  const setFilter = (name: string, value: string) => {
    const next = new URLSearchParams(params);
    next.set(name, value);
    setParams(next);
  };
  const cache = useQueryClient();
  const query = useQuery({
    queryKey: ['moderation', 'unverified', topN, sport],
    queryFn: ({ signal }) => adminApi.verifyQueue(topN, sport === 'all' ? undefined : sport, signal),
  });
  const decision = useMutation({
    mutationFn: ({ id, status, comment }: { id: number; status: Decision; comment: string }) =>
      adminApi.decideVerification(id, { status, comment: comment.trim() || undefined }),
    onSuccess: () =>
      Promise.all([
        cache.invalidateQueries({ queryKey: ['moderation'] }),
        cache.invalidateQueries({ queryKey: ['rating'] }),
      ]),
  });
  return (
    <>
      <div className={['filters-bar', styles.filters].join(' ')}>
        <span className="small muted">Топ-N (на вид × пол)</span>
        <div className={styles.segment}>
          {[10, 20, 50].map((n) => (
            <button
              type="button"
              key={n}
              aria-pressed={topN === n}
              className={[styles.segmentBtn, topN === n ? styles.segmentBtnActive : ''].join(' ')}
              onClick={() => setFilter('top_n', String(n))}
            >
              {n}
            </button>
          ))}
        </div>
        <span className="small muted">Вид спорта</span>
        <div className={styles.segment}>
          {Object.entries(availableSports).map(([value, label]) => (
            <button
              type="button"
              key={value}
              aria-pressed={sport === value}
              className={[styles.segmentBtn, sport === value ? styles.segmentBtnActive : ''].join(' ')}
              onClick={() => setFilter('sport', value)}
            >
              {label}
            </button>
          ))}
        </div>
      </div>
      {decision.error && (
        <p role="alert" className={styles.notice} data-error>
          {decision.error.message}
        </p>
      )}
      {decision.data && (
        <p role="status" className={styles.notice}>
          {decision.data.message}
          {decision.data.auto_blocked_user && ' (связанный пользователь заблокирован)'}
        </p>
      )}
      <AsyncView query={query}>
        {(items) =>
          items.length === 0 ? (
            <EmptyState title="Очередь проверки пуста" text="В выбранном топе нет спортсменов на проверку." />
          ) : (
            <div className={styles.list}>
              {items.map((item) => (
                <VerifyCard
                  key={`${item.athlete_id}-${item.linked_user_id ?? ''}`}
                  item={item}
                  pending={decision.isPending}
                  decide={(status, comment) => decision.mutate({ id: item.athlete_id, status, comment })}
                />
              ))}
            </div>
          )
        }
      </AsyncView>
    </>
  );
}

import { KEEP_SCROLL } from '@/shared/hooks';
import { useAuth } from '@/shared/session';
import { EmptyState, ErrorState, Icon, Loader } from '@/shared/ui';
import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { z } from 'zod';
import styles from './AgentReviewView.module.css';
import { RepairCard } from './RepairCard';
import { ReviewList } from './ReviewList';
import { useAgentReview } from './useAgentReview';
import { useRepairs } from './useRepairs';

const tabs = [
  { value: 'waiting', label: 'Ждут решения' },
  { value: 'all', label: 'Все' },
  { value: 'activated', label: 'Активированы' },
  { value: 'rejected', label: 'Отклонены' },
] as const;

type TabValue = (typeof tabs)[number]['value'];

function matchesTab(status: string, tab: TabValue): boolean {
  if (tab === 'all') return true;
  if (tab === 'waiting') return status === 'waiting' || status === 'running';
  if (tab === 'activated') return status === 'activated' || status === 'unchanged';
  if (tab === 'rejected') return status === 'rejected' || status === 'stale';
  return true;
}

export function AgentReviewView(): React.JSX.Element {
  const { isAdmin, openAuthModal } = useAuth();
  const [params, setParams] = useSearchParams();
  const [pinnedIds, setPinnedIds] = useState<Set<number>>(() => new Set());
  const tab = z
    .enum(['waiting', 'all', 'activated', 'rejected'])
    .catch('waiting')
    .parse(params.get('tab'));

  const pinRepair = (id: number) => {
    setPinnedIds((prev) => {
      if (prev.has(id)) return prev;
      const next = new Set(prev);
      next.add(id);
      return next;
    });
  };

  const { data: legacyData, refetch: reloadLegacy } = useAgentReview(
    tab === 'waiting' ? 'proposed' : tab,
    '',
    isAdmin,
  );
  const { data: repairs, error, isFetching, refetch: reloadRepairs } = useRepairs();

  if (!isAdmin) {
    return (
      <div className="card empty agent-auth-guard">
        <span className="empty__icon">
          <Icon name="user" />
        </span>
        <div className="strong">Требуются права администратора</div>
        <p className="small muted">
          Для просмотра и утверждения правок агента войдите под учётной записью администратора.
        </p>
        <button type="button" className="btn btn--primary" onClick={openAuthModal}>
          Войти как администратор
        </button>
      </div>
    );
  }

  // Строгая сортировка по убыванию ID (#22, #21, #20...) во всех вкладках
  const sortedRepairs = [...(repairs ?? [])].sort((a, b) => b.id - a.id);
  const filteredRepairs = sortedRepairs.filter(
    (r) => matchesTab(r.status, tab) || (tab === 'waiting' && pinnedIds.has(r.id)),
  );
  const counts: Record<TabValue, number> = {
    waiting: sortedRepairs.filter((r) => matchesTab(r.status, 'waiting')).length,
    all: sortedRepairs.length,
    activated: sortedRepairs.filter((r) => matchesTab(r.status, 'activated')).length,
    rejected: sortedRepairs.filter((r) => matchesTab(r.status, 'rejected')).length,
  };

  const legacyItemsCount = legacyData?.items.length ?? 0;
  const isEmpty = filteredRepairs.length === 0 && legacyItemsCount === 0;

  return (
    <>
      <div className="page-head">
        <div className="page-head__text">
          <h1 className="h1 h1-sm">Правки агента</h1>
          <p className="lead">
            Восстановление сбора протоколов, проверка JSON-рецептов на эталонах и инциденты.
          </p>
        </div>
        <button
          type="button"
          className="btn"
          disabled={isFetching}
          onClick={() => {
            void reloadRepairs();
            void reloadLegacy();
          }}
        >
          {isFetching ? 'Обновление…' : 'Обновить'}
        </button>
      </div>

      <div className={styles.tabBar}>
        <div className="rating-segment" role="group" aria-label="Статус ремонтов">
          {tabs.map(({ value, label }) => (
            <button
              key={value}
              type="button"
              aria-pressed={tab === value}
              onClick={() => {
                setPinnedIds(new Set());
                setParams({ tab: value }, KEEP_SCROLL);
              }}
            >
              {label} ({counts[value]})
            </button>
          ))}
        </div>
      </div>

      {error && !repairs ? (
        <ErrorState error={error} onRetry={reloadRepairs} />
      ) : !repairs ? (
        <Loader text="Загрузка ремонтов…" />
      ) : isEmpty ? (
        <EmptyState
          title="Задач в этой вкладке нет"
          text="Выберите вкладку «Все» или запустите проверку агента."
        />
      ) : (
        <div className={styles.repairList}>
          {filteredRepairs.map((repair) => (
            <RepairCard key={repair.id} repair={repair} onDecide={() => pinRepair(repair.id)} />
          ))}
          {legacyData && legacyItemsCount > 0 && (
            <ReviewList data={legacyData} status={tab} hideEmpty />
          )}
        </div>
      )}
    </>
  );
}

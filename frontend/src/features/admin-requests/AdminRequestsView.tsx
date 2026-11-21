import { useAuth } from '@/shared/session';
import { EmptyState, ErrorState, Icon, Loader } from '@/shared/ui';
import { useSearchParams } from 'react-router-dom';
import { z } from 'zod';
import { AccessCard } from './AccessCard';
import styles from './AdminRequestsView.module.css';
import { ReportCard } from './ReportCard';
import { useModeration } from './useModeration';

export function AdminRequestsView(): React.JSX.Element {
  const { user, isAdmin, openAuthModal } = useAuth();
  const isModerator = isAdmin || user?.role === 'captain';

  const [searchParams, setSearchParams] = useSearchParams();
  const currentTab = z.enum(['access', 'reports']).catch('access').parse(searchParams.get('tab'));
  const accessFilter = searchParams.get('access_status') ?? 'pending';
  const reportsFilter = searchParams.get('report_status') ?? 'new';

  const { accessItems, reportItems, active } = useModeration(
    currentTab,
    accessFilter,
    reportsFilter,
    isModerator,
  );
  const { isLoading: loading, error, refetch: loadData } = active;

  if (!isModerator) {
    return (
      <div className="card empty agent-auth-guard">
        <span className="empty__icon">
          <Icon name="user" />
        </span>
        <div className="strong">Требуются права модератора</div>
        <p className="small muted">
          Для просмотра и утверждения заявок требуется учётная запись администратора или капитана.
        </p>
        <button type="button" className="btn btn--primary" onClick={openAuthModal}>
          Войти
        </button>
      </div>
    );
  }

  const setTab = (tab: 'access' | 'reports') => {
    const next = new URLSearchParams(searchParams);
    next.set('tab', tab);
    setSearchParams(next);
  };

  const setAccessStatusFilter = (st: string) => {
    const next = new URLSearchParams(searchParams);
    next.set('access_status', st);
    setSearchParams(next);
  };

  const setReportsStatusFilter = (st: string) => {
    const next = new URLSearchParams(searchParams);
    next.set('report_status', st);
    setSearchParams(next);
  };

  return (
    <>
      <div className="page-head">
        <div className="page-head__text">
          <h1 className="h1 h1-sm">Модерация заявок</h1>
          <p className="lead">Рассмотрение заявок на регистрацию и обращений спортсменов.</p>
        </div>

        <div className="rating-segment">
          <button
            type="button"
            aria-pressed={currentTab === 'access'}
            className={currentTab === 'access' ? 'is-active' : undefined}
            onClick={() => setTab('access')}
          >
            Заявки на доступ
          </button>
          <button
            type="button"
            aria-pressed={currentTab === 'reports'}
            className={currentTab === 'reports' ? 'is-active' : undefined}
            onClick={() => setTab('reports')}
          >
            Обращения
          </button>
        </div>
      </div>

      {currentTab === 'access' && (
        <div className={['filters-bar', styles.filters].join(' ')}>
          <span className="small muted">Статус:</span>
          <div className="rating-segment">
            {[
              { val: 'pending', label: 'Ожидают' },
              { val: 'active', label: 'Одобренные' },
              { val: 'rejected', label: 'Отклонённые' },
              { val: 'all', label: 'Все' },
            ].map((f) => (
              <button
                key={f.val}
                type="button"
                aria-pressed={accessFilter === f.val}
                className={accessFilter === f.val ? 'is-active' : undefined}
                onClick={() => setAccessStatusFilter(f.val)}
              >
                {f.label}
              </button>
            ))}
          </div>
        </div>
      )}

      {currentTab === 'reports' && (
        <div className={['filters-bar', styles.filters].join(' ')}>
          <span className="small muted">Статус:</span>
          <div className="rating-segment">
            {[
              { val: 'new', label: 'Новые' },
              { val: 'accepted', label: 'Принятые' },
              { val: 'resolved', label: 'Выполненные' },
              { val: 'rejected', label: 'Отклонённые' },
              { val: 'all', label: 'Все' },
            ].map((f) => (
              <button
                key={f.val}
                type="button"
                aria-pressed={reportsFilter === f.val}
                className={reportsFilter === f.val ? 'is-active' : undefined}
                onClick={() => setReportsStatusFilter(f.val)}
              >
                {f.label}
              </button>
            ))}
          </div>
        </div>
      )}

      {error ? (
        <ErrorState error={error} onRetry={loadData} />
      ) : loading ? (
        <Loader text="Загрузка списка заявок…" />
      ) : currentTab === 'access' ? (
        accessItems.length === 0 ? (
          <EmptyState
            title="Заявок на доступ не найдено"
            text="С выбранным статусом в системе нет заявок пользователей."
          />
        ) : (
          <div className={['grid-cards', styles.list].join(' ')}>
            {accessItems.map((req) => (
              <AccessCard key={req.id} req={req} />
            ))}
          </div>
        )
      ) : reportItems.length === 0 ? (
        <EmptyState
          title="Обращений не найдено"
          text="С выбранным статусом в системе нет обращений пользователей."
        />
      ) : (
        <div className={['grid-cards', styles.list].join(' ')}>
          {reportItems.map((rep) => (
            <ReportCard key={rep.id} rep={rep} />
          ))}
        </div>
      )}
    </>
  );
}

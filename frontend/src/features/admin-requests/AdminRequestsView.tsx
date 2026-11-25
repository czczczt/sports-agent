import { useAuth } from '@/shared/session';
import { EmptyState, ErrorState, Icon, Loader } from '@/shared/ui';
import { sportTitle } from '@/shared/lib';
import { useSearchParams } from 'react-router-dom';
import { z } from 'zod';
import { AccessCard } from './AccessCard';
import styles from './AdminRequestsView.module.css';
import { ReportCard } from './ReportCard';
import { VerifyQueue } from './VerifyQueue';
import { useModeration } from './useModeration';

const sections = [
  { value: 'access', label: 'Заявки на доступ', icon: 'user' },
  { value: 'reports', label: 'Обращения', icon: 'flag' },
  { value: 'unverified', label: 'Очередь «не проверен»', icon: 'trophy' },
] as const;

const statuses = {
  access: { pending: 'Ожидают', active: 'Одобренные', rejected: 'Отклонённые', all: 'Все' },
  reports: {
    new: 'Новые',
    accepted: 'Принятые',
    resolved: 'Выполненные',
    rejected: 'Отклонённые',
    all: 'Все',
  },
};

export function AdminRequestsView(): React.JSX.Element {
  const { user, isAdmin, openAuthModal } = useAuth();
  const isModerator = isAdmin || user?.role === 'captain';

  const [searchParams, setSearchParams] = useSearchParams();
  const currentTab = z
    .enum(['access', 'reports', 'unverified'])
    .catch('access')
    .parse(searchParams.get('tab'));
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

  const setFilter = (key: string, value: string) => {
    const next = new URLSearchParams(searchParams);
    next.set(key, value);
    setSearchParams(next);
  };

  return (
    <>
      <div className="page-head">
        <div className="page-head__text">
          <div className="row">
            <h1 className="h1 h1-sm">Модерация заявок</h1>
            {user?.role === 'captain' && (
              <span className="chip chip--sm chip--brand">
                Капитан ({user.captain_sports?.map(sportTitle).join(', ') || 'вид не назначен'})
              </span>
            )}
          </div>
          <p className="lead">Регистрация, обращения спортсменов и проверка сотрудников в топе рейтинга.</p>
        </div>
      </div>
      <div className={`rating-segment ${styles.sections}`} role="group" aria-label="Раздел модерации">
        {sections.map(({ value, label, icon }) => (
          <button
            key={value}
            type="button"
            aria-pressed={currentTab === value}
            onClick={() => setFilter('tab', value)}
          >
            <Icon name={icon} />
            {label}
          </button>
        ))}
      </div>

      {currentTab !== 'unverified' && (
        <div className={styles.filterGroup} role="group" aria-label="Статус">
          <span className="small muted">Статус</span>
          <div className={`rating-segment ${styles.choices}`}>
            {Object.entries(statuses[currentTab]).map(([value, label]) => (
              <button
                key={value}
                type="button"
                aria-pressed={(currentTab === 'access' ? accessFilter : reportsFilter) === value}
                onClick={() => setFilter(currentTab === 'access' ? 'access_status' : 'report_status', value)}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      )}

      {currentTab === 'unverified' ? (
        <VerifyQueue />
      ) : error ? (
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

import { plural } from '@/shared/lib';
import { useAuth } from '@/shared/session';
import { ErrorState, Icon, Loader } from '@/shared/ui';
import { AdapterTable } from './AdapterTable';
import styles from './StatusView.module.css';
import { useSystemStatus } from './useSystemStatus';

export function StatusView(): React.JSX.Element {
  const { user, isAdmin, openAuthModal } = useAuth();

  if (!isAdmin) {
    return (
      <div className="card empty agent-auth-guard">
        <span className="empty__icon">
          <Icon name="user" />
        </span>
        <div className="strong">Требуются права администратора</div>
        <p className="small muted">
          Просмотр технического состояния и очереди задач доступен только администратору.
        </p>
        {!user && (
          <button type="button" className="btn btn--primary" onClick={openAuthModal}>
            Войти
          </button>
        )}
      </div>
    );
  }

  return <StatusPanel />;
}

function StatusPanel(): React.JSX.Element {
  const { data, error, isFetching, refetch } = useSystemStatus();
  const athletes = data?.overview.athletes ?? 0;

  return (
    <>
      <header className={styles.header}>
        <h1 className="h1 h1-sm">Статус системы</h1>
        <button
          type="button"
          className="btn btn--ghost btn--sm"
          aria-label="Обновить"
          title="Обновить"
          onClick={() => void refetch()}
          disabled={isFetching}
        >
          <Icon name="refresh" /> <span>Обновить</span>
        </button>
        <p className="muted">Состояние базы данных, очереди задач и источников данных.</p>
      </header>

      {isFetching && !data && <Loader text="Проверка состояния компонентов…" inCard />}
      {error && <ErrorState error={error} onRetry={refetch} />}

      {data && (
        <>
          <div className={styles.metrics}>
            <section className={`card ${styles.metric}`}>
              <div className={styles.metricHead}>
                <h2>База данных</h2>
                <span className={`chip chip--sm ${data.database.connected ? 'chip--brand' : 'chip--error'}`}>
                  {data.database.connected ? 'На связи' : 'Нет связи'}
                </span>
              </div>
              <strong className={styles.value}>{data.database.engine}</strong>
              <p className="muted small">
                Задержка ответа · {data.database.latency_ms.toLocaleString('ru-RU')} мс
              </p>
            </section>

            <section className={`card ${styles.metric}`}>
              <div className={styles.metricHead}>
                <h2>Очередь задач (Procrastinate)</h2>
                <span
                  className={`chip chip--sm ${data.queue.status === 'available' ? 'chip--brand' : 'chip--pending'}`}
                >
                  {data.queue.status === 'available' ? 'Доступна' : 'Недоступна'}
                </span>
              </div>
              <strong className={styles.value}>
                {data.queue.jobs_pending.toLocaleString('ru-RU')} в очереди
              </strong>
              <p className={styles.meta}>
                <span>В работе · {data.queue.jobs_doing ?? 0}</span>
                <span>Ошибок · {data.queue.jobs_failed}</span>
                <span>Успешно · {data.queue.jobs_done.toLocaleString('ru-RU')}</span>
              </p>
            </section>

            <section className={`card ${styles.metric}`}>
              <div className={styles.metricHead}>
                <h2>Данные в системе</h2>
              </div>
              <strong className={styles.value}>
                {athletes.toLocaleString('ru-RU')}{' '}
                {plural(athletes, 'спортсмен', 'спортсмена', 'спортсменов')}
              </strong>
              <p className={styles.meta}>
                <span>Стартов · {(data.overview.competitions ?? 0).toLocaleString('ru-RU')}</span>
                <span>Результатов · {(data.overview.results ?? 0).toLocaleString('ru-RU')}</span>
              </p>
            </section>
          </div>
          <AdapterTable adapters={data.adapters} />
        </>
      )}
    </>
  );
}

import { ErrorState, Icon, Loader } from '@/shared/ui';
import { AdapterTable } from './AdapterTable';
import styles from './StatusView.module.css';
import { useSystemStatus } from './useSystemStatus';

export function StatusView(): React.JSX.Element {
  const { data, error, isFetching: loading, refetch: fetchStatus } = useSystemStatus();

  return (
    <div className={['status-page', styles.page].join(' ')}>
      <div className={styles.header}>
        <div>
          <h1 className={styles.title}>Статус системы и адаптеров</h1>
          <p className={['muted small', styles.subtitle].join(' ')}>
            Мониторинг фоновой очереди, БД и источников данных (SPEC v1.3 §12)
          </p>
        </div>
        <button
          type="button"
          className="btn btn--secondary btn--sm"
          onClick={() => void fetchStatus()}
          disabled={loading}
        >
          <Icon name="spark" /> Обновить
        </button>
      </div>

      {loading && !data && <Loader text="Проверка состояния компонентов..." inCard />}
      {error && <ErrorState error={error} onRetry={fetchStatus} />}

      {data && (
        <div className={styles.content}>
          <div className={styles.metrics}>
            <div className={['card', styles.card].join(' ')}>
              <div className={['muted small uppercase', styles.eyebrow].join(' ')}>База данных</div>
              <div className={styles.metric}>
                <span
                  className={styles.databaseIndicator}
                  data-healthy={data.database.connected || undefined}
                />
                <span className={styles.value}>{data.database.engine}</span>
              </div>
              <div className={['muted small', styles.meta].join(' ')}>
                Задержка ответа: <strong>{data.database.latency_ms} мс</strong>
              </div>
            </div>

            <div className={['card', styles.card].join(' ')}>
              <div className={['muted small uppercase', styles.eyebrow].join(' ')}>
                Очередь задач (Procrastinate)
              </div>
              <div className={styles.metric}>
                <span
                  className={styles.queueIndicator}
                  data-healthy={data.queue.status === 'available' || undefined}
                />
                <span className={styles.value}>В очереди: {data.queue.jobs_pending ?? 0}</span>
              </div>
              <div className={['muted small', styles.meta].join(' ')}>
                В работе: {data.queue.jobs_doing ?? 0} · Ошибок: {data.queue.jobs_failed ?? 0} · Успешно:{' '}
                {data.queue.jobs_done ?? 0}
              </div>
            </div>

            <div className={['card', styles.card].join(' ')}>
              <div className={['muted small uppercase', styles.eyebrow].join(' ')}>Данные в системе</div>
              <div className={styles.total}>
                {data.overview.athletes?.toLocaleString('ru-RU') ?? 0} спортсменов
              </div>
              <div className={['muted small', styles.meta].join(' ')}>
                Стартов: {data.overview.competitions ?? 0} · Результатов:{' '}
                {data.overview.results?.toLocaleString('ru-RU') ?? 0}
              </div>
            </div>
          </div>

          <AdapterTable adapters={data.adapters} />
        </div>
      )}
    </div>
  );
}

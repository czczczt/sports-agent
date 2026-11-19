import { useEffect, useState } from 'react';
import { api } from '@/api/client';
import { Loader, ErrorState, Icon } from '@/components/ui';
import { useDocumentTitle, SITE_TITLE } from '@/hooks/useDocumentTitle';

interface SystemStatus {
  status: string;
  timestamp: number;
  database: {
    connected: boolean;
    latency_ms: number;
    engine: string;
  };
  queue: {
    status: string;
    jobs_pending?: number;
    jobs_doing?: number;
    jobs_failed?: number;
    jobs_done?: number;
  };
  adapters: Array<{
    id: number;
    name: string;
    base_url: string;
    platform: string;
    sport_types: string;
    enabled: boolean;
    competitions_count: number;
    results_count: number;
    open_issues_count: number;
    status: string;
  }>;
  overview: {
    athletes?: number;
    competitions?: number;
    results?: number;
  };
}

export function StatusPage() {
  useDocumentTitle(`Статус системы · ${SITE_TITLE}`);
  const [data, setData] = useState<SystemStatus | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<Error | null>(null);

  const fetchStatus = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.get<SystemStatus>('/api/status');
      setData(res);
    } catch (err) {
      setError(err instanceof Error ? err : new Error('Не удалось загрузить статус системы'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStatus();
  }, []);

  return (
    <div className="status-page" style={{ maxWidth: 1100, margin: '0 auto', padding: '1.5rem 1rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
        <div>
          <h1 style={{ margin: 0, fontSize: '1.75rem', fontWeight: 700 }}>Статус системы и адаптеров</h1>
          <p className="muted small" style={{ margin: '0.25rem 0 0' }}>Мониторинг фоновой очереди, БД и источников данных (SPEC v1.3 §12)</p>
        </div>
        <button type="button" className="btn btn--secondary btn--sm" onClick={fetchStatus} disabled={loading}>
          <Icon name="spark" /> Обновить
        </button>
      </div>

      {loading && !data && <Loader text="Проверка состояния компонентов..." inCard />}
      {error && <ErrorState error={error} onRetry={fetchStatus} />}

      {data && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          {/* Верхние карточки состояния */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '1rem' }}>
            {/* База данных */}
            <div className="card" style={{ padding: '1.25rem' }}>
              <div className="muted small uppercase" style={{ letterSpacing: '0.05em' }}>База данных</div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginTop: '0.5rem' }}>
                <span style={{
                  display: 'inline-block',
                  width: 10,
                  height: 10,
                  borderRadius: '50%',
                  backgroundColor: data.database.connected ? 'var(--color-success, #22c55e)' : 'var(--color-error, #ef4444)'
                }} />
                <span style={{ fontSize: '1.25rem', fontWeight: 600 }}>{data.database.engine}</span>
              </div>
              <div className="muted small" style={{ marginTop: '0.5rem' }}>
                Задержка ответа: <strong>{data.database.latency_ms} мс</strong>
              </div>
            </div>

            {/* Очередь Procrastinate */}
            <div className="card" style={{ padding: '1.25rem' }}>
              <div className="muted small uppercase" style={{ letterSpacing: '0.05em' }}>Очередь задач (Procrastinate)</div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginTop: '0.5rem' }}>
                <span style={{
                  display: 'inline-block',
                  width: 10,
                  height: 10,
                  borderRadius: '50%',
                  backgroundColor: data.queue.status === 'available' ? 'var(--color-success, #22c55e)' : 'var(--color-warning, #f59e0b)'
                }} />
                <span style={{ fontSize: '1.25rem', fontWeight: 600 }}>В очереди: {data.queue.jobs_pending ?? 0}</span>
              </div>
              <div className="muted small" style={{ marginTop: '0.5rem' }}>
                В работе: {data.queue.jobs_doing ?? 0} · Ошибок: {data.queue.jobs_failed ?? 0} · Успешно: {data.queue.jobs_done ?? 0}
              </div>
            </div>

            {/* Метрики хранилища */}
            <div className="card" style={{ padding: '1.25rem' }}>
              <div className="muted small uppercase" style={{ letterSpacing: '0.05em' }}>Данные в системе</div>
              <div style={{ fontSize: '1.25rem', fontWeight: 600, marginTop: '0.5rem' }}>
                {data.overview.athletes?.toLocaleString('ru-RU') ?? 0} спортсменов
              </div>
              <div className="muted small" style={{ marginTop: '0.5rem' }}>
                Стартов: {data.overview.competitions ?? 0} · Результатов: {data.overview.results?.toLocaleString('ru-RU') ?? 0}
              </div>
            </div>
          </div>

          {/* Таблица источников/адаптеров */}
          <div className="card" style={{ padding: '1.5rem' }}>
            <h2 style={{ fontSize: '1.25rem', fontWeight: 600, marginTop: 0, marginBottom: '1rem' }}>
              Адаптеры источников данных ({data.adapters.length})
            </h2>
            <div style={{ overflowX: 'auto' }}>
              <table className="table" style={{ width: '100%', textAlign: 'left', borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--border, #e5e7eb)' }}>
                    <th style={{ padding: '0.75rem 0.5rem' }}>Источник</th>
                    <th style={{ padding: '0.75rem 0.5rem' }}>Платформа</th>
                    <th style={{ padding: '0.75rem 0.5rem' }}>Виды спорта</th>
                    <th style={{ padding: '0.75rem 0.5rem' }}>Стартов</th>
                    <th style={{ padding: '0.75rem 0.5rem' }}>Результатов</th>
                    <th style={{ padding: '0.75rem 0.5rem' }}>Ошибок (issue)</th>
                    <th style={{ padding: '0.75rem 0.5rem' }}>Статус</th>
                  </tr>
                </thead>
                <tbody>
                  {data.adapters.length === 0 ? (
                    <tr>
                      <td colSpan={7} className="muted" style={{ padding: '1.5rem', textAlign: 'center' }}>
                        Источники данных пока не зарегистрированы
                      </td>
                    </tr>
                  ) : (
                    data.adapters.map((src) => (
                      <tr key={src.id} style={{ borderBottom: '1px solid var(--border-subtle, #f3f4f6)' }}>
                        <td style={{ padding: '0.75rem 0.5rem', fontWeight: 600 }}>
                          <a href={src.base_url} target="_blank" rel="noopener noreferrer" style={{ color: 'inherit' }}>
                            {src.name}
                          </a>
                        </td>
                        <td style={{ padding: '0.75rem 0.5rem' }}><code>{src.platform}</code></td>
                        <td style={{ padding: '0.75rem 0.5rem' }}>{src.sport_types || 'все'}</td>
                        <td style={{ padding: '0.75rem 0.5rem' }}>{src.competitions_count}</td>
                        <td style={{ padding: '0.75rem 0.5rem' }}>{src.results_count.toLocaleString('ru-RU')}</td>
                        <td style={{ padding: '0.75rem 0.5rem' }}>
                          {src.open_issues_count > 0 ? (
                            <span style={{ color: 'var(--color-error, #ef4444)', fontWeight: 600 }}>
                              {src.open_issues_count}
                            </span>
                          ) : (
                            <span className="muted">0</span>
                          )}
                        </td>
                        <td style={{ padding: '0.75rem 0.5rem' }}>
                          <span
                            className={`chip chip--sm ${
                              src.status === 'healthy'
                                ? 'chip--success'
                                : src.status === 'warning'
                                ? 'chip--warning'
                                : 'chip--muted'
                            }`}
                          >
                            {src.status === 'healthy' ? 'Активен' : src.status === 'warning' ? 'Требует внимания' : 'Отключён'}
                          </span>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

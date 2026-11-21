import type { SystemStatus } from '@/shared/api';
import styles from './StatusView.module.css';
interface AdapterTableProps {
  adapters: SystemStatus['adapters'];
}
export function AdapterTable({ adapters }: AdapterTableProps): React.JSX.Element {
  return (
    <div className={['card', styles.adapters].join(' ')}>
      <h2 className={styles.sectionTitle}>Адаптеры источников данных ({adapters.length})</h2>
      <div className={styles.viewport}>
        <table className={['table', styles.table].join(' ')}>
          <thead>
            <tr className={styles.columns}>
              <th scope="col" className={styles.cell}>
                Источник
              </th>
              <th scope="col" className={styles.cell}>
                Платформа
              </th>
              <th scope="col" className={styles.cell}>
                Виды спорта
              </th>
              <th scope="col" className={styles.cell}>
                Стартов
              </th>
              <th scope="col" className={styles.cell}>
                Результатов
              </th>
              <th scope="col" className={styles.cell}>
                Ошибок (issue)
              </th>
              <th scope="col" className={styles.cell}>
                Статус
              </th>
            </tr>
          </thead>
          <tbody>
            {adapters.length === 0 ? (
              <tr>
                <td colSpan={7} className={['muted', styles.empty].join(' ')}>
                  Источники данных пока не зарегистрированы
                </td>
              </tr>
            ) : (
              adapters.map((src) => (
                <tr key={src.id} className={styles.row}>
                  <td className={styles.source}>
                    <a
                      href={src.base_url ?? undefined}
                      target="_blank"
                      rel="noopener noreferrer"
                      className={styles.link}
                    >
                      {src.name}
                    </a>
                  </td>
                  <td className={styles.cell}>
                    <code>{src.platform}</code>
                  </td>
                  <td className={styles.cell}>{src.sport_types || 'все'}</td>
                  <td className={styles.cell}>{src.competitions_count}</td>
                  <td className={styles.cell}>{src.results_count.toLocaleString('ru-RU')}</td>
                  <td className={styles.cell}>
                    {src.open_issues_count > 0 ? (
                      <span className={styles.issues}>{src.open_issues_count}</span>
                    ) : (
                      <span className="muted">0</span>
                    )}
                  </td>
                  <td className={styles.cell}>
                    <span
                      className={`chip chip--sm ${
                        src.status === 'healthy'
                          ? 'chip--success'
                          : src.status === 'warning'
                            ? 'chip--warning'
                            : 'chip--muted'
                      }`}
                    >
                      {src.status === 'healthy'
                        ? 'Активен'
                        : src.status === 'warning'
                          ? 'Требует внимания'
                          : 'Отключён'}
                    </span>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

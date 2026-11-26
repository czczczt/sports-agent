import type { SystemStatus } from '@/shared/api';
import { sourceName, sportTitle } from '@/shared/lib';
import { EmptyState, Icon } from '@/shared/ui';
import type { ReactNode } from 'react';
import styles from './StatusView.module.css';

type Adapter = SystemStatus['adapters'][number];
const fields: { label: string; numeric?: boolean; value: (adapter: Adapter) => ReactNode }[] = [
  { label: 'Платформа', value: (src) => src.platform || '—' },
  {
    label: 'Виды спорта',
    value: (src) =>
      src.sport_types
        ?.split(',')
        .map((s) => sportTitle(s.trim()))
        .join(', ') || 'Все виды',
  },
  { label: 'Стартов', numeric: true, value: (src) => src.competitions_count.toLocaleString('ru-RU') },
  { label: 'Результатов', numeric: true, value: (src) => src.results_count.toLocaleString('ru-RU') },
  {
    label: 'Ошибок',
    numeric: true,
    value: (src) => (
      <span className={src.open_issues_count > 0 ? styles.issues : undefined}>
        {src.open_issues_count.toLocaleString('ru-RU')}
      </span>
    ),
  },
];

function AdapterName({ adapter }: { adapter: Adapter }) {
  const name = sourceName(adapter.name);
  return adapter.base_url ? (
    <a href={adapter.base_url} target="_blank" rel="noopener noreferrer" className={styles.source}>
      {name} <Icon name="external" className="icon-sm" />
    </a>
  ) : (
    <span>{name}</span>
  );
}

function AdapterStatus({ status }: { status: string }) {
  if (status === 'healthy') return <span className="chip chip--sm chip--brand">Активен</span>;
  if (status === 'warning') return <span className="chip chip--sm chip--pending">Требует внимания</span>;
  return <span className="chip chip--sm chip--muted">Отключён</span>;
}

export function AdapterTable({ adapters }: { adapters: Adapter[] }): React.JSX.Element {
  return (
    <section className={styles.adapters} aria-labelledby="adapters-title">
      <h2 id="adapters-title" className="h2">
        Адаптеры источников <span className="chip chip--sm">{adapters.length}</span>
      </h2>
      {adapters.length === 0 ? (
        <EmptyState title="Источники данных пока не зарегистрированы" />
      ) : (
        <>
          <div className={`card table-wrap ${styles.tableView}`}>
            <table className="table" aria-labelledby="adapters-title">
              <thead>
                <tr>
                  <th scope="col">Источник</th>
                  {fields.map((field) => (
                    <th key={field.label} scope="col" className={field.numeric ? 'right' : undefined}>
                      {field.label}
                    </th>
                  ))}
                  <th scope="col">Статус</th>
                </tr>
              </thead>
              <tbody>
                {adapters.map((src) => (
                  <tr key={src.id}>
                    <td className="strong">
                      <AdapterName adapter={src} />
                    </td>
                    {fields.map((field) => (
                      <td key={field.label} className={field.numeric ? 'num right' : undefined}>
                        {field.value(src)}
                      </td>
                    ))}
                    <td>
                      <AdapterStatus status={src.status} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <ul className={styles.adapterList}>
            {adapters.map((src) => (
              <li key={src.id} className={`card ${styles.adapterCard}`}>
                <div className={styles.adapterHead}>
                  <h3>
                    <AdapterName adapter={src} />
                  </h3>
                  <AdapterStatus status={src.status} />
                </div>
                <dl className={styles.details}>
                  {fields.map((field) => (
                    <div key={field.label} className={field.numeric ? styles.count : undefined}>
                      <dt>{field.label}</dt>
                      <dd>{field.value(src)}</dd>
                    </div>
                  ))}
                </dl>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}

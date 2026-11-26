import { useState, type FormEvent } from 'react';
import type { CollectionSource, CollectionStartRequest } from './api';
import styles from './AdminCollectionView.module.css';

export function CollectionForm({
  sources,
  starting,
  onStart,
}: {
  sources: CollectionSource[];
  starting: boolean;
  onStart: (body: CollectionStartRequest) => void;
}): React.JSX.Element {
  const [excluded, setExcluded] = useState<Set<string>>(new Set());
  const [codes, setCodes] = useState<Record<string, string>>({});
  const [error, setError] = useState('');
  const selected = sources.filter(({ code }) => !excluded.has(code));

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const starts = selected
      .filter(({ enabled }) => enabled)
      .flatMap(({ code }) =>
        Array.from(new Set((codes[code] ?? '').split(/[\s,;]+/).filter(Boolean))).map((event_code) => ({
          source: code,
          event_code,
        })),
      );
    const invalid = starts.find(({ event_code }) => !/^[a-z0-9_-]{1,200}$/i.test(event_code));
    if (invalid) {
      setError(
        `Некорректный код «${invalid.event_code}» (${invalid.source}). Используй латинские буквы, цифры, дефисы и подчёркивания, до 200 символов.`,
      );
      return;
    }
    if (starts.length > 100) {
      setError('За один запуск можно указать до 100 кодов.');
      return;
    }
    setError('');
    onStart({ sources: selected.map(({ code }) => code), starts });
  }

  return (
    <form className={`card card--pad ${styles.stack}`} onSubmit={submit}>
      <fieldset className={styles.sources} disabled={starting}>
        <legend className="h2">Площадки для сбора</legend>
        <div className={styles.columns}>
          {sources.map(({ code, label, automatic, enabled }) => (
            <div className={styles.panel} key={code}>
              <label className={styles.choice}>
                <input
                  type="checkbox"
                  checked={!excluded.has(code)}
                  onChange={({ target: { checked } }) => {
                    setExcluded((previous) => {
                      const next = new Set(previous);
                      if (checked) next.delete(code);
                      else next.add(code);
                      return next;
                    });
                    setError('');
                  }}
                />
                <strong>{label}</strong>
              </label>
              <p className={`small muted ${styles.sourceMeta}`}>
                {!enabled
                  ? 'Площадка отключена в реестре'
                  : automatic
                    ? 'Автопоиск доступен'
                    : (codes[code] ?? '').trim()
                      ? 'Сбор по коду старта'
                      : 'Нужен код старта'}
              </p>
            </div>
          ))}
        </div>
        {sources.length === 0 && <p className="muted">В реестре нет площадок.</p>}
        {sources.some(({ enabled }) => enabled) && (
          <details className={styles.codes}>
            <summary>Указать известные коды стартов</summary>
            <p className="small muted">Введи коды через запятую или пробел.</p>
            <div className={styles.columns}>
              {sources
                .filter(({ enabled }) => enabled)
                .map(({ code, label }) => (
                  <label className="field" key={code}>
                    Коды стартов · {label}
                    <input
                      type="text"
                      className="input input--sm"
                      value={codes[code] ?? ''}
                      disabled={excluded.has(code)}
                      onChange={({ target }) => {
                        setCodes((previous) => ({ ...previous, [code]: target.value }));
                        setError('');
                      }}
                    />
                  </label>
                ))}
            </div>
          </details>
        )}
      </fieldset>
      {error && (
        <p role="alert" className={styles.error}>
          {error}
        </p>
      )}
      <button
        type="submit"
        className={`btn btn--primary ${styles.action}`}
        disabled={starting || selected.length === 0}
      >
        {starting ? 'Запускаем сбор…' : 'Обновить данные'}
      </button>
    </form>
  );
}

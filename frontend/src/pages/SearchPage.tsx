// «Найти себя» (/). Перенос search.html: поиск по фамилии и году рождения.
// Параметры поиска живут в адресе (?last_name=…&birth_year=…), поэтому ссылку на выдачу можно отправить.
import { useState, type FormEvent } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { athletesApi } from '@/api/endpoints';
import { BirthYearInput } from '@/components/forms/BirthYearInput';
import { EmptyState, ErrorState, Icon, Loader } from '@/components/ui';
import { useApi } from '@/hooks/useApi';
import { SITE_TITLE, useDocumentTitle } from '@/hooks/useDocumentTitle';
import { athleteMeta, initials, plural } from '@/lib/format';

function parseYear(raw: string | null): number | null {
  const s = (raw || '').trim();
  return /^\d+$/.test(s) ? parseInt(s, 10) : null;
}

export function SearchPage() {
  useDocumentTitle(`Найти себя — ${SITE_TITLE}`);
  const [params, setParams] = useSearchParams();
  const lastName = (params.get('last_name') || '').trim();
  const birthYear = parseYear(params.get('birth_year'));
  const missingBirthYear = !!lastName && !birthYear;

  return (
    <>
      <div className="page-head__text">
        <h1 className="h1">Найти себя</h1>
        <p className="lead">Введите фамилию и год рождения - мы найдём ваши старты. В профиле вы сможете увидеть личную статистику, историю и положение среди других спортсменов.</p>
      </div>

      {/* key: при переходе по истории форма заново берёт значения из адреса */}
      <SearchForm
        key={params.toString()}
        initialLastName={lastName}
        initialBirthYear={birthYear ? String(birthYear) : ''}
        onSubmit={(ln, by) => setParams({ last_name: ln, birth_year: by })}
      />

      {missingBirthYear ? (
        <EmptyState title="Укажите год рождения" text="Для поиска укажите фамилию и год рождения." />
      ) : lastName && birthYear ? (
        <SearchResults lastName={lastName} birthYear={birthYear} />
      ) : null}
    </>
  );
}

function SearchForm({ initialLastName, initialBirthYear, onSubmit }: {
  initialLastName: string;
  initialBirthYear: string;
  onSubmit: (lastName: string, birthYear: string) => void;
}) {
  const [lastName, setLastName] = useState(initialLastName);
  const [birthYear, setBirthYear] = useState(initialBirthYear);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    onSubmit(lastName.trim(), birthYear.trim());
  };

  return (
    <form className="card card--pad" onSubmit={submit}>
      <div className="form-search">
        <label className="field">Фамилия
          <input className="input" type="text" id="last_name" name="last_name" value={lastName}
            onChange={(e) => setLastName(e.target.value)} placeholder="Например: Иванов" required autoComplete="family-name" />
        </label>
        <label className="field">Год рождения
          <BirthYearInput value={birthYear} onChange={setBirthYear} />
        </label>
        <button type="submit" className="btn btn--primary btn--lg">Найти</button>
      </div>
    </form>
  );
}

function SearchResults({ lastName, birthYear }: { lastName: string; birthYear: number }) {
  const { data: candidates, error, loading, reload } = useApi(
    (signal) => athletesApi.search(lastName, birthYear, signal),
    [lastName, birthYear],
  );

  if (error) return <ErrorState error={error} onRetry={reload} />;
  if (!candidates || loading) return <Loader text="Ищем спортсменов…" />;

  return (
    <>
      <div className="row row--between">
        <h2 className="strong" style={{ fontSize: 16 }}>
          {candidates.length
            ? `Нашли ${candidates.length} ${plural(candidates.length, 'спортсмена', 'спортсмена', 'спортсменов')}`
            : 'Никого не нашли'}
        </h2>
      </div>

      {candidates.length ? (
        <div className="grid-cards">
          {candidates.map((cand) => {
            const meta = athleteMeta(cand);
            return (
              <div key={cand.id} className="card card--pad candidate-card">
                <div className="row candidate-card__head">
                  <span className="avatar" aria-hidden="true">{initials(cand.display_name)}</span>
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <div className="strong candidate-card__name">{cand.display_name}</div>
                    <div className="small muted num candidate-card__meta" title={meta}>{meta}</div>
                  </div>
                </div>
                <div className="chips" style={{ marginTop: 'auto' }}>
                  <Link to={`/athletes-view/${cand.id}`} className="chip chip--run" title="Открыть результаты в беге">
                    <Icon name="run" className="icon-sm" />
                    Бег · {cand.starts_count} {plural(cand.starts_count, 'старт', 'старта', 'стартов')}
                  </Link>
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <EmptyState title="Спортсмен не найден" text="Проверьте написание фамилии или уберите год рождения." />
      )}
    </>
  );
}

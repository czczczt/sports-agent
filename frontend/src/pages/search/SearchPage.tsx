import { SearchForm, SearchResults } from '@/features/search';
import { SITE_TITLE, useDocumentTitle } from '@/shared/hooks';
import { parseId } from '@/shared/lib';
import { EmptyState } from '@/shared/ui';
import { useSearchParams } from 'react-router-dom';

export function SearchPage(): React.JSX.Element {
  useDocumentTitle('Найти себя — ' + SITE_TITLE);
  const [params, setParams] = useSearchParams();
  const lastName = (params.get('last_name') || '').trim();
  const birthYear = parseId(params.get('birth_year'));
  const missingBirthYear = !!lastName && !birthYear;

  return (
    <>
      <div className="page-head__text">
        <h1 className="h1">Найти себя</h1>
        <p className="lead">
          Введите фамилию и год рождения - мы найдём ваши старты. В профиле вы сможете увидеть личную
          статистику, историю и положение среди других спортсменов.
        </p>
      </div>

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

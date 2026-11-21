import { useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import styles from './ProtocolSearch.module.css';

interface ProtocolSearchProps {
  initial: string;
  onSearch: (value: string) => void;
  resetTo: string;
}

export function ProtocolSearch({ initial, onSearch, resetTo }: ProtocolSearchProps): React.JSX.Element {
  const [value, setValue] = useState(initial);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    onSearch(value.trim());
  };
  return (
    <form className={['form-inline', styles.form].join(' ')} role="search" onSubmit={submit}>
      <label className="sr-only" htmlFor="protocol-search">
        Поиск в протоколе
      </label>
      <input
        id="protocol-search"
        className="input input--sm"
        type="search"
        name="search"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder="Фамилия или номер"
      />
      <button type="submit" className={['btn btn--primary', styles.button].join(' ')}>
        Найти
      </button>
      {initial && (
        <Link to={resetTo} preventScrollReset className={['btn btn--ghost', styles.button].join(' ')}>
          Сбросить
        </Link>
      )}
    </form>
  );
}

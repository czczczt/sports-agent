import { useState, type FormEvent } from 'react';
import { BirthYearInput } from './BirthYearInput';

interface SearchFormProps {
  initialLastName: string;
  initialBirthYear: string;
  onSubmit: (lastName: string, birthYear: string) => void;
}

export function SearchForm({
  initialLastName,
  initialBirthYear,
  onSubmit,
}: SearchFormProps): React.JSX.Element {
  const [lastName, setLastName] = useState(initialLastName);
  const [birthYear, setBirthYear] = useState(initialBirthYear);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    onSubmit(lastName.trim(), birthYear.trim());
  };

  return (
    <form className="card card--pad" onSubmit={submit}>
      <div className="form-search">
        <label className="field">
          Фамилия
          <input
            className="input"
            type="text"
            id="last_name"
            name="last_name"
            value={lastName}
            onChange={(e) => setLastName(e.target.value)}
            placeholder="Например: Иванов"
            required
            autoComplete="family-name"
          />
        </label>
        <label htmlFor="birth_year" className="field">
          Год рождения
          <BirthYearInput value={birthYear} onChange={setBirthYear} />
        </label>
        <button type="submit" className="btn btn--primary btn--lg">
          Найти
        </button>
      </div>
    </form>
  );
}

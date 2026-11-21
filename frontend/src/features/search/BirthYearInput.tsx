const BASE_YEAR = 1990;

interface Props {
  id?: string;
  name?: string;
  value: string;
  onChange: (value: string) => void;
}

export function BirthYearInput({
  id = 'birth_year',
  name = 'birth_year',
  value,
  onChange,
}: Props): React.JSX.Element {
  return (
    <input
      className="input"
      type="number"
      inputMode="numeric"
      id={id}
      name={name}
      value={value}
      onChange={(e) => onChange(e.target.value.slice(0, 4))}
      placeholder={String(BASE_YEAR)}
      min={1920}
      max={new Date().getFullYear()}
      required
    />
  );
}

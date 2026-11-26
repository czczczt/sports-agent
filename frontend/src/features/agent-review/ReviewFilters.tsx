import type { AgentReviewPage as AgentReviewData } from '@/shared/api';
import { sourceName } from '@/shared/lib';
import { SelectField } from '@/shared/ui';
import { useState, type FormEvent } from 'react';
import layout from './AgentReviewView.module.css';

interface ReviewFiltersProps {
  data?: AgentReviewData;
  status: string;
  source: string;
  onApply: (status: string, source: string) => void;
}

export function ReviewFilters({ data, status, source, onApply }: ReviewFiltersProps): React.JSX.Element {
  const [st, setSt] = useState(status);
  const [src, setSrc] = useState(source);
  const statuses = data?.statuses ?? [status];
  const submit = (e: FormEvent) => {
    e.preventDefault();
    onApply(st, src);
  };
  return (
    <form className={layout.reviewFilters} onSubmit={submit}>
      <SelectField
        label="Статус"
        name="status"
        value={st}
        onChange={setSt}
        options={statuses.map((value) => ({ value, label: value }))}
      />
      <SelectField
        label="Площадка"
        name="source"
        value={src}
        onChange={setSrc}
        options={[
          { value: '', label: 'Все площадки' },
          ...(data?.sources ?? []).map((value) => ({ value, label: sourceName(value) })),
        ]}
      />
      <button className="btn btn--primary">Показать</button>
    </form>
  );
}

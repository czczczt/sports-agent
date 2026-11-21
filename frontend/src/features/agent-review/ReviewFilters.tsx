import type { AgentReviewPage as AgentReviewData } from '@/shared/api';
import { sourceName } from '@/shared/lib';
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
      <label className="field">
        Статус
        <select name="status" className="input input--sm" value={st} onChange={(e) => setSt(e.target.value)}>
          {statuses.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </label>
      <label className="field">
        Площадка
        <select
          name="source"
          className="input input--sm"
          value={src}
          onChange={(e) => setSrc(e.target.value)}
        >
          <option value="">все</option>
          {(data?.sources ?? []).map((s) => (
            <option key={s} value={s}>
              {sourceName(s)}
            </option>
          ))}
        </select>
      </label>
      <button className="btn btn--primary">Показать</button>
    </form>
  );
}

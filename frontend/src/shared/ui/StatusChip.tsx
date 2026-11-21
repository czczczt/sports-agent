interface StatusChipProps {
  status?: string | null;
}

export function StatusChip({ status }: StatusChipProps): React.JSX.Element {
  if (status === 'FIN') return <span className="chip chip--sm chip--brand">финиш</span>;
  if (status === 'DNF') return <span className="chip chip--sm chip--pending">DNF</span>;
  if (status === 'DSQ') return <span className="chip chip--sm chip--error">DSQ</span>;
  return <span className="chip chip--sm chip--muted">{status || '—'}</span>;
}

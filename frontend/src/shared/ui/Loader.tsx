interface LoaderProps {
  text?: string;
  inCard?: boolean;
}

export function Loader({ text = 'Загрузка…', inCard = true }: LoaderProps): React.JSX.Element {
  return (
    <div className={inCard ? 'card empty' : 'empty'} role="status" aria-live="polite">
      <span className="spinner" aria-hidden="true" />
      <p className="small muted">{text}</p>
    </div>
  );
}

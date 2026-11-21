import { renderAssessmentMarkdown } from '@/shared/lib';
import { Icon } from '@/shared/ui';
import { useMutation } from '@tanstack/react-query';
import { useState } from 'react';
import { athletesApi } from './api';
import styles from './AssessmentCard.module.css';

interface AssessmentCardProps {
  athleteId: number;
}

export function AssessmentCard({ athleteId }: AssessmentCardProps): React.JSX.Element {
  const [open, setOpen] = useState(true);
  const assessment = useMutation({ mutationFn: athletesApi.assessment });
  const onClick = () => {
    if (assessment.data) setOpen(!open);
    else assessment.mutate(athleteId);
  };
  const buttonText = assessment.isPending
    ? 'Формируем отчёт…'
    : assessment.isError
      ? 'Попробовать снова'
      : assessment.data && open
        ? 'Скрыть отчёт'
        : 'Показать отчёт';
  const visible = assessment.isPending || assessment.isError || (assessment.data && open);

  return (
    <section id="agent" className="card card--pad">
      <div className={['row row--between', styles.header].join(' ')}>
        <div className={styles.heading}>
          <h2 className="h2">ИИ-оценка</h2>
        </div>
        <button
          type="button"
          className="btn btn--primary btn--stretch-mobile"
          disabled={assessment.isPending}
          onClick={onClick}
        >
          <Icon name="spark" />
          <span>{buttonText}</span>
        </button>
      </div>
      {visible && (
        <div>
          {assessment.isPending && (
            <div className={['row', styles.progress].join(' ')}>
              <span className="spinner" aria-hidden="true" />
              <span className="small muted">Агент обрабатывает метрики и пишет отчёт…</span>
            </div>
          )}
          {assessment.isError && (
            <div className="assessment" aria-live="polite">
              Не удалось сформировать оценку: {assessment.error.message}
            </div>
          )}
          {assessment.data && (
            <>
              <div
                className="assessment"
                aria-live="polite"
                dangerouslySetInnerHTML={{
                  __html: renderAssessmentMarkdown(assessment.data.assessment_text),
                }}
              />
              <div className={['row small muted', styles.footnote].join(' ')}>
                <span className={styles.disclaimer}>Оценка носит исключительно справочный характер</span>
              </div>
            </>
          )}
        </div>
      )}
    </section>
  );
}

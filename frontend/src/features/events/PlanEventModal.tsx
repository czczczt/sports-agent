import type { components } from '@/shared/api';
import { useAuth } from '@/shared/session';
import { DateInput, Icon, SelectField } from '@/shared/ui';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';
import { eventsApi } from './api';
import styles from './PlanEventModal.module.css';

interface PlanEventModalProps {
  isOpen: boolean;
  onClose: () => void;
}

const sportLabels: Record<string, string> = {
  run: 'Бег',
  ski: 'Лыжи',
  triathlon: 'Триатлон',
  trail: 'Трейл',
};

export function PlanEventModal({ isOpen, onClose }: PlanEventModalProps): React.JSX.Element | null {
  const { isAdmin, captainSports } = useAuth();
  const queryClient = useQueryClient();
  const dialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!isOpen || !dialog) return;
    dialog.showModal();
    return () => dialog.close();
  }, [isOpen]);

  const allowedSports = isAdmin
    ? ['run', 'ski', 'triathlon', 'trail']
    : captainSports.length
      ? captainSports
      : ['run'];

  const [title, setTitle] = useState('');
  const [sport, setSport] = useState(allowedSports[0] || 'run');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [city, setCity] = useState('');
  const [address, setAddress] = useState('');
  const [raceName, setRaceName] = useState('Основная дистанция');
  const [distanceKm, setDistanceKm] = useState<number | undefined>(undefined);
  const [note, setNote] = useState('');
  const [errorMsg, setErrorMsg] = useState('');

  const mutation = useMutation({
    mutationFn: (body: components['schemas']['PlannedEventCreate']) => eventsApi.createPlanned(body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['events'] });
      onClose();
    },
    onError: (err: Error) => {
      setErrorMsg(err.message || 'Ошибка создания запланированного старта');
    },
  });

  if (!isOpen) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg('');
    if (!title || !startDate) {
      setErrorMsg('Укажите название и дату старта');
      return;
    }

    mutation.mutate({
      title,
      sport,
      planned_date_start: startDate,
      planned_date_end: endDate || undefined,
      city: city || undefined,
      address: address || undefined,
      planned_note: note || undefined,
      races: [
        {
          name: raceName || 'Дистанция',
          distance_km: distanceKm,
        },
      ],
    });
  };

  return (
    <dialog
      ref={dialogRef}
      className={styles.dialog}
      aria-labelledby="plan-event-title"
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      onPointerDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <form onSubmit={handleSubmit} className={styles.form}>
        <header className={styles.header}>
          <span className={styles.mark}>
            <Icon name="calendar" />
          </span>
          <h2 className="h2" id="plan-event-title">
            Запланировать старт
          </h2>
          <button type="button" className={styles.close} onClick={onClose} aria-label="Закрыть окно">
            <Icon name="close" />
          </button>
        </header>
        <div className={styles.body}>
          {errorMsg && (
            <div className="auth-error" role="alert">
              {errorMsg}
            </div>
          )}

          <label className="field">
            <span className="field__label">Название старта *</span>
            <input
              type="text"
              className="input input--sm"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Например: Московский Марафон"
              required
            />
          </label>

          <div className={styles.pair}>
            <SelectField
              label="Вид спорта"
              name="sport"
              value={sport}
              onChange={setSport}
              options={allowedSports.map((value) => ({ value, label: sportLabels[value] ?? value }))}
            />

            <label className="field">
              <span className="field__label">Город</span>
              <input
                type="text"
                className="input input--sm"
                value={city}
                onChange={(e) => setCity(e.target.value)}
                placeholder="Москва"
              />
            </label>
          </div>

          <div className={styles.pair}>
            <div className="field">
              <label htmlFor="plan-start-date">Дата начала *</label>
              <DateInput
                id="plan-start-date"
                calendarLabel="Открыть календарь даты начала"
                value={startDate}
                onChange={setStartDate}
                required
              />
            </div>

            <div className="field">
              <label htmlFor="plan-end-date">Дата окончания</label>
              <DateInput
                id="plan-end-date"
                calendarLabel="Открыть календарь даты окончания"
                value={endDate}
                onChange={setEndDate}
              />
            </div>
          </div>

          <label className="field">
            <span className="field__label">Локация / Адрес</span>
            <input
              type="text"
              className="input input--sm"
              value={address}
              onChange={(e) => setAddress(e.target.value)}
              placeholder="Лужники"
            />
          </label>

          <div className={styles.distance}>
            <label className="field">
              <span className="field__label">Планируемая дистанция</span>
              <input
                type="text"
                className="input input--sm"
                value={raceName}
                onChange={(e) => setRaceName(e.target.value)}
                placeholder="42.2 км"
              />
            </label>
            <label className="field">
              <span className="field__label">Км</span>
              <input
                type="number"
                step="0.1"
                className="input input--sm"
                value={distanceKm !== undefined ? distanceKm : ''}
                onChange={(e) => setDistanceKm(e.target.value ? parseFloat(e.target.value) : undefined)}
                placeholder="42.2"
              />
            </label>
          </div>

          <label className="field">
            <span className="field__label">Заметка</span>
            <textarea
              className="input input--sm"
              rows={2}
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="Примечание к планируемому старту"
            />
          </label>
        </div>
        <footer className={styles.actions}>
          <button type="button" className="btn btn--ghost" onClick={onClose} disabled={mutation.isPending}>
            Отмена
          </button>
          <button type="submit" className="btn btn--primary" disabled={mutation.isPending}>
            {mutation.isPending ? 'Сохранение...' : 'Запланировать'}
          </button>
        </footer>
      </form>
    </dialog>
  );
}

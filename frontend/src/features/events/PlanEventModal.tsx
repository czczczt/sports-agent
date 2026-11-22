import type { components } from '@/shared/api';
import { useAuth } from '@/shared/session';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { eventsApi } from './api';

interface PlanEventModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export function PlanEventModal({ isOpen, onClose }: PlanEventModalProps): React.JSX.Element | null {
  const { isAdmin, captainSports } = useAuth();
  const queryClient = useQueryClient();

  const allowedSports = isAdmin ? ['run', 'ski', 'triathlon', 'trail'] : captainSports.length ? captainSports : ['run'];

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
    <div
      role="dialog"
      aria-modal="true"
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 100,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '16px',
        background: 'rgba(0, 0, 0, 0.65)',
        backdropFilter: 'blur(4px)',
      }}
      onPointerDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        className="card"
        style={{
          width: '100%',
          maxWidth: '520px',
          padding: '24px',
          background: 'var(--surface)',
          borderRadius: '12px',
          maxHeight: '90vh',
          overflowY: 'auto',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
          <h2 className="h2" style={{ margin: 0 }}>Запланировать старт</h2>
          <button type="button" className="btn btn--sm btn--ghost" onClick={onClose}>✕</button>
        </div>

        {errorMsg && (
          <div className="auth-error" style={{ marginBottom: '16px' }}>
            {errorMsg}
          </div>
        )}

        <form onSubmit={handleSubmit} className="modal-form">
          <label className="field">
            <span className="field__label">Название старта *</span>
            <input
              type="text"
              className="field__input"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Например: Московский Марафон"
              required
            />
          </label>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
            <label className="field">
              <span className="field__label">Вид спорта</span>
              <select
                className="field__input"
                value={sport}
                onChange={(e) => setSport(e.target.value)}
              >
                {allowedSports.map((s) => (
                  <option key={s} value={s}>
                    {s === 'run' ? 'Бег' : s === 'ski' ? 'Лыжи' : s === 'triathlon' ? 'Триатлон' : 'Трейл'}
                  </option>
                ))}
              </select>
            </label>

            <label className="field">
              <span className="field__label">Город</span>
              <input
                type="text"
                className="field__input"
                value={city}
                onChange={(e) => setCity(e.target.value)}
                placeholder="Москва"
              />
            </label>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
            <label className="field">
              <span className="field__label">Дата начала *</span>
              <input
                type="date"
                className="field__input"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                required
              />
            </label>

            <label className="field">
              <span className="field__label">Дата окончания</span>
              <input
                type="date"
                className="field__input"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
              />
            </label>
          </div>

          <label className="field">
            <span className="field__label">Локация / Адрес</span>
            <input
              type="text"
              className="field__input"
              value={address}
              onChange={(e) => setAddress(e.target.value)}
              placeholder="Лужники"
            />
          </label>

          <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '12px' }}>
            <label className="field">
              <span className="field__label">Планируемая дистанция</span>
              <input
                type="text"
                className="field__input"
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
                className="field__input"
                value={distanceKm !== undefined ? distanceKm : ''}
                onChange={(e) => setDistanceKm(e.target.value ? parseFloat(e.target.value) : undefined)}
                placeholder="42.2"
              />
            </label>
          </div>

          <label className="field">
            <span className="field__label">Заметка</span>
            <textarea
              className="field__input"
              rows={2}
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="Примечание к планируемому старту"
            />
          </label>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px', marginTop: '16px' }}>
            <button type="button" className="btn btn--secondary" onClick={onClose} disabled={mutation.isPending}>
              Отмена
            </button>
            <button type="submit" className="btn btn--primary" disabled={mutation.isPending}>
              {mutation.isPending ? 'Сохранение...' : 'Запланировать'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

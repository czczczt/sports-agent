import { dateRu, formatDateRu, parseIsoDate, toIsoDate } from '@/shared/lib';
import AirDatepicker from 'air-datepicker';
import { useEffect, useRef } from 'react';
import { Icon } from './Icon';

interface DateInputProps {
  id: string;
  calendarLabel: string;
  value: string;
  onChange: (value: string) => void;
  required?: boolean;
}

export function DateInput({ id, calendarLabel, value, onChange, required }: DateInputProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const triggerRef = useRef<HTMLInputElement>(null);
  const calendar = useRef<AirDatepicker<HTMLInputElement>>();
  const notify = useRef(onChange);
  notify.current = onChange;

  useEffect(() => {
    const input = inputRef.current;
    const trigger = triggerRef.current;
    if (!input || !trigger) return;
    const position = () => {
      const popup = picker.$datepicker;
      const field = input.getBoundingClientRect();
      const gap = 8;
      const maxLeft = document.documentElement.clientWidth - popup.offsetWidth - gap;
      const maxTop = document.documentElement.clientHeight - popup.offsetHeight - gap;
      const below = field.bottom + gap;
      const top = below <= maxTop ? below : field.top - popup.offsetHeight - gap;
      popup.style.left = `${Math.max(gap, Math.min(field.left, maxLeft))}px`;
      popup.style.top = `${Math.max(gap, Math.min(top, maxTop))}px`;
    };
    const picker = new AirDatepicker(trigger, {
      container: input.closest('dialog') ?? undefined,
      classes: 'single-date-calendar',
      position,
      autoClose: true,
      showEvent: 'click',
      dateFormat: 'dd.MM.yyyy',
      buttons: [
        { content: 'Сегодня', attrs: { type: 'button' }, onClick: (dp) => dp.selectDate(new Date()) },
        {
          content: 'Очистить',
          attrs: { type: 'button' },
          onClick: (dp) => {
            dp.clear();
            dp.hide();
          },
        },
      ],
      onSelect: ({ date }) => {
        input.setCustomValidity('');
        input.value = date instanceof Date ? formatDateRu(date) : '';
        notify.current(date instanceof Date ? toIsoDate(date) : '');
      },
    });
    calendar.current = picker;
    const reposition = () => {
      if (picker.visible) position();
    };
    window.addEventListener('resize', reposition);
    window.addEventListener('scroll', reposition, true);
    return () => {
      window.removeEventListener('resize', reposition);
      window.removeEventListener('scroll', reposition, true);
      picker.destroy();
      calendar.current = undefined;
    };
  }, []);

  useEffect(() => {
    const picker = calendar.current;
    const date = parseIsoDate(value);
    if (!picker) return;
    if (date && (!picker.selectedDates[0] || toIsoDate(picker.selectedDates[0]) !== value)) {
      picker.selectDate(date, { silent: true });
      picker.setViewDate(date);
    } else if (!date && picker.selectedDates.length) {
      picker.clear({ silent: true });
    }
    if (inputRef.current) {
      inputRef.current.value = date ? formatDateRu(date) : '';
      inputRef.current.setCustomValidity('');
    }
  }, [value]);

  return (
    <span className="date-field__box">
      <input
        ref={inputRef}
        id={id}
        type="text"
        className="input input--sm"
        defaultValue={value ? dateRu(value) : ''}
        placeholder="дд.мм.гггг"
        autoComplete="off"
        required={required}
        onKeyDown={(event) => {
          if (event.key === 'ArrowDown') {
            event.preventDefault();
            triggerRef.current?.focus();
            calendar.current?.show();
          }
        }}
        onChange={({ currentTarget }) => {
          const raw = currentTarget.value;
          const iso = raw.replace(/^(\d{2})\.(\d{2})\.(\d{4})$/, '$3-$2-$1');
          const date = parseIsoDate(iso);
          const valid = date && toIsoDate(date) === iso;
          currentTarget.setCustomValidity(raw && !valid ? 'Введите дату в формате дд.мм.гггг' : '');
          if (!raw || valid) notify.current(iso);
        }}
      />
      <span className="date-field__trigger">
        <Icon name="calendar" />
        <input
          ref={triggerRef}
          type="button"
          aria-label={calendarLabel}
          title={calendarLabel}
          onKeyDownCapture={(event) => {
            if (!calendar.current?.visible) {
              event.stopPropagation();
              return;
            }
            if (event.key === 'Enter') event.preventDefault();
            if (event.key === 'Escape') {
              event.preventDefault();
              event.stopPropagation();
              calendar.current.hide();
              triggerRef.current?.focus();
            }
          }}
        />
      </span>
    </span>
  );
}

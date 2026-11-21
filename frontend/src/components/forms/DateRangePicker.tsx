// Поле «Дата» каталога стартов: диапазон или одна дата через Air Datepicker
// (перенос скрипта из events_catalog.html). Значения — ISO «YYYY-MM-DD».
import { useEffect, useRef } from 'react';
import AirDatepicker from 'air-datepicker';
import { Icon } from '@/components/ui/Icon';
import { formatDateRu, parseIsoDate, toIsoDate } from '@/lib/format';

const LOCALE_RU = {
  days: ['Воскресенье', 'Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота'],
  daysShort: ['Вс', 'Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб'],
  daysMin: ['Вс', 'Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб'],
  months: ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь', 'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'],
  monthsShort: ['Янв', 'Фев', 'Мар', 'Апр', 'Май', 'Июн', 'Июл', 'Авг', 'Сен', 'Окт', 'Ноя', 'Дек'],
  today: 'Сегодня',
  clear: 'Очистить',
  dateFormat: 'dd.MM.yyyy',
  timeFormat: 'HH:mm',
  firstDay: 1 as const,
};

interface Props {
  from: string;
  to: string;
  onChange: (from: string, to: string) => void;
}

export function DateRangePicker({ from, to, onChange }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;

  useEffect(() => {
    const input = inputRef.current;
    if (!input) return;
    const emit = (a: Date | null, b: Date | null) => onChangeRef.current(a ? toIsoDate(a) : '', b ? toIsoDate(b) : '');

    const dp: AirDatepicker<HTMLInputElement> = new AirDatepicker(input, {
      range: true,
      toggleSelected: false,
      multipleDatesSeparator: ' — ',
      minDate: new Date(1920, 0, 1),
      maxDate: new Date(new Date().getFullYear(), 11, 31, 23, 59, 59),
      autoClose: true,
      buttons: [
        {
          content: 'Только эта дата',
          className: 'air-datepicker-button-single',
          onClick: (picker) => {
            if (picker.selectedDates.length >= 1) {
              const d = picker.selectedDates[0];
              picker.selectDate([d, d]);
              picker.hide();
            }
          },
        },
        'today',
        'clear',
      ],
      locale: LOCALE_RU,
      onSelect({ date }) {
        if (Array.isArray(date) && date.length === 1) {
          // Кликнута одна дата — сразу показываем её и считаем фильтром «от и до».
          input.value = formatDateRu(date[0]);
          emit(date[0], date[0]);
        } else if (Array.isArray(date) && date.length >= 2) {
          if (date[0].getTime() === date[1].getTime()) input.value = formatDateRu(date[0]);
          emit(date[0], date[1]);
        } else {
          emit(null, null);
        }
      },
      onHide() {
        if (dp.selectedDates.length === 1) {
          const d = dp.selectedDates[0];
          input.value = formatDateRu(d);
          emit(d, d);
        }
      },
    });

    // Повторный клик по выбранной дате фиксирует одну дату и закрывает календарь.
    const onDocClick = (e: MouseEvent) => {
      const cell = (e.target as Element | null)?.closest?.('.air-datepicker-cell.-day-.-selected-');
      if (cell && dp.selectedDates.length === 1) {
        const d = dp.selectedDates[0];
        dp.selectDate([d, d]);
        dp.hide();
      }
    };
    document.addEventListener('click', onDocClick, true);

    // Начальные даты (из адреса страницы).
    const initFrom = parseIsoDate(from);
    const initTo = parseIsoDate(to);
    if (initFrom && initTo && initFrom.getTime() === initTo.getTime()) {
      dp.selectDate(initFrom);
      input.value = formatDateRu(initFrom);
    } else {
      const selected = [initFrom, initTo].filter((d): d is Date => !!d);
      if (selected.length) dp.selectDate(selected);
    }

    return () => {
      document.removeEventListener('click', onDocClick, true);
      dp.destroy();
    };
    // Календарь создаётся один раз; при смене адреса форма пересоздаётся через key.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <label className="field date-field">Дата
      <div className="date-field__box">
        <input ref={inputRef} className="input input--sm" type="text" id="date_range_picker"
          placeholder="01.01.2000" readOnly autoComplete="off" />
        <span className="date-field__icon"><Icon name="calendar" className="icon-sm" /></span>
      </div>
    </label>
  );
}

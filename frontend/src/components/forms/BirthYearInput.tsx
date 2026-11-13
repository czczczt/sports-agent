// Поле «Год рождения» (перенос скрипта из search.html):
// только цифры, максимум 4 знака; на пустом поле стрелки/колёсико/спин-кнопки
// начинают с года из placeholder (1990), а не с нуля.
import { useEffect, useRef, type KeyboardEvent, type ClipboardEvent, type PointerEvent } from 'react';

const ALLOWED_KEYS = ['Backspace', 'Delete', 'Tab', 'Escape', 'Enter', 'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'Home', 'End'];
const BASE_YEAR = 1990;

interface Props {
  id?: string;
  name?: string;
  value: string;
  onChange: (value: string) => void;
}

export function BirthYearInput({ id = 'birth_year', name = 'birth_year', value, onChange }: Props) {
  const ref = useRef<HTMLInputElement>(null);
  const valueRef = useRef(value);
  valueRef.current = value;

  const step = (up: boolean) => onChange(String(up ? BASE_YEAR + 1 : BASE_YEAR - 1));

  // Колёсико — только через нативный слушатель: React вешает wheel как passive, preventDefault не сработает.
  useEffect(() => {
    const input = ref.current;
    if (!input) return;
    const onWheel = (e: WheelEvent) => {
      if (!valueRef.current && document.activeElement === input) {
        e.preventDefault();
        step(e.deltaY < 0);
      }
    };
    input.addEventListener('wheel', onWheel, { passive: false });
    return () => input.removeEventListener('wheel', onWheel);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Клик по браузерным стрелочкам (spin button) — правые ~35px поля.
  const onPointerDown = (e: PointerEvent<HTMLInputElement>) => {
    if (value) return;
    const rect = e.currentTarget.getBoundingClientRect();
    if (e.clientX >= rect.right - 35) {
      e.preventDefault();
      step(e.clientY < rect.top + rect.height / 2);
      e.currentTarget.focus();
    }
  };

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (!value && (e.key === 'ArrowUp' || e.key === 'ArrowDown')) {
      e.preventDefault();
      step(e.key === 'ArrowUp');
      return;
    }
    if (ALLOWED_KEYS.includes(e.key) || e.ctrlKey || e.metaKey || e.altKey) return;
    if (!/^[0-9]$/.test(e.key)) {
      e.preventDefault();
      return;
    }
    // number-инпут не даёт selectionStart — проверяем выделение документа.
    const hasSelection = (window.getSelection()?.toString().length ?? 0) > 0;
    if (value.length >= 4 && !hasSelection) e.preventDefault();
  };

  const onPaste = (e: ClipboardEvent<HTMLInputElement>) => {
    e.preventDefault();
    const digits = (e.clipboardData.getData('text') || '').replace(/\D/g, '').slice(0, 4);
    if (digits) onChange(digits);
  };

  return (
    <input
      ref={ref}
      className="input"
      type="number"
      inputMode="numeric"
      id={id}
      name={name}
      value={value}
      onChange={(e) => onChange(e.target.value.slice(0, 4))}
      onPointerDown={onPointerDown}
      onKeyDown={onKeyDown}
      onPaste={onPaste}
      placeholder={String(BASE_YEAR)}
      min={1920}
      max={new Date().getFullYear()}
      required
    />
  );
}

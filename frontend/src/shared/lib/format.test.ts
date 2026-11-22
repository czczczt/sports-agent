import { expect, it } from 'vitest';
import { dateRu, initials, plural, sportTitle } from './format';
import { parseId } from './parseId';

it('форматирует пустые и заполненные данные спортсмена', () => {
  expect(dateRu(null)).toBe('—');
  expect(dateRu('2026-11-20')).toBe('20.11.2026');
  expect(initials('Иван Иванов')).toBe('ИИ');
  expect(initials('Иван')).toBe('И');
  expect(plural(12, 'старт', 'старта', 'стартов')).toBe('стартов');
});

it('возвращает названия видов спорта', () => {
  expect(sportTitle('run')).toBe('Бег');
  expect(sportTitle('ski')).toBe('Лыжи и биатлон');
  expect(sportTitle('triathlon')).toBe('Триатлон');
  expect(sportTitle('trail')).toBe('Трейл');
  expect(sportTitle('all')).toBe('Все виды');
  expect(sportTitle(null)).toBe('');
});

it('принимает положительный целый ID из URL', () => {
  expect(parseId('7')).toBe(7);
  for (const value of [null, '', 'abc', '-1', '1.5']) expect(parseId(value)).toBeNull();
});

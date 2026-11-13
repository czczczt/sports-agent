// Тема: «Системная» / «Светлая» / «Тёмная» (ADR-0001). Перенос app/static/js/theme.js.
// Выбор хранится в localStorage('theme'), до отрисовки его применяет инлайн-скрипт в index.html.
// Графики берут цвета из CSS-токенов (themeToken) и перерисовываются при смене effective.
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';

export type ThemeChoice = 'system' | 'light' | 'dark';
export type EffectiveTheme = 'light' | 'dark';

const KEY = 'theme';
const media = typeof window !== 'undefined' && window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null;

function readStored(): ThemeChoice {
  try {
    const t = localStorage.getItem(KEY);
    return t === 'light' || t === 'dark' ? t : 'system';
  } catch {
    return 'system';
  }
}

function resolve(choice: ThemeChoice, systemDark: boolean): EffectiveTheme {
  if (choice === 'light' || choice === 'dark') return choice;
  return systemDark ? 'dark' : 'light';
}

interface ThemeContextValue {
  choice: ThemeChoice;
  effective: EffectiveTheme;
  setChoice: (choice: ThemeChoice) => void;
  toggle: () => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [choice, setChoiceState] = useState<ThemeChoice>(readStored);
  const [systemDark, setSystemDark] = useState<boolean>(() => !!media?.matches);

  useEffect(() => {
    if (!media) return;
    const onChange = () => setSystemDark(media.matches);
    media.addEventListener('change', onChange);
    return () => media.removeEventListener('change', onChange);
  }, []);

  const setChoice = useCallback((next: ThemeChoice) => {
    const root = document.documentElement;
    if (next === 'light' || next === 'dark') root.setAttribute('data-theme', next);
    else root.removeAttribute('data-theme');
    try {
      if (next === 'system') localStorage.removeItem(KEY);
      else localStorage.setItem(KEY, next);
    } catch {
      /* хранилище недоступно — тема действует до перезагрузки */
    }
    setChoiceState(next);
  }, []);

  const effective = resolve(choice, systemDark);
  const toggle = useCallback(() => setChoice(effective === 'dark' ? 'light' : 'dark'), [effective, setChoice]);

  const value = useMemo(() => ({ choice, effective, setChoice, toggle }), [choice, effective, setChoice, toggle]);
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error('useTheme вызван вне ThemeProvider');
  return ctx;
}

/** Значение CSS-токена текущей темы — для Chart.js и прочего canvas. */
export function themeToken(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

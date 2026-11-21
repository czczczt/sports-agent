import { useTheme } from '@/shared/theme';
import { Icon } from '@/shared/ui';

export function ThemeControls(): React.JSX.Element {
  const { effective, setChoice, toggle } = useTheme();
  return (
    <>
      <div className="theme-switch" role="group" aria-label="Тема">
        <button type="button" aria-pressed={effective === 'light'} onClick={() => setChoice('light')}>
          Светлая
        </button>
        <button type="button" aria-pressed={effective === 'dark'} onClick={() => setChoice('dark')}>
          Тёмная
        </button>
      </div>
      <button
        type="button"
        className="theme-toggle"
        data-effective={effective}
        aria-label={
          effective === 'dark' ? 'Тема: тёмная. Включить светлую' : 'Тема: светлая. Включить тёмную'
        }
        aria-pressed={effective === 'dark'}
        onClick={toggle}
      >
        <span className="icon-moon">
          <Icon name="moon" />
        </span>
        <span className="icon-sun">
          <Icon name="sun" />
        </span>
      </button>
    </>
  );
}

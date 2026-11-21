import { Icon } from '@/shared/ui';
import { useState } from 'react';
import { AuthForm, type AuthMode } from './AuthForm';

export function AuthCard(): React.JSX.Element {
  const [mode, setMode] = useState<AuthMode>('login');

  const titles: Record<AuthMode, { title: string; subtitle: string }> = {
    login: {
      title: 'Вход в систему',
      subtitle: 'Внутренний сервис платформы рейтинга спортсменов. Для просмотра данных войдите в систему.',
    },
    register: {
      title: 'Заявка на доступ',
      subtitle:
        'Заполните форму для регистрации. Доступ открывается после одобрения администратором или капитаном.',
    },
    reset: {
      title: 'Сброс пароля',
      subtitle: 'Восстановление доступа к вашей учётной записи.',
    },
  };

  return (
    <div className="auth-card" data-mode={mode}>
      <div className="auth-card__icon" aria-hidden="true">
        <Icon name="logo" />
      </div>
      <h1 className="auth-card__title">{titles[mode].title}</h1>
      <p className="auth-card__subtitle">{titles[mode].subtitle}</p>
      <AuthForm mode={mode} switchMode={setMode} />
    </div>
  );
}

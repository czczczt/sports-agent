import { ApiError } from '@/shared/api';
import { authApi } from '@/shared/session';
import { zodResolver } from '@hookform/resolvers/zod';
import { useMutation } from '@tanstack/react-query';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import layout from './AuthForm.module.css';
import styles from './RegistrationForm.module.css';

import type { AuthFormProps } from './AuthForm';
const registrationSchema = z.object({
  username: z.string().trim().min(3, 'Логин должен содержать не менее 3 символов').max(100),
  email: z.string().trim().email('Укажите корректный email'),
  password: z.string().min(6, 'Пароль должен содержать не менее 6 символов'),
  first_name: z.string().trim().min(1, 'Укажите имя').max(100),
  last_name: z.string().trim().min(1, 'Укажите фамилию').max(100),
  middle_name: z.string().trim(),
  city: z.string().trim(),
  birth_date: z.string(),
  consent: z.boolean().refine(Boolean, 'Необходимо согласие на обработку персональных данных'),
});

const FIELD_PAIRS = [
  [
    { name: 'last_name', label: 'Фамилия *', type: 'text', autoComplete: 'family-name', required: true },
    { name: 'first_name', label: 'Имя *', type: 'text', autoComplete: 'given-name', required: true },
  ],
  [
    {
      name: 'middle_name',
      label: 'Отчество',
      type: 'text',
      autoComplete: 'additional-name',
      required: false,
    },
    { name: 'city', label: 'Город', type: 'text', autoComplete: 'address-level2', required: false },
  ],
  [
    { name: 'birth_date', label: 'Дата рождения', type: 'date', autoComplete: 'bday', required: false },
    { name: 'username', label: 'Логин *', type: 'text', autoComplete: 'username', required: true },
  ],
  [
    { name: 'email', label: 'Email *', type: 'email', autoComplete: 'email', required: true },
    { name: 'password', label: 'Пароль *', type: 'password', autoComplete: 'new-password', required: true },
  ],
] as const;

export function RegistrationForm({ switchMode }: AuthFormProps): React.JSX.Element {
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<z.infer<typeof registrationSchema>>({ resolver: zodResolver(registrationSchema) });
  const registration = useMutation({ mutationFn: authApi.register });
  const [error, setError] = useState<string | null>(null);
  const successMsg =
    registration.data &&
    (registration.data.message || 'Заявка на доступ успешно подана и ожидает подтверждения.');
  const submitting = registration.isPending;

  const handleRegisterSubmit = handleSubmit(
    async (values) => {
      setError(null);
      try {
        await registration.mutateAsync({
          ...values,
          consent_version: 'v1.0',
          middle_name: values.middle_name || null,
          city: values.city || null,
          birth_date: values.birth_date || null,
        });
      } catch (err) {
        if (err instanceof ApiError) {
          setError(err.detail);
        } else if (err instanceof Error) {
          setError(err.message);
        } else {
          setError('Ошибка при отправке заявки');
        }
      }
    },
    (errors) => setError(Object.values(errors)[0]?.message ?? 'Проверьте поля формы'),
  );

  return (
    <form onSubmit={handleRegisterSubmit} className="modal-form">
      {successMsg ? (
        <div className="auth-success" role="status">
          <p className={styles.successTitle}>Заявка принята!</p>
          <p className={styles.message}>{successMsg}</p>
          <div className={styles.successActions}>
            <button type="button" className="btn btn--primary btn--block" onClick={() => switchMode('login')}>
              Вернуться ко входу
            </button>
          </div>
        </div>
      ) : (
        <>
          {FIELD_PAIRS.map((pair) => (
            <div key={pair[0].name} className={styles.fieldPair}>
              {pair.map((field) => (
                <label key={field.name} className="field" htmlFor={'register-' + field.name}>
                  <span>{field.label}</span>
                  <input
                    {...register(field.name)}
                    id={'register-' + field.name}
                    className="input"
                    type={field.type}
                    autoComplete={field.autoComplete}
                    required={field.required}
                    disabled={submitting}
                    aria-invalid={!!errors[field.name]}
                    aria-describedby={errors[field.name] ? 'registration-error' : undefined}
                  />
                </label>
              ))}
            </div>
          ))}
          <label className={layout.authCheckbox}>
            <input type="checkbox" {...register('consent')} disabled={submitting} required />
            <span>Я даю согласие на обработку персональных данных в соответствии с 152-ФЗ *</span>
          </label>

          {error && (
            <div id="registration-error" className="auth-error" role="alert">
              {error}
            </div>
          )}

          <button type="submit" className="btn btn--primary btn--block" disabled={submitting}>
            {submitting ? 'Отправка заявки…' : 'Подать заявку'}
          </button>

          <div className={['auth-links', styles.links].join(' ')}>
            <span>Уже есть аккаунт?</span>
            <button type="button" className="auth-link-btn" onClick={() => switchMode('login')}>
              Войти
            </button>
          </div>
        </>
      )}
    </form>
  );
}

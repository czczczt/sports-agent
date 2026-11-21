import { ResetPasswordView } from '@/features/reset-password';
import { useDocumentTitle } from '@/shared/hooks';

export function ResetPasswordPage(): React.JSX.Element {
  useDocumentTitle('Новый пароль');
  return <ResetPasswordView />;
}

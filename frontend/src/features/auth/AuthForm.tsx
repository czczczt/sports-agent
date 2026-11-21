import { LoginForm } from './LoginForm';
import { PasswordRequestForm } from './PasswordRequestForm';
import { RegistrationForm } from './RegistrationForm';

export type AuthMode = 'login' | 'register' | 'reset';
export interface AuthFormProps {
  switchMode: (mode: AuthMode) => void;
}

export function AuthForm({ mode, switchMode }: AuthFormProps & { mode: AuthMode }): React.JSX.Element {
  if (mode === 'register') return <RegistrationForm switchMode={switchMode} />;
  if (mode === 'reset') return <PasswordRequestForm switchMode={switchMode} />;
  return <LoginForm switchMode={switchMode} />;
}

import type { User } from '@/shared/api';
import { ApiError, readToken } from '@/shared/api';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react';
import { authApi } from './api';

interface AuthContextValue {
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  isAdmin: boolean;
  isAuthModalOpen: boolean;
  openAuthModal: () => void;
  closeAuthModal: () => void;
  login: (username: string, password: string) => Promise<User>;
  logout: () => Promise<void>;
}

const SESSION_KEY = ['session', 'me'] as const;
const AuthContext = createContext<AuthContextValue | null>(null);

interface AuthProviderProps {
  children: ReactNode;
}

export function AuthProvider({ children }: AuthProviderProps): React.JSX.Element {
  const cache = useQueryClient();
  const [hasToken, setHasToken] = useState(() => Boolean(readToken()));
  const [isAuthModalOpen, setIsAuthModalOpen] = useState(false);
  const closeAuthModal = useCallback(() => setIsAuthModalOpen(false), []);
  const session = useQuery({
    queryKey: SESSION_KEY,
    queryFn: ({ signal }) => authApi.me(signal),
    enabled: hasToken,
  });
  const clearSession = useCallback(() => {
    localStorage.removeItem('auth_token');
    setHasToken(false);
    cache.clear();
  }, [cache]);
  useEffect(() => {
    if (session.error instanceof ApiError && session.error.status === 401) clearSession();
  }, [session.error, clearSession]);

  const signIn = useMutation({ mutationFn: authApi.login });
  const signOut = useMutation({ mutationFn: authApi.logout, onSettled: clearSession });
  const login = async (username: string, password: string): Promise<User> => {
    const result = await signIn.mutateAsync({ username, password });
    cache.clear();
    localStorage.setItem('auth_token', result.access_token);
    cache.setQueryData(SESSION_KEY, result.user);
    setHasToken(true);
    closeAuthModal();
    return result.user;
  };
  const user = hasToken ? (session.data ?? null) : null;
  const logout = async () => {
    await signOut.mutateAsync();
  };

  const value: AuthContextValue = {
    user,
    isLoading: hasToken && session.isLoading,
    isAuthenticated: user !== null,
    isAdmin: user?.role === 'admin',
    isAuthModalOpen,
    openAuthModal: () => setIsAuthModalOpen(true),
    closeAuthModal,
    login,
    logout,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return ctx;
}

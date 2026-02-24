import { createContext, useContext, useState, useCallback, useMemo } from 'react';
import { AUTH_KEYS } from '../lib/constants';

const AuthContext = createContext(null);

/**
 * Reads all auth state from localStorage (snapshot, not reactive).
 */
function readAuthState() {
  return {
    token: localStorage.getItem(AUTH_KEYS.TOKEN),
    isAdmin: localStorage.getItem(AUTH_KEYS.IS_ADMIN) === 'true',
    businessName: localStorage.getItem(AUTH_KEYS.BUSINESS) || 'LeadLock',
    clientId: localStorage.getItem(AUTH_KEYS.CLIENT_ID),
  };
}

export function AuthProvider({ children }) {
  const [auth, setAuth] = useState(readAuthState);

  const login = useCallback((data) => {
    localStorage.setItem(AUTH_KEYS.TOKEN, data.token);
    if (data.is_admin) localStorage.setItem(AUTH_KEYS.IS_ADMIN, 'true');
    if (data.business_name) localStorage.setItem(AUTH_KEYS.BUSINESS, data.business_name);
    if (data.client_id) localStorage.setItem(AUTH_KEYS.CLIENT_ID, data.client_id);
    if (data.onboarding_status) localStorage.setItem('ll_onboarding_status', data.onboarding_status);
    if (data.billing_status) localStorage.setItem('ll_billing_status', data.billing_status);
    setAuth(readAuthState());
  }, []);

  const logout = useCallback(() => {
    Object.values(AUTH_KEYS).forEach((key) => localStorage.removeItem(key));
    setAuth({ token: null, isAdmin: false, businessName: 'LeadLock', clientId: null });
    window.location.href = '/login';
  }, []);

  const value = useMemo(() => ({
    ...auth,
    login,
    logout,
    initial: auth.businessName.charAt(0).toUpperCase(),
  }), [auth, login, logout]);

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
}

/**
 * Hook to access auth state and actions.
 * @returns {{ token: string|null, isAdmin: boolean, businessName: string, clientId: string|null, initial: string, login: Function, logout: Function }}
 */
export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}

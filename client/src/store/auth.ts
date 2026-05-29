import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { User } from '@truck-dispatch/shared';
import api from '../lib/api';

interface AuthState {
  user: User | null;
  accessToken: string | null;
  refreshToken: string | null;
  isAuthenticated: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  setTokens: (access: string, refresh: string, user: User) => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      user: null,
      accessToken: null,
      refreshToken: null,
      isAuthenticated: false,

      login: async (email, password) => {
        const { data } = await api.post('/auth/login', { email, password });
        const { accessToken, refreshToken, user } = data.data;
        localStorage.setItem('accessToken', accessToken);
        localStorage.setItem('refreshToken', refreshToken);
        set({ user, accessToken, refreshToken, isAuthenticated: true });
      },

      logout: () => {
        const { refreshToken } = get();
        if (refreshToken) {
          api.post('/auth/logout', { refreshToken }).catch(() => {});
        }
        localStorage.removeItem('accessToken');
        localStorage.removeItem('refreshToken');
        set({ user: null, accessToken: null, refreshToken: null, isAuthenticated: false });
      },

      setTokens: (access, refresh, user) => {
        localStorage.setItem('accessToken', access);
        localStorage.setItem('refreshToken', refresh);
        set({ user, accessToken: access, refreshToken: refresh, isAuthenticated: true });
      },
    }),
    {
      name: 'auth-store',
      partialize: (state) => ({ user: state.user, accessToken: state.accessToken, refreshToken: state.refreshToken, isAuthenticated: state.isAuthenticated }),
    }
  )
);

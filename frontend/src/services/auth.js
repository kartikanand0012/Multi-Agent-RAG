import axios from 'axios';

const BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';
const client = axios.create({ baseURL: BASE, timeout: 30000 });

const TOKEN_KEY   = 'rag_access_token';
const REFRESH_KEY = 'rag_refresh_token';

export const tokenStore = {
  get:        ()    => localStorage.getItem(TOKEN_KEY),
  set:        (t)   => localStorage.setItem(TOKEN_KEY, t),
  getRefresh: ()    => localStorage.getItem(REFRESH_KEY),
  setRefresh: (t)   => localStorage.setItem(REFRESH_KEY, t),
  clear:      ()    => { localStorage.removeItem(TOKEN_KEY); localStorage.removeItem(REFRESH_KEY); },
};

// Attach token to every request
client.interceptors.request.use(cfg => {
  const token = tokenStore.get();
  if (token) cfg.headers.Authorization = `Bearer ${token}`;
  return cfg;
});

// Auto-refresh on 401
client.interceptors.response.use(
  r => r,
  async err => {
    const original = err.config;
    if (err.response?.status === 401 && !original._retry) {
      original._retry = true;
      try {
        const refresh = tokenStore.getRefresh();
        if (!refresh) throw new Error('no refresh token');
        const { data } = await axios.post(`${BASE}/auth/refresh`, null, {
          params: { refresh_token: refresh },
        });
        tokenStore.set(data.access_token);
        original.headers.Authorization = `Bearer ${data.access_token}`;
        return client(original);
      } catch {
        tokenStore.clear();
        window.location.href = '/';
      }
    }
    return Promise.reject(err);
  }
);

export const authApi = {
  register: (email, username, password, full_name = '') =>
    client.post('/auth/register', { email, username, password, full_name }).then(r => r.data),

  login: (email, password) =>
    client.post('/auth/login', { email, password }).then(r => r.data),

  me: () => client.get('/auth/me').then(r => r.data),

  updateProfile: (data) => client.patch('/auth/me', data).then(r => r.data),

  changePassword: (old_password, new_password) =>
    client.post('/auth/me/change-password', { old_password, new_password }),

  rotateApiKey: () => client.post('/auth/me/api-key/rotate').then(r => r.data),
};

export { client as apiClient };

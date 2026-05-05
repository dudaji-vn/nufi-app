import { create } from 'zustand';

type Theme = 'light' | 'dark' | 'system';
type Resolved = 'light' | 'dark';

type Store = {
  theme: Theme;
  resolved: Resolved;
  setTheme: (t: Theme) => void;
};

const STORAGE_KEY = 'console.theme';

function systemPref(): Resolved {
  if (typeof window === 'undefined') return 'light';
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

function apply(resolved: Resolved) {
  if (typeof document === 'undefined') return;
  document.documentElement.classList.toggle('dark', resolved === 'dark');
  document.documentElement.style.colorScheme = resolved;
}

function read(): Theme {
  if (typeof localStorage === 'undefined') return 'system';
  const v = localStorage.getItem(STORAGE_KEY);
  return v === 'light' || v === 'dark' || v === 'system' ? v : 'system';
}

const initial = read();
const initialResolved = initial === 'system' ? systemPref() : initial;
apply(initialResolved);

export const useTheme = create<Store>((set) => ({
  theme: initial,
  resolved: initialResolved,
  setTheme: (theme) => {
    if (typeof localStorage !== 'undefined') localStorage.setItem(STORAGE_KEY, theme);
    const resolved = theme === 'system' ? systemPref() : theme;
    apply(resolved);
    set({ theme, resolved });
  },
}));

// Keep the resolved value in sync if the user is on `system` and toggles OS theme.
if (typeof window !== 'undefined') {
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
    const { theme, setTheme } = useTheme.getState();
    if (theme === 'system') setTheme('system');
  });
}

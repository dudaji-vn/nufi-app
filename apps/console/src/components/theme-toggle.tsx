import { Moon, Sun } from 'lucide-react';
import { Button } from './ui/button';
import { useTheme } from '@/stores/theme';

export function ThemeToggle() {
  const resolved = useTheme((s) => s.resolved);
  const setTheme = useTheme((s) => s.setTheme);

  return (
    <Button
      variant="ghost"
      size="icon"
      onClick={() => setTheme(resolved === 'dark' ? 'light' : 'dark')}
      aria-label={`Switch to ${resolved === 'dark' ? 'light' : 'dark'} mode`}
    >
      <Sun className="size-4 scale-100 rotate-0 transition-all dark:scale-0 dark:-rotate-90" />
      <Moon className="absolute size-4 scale-0 rotate-90 transition-all dark:scale-100 dark:rotate-0" />
    </Button>
  );
}

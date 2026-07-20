import { Monitor, Moon, Sun } from 'lucide-react';
import type * as t from '@/types';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui';
import { useTheme } from '@/contexts/ThemeContext';
import { useLocalize } from '@/hooks';
import { cn } from '@/utils';

const THEME_OPTIONS: { value: t.ThemeOption; labelKey: string; icon: typeof Sun }[] = [
  { value: 'system', labelKey: 'com_nav_theme_system', icon: Monitor },
  { value: 'light', labelKey: 'com_nav_theme_light', icon: Sun },
  { value: 'dark', labelKey: 'com_nav_theme_dark', icon: Moon },
];

export function SettingsDialog({ open, onClose }: t.SettingsDialogProps) {
  const localize = useLocalize();
  const { theme, setTheme } = useTheme();

  return (
    <Dialog
      open={open}
      onOpenChange={(isOpen) => {
        if (!isOpen) onClose();
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{localize('com_ui_settings')}</DialogTitle>
          <DialogDescription>{localize('com_settings_theme_desc')}</DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-6 pt-2">
          <div className="flex items-center justify-between gap-4">
            <div className="flex flex-col gap-0.5">
              <span className="text-sm font-medium text-foreground">
                {localize('com_nav_theme')}
              </span>
            </div>
            <div className="flex gap-1 rounded-md border border-input bg-background p-0.5">
              {THEME_OPTIONS.map(({ value, labelKey, icon: Icon }) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => setTheme(value)}
                  className={cn(
                    'inline-flex cursor-pointer items-center gap-1.5 rounded-sm px-2.5 py-1 text-xs font-medium transition-colors',
                    theme === value
                      ? 'bg-accent text-accent-foreground'
                      : 'text-muted-foreground hover:text-foreground',
                  )}
                  aria-pressed={theme === value}
                >
                  <Icon className="h-3.5 w-3.5" />
                  {localize(labelKey)}
                </button>
              ))}
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

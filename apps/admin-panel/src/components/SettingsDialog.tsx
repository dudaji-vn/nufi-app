import { Monitor, Moon, Sun } from 'lucide-react';
import { useTranslation } from 'react-i18next';
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

const LANGUAGE_OPTIONS: { value: string; label: string }[] = [
  { value: 'en', label: 'English' },
  { value: 'ko', label: '한국어' },
];

export function SettingsDialog({ open, onClose }: t.SettingsDialogProps) {
  const localize = useLocalize();
  const { theme, setTheme } = useTheme();
  const { i18n } = useTranslation();
  const currentLang = i18n.resolvedLanguage ?? i18n.language;

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
          <div className="flex items-center justify-between gap-4">
            <div className="flex flex-col gap-0.5">
              <span className="text-sm font-medium text-foreground">
                {localize('com_config_field_language')}
              </span>
            </div>
            <div className="flex gap-1 rounded-md border border-input bg-background p-0.5">
              {LANGUAGE_OPTIONS.map(({ value, label }) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => i18n.changeLanguage(value)}
                  className={cn(
                    'inline-flex cursor-pointer items-center gap-1.5 rounded-sm px-2.5 py-1 text-xs font-medium transition-colors',
                    currentLang === value
                      ? 'bg-accent text-accent-foreground'
                      : 'text-muted-foreground hover:text-foreground',
                  )}
                  aria-pressed={currentLang === value}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

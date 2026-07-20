import { Eye, EyeOff } from 'lucide-react';
import { forwardRef, useState } from 'react';
import type { InputHTMLAttributes, KeyboardEvent } from 'react';
import { Input, Label } from '@/components/ui';
import { useLocalize } from '@/hooks';
import { cn } from '@/utils';

interface PasswordInputProps
  extends Omit<InputHTMLAttributes<HTMLInputElement>, 'onChange' | 'type'> {
  label?: string;
  value: string;
  onChange: (value: string) => void;
  onKeyDown?: (event: KeyboardEvent<HTMLInputElement>) => void;
  error?: string;
}

export const PasswordInput = forwardRef<HTMLInputElement, PasswordInputProps>(
  ({ label, value, onChange, error, className, id, ...props }, ref) => {
    const localize = useLocalize();
    const [visible, setVisible] = useState(false);
    const inputId = id ?? `password-${label?.replace(/\s+/g, '-').toLowerCase() ?? 'input'}`;

    return (
      <div className="flex w-full flex-col gap-1.5">
        {label && (
          <Label htmlFor={inputId} className="text-sm font-medium text-foreground">
            {label}
          </Label>
        )}
        <div className="relative">
          <Input
            ref={ref}
            id={inputId}
            type={visible ? 'text' : 'password'}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            aria-invalid={error ? true : undefined}
            className={cn('pr-10', error && 'border-destructive focus-visible:ring-destructive', className)}
            {...props}
          />
          <button
            type="button"
            onClick={() => setVisible((v) => !v)}
            aria-label={
              visible ? localize('com_auth_hide_password') : localize('com_auth_show_password')
            }
            className="absolute inset-y-0 right-0 flex items-center px-3 text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:text-foreground"
          >
            {visible ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
          </button>
        </div>
        {error && <span className="text-xs text-destructive">{error}</span>}
      </div>
    );
  },
);
PasswordInput.displayName = 'PasswordInput';

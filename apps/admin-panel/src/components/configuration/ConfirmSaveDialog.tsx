import yaml from 'js-yaml';
import type { ReactNode } from 'react';
import type * as t from '@/types';
import {
  Badge,
  Button,
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui';
import { useLocalize } from '@/hooks';

export function ConfirmSaveDialog({
  open,
  editedValues,
  originalValues,
  saving,
  error,
  onConfirm,
  onCancel,
}: t.ConfirmSaveDialogProps) {
  const localize = useLocalize();
  const entries = Object.entries(editedValues).sort(([a], [b]) => a.localeCompare(b));
  const count = entries.length;
  const countLabel =
    count === 1
      ? localize('com_config_field_change_count', { count })
      : localize('com_config_field_change_count_plural', { count });

  return (
    <Dialog
      open={open}
      onOpenChange={(isOpen) => {
        if (!isOpen) onCancel();
      }}
    >
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{localize('com_config_confirm_save_title')}</DialogTitle>
        </DialogHeader>

        <p className="text-sm text-muted-foreground">{countLabel}</p>

        <div className="flex max-h-80 flex-col gap-3 overflow-y-auto pr-1">
          {entries.map(([path, newValue]) => {
            const oldValue = originalValues?.[path];
            return <ChangeCard key={path} path={path} oldValue={oldValue} newValue={newValue} />;
          })}
        </div>

        {error && <p className="text-sm text-destructive">{error}</p>}

        <DialogFooter>
          <Button type="button" variant="outline" onClick={onCancel} disabled={saving}>
            {localize('com_ui_cancel')}
          </Button>
          <Button type="button" onClick={onConfirm} disabled={saving}>
            {saving ? localize('com_ui_loading') : localize('com_config_save')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function resolvePathLabel(path: string, newValue: t.ConfigValue, oldValue: t.ConfigValue): string {
  const match = /^(.+)\.(\d+)$/.exec(path);
  if (!match) return path;
  const val = (newValue ?? oldValue) as Record<string, t.ConfigValue> | undefined;
  const name = val && typeof val === 'object' && !Array.isArray(val)
    ? (val as Record<string, string>).name
    : undefined;
  return name ? `${match[1]}[${match[2]}] (${name})` : `${match[1]}[${match[2]}]`;
}

function ChangeCard({
  path,
  oldValue,
  newValue,
}: {
  path: string;
  oldValue: t.ConfigValue;
  newValue: t.ConfigValue;
}) {
  const localize = useLocalize();
  const notSet = localize('com_config_field_not_set');
  const isRemoval = newValue === undefined || newValue === null;
  const isAddition = oldValue === undefined || oldValue === null;
  const displayPath = resolvePathLabel(path, newValue, oldValue);

  return (
    <div className="rounded-lg border border-border bg-muted">
      <div className="flex items-center gap-2 border-b border-border px-3 py-2">
        <span className="font-mono text-xs font-medium text-foreground">
          {displayPath}
        </span>
        {isAddition && (
          <Badge className="border-emerald-500/30 bg-emerald-500/15 px-2 py-0 text-[10px] font-semibold text-emerald-400">
            {localize('com_config_field_added')}
          </Badge>
        )}
        {isRemoval && (
          <Badge variant="destructive" className="px-2 py-0 text-[10px] font-semibold">
            {localize('com_config_field_removed')}
          </Badge>
        )}
      </div>

      <div className="flex flex-col gap-0 divide-y divide-border">
        {!isAddition && (
          <div className="flex items-baseline gap-2 px-3 py-2">
            <span className="w-12 shrink-0 text-[10px] font-medium tracking-wide text-muted-foreground uppercase">
              {localize('com_config_field_before')}
            </span>
            <div className="min-w-0 flex-1 overflow-x-auto">
              <ValueDisplay value={oldValue} notSet={notSet} variant="old" />
            </div>
          </div>
        )}
        {!isRemoval && (
          <div className="flex items-baseline gap-2 px-3 py-2">
            <span className="w-12 shrink-0 text-[10px] font-medium tracking-wide text-muted-foreground uppercase">
              {localize('com_config_field_after')}
            </span>
            <div className="min-w-0 flex-1 overflow-x-auto">
              <ValueDisplay value={newValue} notSet={notSet} variant="new" />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function isPrimitive(v: t.ConfigValue): v is string | number | boolean {
  return typeof v === 'string' || typeof v === 'number' || typeof v === 'boolean';
}

function ValueDisplay({
  value,
  notSet,
  variant,
}: {
  value: t.ConfigValue;
  notSet: string;
  variant: 'old' | 'new';
}) {
  const formatted = formatValue(value, notSet);
  const isBlock = typeof formatted === 'string' && formatted.includes('\n');

  if (isBlock) {
    return (
      <code
        className={`block font-mono text-[11px] leading-snug whitespace-pre ${
          variant === 'new' ? 'text-foreground' : 'text-muted-foreground'
        }`}
      >
        {formatted}
      </code>
    );
  }

  return (
    <span
      className={`text-xs ${
        variant === 'new'
          ? 'font-medium text-foreground'
          : 'text-muted-foreground'
      }`}
    >
      {formatted}
    </span>
  );
}

function formatValue(value: t.ConfigValue, notSetLabel: string): ReactNode {
  if (value === undefined || value === null) return notSetLabel;
  if (typeof value === 'boolean') return value ? 'true' : 'false';
  if (typeof value === 'number' || typeof value === 'string') return String(value);

  if (Array.isArray(value)) {
    if (value.length === 0) return '[]';
    if (value.length <= 5 && value.every(isPrimitive)) {
      return value.map(String).join(', ');
    }
    return yaml.dump(value, { lineWidth: -1 }).trimEnd();
  }

  if (typeof value === 'object') {
    if (Object.keys(value).length === 0) return '{}';
    return yaml.dump(value, { lineWidth: -1 }).trimEnd();
  }

  try {
    return yaml.dump(value, { lineWidth: -1 }).trimEnd();
  } catch {
    return String(value);
  }
}

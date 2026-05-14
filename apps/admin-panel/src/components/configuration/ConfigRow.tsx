import { Icon } from '@clickhouse/click-ui';
import type * as t from '@/types';
import { SectionControls } from './SectionControls';
import { SectionHeader } from './SectionHeader';
import { useLocalize } from '@/hooks';
import { cn } from '@/utils';

export function ConfigRow({
  title,
  description,
  learnMoreUrl,
  badge,
  children,
  disabled,
  hidden,
  fieldId,
  fieldPath,
  previewChangedPaths,
  permissions,
  onResetField,
  isConfigured,
  isDbOverride,
  isPendingReset,
  defaultHint,
}: t.ConfigRowProps) {
  const localize = useLocalize();
  if (hidden) return null;

  const isChanged = fieldPath && previewChangedPaths?.includes(fieldPath);
  const showReset =
    !isPendingReset &&
    (isDbOverride || isChanged) &&
    fieldPath &&
    !disabled &&
    permissions?.canEdit &&
    onResetField;

  const resetAction = showReset ? (
    <button
      type="button"
      onClick={() => onResetField(fieldPath)}
      aria-label={
        isChanged
          ? localize('com_a11y_remove_override', { name: title })
          : localize('com_a11y_reset_to_default', { name: title })
      }
      className="inline-flex items-center gap-0.5 text-[11px] text-muted-foreground transition-colors hover:text-foreground"
    >
      <Icon name="refresh" size="sm" />
      <span>{localize('com_ui_reset')}</span>
    </button>
  ) : null;

  const pendingResetHint = isPendingReset ? (
    <span className="text-[11px] font-medium text-destructive">
      {localize('com_config_pending_reset')}
    </span>
  ) : null;

  const configuredDot =
    isConfigured && !isPendingReset ? (
      <span
        className="inline-block h-1.5 w-1.5 shrink-0 rounded-full bg-primary"
        aria-hidden="true"
      />
    ) : null;

  const defaultHintEl =
    defaultHint != null ? (
      <span className="text-[11px] text-muted-foreground">
        {localize('com_config_default_hint', { value: String(defaultHint) })}
      </span>
    ) : null;

  const hasSubContent = description || resetAction || pendingResetHint || badge;

  return (
    <div
      className={cn(
        'config-row flex w-full gap-6 rounded-md px-2.5 py-2',
        hasSubContent ? 'items-start' : 'items-center',
        disabled && 'pointer-events-none opacity-60',
        isPendingReset && 'opacity-60',
      )}
    >
      <SectionHeader
        title={title}
        description={description}
        learnMoreUrl={learnMoreUrl}
        htmlFor={fieldId}
        titleAdornment={configuredDot}
        subtitle={defaultHintEl}
      >
        {resetAction}
        {pendingResetHint}
        {badge}
      </SectionHeader>
      <SectionControls>{children}</SectionControls>
    </div>
  );
}

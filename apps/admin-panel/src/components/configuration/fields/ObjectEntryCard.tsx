import { ChevronRight, Pencil, Plus } from 'lucide-react';
import { useState, useCallback, useRef, useEffect } from 'react';
import type * as t from '@/types';
import { TrashButton } from '@/components/shared';
import { CodeField } from './CodeField';
import { useLocalize } from '@/hooks';
import { cn } from '@/utils';

export function ObjectEntryCard({
  id,
  entryKey,
  fields,
  value,
  onValueChange,
  onRemove,
  onRename,
  disabled,
  defaultExpanded = false,
  renderFields,
  headerExtra,
}: t.ObjectEntryCardProps) {
  const localize = useLocalize();
  const [isExpanded, setIsExpanded] = useState(defaultExpanded);
  const [hasEverExpanded, setHasEverExpanded] = useState(defaultExpanded);
  const [isEditing, setIsEditing] = useState(false);
  const [editKey, setEditKey] = useState(entryKey);
  const [hasAddField, setHasAddField] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const cardRef = useRef<HTMLDivElement>(null);
  const addFieldTriggerRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    if (isExpanded && !hasEverExpanded) setHasEverExpanded(true);
  }, [isExpanded, hasEverExpanded]);


  // Track whether renderFields registered an addFieldTrigger.
  // Runs every render because the ref is populated by children after mount.
  useEffect(() => {
    const has = addFieldTriggerRef.current != null;
    setHasAddField((prev) => (prev === has ? prev : has));
  });

  useEffect(() => {
    if (isEditing && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [isEditing]);

  // Auto-focus first input when a new entry opens expanded
  useEffect(() => {
    if (defaultExpanded && isExpanded && cardRef.current) {
      requestAnimationFrame(() => {
        const firstInput = cardRef.current?.querySelector<HTMLElement>(
          'input:not([type="hidden"]), select, textarea, [role="switch"]',
        );
        firstInput?.focus();
      });
    }
  }, []); // Only on mount

  const toggle = useCallback(() => setIsExpanded((prev) => !prev), []);

  const handleFieldChange = useCallback(
    (fieldPath: string, fieldValue: t.ConfigValue) => {
      const current =
        typeof value === 'object' && value !== null && !Array.isArray(value)
          ? (value as Record<string, t.ConfigValue>)
          : {};
      const segments = fieldPath.split('.');
      const leafKey = segments[segments.length - 1];
      onValueChange({ ...current, [leafKey]: fieldValue });
    },
    [value, onValueChange],
  );

  const commitRename = useCallback(() => {
    setIsEditing(false);
    const trimmed = editKey.trim();
    if (trimmed && trimmed !== entryKey && onRename) {
      onRename(trimmed);
    } else {
      setEditKey(entryKey);
    }
  }, [editKey, entryKey, onRename]);

  const summary = getSummary(value, {
    enabled: localize('com_ui_enabled'),
    disabled: localize('com_ui_disabled'),
  });

  return (
    <div
      ref={cardRef}
      id={id}
      className="overflow-hidden rounded-md border border-border bg-muted/30"
    >
      <div
        data-section-id={id}
        className={cn(
          'group flex w-full cursor-pointer items-center gap-3 px-3 py-2.5 select-none bg-card transition-colors hover:bg-muted focus-visible:outline-1 focus-visible:-outline-offset-1 focus-visible:outline-ring',
          isExpanded && 'sticky top-0 z-5',
        )}
        onClick={isEditing ? undefined : toggle}
        role="button"
        tabIndex={isEditing ? -1 : 0}
        onKeyDown={
          isEditing
            ? undefined
            : (e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  toggle();
                }
              }
        }
        aria-expanded={isExpanded}
      >
        <ChevronRight
          aria-hidden="true"
          className={cn(
            'h-4 w-4 shrink-0 text-muted-foreground transition-transform duration-200',
            isExpanded && 'rotate-90',
          )}
        />
        <span className="flex min-w-0 flex-1 items-center gap-2">
          {isEditing && onRename ? (
            <input
              ref={inputRef}
              type="text"
              value={editKey}
              onChange={(e) => setEditKey(e.target.value)}
              onBlur={commitRename}
              onKeyDown={(e) => {
                if (e.key === 'Enter') commitRename();
                if (e.key === 'Escape') {
                  setEditKey(entryKey);
                  setIsEditing(false);
                }
              }}
              onClick={(e) => e.stopPropagation()}
              className="config-input-ghost w-auto max-w-50 min-w-20 text-sm font-medium"
            />
          ) : (
            <>
              <span
                className="truncate text-sm font-medium text-foreground"
                title={entryKey}
              >
                {entryKey}
              </span>
              {isExpanded && onRename && !disabled && (
                <button
                  type="button"
                  tabIndex={0}
                  onClick={(e) => {
                    e.stopPropagation();
                    setIsEditing(true);
                  }}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      e.stopPropagation();
                      setIsEditing(true);
                    }
                  }}
                  className="inline-flex shrink-0 cursor-pointer items-center rounded border-none bg-transparent p-1 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground focus-visible:outline focus-visible:outline-2 focus-visible:outline-ring"
                  aria-label={localize('com_a11y_rename_entry', { name: entryKey })}
                >
                  <Pencil className="h-3.5 w-3.5" />
                </button>
              )}
            </>
          )}
          {summary && !isExpanded && (
            <span className="truncate text-xs text-muted-foreground">{summary}</span>
          )}
        </span>
        {headerExtra}
        {!disabled && hasAddField && (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              if (!isExpanded) setIsExpanded(true);
              requestAnimationFrame(() => addFieldTriggerRef.current?.());
            }}
            className="config-add-btn"
          >
            <Plus className="h-3.5 w-3.5" />
            <span>{localize('com_config_add_field')}</span>
          </button>
        )}
        {!disabled && onRemove && (
          <span
            className="opacity-0 transition-opacity group-focus-within:opacity-100 group-hover:opacity-100"
            onClick={(e) => e.stopPropagation()}
          >
            <TrashButton
              onClick={onRemove}
              ariaLabel={`${localize('com_ui_delete')} ${entryKey}`}
            />
          </span>
        )}
      </div>
      <div
        className={cn(
          'config-section-grid',
          isExpanded ? 'config-section-grid-open' : 'config-section-grid-closed',
        )}
        inert={!isExpanded ? true : undefined}
      >
        <div className="config-section-inner">
          <div className="flex flex-col gap-4 border-t border-border px-4 py-3">
            {hasEverExpanded && (
              <>
                {isPrimitive(value) && (
                  <PrimitiveEntry
                    value={value}
                    onChange={onValueChange}
                    fields={fields}
                    disabled={disabled}
                  />
                )}
                {!isPrimitive(value) &&
                  fields.length > 0 &&
                  renderFields(fields, value, entryKey, handleFieldChange, addFieldTriggerRef)}
                {!isPrimitive(value) && fields.length === 0 && (
                  <CodeField
                    id={`entry-${entryKey}`}
                    value={value}
                    onChange={onValueChange}
                    disabled={disabled}
                  />
                )}
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function isPrimitive(value: t.ConfigValue): boolean {
  return value === null || value === undefined || typeof value !== 'object';
}

function PrimitiveEntry({
  value,
  onChange,
  fields,
  disabled,
}: {
  value: t.ConfigValue;
  onChange: (v: t.ConfigValue) => void;
  fields: t.SchemaField[];
  disabled?: boolean;
}) {
  const localize = useLocalize();
  return (
    <div className="flex items-center gap-3">
      <span className="text-sm text-muted-foreground">
        {typeof value === 'boolean'
          ? localize(value ? 'com_ui_enabled' : 'com_ui_disabled')
          : String(value ?? '')}
      </span>
      {fields.length > 0 && !disabled && (
        <button
          type="button"
          onClick={() => onChange({})}
          className="text-xs text-primary hover:underline"
        >
          {localize('com_config_customize')}
        </button>
      )}
    </div>
  );
}

function getSummary(
  value: t.ConfigValue,
  labels: { enabled: string; disabled: string },
): string | null {
  if (typeof value === 'boolean') return value ? labels.enabled : labels.disabled;
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  const obj = value as Record<string, t.ConfigValue>;
  const parts: string[] = [];
  if (typeof obj.type === 'string') parts.push(obj.type);
  if (typeof obj.url === 'string') parts.push(obj.url);
  if (typeof obj.command === 'string') parts.push(obj.command);
  if (typeof obj.baseURL === 'string') parts.push(obj.baseURL);
  if (typeof obj.name === 'string' && parts.length === 0) parts.push(obj.name);
  return parts.length > 0 ? parts.join(' · ') : null;
}

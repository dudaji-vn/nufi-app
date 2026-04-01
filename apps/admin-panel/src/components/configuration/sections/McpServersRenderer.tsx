/**
 * Custom section renderer for `mcpServers` — the MCP Servers tab.
 *
 * Renders MCP server entries as expandable cards with:
 *  - Transport-type-aware field visibility (stdio vs sse vs streamable-http vs websocket)
 *  - Semantic field groups (Connection, Authentication, Server Options, Advanced)
 *  - A "Create MCP Server" dialog for adding new entries
 *  - TOC-compatible scroll targets via entry card IDs
 */

import { Icon } from '@clickhouse/click-ui';
import { useState, useCallback } from 'react';
import type { ReactNode } from 'react';
import type * as t from '@/types';
import { useCollapsibleSection } from '../useCollapsibleSection';
import { ObjectEntryCard } from '../fields/ObjectEntryCard';
import { renderCollapsible } from '../renderCollapsible';
import { renderInlineField } from '../FieldRenderer';
import { SelectField } from '../fields/SelectField';
import { FormDialog } from '@/components/shared';
import { useLocalize } from '@/hooks';
import { cn } from '@/utils';

// ---------------------------------------------------------------------------
// Transport type → field visibility
// ---------------------------------------------------------------------------

/** Fields specific to each transport type. */
const TRANSPORT_FIELDS: Record<string, string[]> = {
  stdio: ['command', 'args', 'env', 'stderr'],
  sse: ['url', 'headers'],
  'streamable-http': ['url', 'headers'],
  http: ['url', 'headers'],
  websocket: ['url'],
};

/** All transport-specific field keys (union of all TRANSPORT_FIELDS values). */
const ALL_TRANSPORT_KEYS = new Set(Object.values(TRANSPORT_FIELDS).flat());

/** Auth-related fields only shown for remote transports (not stdio). */
const REMOTE_ONLY_FIELDS = new Set(['requiresOAuth', 'apiKey', 'oauth', 'oauth_headers']);

const REMOTE_TRANSPORTS = new Set(['sse', 'streamable-http', 'http', 'websocket']);

/** Fields that require a value depending on transport type. */
const REQUIRED_BY_TRANSPORT: Record<string, Set<string>> = {
  stdio: new Set(['command', 'args']),
  sse: new Set(['url']),
  'streamable-http': new Set(['url']),
  http: new Set(['url']),
  websocket: new Set(['url']),
};

/** Curated transport type options with lowercase labels, excluding `http` alias. */
const TRANSPORT_TYPE_OPTIONS: { label: string; value: string }[] = [
  { label: 'streamable-http', value: 'streamable-http' },
  { label: 'sse', value: 'sse' },
  { label: 'stdio', value: 'stdio' },
  { label: 'websocket', value: 'websocket' },
];

/** The `type` field is always required. */
const ALWAYS_REQUIRED = new Set(['type']);

/**
 * Infer transport type from configured fields, mirroring Zod's union resolution
 * order in MCPOptionsSchema: Stdio → WebSocket → SSE → StreamableHTTP.
 *
 * YAML configs can omit `type` because each transport schema (except
 * streamable-http) provides a default. The backend infers the type from the
 * discriminating fields (command, url protocol). We replicate that here so the
 * UI shows the effective type for existing configs.
 */
function inferTransportType(values: Record<string, t.ConfigValue>): string {
  if (typeof values.type === 'string' && values.type) return values.type;
  if (typeof values.command === 'string' && values.command) return 'stdio';
  if (typeof values.url === 'string' && values.url) {
    try {
      const protocol = new URL(values.url).protocol;
      if (protocol === 'ws:' || protocol === 'wss:') return 'websocket';
    } catch {
      // invalid URL — fall through to sse as default for any url presence
    }
    return 'sse';
  }
  return '';
}

function withFieldOverrides(field: t.SchemaField, transportType: string): t.SchemaField {
  if (ALWAYS_REQUIRED.has(field.key)) {
    return { ...field, isOptional: false };
  }
  const transportRequired = REQUIRED_BY_TRANSPORT[transportType];
  if (transportRequired?.has(field.key)) {
    return { ...field, isOptional: false };
  }
  return field;
}

// ---------------------------------------------------------------------------
// Semantic field groups
// ---------------------------------------------------------------------------

interface FieldGroupDef {
  labelKey: string;
  fields: string[];
  defaultExpanded: boolean;
  /** Nested sub-groups rendered inside this group (fields should be empty when using children). */
  children?: FieldGroupDef[];
}

const MCP_FIELD_GROUPS: FieldGroupDef[] = [
  {
    labelKey: 'com_config_group_connection',
    fields: ['type', 'url', 'command', 'args', 'headers', 'env', 'stderr', 'requiresOAuth'],
    defaultExpanded: true,
  },
  {
    labelKey: 'com_config_group_authentication',
    fields: [],
    defaultExpanded: false,
    children: [
      {
        labelKey: 'com_config_group_api_key',
        fields: ['apiKey'],
        defaultExpanded: true,
      },
      {
        labelKey: 'com_config_group_oauth',
        fields: ['oauth', 'oauth_headers'],
        defaultExpanded: false,
      },
    ],
  },
  {
    labelKey: 'com_config_group_server_options',
    fields: [
      'title',
      'description',
      'startup',
      'chatMenu',
      'serverInstructions',
      'timeout',
      'sseReadTimeout',
      'initTimeout',
      'iconPath',
    ],
    defaultExpanded: false,
  },
];

// ---------------------------------------------------------------------------
// FieldGroup — collapsible group within a card (replicates EndpointsRenderer)
// ---------------------------------------------------------------------------

function flattenGroupFields(
  fields: t.SchemaField[],
  parentValue: t.ConfigValue,
  parentPath: string,
  onChange: (path: string, value: t.ConfigValue) => void,
  localize: (key: string, interpolation?: Record<string, string | number>) => string,
  transportType: string,
  disabled?: boolean,
  collectionRenderOverrides?: Record<string, t.CollectionRenderFields>,
): ReactNode[] {
  const values =
    typeof parentValue === 'object' && parentValue !== null && !Array.isArray(parentValue)
      ? (parentValue as Record<string, t.ConfigValue>)
      : {};

  const nodes: ReactNode[] = [];
  for (const field of fields) {
    // Custom render for transport type select — curated options with lowercase labels.
    // When `type` is omitted (common in YAML configs), infer it from other fields
    // to mirror backend Zod union resolution.
    if (field.key === 'type') {
      const fieldId = `${parentPath}-${field.key}`;
      const label = localize(`com_config_field_${field.key}`);
      const explicitValue = typeof values.type === 'string' ? values.type : '';
      const rawValue = explicitValue || inferTransportType(values);
      const displayValue = rawValue === 'http' ? 'streamable-http' : rawValue;
      nodes.push(
        <div key={field.key} className="flex flex-col gap-1 sm:flex-row sm:items-center sm:gap-4">
          <label
            htmlFor={fieldId}
            className="shrink-0 text-sm font-medium text-(--cui-color-text-default) sm:w-35"
          >
            {label}
            <span className="ml-0.5 text-(--cui-color-text-danger)">*</span>
          </label>
          <div className="flex-1">
            <SelectField
              id={fieldId}
              value={displayValue}
              options={TRANSPORT_TYPE_OPTIONS}
              onChange={(v) => onChange(field.key, v)}
              disabled={disabled}
              aria-label={label}
            />
          </div>
        </div>,
      );
      continue;
    }

    if (field.children && field.children.length > 0 && !field.isArray && field.type !== 'record') {
      const nested = values[field.key];
      const nestedObj =
        typeof nested === 'object' && nested !== null && !Array.isArray(nested)
          ? (nested as Record<string, t.ConfigValue>)
          : {};
      for (const child of field.children) {
        nodes.push(
          renderInlineField(
            withFieldOverrides(child, transportType),
            nested,
            `${parentPath}.${field.key}`,
            (childKey, childValue) => {
              onChange(field.key, { ...nestedObj, [childKey]: childValue });
            },
            localize,
            disabled,
            collectionRenderOverrides,
            true,
          ),
        );
      }
    } else {
      nodes.push(
        renderInlineField(
          withFieldOverrides(field, transportType),
          parentValue,
          parentPath,
          onChange,
          localize,
          disabled,
          collectionRenderOverrides,
          true,
        ),
      );
    }
  }
  return nodes;
}

/** Parent-level collapsible section that wraps child sub-groups. */
function FieldGroupSection({
  labelKey,
  defaultExpanded,
  children,
}: {
  labelKey: string;
  defaultExpanded: boolean;
  children: ReactNode;
}) {
  const localize = useLocalize();
  const { isExpanded, hasEverExpanded, sectionRef, toggle } = useCollapsibleSection({
    defaultExpanded,
  });

  return (
    <section ref={sectionRef} className="flex flex-col">
      <div className="flex items-center gap-2 border-b border-(--cui-color-stroke-default) pb-2">
        <button
          type="button"
          aria-expanded={isExpanded}
          onClick={toggle}
          className="flex cursor-pointer items-center gap-2 border-none bg-transparent px-0 select-none"
        >
          <span
            className={cn(
              'flex shrink-0 items-center justify-center transition-transform duration-200',
              isExpanded && 'rotate-90',
            )}
          >
            <Icon name="chevron-right" size="xs" />
          </span>
          <span className="text-xs font-medium text-(--cui-color-text-muted)">
            {localize(labelKey)}
          </span>
        </button>
      </div>
      {renderCollapsible(
        isExpanded,
        hasEverExpanded,
        <div className="flex flex-col gap-4 pt-2 pl-3">{children}</div>,
      )}
    </section>
  );
}

function FieldGroup({
  labelKey,
  fields,
  parentValue,
  parentPath,
  onChange,
  disabled,
  defaultExpanded,
  transportType,
}: {
  labelKey: string;
  fields: t.SchemaField[];
  parentValue: t.ConfigValue;
  parentPath: string;
  onChange: (path: string, value: t.ConfigValue) => void;
  disabled?: boolean;
  defaultExpanded: boolean;
  transportType: string;
}) {
  const localize = useLocalize();
  const { isExpanded, hasEverExpanded, sectionRef, toggle } = useCollapsibleSection({
    defaultExpanded,
  });

  if (fields.length === 0) return null;

  return (
    <section ref={sectionRef} className="flex flex-col">
      <div className="flex items-center gap-2 border-b border-(--cui-color-stroke-default) pb-2">
        <button
          type="button"
          aria-expanded={isExpanded}
          onClick={toggle}
          className="flex cursor-pointer items-center gap-2 border-none bg-transparent px-0 select-none"
        >
          <span
            className={cn(
              'flex shrink-0 items-center justify-center transition-transform duration-200',
              isExpanded && 'rotate-90',
            )}
          >
            <Icon name="chevron-right" size="xs" />
          </span>
          <span className="text-xs font-medium text-(--cui-color-text-muted)">
            {localize(labelKey)}
          </span>
        </button>
      </div>
      {renderCollapsible(
        isExpanded,
        hasEverExpanded,
        <div className="flex flex-col gap-3 pt-1">
          {flattenGroupFields(
            fields,
            parentValue,
            parentPath,
            onChange,
            localize,
            transportType,
            disabled,
          )}
        </div>,
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// McpEntryFields — dynamic visibility based on transport type
// ---------------------------------------------------------------------------

function McpEntryFields({
  fields,
  parentValue,
  parentPath,
  onChange,
  disabled,
}: {
  fields: t.SchemaField[];
  parentValue: t.ConfigValue;
  parentPath: string;
  onChange: (path: string, value: t.ConfigValue) => void;
  disabled?: boolean;
}) {
  const localize = useLocalize();
  const values =
    typeof parentValue === 'object' && parentValue !== null && !Array.isArray(parentValue)
      ? (parentValue as Record<string, t.ConfigValue>)
      : {};
  const explicitType = typeof values.type === 'string' ? values.type : '';
  const currentType = explicitType || inferTransportType(values);

  // Build visible field keys based on current transport type
  const currentTransportFields = new Set(TRANSPORT_FIELDS[currentType] ?? []);
  const isRemote = REMOTE_TRANSPORTS.has(currentType);
  const visibleKeys = new Set<string>();
  for (const field of fields) {
    // Transport-specific fields: only show if they belong to the current transport
    if (ALL_TRANSPORT_KEYS.has(field.key)) {
      if (currentTransportFields.has(field.key)) {
        visibleKeys.add(field.key);
      }
      // Auth fields: only show for remote transports
    } else if (REMOTE_ONLY_FIELDS.has(field.key)) {
      if (isRemote) {
        visibleKeys.add(field.key);
      }
    } else {
      visibleKeys.add(field.key);
    }
  }

  // When type changes, we only update the type field itself. Transport-specific
  // fields from the old type are already hidden by the visibility logic above,
  // so stale values are invisible. We intentionally avoid clearing them here
  // because ObjectEntryCard.handleFieldChange captures a stale `value` snapshot
  // per call — multiple synchronous onChange calls would lose all but the last.
  const handleChange = (key: string, value: t.ConfigValue) => {
    onChange(key, value);
  };

  // Filter fields through visibility, then organize into groups
  const fieldsByKey = new Map(fields.map((f) => [f.key, f]));
  const collectGroupKeys = (groups: FieldGroupDef[]): string[] =>
    groups.flatMap((g) => [...g.fields, ...(g.children ? collectGroupKeys(g.children) : [])]);
  const allGroupedKeys = new Set(collectGroupKeys(MCP_FIELD_GROUPS));
  const ungrouped = fields.filter((f) => !allGroupedKeys.has(f.key) && visibleKeys.has(f.key));

  const resolveFields = (keys: string[]) =>
    keys
      .map((key) => fieldsByKey.get(key))
      .filter((f): f is t.SchemaField => f != null && visibleKeys.has(f.key));

  const renderGroup = (group: FieldGroupDef) => {
    const hasChildren = group.children && group.children.length > 0;
    const groupFields = resolveFields(group.fields);

    // For parent groups with children, check if any child sub-group has visible fields
    if (hasChildren) {
      const childGroups = group.children!.filter((child) => resolveFields(child.fields).length > 0);
      if (childGroups.length === 0 && groupFields.length === 0) return null;
      return (
        <FieldGroupSection
          key={group.labelKey}
          labelKey={group.labelKey}
          defaultExpanded={group.defaultExpanded}
        >
          {groupFields.length > 0 && (
            <div className="flex flex-col gap-3">
              {flattenGroupFields(
                groupFields,
                parentValue,
                parentPath,
                handleChange,
                localize,
                currentType,
                disabled,
              )}
            </div>
          )}
          {childGroups.map((child) => (
            <FieldGroup
              key={child.labelKey}
              labelKey={child.labelKey}
              fields={resolveFields(child.fields)}
              parentValue={parentValue}
              parentPath={parentPath}
              onChange={handleChange}
              disabled={disabled}
              defaultExpanded={child.defaultExpanded}
              transportType={currentType}
            />
          ))}
        </FieldGroupSection>
      );
    }

    return (
      <FieldGroup
        key={group.labelKey}
        labelKey={group.labelKey}
        fields={groupFields}
        parentValue={parentValue}
        parentPath={parentPath}
        onChange={handleChange}
        disabled={disabled}
        defaultExpanded={group.defaultExpanded}
        transportType={currentType}
      />
    );
  };

  return (
    <div className="flex flex-col gap-4">
      {MCP_FIELD_GROUPS.map(renderGroup)}
      {ungrouped.length > 0 && (
        <FieldGroup
          labelKey="com_config_group_advanced"
          fields={ungrouped}
          parentValue={parentValue}
          parentPath={parentPath}
          onChange={handleChange}
          disabled={disabled}
          defaultExpanded={false}
          transportType={currentType}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// CreateMcpServerDialog
// ---------------------------------------------------------------------------

function CreateMcpServerDialog({
  open,
  onClose,
  onSave,
  fields,
  existingKeys,
  renderFields,
}: {
  open: boolean;
  onClose: () => void;
  onSave: (serverName: string, entry: Record<string, t.ConfigValue>) => void;
  fields: t.SchemaField[];
  existingKeys: Set<string>;
  renderFields: t.CollectionRenderFields;
}) {
  const localize = useLocalize();
  const [serverName, setServerName] = useState('');
  const [draft, setDraft] = useState<Record<string, t.ConfigValue>>({});
  const [error, setError] = useState<string | undefined>();

  const handleFieldChange = useCallback((key: string, value: t.ConfigValue) => {
    setDraft((prev) => ({ ...prev, [key]: value }));
    setError(undefined);
  }, []);

  const handleSubmit = useCallback(() => {
    const name = serverName.trim();
    if (!name) {
      setError(localize('com_config_server_name_required'));
      return;
    }
    if (existingKeys.has(name)) {
      setError(localize('com_config_server_name_exists'));
      return;
    }
    const entry: Record<string, t.ConfigValue> = {};
    for (const [key, val] of Object.entries(draft)) {
      if (val === '' || val === undefined || val === null) continue;
      if (Array.isArray(val) && val.length === 0) continue;
      entry[key] = val;
    }
    onSave(name, entry);
    setServerName('');
    setDraft({});
    setError(undefined);
    onClose();
  }, [serverName, draft, existingKeys, localize, onSave, onClose]);

  const handleClose = useCallback(() => {
    setServerName('');
    setDraft({});
    setError(undefined);
    onClose();
  }, [onClose]);

  return (
    <FormDialog
      open={open}
      title={localize('com_config_create_mcp_server')}
      submitLabel={localize('com_ui_create')}
      submitDisabled={!serverName.trim() || !(draft.type || inferTransportType(draft))}
      saving={false}
      error={error}
      size="lg"
      onSubmit={handleSubmit}
      onClose={handleClose}
    >
      <div className="flex flex-col gap-4">
        <div className="flex flex-col gap-1.5">
          <label
            htmlFor="mcp-server-name"
            className="text-sm font-medium text-(--cui-color-text-default)"
          >
            {localize('com_config_server_name')} <span className="text-red-500">*</span>
          </label>
          <input
            id="mcp-server-name"
            type="text"
            value={serverName}
            onChange={(e) => {
              setServerName(e.target.value);
              setError(undefined);
            }}
            placeholder={localize('com_config_server_name')}
            className="config-input px-2.5 py-1.5 text-sm"
            autoFocus
          />
        </div>
        {renderFields(fields, draft, 'create-mcp-server', handleFieldChange)}
      </div>
    </FormDialog>
  );
}

// ---------------------------------------------------------------------------
// McpServersRenderer — main export
// ---------------------------------------------------------------------------

export function McpServersRenderer(props: t.FieldRendererProps) {
  const { fields, parentPath, parentValue, getValue, onChange, disabled } = props;
  const localize = useLocalize();
  const [createOpen, setCreateOpen] = useState(false);
  const [justAddedKey, setJustAddedKey] = useState<string | null>(null);

  const renderGroupedMcpFields: t.CollectionRenderFields = useCallback(
    (entryFields, entryValue, entryPath, entryOnChange) => (
      <McpEntryFields
        fields={entryFields}
        parentValue={entryValue}
        parentPath={entryPath}
        onChange={entryOnChange}
        disabled={disabled}
      />
    ),
    [disabled],
  );

  const path = parentPath;
  const value = getValue(path, parentValue ?? {});
  const record =
    value && typeof value === 'object' && !Array.isArray(value)
      ? (value as Record<string, t.ConfigValue>)
      : {};
  const entries = Object.entries(record);
  const existingKeys = new Set(Object.keys(record));

  const handleCreate = useCallback(
    (serverName: string, entry: Record<string, t.ConfigValue>) => {
      const next: Record<string, t.ConfigValue> = { [serverName]: entry };
      for (const [k, v] of entries) {
        next[k] = v;
      }
      onChange(path, next);
      setJustAddedKey(serverName);
    },
    [entries, onChange, path],
  );

  const handleRemove = useCallback(
    (key: string) => {
      const next = { ...record };
      delete next[key];
      onChange(path, next);
    },
    [record, onChange, path],
  );

  const handleRename = useCallback(
    (oldKey: string, newKey: string) => {
      if (newKey === oldKey || newKey in record) return;
      const next: Record<string, t.ConfigValue> = {};
      for (const [k, v] of Object.entries(record)) {
        next[k === oldKey ? newKey : k] = v;
      }
      onChange(path, next);
    },
    [record, onChange, path],
  );

  const handleEntryChange = useCallback(
    (key: string, newValue: t.ConfigValue) => {
      onChange(path, { ...record, [key]: newValue });
    },
    [record, onChange, path],
  );

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-3 py-2">
        <button
          type="button"
          onClick={() => setCreateOpen(true)}
          disabled={disabled}
          className="config-add-btn"
        >
          <Icon name="plus" size="sm" />
          <span>{localize('com_config_create_mcp_server')}</span>
        </button>
      </div>
      {entries.map(([key, entryValue]) => {
        // Normalize type for card summary display: resolve http alias and infer
        // omitted type so the collapsed card shows the effective transport.
        const entryObj =
          entryValue && typeof entryValue === 'object' && !Array.isArray(entryValue)
            ? (entryValue as Record<string, t.ConfigValue>)
            : {};
        const rawType = typeof entryObj.type === 'string' ? entryObj.type : '';
        const effectiveType =
          (rawType || inferTransportType(entryObj)) === 'http'
            ? 'streamable-http'
            : rawType || inferTransportType(entryObj);
        const displayValue =
          effectiveType !== rawType ? { ...entryObj, type: effectiveType } : entryValue;

        return (
          <ObjectEntryCard
            key={key}
            id={`section-mcpServers-${encodeURIComponent(key)}`}
            entryKey={key}
            fields={fields}
            value={displayValue}
            onValueChange={(v) => handleEntryChange(key, v)}
            onRemove={disabled ? undefined : () => handleRemove(key)}
            onRename={disabled ? undefined : (renamed) => handleRename(key, renamed)}
            disabled={disabled}
            defaultExpanded={key === justAddedKey}
            renderFields={renderGroupedMcpFields}
          />
        );
      })}
      {entries.length === 0 && (
        <p className="py-2 text-sm text-(--cui-color-text-muted)">
          {localize('com_config_no_entries')}
        </p>
      )}
      <CreateMcpServerDialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onSave={handleCreate}
        fields={fields}
        existingKeys={existingKeys}
        renderFields={renderGroupedMcpFields}
      />
    </div>
  );
}

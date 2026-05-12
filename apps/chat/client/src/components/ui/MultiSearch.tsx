import { Search, X } from 'lucide-react';
import React, { useState, useMemo, useCallback } from 'react';
import { useLocalize } from '~/hooks';
import { cn } from '~/utils';

// This is a generic that can be added to Menu and Select components

export default function MultiSearch({
  value,
  onChange,
  placeholder,
  className = '',
}: {
  value: string | null;
  onChange: (filter: string) => void;
  placeholder?: string;
  className?: string;
}) {
  const localize = useLocalize();
  const onChangeHandler: React.ChangeEventHandler<HTMLInputElement> = useCallback(
    (e) => onChange(e.target.value),
    [onChange],
  );

  return (
    <div
      className={cn(
        'group sticky left-0 top-0 z-10 mb-1 flex h-10 items-center gap-2 border-b border-border bg-popover px-3 text-text-primary',
        className,
      )}
    >
      <Search className="h-4 w-4 text-text-secondary transition-colors duration-200 group-focus-within:text-text-primary" />
      <input
        type="text"
        value={value ?? ''}
        onChange={onChangeHandler}
        placeholder={placeholder ?? localize('com_ui_select_search_model')}
        className="flex-1 border-none bg-transparent px-1 py-2 text-sm text-text-primary placeholder:text-text-secondary focus:outline-none focus:ring-0"
      />
      <div className="relative flex h-5 w-5 items-center justify-end">
        <X
          className={cn(
            'h-4 w-4 text-text-secondary hover:text-text-primary',
            value?.length ?? 0 ? 'cursor-pointer opacity-100' : 'opacity-0',
          )}
          onClick={() => onChange('')}
        />
      </div>
    </div>
  );
}

/**
 * Helper function that will take a multiSearch input
 * @param node
 */
function defaultGetStringKey(node: unknown): string {
  if (typeof node === 'string') {
    // BUGFIX: Detect psedeo separators and make sure they don't appear in the list when filtering items
    // it makes sure (for the most part) that the model name starts and ends with dashes
    // The long-term fix here would be to enable seperators (model groupings) but there's no
    // feature mocks for such a thing yet
    if (node.startsWith('---') && node.endsWith('---')) {
      return '';
    }

    return node.toUpperCase();
  }
  // This should be a noop, but it's here for redundancy
  return '';
}

/**
 * Hook for conditionally making a multi-element list component into a sortable component
 * Returns a RenderNode for search input when search functionality is available
 * @param availableOptions
 * @param placeholder
 * @param getTextKeyOverride
 * @param className - Additional classnames to add to the search container
 * @param disabled - If the search should be disabled
 * @returns
 */
export function useMultiSearch<OptionsType extends unknown[]>({
  availableOptions,
  placeholder,
  getTextKeyOverride,
  className,
  disabled = false,
}: {
  availableOptions: OptionsType;
  placeholder?: string;
  getTextKeyOverride?: (node: OptionsType[0]) => string;
  className?: string;
  disabled?: boolean;
}): [OptionsType, React.ReactNode] {
  const [filterValue, setFilterValue] = useState<string | null>(null);

  // We conditionally show the search when there's more than 10 elements in the menu
  const shouldShowSearch = availableOptions.length > 10 && !disabled;

  // Define the helper function used to enable search
  // If this is invalidly described, we will assume developer error - tf. avoid rendering
  const getTextKeyHelper = getTextKeyOverride || defaultGetStringKey;

  // Iterate said options
  const filteredOptions = useMemo(() => {
    const currentFilter = filterValue ?? '';
    if (!shouldShowSearch || !currentFilter || !availableOptions.length) {
      // Don't render if available options aren't present, there's no filter active
      return availableOptions;
    }
    // Filter through the values, using a simple text-based search
    // nothing too fancy, but we can add a better search algo later if we need
    const upperFilterValue = currentFilter.toUpperCase();

    return availableOptions.filter((value) =>
      getTextKeyHelper(value).includes(upperFilterValue),
    ) as OptionsType;
  }, [availableOptions, getTextKeyHelper, filterValue, shouldShowSearch]);

  const onSearchChange = useCallback(
    (nextFilterValue: string) => setFilterValue(nextFilterValue),
    [],
  );

  const searchRender = shouldShowSearch ? (
    <MultiSearch
      value={filterValue}
      className={className}
      onChange={onSearchChange}
      placeholder={placeholder}
    />
  ) : null;

  return [filteredOptions, searchRender];
}

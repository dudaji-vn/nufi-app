import { createPortal } from 'react-dom';
import { Search } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { useState, useRef, useEffect, useLayoutEffect } from 'react';
import type { AdminUserSearchResult } from '@librechat/data-schemas';
import type * as t from '@/types';
import { searchUsersFn } from '@/server';
import { useLocalize } from '@/hooks';
import { Avatar } from './Avatar';
import { cn } from '@/utils';

export function UserSearchInline({
  existingIds,
  onAdd,
  listboxId = 'user-search-results',
  disabled,
}: t.UserSearchInlineProps) {
  const localize = useLocalize();
  const [query, setQuery] = useState('');
  const [debouncedQuery, setDebouncedQuery] = useState('');
  const [showResults, setShowResults] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(undefined);
  const blurRef = useRef<ReturnType<typeof setTimeout>>(undefined);
  const [dropdownRect, setDropdownRect] = useState<{
    top: number;
    left: number;
    width: number;
  } | null>(null);

  useEffect(() => {
    return () => {
      clearTimeout(debounceRef.current);
      clearTimeout(blurRef.current);
    };
  }, []);

  const searchQuery = useQuery({
    queryKey: ['userSearch', debouncedQuery],
    queryFn: () => searchUsersFn({ data: { query: debouncedQuery } }),
    enabled: debouncedQuery.trim().length > 0,
    select: (data) => data.users.filter((u) => !existingIds.includes(u.id)),
  });

  const results = searchQuery.data ?? [];

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    setQuery(value);
    setActiveIndex(-1);

    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (!value.trim()) {
      setDebouncedQuery('');
      setShowResults(false);
      return;
    }

    debounceRef.current = setTimeout(() => {
      setDebouncedQuery(value);
      setShowResults(true);
    }, 200);
  };

  const handleSelect = (user: AdminUserSearchResult) => {
    onAdd(user);
    setQuery('');
    setDebouncedQuery('');
    setShowResults(false);
    inputRef.current?.focus();
  };

  const scrollToIndex = (index: number) => {
    (listRef.current?.children[index] as HTMLElement | undefined)?.scrollIntoView({
      block: 'nearest',
    });
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (!showResults || results.length === 0) return;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      const next = activeIndex < results.length - 1 ? activeIndex + 1 : 0;
      setActiveIndex(next);
      scrollToIndex(next);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      const next = activeIndex > 0 ? activeIndex - 1 : results.length - 1;
      setActiveIndex(next);
      scrollToIndex(next);
    } else if (e.key === 'Enter' && activeIndex >= 0) {
      e.preventDefault();
      handleSelect(results[activeIndex]);
    } else if (e.key === 'Escape') {
      setShowResults(false);
    }
  };

  const hasResults = showResults && debouncedQuery.trim().length > 0;

  const renderDropdownContent = (rect: { top: number; left: number; width: number }) => {
    const positionStyle = {
      position: 'fixed' as const,
      top: rect.top,
      left: rect.left,
      width: rect.width,
      pointerEvents: 'auto' as const,
    };
    if (results.length > 0) {
      return (
        <ul
          ref={listRef}
          id={listboxId}
          role="listbox"
          style={positionStyle}
          className="max-h-48 overflow-auto rounded-md border border-border bg-popover shadow-lg"
        >
          {results.map((user, i) => (
            <li
              key={user.id}
              role="option"
              aria-selected={i === activeIndex}
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => handleSelect(user)}
              className={cn(
                'flex cursor-pointer items-center gap-3 px-3 py-2 text-sm transition-colors',
                i === activeIndex
                  ? 'bg-accent text-accent-foreground'
                  : 'text-popover-foreground hover:bg-accent/60 hover:text-accent-foreground',
              )}
            >
              <Avatar name={user.name} size="sm" />
              <div className="flex flex-col">
                <span className="font-medium">{user.name}</span>
                <span className="text-xs text-muted-foreground">{user.email}</span>
              </div>
            </li>
          ))}
        </ul>
      );
    }
    if (!searchQuery.isLoading) {
      return (
        <div
          style={positionStyle}
          className="rounded-md border border-border bg-popover px-3 py-3 text-center text-sm text-muted-foreground shadow-lg"
        >
          {localize('com_access_no_users_found')}
        </div>
      );
    }
    return null;
  };

  useLayoutEffect(() => {
    if (!hasResults || !inputRef.current) {
      setDropdownRect(null);
      return;
    }

    const updatePosition = () => {
      if (!inputRef.current) return;
      const rect = inputRef.current.getBoundingClientRect();
      const top = rect.bottom + 4;
      setDropdownRect((prev) => {
        if (prev && prev.top === top && prev.left === rect.left && prev.width === rect.width) {
          return prev;
        }
        return { top, left: rect.left, width: rect.width };
      });
    };

    updatePosition();

    window.addEventListener('scroll', updatePosition, true);
    window.addEventListener('resize', updatePosition);

    return () => {
      window.removeEventListener('scroll', updatePosition, true);
      window.removeEventListener('resize', updatePosition);
    };
  }, [hasResults]);

  return (
    <div className="relative">
      <Search
        aria-hidden="true"
        className="pointer-events-none absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 text-muted-foreground"
      />
      <input
        ref={inputRef}
        type="text"
        value={query}
        onChange={handleInputChange}
        onKeyDown={handleKeyDown}
        onBlur={() => {
          blurRef.current = setTimeout(() => setShowResults(false), 150);
        }}
        onFocus={() => {
          if (results.length > 0 && debouncedQuery.trim()) setShowResults(true);
        }}
        placeholder={localize('com_access_add_members_placeholder')}
        aria-label={localize('com_access_add_members_placeholder')}
        aria-expanded={hasResults && results.length > 0}
        aria-autocomplete="list"
        aria-controls={listboxId}
        role="combobox"
        disabled={disabled}
        className="w-full rounded-md border border-input bg-background py-2 pr-3 pl-9 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
      />
      {hasResults &&
        dropdownRect &&
        createPortal(renderDropdownContent(dropdownRect), document.body)}
    </div>
  );
}

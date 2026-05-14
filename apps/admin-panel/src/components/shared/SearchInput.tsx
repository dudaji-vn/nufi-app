import { Search } from 'lucide-react';
import type * as t from '@/types';
import { Input } from '@/components/ui';
import { cn } from '@/utils';

export function SearchInput({ value, onChange, placeholder, className }: t.SearchInputProps) {
  return (
    <div className={cn('relative w-full max-w-sm', className)}>
      <Search
        className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
        aria-hidden="true"
      />
      <Input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="h-9 pl-9"
      />
    </div>
  );
}

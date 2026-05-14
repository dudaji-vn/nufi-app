import type * as t from '@/types';
import { Avatar as UIAvatar, AvatarFallback } from '@/components/ui';
import { cn, getInitials } from '@/utils';

const sizeClasses: Record<NonNullable<t.AvatarProps['size']>, string> = {
  sm: 'h-7 w-7 text-[10px]',
  md: 'h-10 w-10 text-sm',
};

export function Avatar({ name, size = 'md', className }: t.AvatarProps) {
  return (
    <UIAvatar
      title={name}
      className={cn(sizeClasses[size], 'bg-muted text-muted-foreground', className)}
    >
      <AvatarFallback className="bg-transparent font-medium">{getInitials(name)}</AvatarFallback>
    </UIAvatar>
  );
}

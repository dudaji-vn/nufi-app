import { Plus } from 'lucide-react';
import { Button } from '@/components/ui';

export function AddItemButton({
  label,
  onClick,
  disabled,
}: {
  label: string;
  onClick: () => void;
  disabled?: boolean;
}) {
  return (
    <Button variant="outline" size="sm" onClick={onClick} disabled={disabled}>
      <Plus />
      {label}
    </Button>
  );
}

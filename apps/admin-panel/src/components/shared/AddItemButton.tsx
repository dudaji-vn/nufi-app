import { Button } from '@clickhouse/click-ui';

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
    <Button
      type="secondary"
      iconLeft="plus"
      label={label}
      onClick={onClick}
      disabled={disabled}
    />
  );
}

import React from 'react';
import { Button, TrashIcon } from '@librechat/client';

type DeleteIconButtonProps = {
  onClick: () => void;
};

export default function DeleteIconButton({ onClick }: DeleteIconButtonProps) {
  return (
    <div className="w-fit">
      <Button className="bg-destructive p-3 text-destructive-foreground hover:bg-destructive/80" onClick={onClick}>
        <TrashIcon />
      </Button>
    </div>
  );
}

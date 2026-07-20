import React from 'react';
import { ToggleContext } from './ToggleContext';
import { cn } from '~/utils';

const HoverToggle = ({
  children,
  isActiveConvo,
  isPopoverActive,
  setIsPopoverActive,
  className = 'absolute bottom-0 right-0 top-0',
  onClick,
}: {
  children: React.ReactNode;
  isActiveConvo: boolean;
  isPopoverActive: boolean;
  setIsPopoverActive: (isActive: boolean) => void;
  className?: string;
  onClick?: (e: React.MouseEvent<HTMLDivElement>) => void;
}) => {
  const setPopoverActive = (value: boolean) => setIsPopoverActive(value);
  return (
    <ToggleContext.Provider value={{ isPopoverActive, setPopoverActive }}>
      <div
        onClick={onClick}
        className={cn(
          'peer items-center gap-1.5 rounded-r-lg pl-2 pr-2 dark:text-white',
          isPopoverActive || isActiveConvo ? 'flex' : 'hidden group-hover:flex',
          className,
        )}
      >
        {children}
      </div>
    </ToggleContext.Provider>
  );
};

export default HoverToggle;

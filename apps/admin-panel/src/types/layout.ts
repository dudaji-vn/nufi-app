import type { ComponentType, ReactNode, SVGProps } from 'react';
import type { IconName } from './scope';

export type LucideIconComponent = ComponentType<SVGProps<SVGSVGElement>>;

export interface SidebarProps {
  user?: {
    name?: string;
    email?: string;
  } | null;
  collapsed: boolean;
  onToggle: () => void;
}

export interface NavItem {
  labelKey: string;
  path: string;
  icon: LucideIconComponent;
  capability?: string | string[];
}

export interface HeaderProps {
  title?: string;
  onSearchClick?: () => void;
  children?: ReactNode;
}

export interface CommandMenuProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export interface CommandItemProps {
  icon?: IconName | LucideIconComponent;
  label: string;
  keywords?: string[];
  onSelect: () => void;
}

export interface SettingsDialogProps {
  open: boolean;
  onClose: () => void;
}

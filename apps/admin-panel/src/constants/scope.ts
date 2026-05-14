import { Lock, Settings2, User, Users } from 'lucide-react';
import { PrincipalType } from 'librechat-data-provider';
import type * as t from '@/types';

export const SCOPE_TYPE_CONFIG: Record<t.ScopePrincipalType | 'BASE', t.ScopeTypeConfigEntry> = {
  BASE: {
    icon: Settings2,
    color: 'hsl(var(--primary))',
    labelKey: 'com_scope_base_config',
    badgeClass: '',
  },
  [PrincipalType.ROLE]: {
    icon: Lock,
    color: 'hsl(var(--secondary))',
    labelKey: 'com_scope_roles',
    badgeClass: 'badge-role',
  },
  [PrincipalType.GROUP]: {
    icon: Users,
    color: 'hsl(var(--primary))',
    labelKey: 'com_scope_groups',
    badgeClass: 'badge-group',
  },
  [PrincipalType.USER]: {
    icon: User,
    color: 'hsl(var(--secondary))',
    labelKey: 'com_scope_users',
    badgeClass: 'badge-user',
  },
};

/** Safe lookup — falls back to BASE config if the type has no scope entry (e.g. PUBLIC). */
export function getScopeTypeConfig(type: PrincipalType | 'BASE'): t.ScopeTypeConfigEntry {
  return SCOPE_TYPE_CONFIG[type as t.ScopePrincipalType | 'BASE'] ?? SCOPE_TYPE_CONFIG.BASE;
}

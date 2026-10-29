import type { MouseEvent, ReactNode } from 'react';
import { useNavigate, useRouterState } from '@tanstack/react-router';

// An anchor to a section of the home page (#how, #features, #contact). On the
// home route it smooth-scrolls; from another route it navigates home first,
// then scrolls once the section has mounted.
export function SectionLink({
  id,
  className,
  children,
  onNavigate,
}: {
  id: string;
  className?: string;
  children: ReactNode;
  onNavigate?: () => void;
}) {
  const navigate = useNavigate();
  const pathname = useRouterState({ select: (s) => s.location.pathname });

  const onClick = (e: MouseEvent) => {
    e.preventDefault();
    onNavigate?.();
    const scroll = () => document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    if (pathname === '/') scroll();
    else void navigate({ to: '/' }).then(() => setTimeout(scroll, 60));
  };

  return (
    <a href={`#${id}`} className={className} onClick={onClick}>
      {children}
    </a>
  );
}

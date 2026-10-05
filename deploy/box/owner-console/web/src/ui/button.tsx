import type { ButtonHTMLAttributes } from 'react';
import './ui.css';

export type ButtonVariant = 'primary' | 'secondary' | 'danger' | 'ghost';
export type ButtonSize = 'sm' | 'md' | 'lg';

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  size?: ButtonSize;
};

export function Button({ variant = 'primary', size = 'md', className, type = 'button', ...rest }: Props) {
  const cls = ['ui-btn', `ui-btn--${variant}`, size !== 'md' && `ui-btn--${size}`, className]
    .filter(Boolean)
    .join(' ');
  return <button type={type} className={cls} {...rest} />;
}

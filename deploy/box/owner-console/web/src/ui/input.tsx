import type { InputHTMLAttributes } from 'react';
import './ui.css';

export function Input({ className, ...rest }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={['ui-input', className].filter(Boolean).join(' ')} {...rest} />;
}

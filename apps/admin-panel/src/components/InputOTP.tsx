import * as React from 'react';
import { OTPInput, OTPInputContext } from 'input-otp';
import { cn } from '@/utils';

const InputOTP = React.forwardRef<
  React.ElementRef<typeof OTPInput>,
  React.ComponentPropsWithoutRef<typeof OTPInput>
>(({ className, containerClassName, ...props }, ref) => (
  <OTPInput
    ref={ref}
    containerClassName={cn(
      'flex items-center gap-2 has-[:disabled]:opacity-50',
      containerClassName,
    )}
    className={cn('disabled:cursor-not-allowed', className)}
    {...props}
  />
));
InputOTP.displayName = 'InputOTP';

const InputOTPGroup = React.forwardRef<
  React.ElementRef<'div'>,
  React.ComponentPropsWithoutRef<'div'>
>(({ className, ...props }, ref) => (
  <div ref={ref} className={cn('flex items-center', className)} {...props} />
));
InputOTPGroup.displayName = 'InputOTPGroup';

const InputOTPSlot = React.forwardRef<
  React.ElementRef<'div'>,
  React.ComponentPropsWithoutRef<'div'> & { index: number }
>(({ index, className, ...props }, ref) => {
  const inputOTPContext = React.useContext(OTPInputContext);

  if (!inputOTPContext) {
    throw new Error('InputOTPSlot must be used within an OTPInput');
  }

  const slot = inputOTPContext.slots[index];
  if (!slot) {
    throw new Error(
      `InputOTPSlot index ${index} is out of range (${inputOTPContext.slots.length} slots)`,
    );
  }
  const { char, hasFakeCaret, isActive } = slot;

  return (
    <div
      ref={ref}
      className={cn(
        'relative flex h-12 w-11 items-center justify-center',
        'border-y border-r border-input bg-background text-foreground',
        'text-lg font-medium shadow-sm transition-all',
        'first:rounded-l-md first:border-l last:rounded-r-md',
        isActive ? 'z-10 border-ring ring-1 ring-ring' : 'hover:border-ring/60',
        className,
      )}
      {...props}
    >
      {char}
      {hasFakeCaret && (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
          <div className="h-5 w-px animate-pulse bg-foreground duration-1000" />
        </div>
      )}
    </div>
  );
});
InputOTPSlot.displayName = 'InputOTPSlot';

const InputOTPSeparator = React.forwardRef<
  React.ElementRef<'div'>,
  React.ComponentPropsWithoutRef<'div'>
>(({ ...props }, ref) => (
  <div ref={ref} role="separator" className="text-muted-foreground" {...props}>
    <svg width="16" height="2" viewBox="0 0 16 2" fill="none" aria-hidden="true">
      <line x1="0" y1="1" x2="16" y2="1" stroke="currentColor" strokeWidth="2" />
    </svg>
  </div>
));
InputOTPSeparator.displayName = 'InputOTPSeparator';

export { InputOTP, InputOTPGroup, InputOTPSlot, InputOTPSeparator };

import { z } from 'zod';
import { AlertTriangle, Loader2 } from 'lucide-react';
import { REGEXP_ONLY_DIGITS } from 'input-otp';
import { useQuery } from '@tanstack/react-query';
import { useRouter } from '@tanstack/react-router';
import { useState, useEffect, useRef, useMemo } from 'react';
import type * as t from '@/types';
import { adminLoginFn, adminVerify2FAFn, openIdCheckOptions, openidLoginFn } from '@/server';
import { Button, Card, CardContent, Input, Label, Separator } from '@/components/ui';
import { InputOTP, InputOTPGroup, InputOTPSlot, InputOTPSeparator } from './InputOTP';
import { PasswordInput } from './PasswordInput';
import { useLocalize } from '@/hooks';
import nufiLogo from '@/assets/nufi-logo.svg';
import { cn } from '@/utils';

export function AuthCard({
  redirectTo = '/',
  autoRedirectSso = false,
  ssoAvailable: ssoAvailableProp,
}: t.AuthCardProps) {
  const router = useRouter();
  const localize = useLocalize();
  const [step, setStep] = useState<t.AuthStep>('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [generalError, setGeneralError] = useState('');
  const [errors, setErrors] = useState<t.FieldErrors>({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [announcement, setAnnouncement] = useState('');
  const [ssoLoading, setSsoLoading] = useState(false);
  const [autoRedirectFailed, setAutoRedirectFailed] = useState(false);
  const autoRedirectAttempted = useRef(false);

  const [tempToken, setTempToken] = useState('');
  const [totpCode, setTotpCode] = useState('');

  const { data: openIdData } = useQuery({
    ...openIdCheckOptions,
    enabled: ssoAvailableProp === undefined,
  });
  const ssoAvailable = ssoAvailableProp ?? openIdData?.available ?? false;

  const showAutoRedirect = autoRedirectSso && !autoRedirectFailed;

  useEffect(() => {
    const messages = [generalError, errors.email, errors.password].filter(Boolean);
    if (messages.length === 0) {
      setAnnouncement('');
      return;
    }
    setAnnouncement(messages.join('. '));
    const timeout = setTimeout(() => setAnnouncement(''), 4000);
    return () => clearTimeout(timeout);
  }, [generalError, errors.email, errors.password]);

  useEffect(() => {
    if (!autoRedirectSso || autoRedirectAttempted.current) return;
    autoRedirectAttempted.current = true;

    setSsoLoading(true);
    openidLoginFn()
      .then((result) => {
        if (result.error || !result.authUrl) {
          setAutoRedirectFailed(true);
          setGeneralError(result.message || localize('com_auth_sso_redirect_failed'));
          return;
        }
        const authUrl = new URL(result.authUrl);
        if (redirectTo && redirectTo !== '/') {
          authUrl.searchParams.set('redirectTo', redirectTo);
        }
        window.location.href = authUrl.toString();
      })
      .catch(() => {
        setAutoRedirectFailed(true);
        setGeneralError(localize('com_auth_sso_redirect_failed'));
      })
      .finally(() => setSsoLoading(false));
  }, [autoRedirectSso, localize, redirectTo]);

  const emailSchema = useMemo(
    () => z.string().email(localize('com_auth_email_invalid')),
    [localize],
  );

  const handleLogin = async () => {
    if (isSubmitting) return;

    const newErrors: t.FieldErrors = {};

    if (!email.trim()) {
      newErrors.email = localize('com_auth_email_required');
    } else {
      const emailResult = emailSchema.safeParse(email);
      if (!emailResult.success) {
        newErrors.email = emailResult.error.issues[0].message;
      }
    }

    if (!password) {
      newErrors.password = localize('com_auth_password_required');
    }

    if (Object.keys(newErrors).length > 0) {
      setErrors(newErrors);
      setGeneralError('');
      return;
    }

    setErrors({});
    setGeneralError('');
    setIsSubmitting(true);

    try {
      const result = await adminLoginFn({ data: { email, password } });

      if (result.error) {
        setGeneralError(result.message || localize('com_auth_login_failed'));
        return;
      }

      if (result.requires2FA) {
        if (!result.tempToken) {
          setGeneralError(localize('com_auth_login_failed'));
          return;
        }
        setTempToken(result.tempToken);
        setTotpCode('');
        setGeneralError('');
        setStep('2fa');
        return;
      }

      setPassword('');
      await router.invalidate();
      router.navigate({ to: redirectTo });
    } catch (error) {
      console.error('Login error:', error);
      setGeneralError(localize('com_auth_unable_connect'));
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleVerify2FA = async (codeOverride?: string) => {
    if (isSubmitting) return;

    const code = codeOverride ?? totpCode;
    if (!/^\d{6}$/.test(code)) {
      setGeneralError(localize('com_auth_2fa_invalid_code'));
      return;
    }

    setGeneralError('');
    setIsSubmitting(true);

    try {
      const result = await adminVerify2FAFn({ data: { tempToken, totpCode: code } });

      if (result.error) {
        if (result.expired) {
          setGeneralError(localize('com_auth_2fa_expired'));
          setStep('login');
          setTempToken('');
          setTotpCode('');
          return;
        }
        setGeneralError(result.message || localize('com_auth_2fa_invalid_code'));
        setTotpCode('');
        return;
      }

      setPassword('');
      setTotpCode('');
      setTempToken('');
      await router.invalidate();
      router.navigate({ to: redirectTo });
    } catch (error) {
      console.error('2FA verification error:', error);
      setGeneralError(localize('com_auth_unable_connect'));
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleBack = () => {
    setStep('login');
    setTempToken('');
    setTotpCode('');
    setGeneralError('');
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') handleLogin();
  };

  const handleSsoLogin = async () => {
    if (ssoLoading) return;
    setSsoLoading(true);
    try {
      const result = await openidLoginFn();
      if (result.error) {
        setGeneralError(result.message || localize('com_auth_login_failed'));
        return;
      }
      if (result.authUrl) {
        window.location.href = result.authUrl;
      }
    } catch {
      setGeneralError(localize('com_auth_unable_connect'));
    } finally {
      setSsoLoading(false);
    }
  };

  const Brand = (
    <div className="flex flex-col items-center gap-3">
      <div className="flex h-16 w-16 items-center justify-center rounded-xl bg-white shadow-md">
        <img src={nufiLogo} alt={localize('com_a11y_logo_alt')} className="h-11 w-11" />
      </div>
      <div className="flex flex-col items-center gap-1">
        <h1 className="text-2xl font-semibold tracking-tight text-foreground">
          {step === '2fa' ? localize('com_auth_2fa_title') : localize('com_auth_title')}
        </h1>
        {step !== '2fa' && (
          <p className="text-sm text-muted-foreground">{localize('com_auth_subtitle')}</p>
        )}
      </div>
    </div>
  );

  if (showAutoRedirect) {
    return (
      <Card className="w-full max-w-md border-border/60 shadow-2xl shadow-black/30">
        <CardContent className="flex flex-col items-center gap-6 p-8">
          {Brand}
          <p className="text-center text-sm text-muted-foreground">
            {localize('com_auth_sso_redirecting_auto')}
          </p>
          <Loader2 className="h-6 w-6 animate-spin text-primary" />
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="w-full max-w-md border-border/60 shadow-2xl shadow-black/30">
      <CardContent className="flex flex-col gap-6 p-8">
        {Brand}

        {generalError && (
          <div
            role="alert"
            className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive"
          >
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            <span>{generalError}</span>
          </div>
        )}

        {step === '2fa' ? (
          <>
            <p className="text-center text-sm text-muted-foreground">
              {localize('com_auth_2fa_prompt')}
            </p>
            <div className="flex justify-center">
              <InputOTP
                maxLength={6}
                value={totpCode}
                onChange={(value) => setTotpCode(value)}
                onComplete={handleVerify2FA}
                pattern={REGEXP_ONLY_DIGITS}
                disabled={isSubmitting}
                aria-label={localize('com_auth_2fa_code_label')}
                autoFocus
              >
                <InputOTPGroup>
                  <InputOTPSlot index={0} />
                  <InputOTPSlot index={1} />
                  <InputOTPSlot index={2} />
                </InputOTPGroup>
                <InputOTPSeparator />
                <InputOTPGroup>
                  <InputOTPSlot index={3} />
                  <InputOTPSlot index={4} />
                  <InputOTPSlot index={5} />
                </InputOTPGroup>
              </InputOTP>
            </div>
            {isSubmitting && (
              <p className="text-center text-sm text-muted-foreground">
                {localize('com_auth_2fa_verifying')}
              </p>
            )}
            <button
              type="button"
              onClick={handleBack}
              disabled={isSubmitting}
              className={cn(
                'text-sm text-primary transition-colors hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                'disabled:pointer-events-none disabled:opacity-50',
              )}
            >
              {localize('com_auth_2fa_back')}
            </button>
          </>
        ) : (
          <>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="login-email">{localize('com_auth_email_label')}</Label>
              <Input
                id="login-email"
                type="email"
                placeholder={localize('com_auth_email_placeholder')}
                value={email}
                onChange={(e) => {
                  setEmail(e.target.value);
                  if (errors.email) setErrors((prev) => ({ ...prev, email: undefined }));
                }}
                onKeyDown={handleKeyDown}
                aria-invalid={errors.email ? true : undefined}
                className={errors.email ? 'border-destructive focus-visible:ring-destructive' : ''}
              />
              {errors.email && <span className="text-xs text-destructive">{errors.email}</span>}
            </div>

            <PasswordInput
              label={localize('com_auth_password_label')}
              placeholder={localize('com_auth_password_placeholder')}
              value={password}
              onChange={(value) => {
                setPassword(value);
                if (errors.password) setErrors((prev) => ({ ...prev, password: undefined }));
              }}
              onKeyDown={handleKeyDown}
              error={errors.password}
            />

            <Button onClick={handleLogin} disabled={isSubmitting} className="w-full">
              {isSubmitting && <Loader2 className="h-4 w-4 animate-spin" />}
              {isSubmitting ? localize('com_auth_signing_in') : localize('com_auth_sign_in')}
            </Button>

            {ssoAvailable && (
              <>
                <Separator />
                <Button
                  variant="outline"
                  onClick={handleSsoLogin}
                  disabled={ssoLoading}
                  className="w-full"
                >
                  {ssoLoading && <Loader2 className="h-4 w-4 animate-spin" />}
                  {ssoLoading
                    ? localize('com_auth_sso_redirecting')
                    : localize('com_auth_sso_sign_in')}
                </Button>
              </>
            )}
          </>
        )}
        <div role="status" aria-live="polite" aria-atomic="true" className="sr-only">
          {announcement}
        </div>
      </CardContent>
    </Card>
  );
}

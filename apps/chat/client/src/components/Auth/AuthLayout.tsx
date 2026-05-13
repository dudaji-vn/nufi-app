import { Link } from 'react-router-dom';
import { useLocalize } from '~/hooks';
import { BlinkAnimation } from './BlinkAnimation';
import { TStartupConfig } from 'librechat-data-provider';
import SocialLoginRender from './SocialLoginRender';
import { ThemeSelector } from '~/components/ui';
import { Banner } from '../Banners';
import Footer from './Footer';

const ErrorRender = ({ children }: { children: React.ReactNode }) => (
  <div className="mb-4 flex justify-center">
    <div
      className="w-full rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-600 dark:text-red-300"
      role="alert"
    >
      {children}
    </div>
  </div>
);

function AuthLayout({
  children,
  header,
  isFetching,
  startupConfig,
  startupConfigError,
  pathname,
  error,
}: {
  children: React.ReactNode;
  header: React.ReactNode;
  isFetching: boolean;
  startupConfig: TStartupConfig | null | undefined;
  startupConfigError: unknown | null | undefined;
  pathname: string;
  error: string | null;
}) {
  const localize = useLocalize();

  const DisplayError = () => {
    if (startupConfigError !== null && startupConfigError !== undefined) {
      return <ErrorRender>{localize('com_auth_error_login_server')}</ErrorRender>;
    } else if (error === 'com_auth_error_invalid_reset_token') {
      return (
        <ErrorRender>
          {localize('com_auth_error_invalid_reset_token')}{' '}
          <Link
            className="font-semibold text-brand-purple hover:underline"
            to="/forgot-password"
          >
            {localize('com_auth_click_here')}
          </Link>{' '}
          {localize('com_auth_to_try_again')}
        </ErrorRender>
      );
    } else if (error) {
      return <ErrorRender>{localize(error)}</ErrorRender>;
    }
    return null;
  };

  return (
    <div className="relative min-h-screen bg-white text-text-primary dark:bg-[hsl(var(--background))]">
      <Banner />

      <div className="absolute right-4 top-4 z-20">
        <ThemeSelector />
      </div>

      <div className="grid min-h-screen lg:grid-cols-2">
        {/* Hero / branding panel */}
        <div className="relative hidden overflow-hidden bg-[hsl(var(--sidebar-background))] lg:flex lg:flex-col lg:justify-between lg:p-12">
          {/* Cyber-Grid background */}
          <div
            aria-hidden
            className="pointer-events-none absolute inset-0 opacity-[0.35]"
            style={{
              backgroundImage:
                'linear-gradient(hsl(var(--border)) 1px, transparent 1px), linear-gradient(90deg, hsl(var(--border)) 1px, transparent 1px)',
              backgroundSize: '48px 48px',
              maskImage:
                'radial-gradient(ellipse at center, black 40%, transparent 75%)',
              WebkitMaskImage:
                'radial-gradient(ellipse at center, black 40%, transparent 75%)',
            }}
          />
          {/* Glow accents */}
          <div
            aria-hidden
            className="pointer-events-none absolute -left-32 -top-32 h-96 w-96 rounded-full blur-3xl"
            style={{ background: 'hsl(var(--primary) / 0.25)' }}
          />
          <div
            aria-hidden
            className="pointer-events-none absolute -bottom-40 -right-20 h-[28rem] w-[28rem] rounded-full blur-3xl"
            style={{ background: 'hsl(var(--secondary) / 0.18)' }}
          />

          <div className="relative z-10 inline-flex w-fit items-center gap-3 rounded-2xl bg-white px-4 py-2.5 shadow-lg ring-1 ring-white/10">
            <img src="/assets/nufi-logo.svg" alt="NUFI" className="h-9 w-auto" />
          </div>

          <div className="relative z-10 max-w-lg">
            <h2 className="text-4xl font-semibold leading-tight tracking-tight text-foreground">
              Think it. Ask it. Done.
            </h2>
            <p className="mt-4 text-base leading-relaxed text-muted-foreground">
              Your everyday AI for writing, learning, and getting things done —
              ready whenever you are.
            </p>
          </div>

          <div className="relative z-10 text-xs text-muted-foreground">
            © {new Date().getFullYear()} NUFI · All rights reserved
          </div>
        </div>

        {/* Form panel */}
        <div className="relative flex flex-col">
          <div className="flex flex-1 items-center justify-center px-4 py-10 sm:px-8">
            <div className="w-full max-w-md">
              {/* Mobile logo */}
              <div className="mb-8 flex justify-center lg:hidden">
                <BlinkAnimation active={isFetching}>
                  <div className="inline-flex items-center rounded-2xl bg-white px-4 py-2.5 shadow-md ring-1 ring-black/5 dark:ring-white/10">
                    <img src="/assets/nufi-logo.svg" alt="NUFI" className="h-9 w-auto" />
                  </div>
                </BlinkAnimation>
              </div>

              <DisplayError />

              {!startupConfigError && !isFetching && (
                <div className="mb-8 text-center lg:text-left">
                  <h1
                    className="text-3xl font-semibold tracking-tight text-foreground"
                    style={{ userSelect: 'none' }}
                  >
                    {header}
                  </h1>
                  {(pathname.includes('login') || pathname.includes('register')) &&
                    startupConfig?.registrationEnabled !== false && (
                      <p className="mt-2 text-sm text-muted-foreground">
                        {pathname.includes('register')
                          ? localize('com_auth_already_have_account') + ' '
                          : localize('com_auth_no_account') + ' '}
                        <Link
                          to={pathname.includes('register') ? '/login' : '/register'}
                          className="font-medium text-brand-purple hover:underline"
                        >
                          {pathname.includes('register')
                            ? localize('com_auth_login')
                            : localize('com_auth_sign_up')}
                        </Link>
                      </p>
                    )}
                </div>
              )}

              <div>
                {children}
                {(pathname.includes('login') || pathname.includes('register')) && (
                  <SocialLoginRender startupConfig={startupConfig} />
                )}
              </div>
            </div>
          </div>
          <Footer startupConfig={startupConfig} />
        </div>
      </div>
    </div>
  );
}

export default AuthLayout;

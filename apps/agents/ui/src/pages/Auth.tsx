import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useSearchParams } from "@/lib/router";
import { authApi } from "../api/auth";
import { queryKeys } from "../lib/queryKeys";
import { getRememberedInvitePath } from "../lib/invite-memory";
import { Button } from "@/components/ui/button";
import { AsciiArtAnimation } from "@/components/AsciiArtAnimation";
import { ThemeToggle } from "@/components/ThemeToggle";
import { Sparkles } from "lucide-react";

type AuthMode = "sign_in" | "sign_up";

export function AuthPage() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [mode, setMode] = useState<AuthMode>("sign_in");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [oauthPending, setOauthPending] = useState(false);
  const errorId = "auth-error";

  const autoStarted = useRef(false);

  /**
   * Hand off to the NUFI console.
   *
   * The button is rendered without probing first: the only way to ask whether
   * the provider exists is to start the flow, and doing that on mount would set
   * a state cookie on every visit to this page. So an instance with no OIDC
   * configured shows the button and says so plainly when it is pressed, which
   * is a better trade than a request nobody asked for.
   */
  const startOAuth = async () => {
    if (oauthPending) return;
    setOauthPending(true);
    setError(null);
    try {
      const url = await authApi.signInOAuth({ providerId: "nufi", callbackURL: nextPath });
      if (!url) {
        setError("This instance is not connected to a NUFI console. Sign in with your email and password.");
        return;
      }
      window.location.assign(url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not reach the NUFI console.");
    } finally {
      setOauthPending(false);
    }
  };

  const nextPath = useMemo(
    () => searchParams.get("next") || getRememberedInvitePath() || "/",
    [searchParams],
  );
  const { data: session, isLoading: isSessionLoading } = useQuery({
    queryKey: queryKeys.auth.session,
    queryFn: () => authApi.getSession(),
    retry: false,
  });

  useEffect(() => {
    if (session) {
      navigate(nextPath, { replace: true });
    }
  }, [session, navigate, nextPath]);

  /**
   * Arriving from the chooser at agents.nufi.me means the visitor has already
   * chosen NUFI Works and already has a NUFI session; making them press a
   * second button is a step that exists only because this product signs in
   * over OAuth while Studio reads a cookie. So `?sso=1` starts the flow on
   * arrival and the two products feel the same.
   *
   * It is gated on that parameter rather than simply "no session yet" because
   * an unconditional redirect is a lockout waiting to happen: if the console
   * is misconfigured or unreachable, every visit to this page bounces, the
   * local sign-in form becomes unreachable, and nobody -- including whoever
   * would fix it -- can get in. The callback returns to `nextPath`, which
   * never carries `sso`, so a failed round trip lands here with an error
   * instead of looping.
   */
  useEffect(() => {
    if (autoStarted.current) return;
    if (searchParams.get("sso") !== "1") return;
    if (isSessionLoading || session) return;
    autoStarted.current = true;
    void startOAuth();
    // startOAuth is stable for this purpose: the effect runs at most once,
    // guarded by the ref above.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams, isSessionLoading, session]);

  const mutation = useMutation({
    mutationFn: async () => {
      if (mode === "sign_in") {
        await authApi.signInEmail({ email: email.trim(), password });
        return;
      }
      await authApi.signUpEmail({
        name: name.trim(),
        email: email.trim(),
        password,
      });
    },
    onSuccess: async () => {
      setError(null);
      await queryClient.invalidateQueries({ queryKey: queryKeys.auth.session });
      await queryClient.invalidateQueries({ queryKey: queryKeys.health });
      await queryClient.invalidateQueries({ queryKey: queryKeys.companies.all });
      navigate(nextPath, { replace: true });
    },
    onError: (err) => {
      setError(err instanceof Error ? err.message : "Authentication failed");
    },
  });

  const canSubmit =
    email.trim().length > 0 &&
    password.trim().length > 0 &&
    (mode === "sign_in" || (name.trim().length > 0 && password.trim().length >= 8));

  if (isSessionLoading) {
    return (
      <div className="fixed inset-0 flex items-center justify-center">
        <p className="text-sm text-muted-foreground">Loading…</p>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 flex bg-background">
      <div className="absolute top-4 right-4 z-10">
        <ThemeToggle />
      </div>
      {/* Left half — form */}
      <div className="w-full md:w-1/2 flex flex-col overflow-y-auto">
        <div className="w-full max-w-md mx-auto my-auto px-8 py-12">
          <div className="flex items-center gap-2 mb-8">
            <Sparkles className="h-4 w-4 text-muted-foreground" />
            <span className="text-sm font-medium">Paperclip</span>
          </div>

          <h1 className="text-xl font-semibold">
            {mode === "sign_in" ? "Sign in to Paperclip" : "Create your Paperclip account"}
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {mode === "sign_in"
              ? "Use your email and password to access this instance."
              : "Create an account for this instance. Email confirmation is not required in v1."}
          </p>

          <Button
            type="button"
            variant="outline"
            className="mt-6 w-full"
            onClick={startOAuth}
            disabled={oauthPending}
          >
            {oauthPending ? "Redirecting…" : "Continue with NUFI"}
          </Button>

          <div className="mt-4 flex items-center gap-3">
            <span className="h-px flex-1 bg-border" />
            <span className="text-[11px] uppercase tracking-wide text-muted-foreground">or</span>
            <span className="h-px flex-1 bg-border" />
          </div>

          <form
            className="mt-4 space-y-4"
            method="post"
            action={mode === "sign_up" ? "/api/auth/sign-up/email" : "/api/auth/sign-in/email"}
            onSubmit={(event) => {
              event.preventDefault();
              if (mutation.isPending) return;
              if (!canSubmit) {
                setError("Please fill in all required fields.");
                return;
              }
              mutation.mutate();
            }}
          >
            {mode === "sign_up" && (
              <div>
                <label htmlFor="name" className="text-xs text-muted-foreground mb-1 block">Name</label>
                <input
                  id="name"
                  name="name"
                  className="w-full rounded-md border border-border bg-transparent px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-ring placeholder:text-muted-foreground/50"
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  autoComplete="name"
                  required
                  aria-required="true"
                  aria-invalid={error ? true : undefined}
                  aria-describedby={error ? errorId : undefined}
                  autoFocus
                />
              </div>
            )}
            <div>
              <label htmlFor="email" className="text-xs text-muted-foreground mb-1 block">Email</label>
              <input
                id="email"
                name="email"
                className="w-full rounded-md border border-border bg-transparent px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-ring placeholder:text-muted-foreground/50"
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                autoComplete="username"
                required
                aria-required="true"
                aria-invalid={error ? true : undefined}
                aria-describedby={error ? errorId : undefined}
                autoFocus={mode === "sign_in"}
              />
            </div>
            <div>
              <label htmlFor="password" className="text-xs text-muted-foreground mb-1 block">Password</label>
              <input
                id="password"
                name="password"
                className="w-full rounded-md border border-border bg-transparent px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-ring placeholder:text-muted-foreground/50"
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                autoComplete={mode === "sign_in" ? "current-password" : "new-password"}
                required
                aria-required="true"
                aria-invalid={error ? true : undefined}
                aria-describedby={error ? errorId : undefined}
              />
            </div>
            {error && (
              <p id={errorId} role="alert" className="text-xs text-destructive">
                {error}
              </p>
            )}
            <Button
              type="submit"
              disabled={mutation.isPending}
              aria-disabled={!canSubmit || mutation.isPending}
              className={`w-full ${!canSubmit && !mutation.isPending ? "opacity-50" : ""}`}
            >
              {mutation.isPending
                ? "Working…"
                : mode === "sign_in"
                  ? "Sign In"
                  : "Create Account"}
            </Button>
          </form>

          <div className="mt-5 text-sm text-muted-foreground">
            {mode === "sign_in" ? "Need an account?" : "Already have an account?"}{" "}
            <button
              type="button"
              className="font-medium text-foreground underline underline-offset-2"
              onClick={() => {
                setError(null);
                setMode(mode === "sign_in" ? "sign_up" : "sign_in");
              }}
            >
              {mode === "sign_in" ? "Create one" : "Sign in"}
            </button>
          </div>
        </div>
      </div>

      {/* Right half — ASCII art animation (hidden on mobile) */}
      <div className="hidden md:block w-1/2 overflow-hidden">
        <AsciiArtAnimation />
      </div>
    </div>
  );
}

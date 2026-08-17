import { useCallback, useEffect, useState } from "react";
import type { PluginWidgetProps } from "@paperclipai/plugin-sdk/ui";
import { ConnectCancelled, requestKey } from "./connect-popup.js";
import {
  createDefinition,
  createMyUserSecret,
  HostApiError,
  listMyUserSecrets,
  readConsoleUrl,
  rotateMyUserSecret,
  SECRET_KEY,
  type UserSecretEntry,
} from "./host-api.js";

/**
 * Settings → NUFI.
 *
 * One job: get this member's own gateway key into their own agent runs, without
 * anyone reading a credential out of one browser tab and typing it into
 * another.
 *
 * Styling is inline against the host's CSS custom properties rather than its
 * Tailwind classes. The host compiles Tailwind by scanning its own sources, and
 * this bundle is not among them — a class that happens to work today would
 * vanish the moment the host stopped using it elsewhere. The custom properties
 * are a real contract and follow the theme.
 */

type Status = "idle" | "working";

export function NufiConnectionPage({ context }: PluginWidgetProps) {
  const companyId = context.companyId;

  const [consoleUrl, setConsoleUrl] = useState<string | null | undefined>(undefined);
  const [entries, setEntries] = useState<UserSecretEntry[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [status, setStatus] = useState<Status>("idle");
  const [notice, setNotice] = useState<{ tone: "ok" | "bad"; text: string } | null>(null);

  const reload = useCallback(async () => {
    if (!companyId) return;
    try {
      const [secrets, url] = await Promise.all([
        listMyUserSecrets(companyId),
        // An unreadable config is not a reason to hide the page: everything
        // except the button still works, and the page says what is missing.
        readConsoleUrl(companyId).catch(() => null),
      ]);
      setEntries(secrets);
      setConsoleUrl(url);
      setLoadError(null);
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : "Could not read your secrets.");
    }
  }, [companyId]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const entry = entries?.find((e) => e.definition.key === SECRET_KEY) ?? null;
  const connected = entry?.secret != null;

  const onDeclare = async () => {
    if (!companyId) return;
    setStatus("working");
    setNotice(null);
    try {
      await createDefinition(companyId);
      await reload();
      setNotice({ tone: "ok", text: `${SECRET_KEY} is now available for everyone in this company.` });
    } catch (err) {
      setNotice({
        tone: "bad",
        text:
          err instanceof HostApiError && err.status === 403
            ? "You do not have permission to add a company secret. Ask an administrator to open this page once."
            : err instanceof Error
              ? err.message
              : "Could not add the secret.",
      });
    } finally {
      setStatus("idle");
    }
  };

  const onConnect = async () => {
    if (!companyId || !consoleUrl || !entry) return;
    setStatus("working");
    setNotice(null);
    try {
      const key = await requestKey({ consoleUrl, workspaceId: companyId, win: window });
      // The value goes straight to the server. It is never put in component
      // state, never rendered, and never logged.
      if (entry.secret) {
        await rotateMyUserSecret(companyId, entry.secret.id, key);
      } else {
        await createMyUserSecret(companyId, key);
      }
      await reload();
      setNotice({ tone: "ok", text: "Connected. Agents bound to this secret now run as you." });
    } catch (err) {
      setNotice({
        tone: "bad",
        text:
          err instanceof ConnectCancelled
            ? err.message
            : err instanceof Error
              ? err.message
              : "Could not connect.",
      });
    } finally {
      setStatus("idle");
    }
  };

  if (!companyId) {
    return (
      <Page>
        <P>Open this page inside a company to connect your NUFI account.</P>
      </Page>
    );
  }

  return (
    <Page>
      <h1 style={{ fontSize: 24, fontWeight: 600, letterSpacing: "-0.01em", margin: 0 }}>
        NUFI account
      </h1>
      <P>
        Agents reach NUFI models through the gateway, and the gateway needs a key. Connect yours and
        the agents you are responsible for call as <strong>you</strong> — your budget, your usage,
        revocable on its own.
      </P>

      {consoleUrl === undefined && <P muted>Checking this installation…</P>}

      {consoleUrl === null && (
        <Card tone="warn">
          <strong>Not pointed at a console yet.</strong>
          <P muted>
            An instance administrator sets <Code>NUFI console URL</Code> under Settings → Plugins →
            NUFI Connection, and lists this app's address in <Code>AGENTS_ALLOWED_ORIGINS</Code> on
            the console. Until both are done, keys have to be pasted in by hand under Settings →
            Secrets.
          </P>
        </Card>
      )}

      {loadError && <Card tone="bad">{loadError}</Card>}

      {entries && !entry && (
        <Card>
          <strong>One-time setup</strong>
          <P muted>
            This company has no <Code>{SECRET_KEY}</Code> secret yet, so there is nothing for members
            to fill in. Adding it creates the slot — each person still supplies their own value.
          </P>
          <Button onClick={onDeclare} disabled={status === "working"}>
            {status === "working" ? "Adding…" : `Add ${SECRET_KEY}`}
          </Button>
        </Card>
      )}

      {entry && (
        <Card>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <Dot ok={connected} />
            <strong>{connected ? "Connected" : "Not connected"}</strong>
          </div>
          <P muted>
            {connected
              ? `Your key was set ${formatWhen(entry.secret?.lastRotatedAt ?? entry.secret?.createdAt ?? null)}. Reconnecting issues a new one and revokes the old.`
              : "No key of yours is stored. Agents bound to this secret cannot run for you until there is one."}
          </P>
          <Button
            onClick={onConnect}
            disabled={status === "working" || !consoleUrl}
            variant={connected ? "outline" : "solid"}
          >
            {status === "working"
              ? "Waiting for NUFI…"
              : connected
                ? "Reconnect"
                : "Connect NUFI account"}
          </Button>
        </Card>
      )}

      {notice && <Card tone={notice.tone === "ok" ? "ok" : "bad"}>{notice.text}</Card>}

      {connected && (
        <Card>
          <strong>Using it on an agent</strong>
          <P muted>
            On the agent, add an environment variable named <Code>{SECRET_KEY}</Code> bound to the
            user secret of the same name. Each run then resolves it to the key of whoever the work
            belongs to. An agent with no such binding falls back to the server-wide key, if the
            operator set one.
          </P>
        </Card>
      )}
    </Page>
  );
}

// --- Presentation ----------------------------------------------------------

function formatWhen(iso: string | null): string {
  if (!iso) return "already";
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? "already" : `on ${date.toLocaleDateString()}`;
}

function Page({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ display: "grid", gap: 16, maxWidth: 640, color: "var(--foreground)" }}>
      {children}
    </div>
  );
}

function P({ children, muted }: { children: React.ReactNode; muted?: boolean }) {
  return (
    <p
      style={{
        margin: 0,
        fontSize: 14,
        lineHeight: 1.6,
        color: muted ? "var(--muted-foreground)" : "inherit",
      }}
    >
      {children}
    </p>
  );
}

function Code({ children }: { children: React.ReactNode }) {
  return (
    <code
      style={{
        fontFamily: "var(--font-mono)",
        fontSize: "0.92em",
        background: "var(--muted)",
        borderRadius: 4,
        padding: "1px 5px",
      }}
    >
      {children}
    </code>
  );
}

function Card({
  children,
  tone = "plain",
}: {
  children: React.ReactNode;
  tone?: "plain" | "ok" | "bad" | "warn";
}) {
  const accent =
    tone === "bad" ? "var(--destructive)" : tone === "ok" ? "var(--primary)" : "var(--border)";
  return (
    <section
      style={{
        display: "grid",
        gap: 10,
        justifyItems: "start",
        border: "1px solid var(--border)",
        borderLeft: `3px solid ${accent}`,
        borderRadius: "var(--radius-lg)",
        background: "var(--card)",
        padding: 16,
        fontSize: 14,
        lineHeight: 1.6,
      }}
    >
      {children}
    </section>
  );
}

function Dot({ ok }: { ok: boolean }) {
  return (
    <span
      aria-hidden
      style={{
        width: 8,
        height: 8,
        borderRadius: 999,
        background: ok ? "var(--primary)" : "var(--muted-foreground)",
      }}
    />
  );
}

function Button({
  children,
  onClick,
  disabled,
  variant = "solid",
}: {
  children: React.ReactNode;
  onClick: () => void;
  disabled?: boolean;
  variant?: "solid" | "outline";
}) {
  const solid = variant === "solid";
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      style={{
        height: 36,
        padding: "0 14px",
        borderRadius: "var(--radius-md)",
        fontSize: 14,
        fontWeight: 500,
        cursor: disabled ? "not-allowed" : "pointer",
        opacity: disabled ? 0.6 : 1,
        border: solid ? "1px solid transparent" : "1px solid var(--border)",
        background: solid ? "var(--primary)" : "transparent",
        color: solid ? "var(--primary-foreground)" : "var(--foreground)",
      }}
    >
      {children}
    </button>
  );
}

#!/usr/bin/env python3
"""nufi-app adapter egress guard — the on-box AI twin of MeshBox's EgressPolicy
(CMP-511 W4, feasibility gap #6).

The MeshBox appliance already refuses to forward a member's chat/agent payload to
an off-mesh target (appliance ``portal/egress.py``). This module gives the
*nufi-app side* the symmetric guarantee: an adapter must not be talked into
dialing an upstream (litellm-proxy, nufi-agent, console) that sits on the public
internet. If ``NUFI_UPSTREAM_URL`` / ``NUFI_AGENT_URL`` is ever mis-set or
tampered to a public host, an enforcing adapter refuses (403) instead of shipping
department data off the box.

Allowed = a loopback / RFC1918-private / link-local IP, a mesh name
(``.mesh`` or the configured mesh domain), a host inside a configured mesh CIDR,
or an explicitly allow-listed host. Everything else is public and DENIED in
``enforce`` mode; ``audit`` (the default) records the decision and never raises so
turning enforcement on is an explicit per-deployment choice — but the sellable
appliance stack sets ``enforce``.

Kept intentionally stdlib-only and dependency-free to mirror the adapters.
"""
import ipaddress
import os
import urllib.parse

MODE_AUDIT = "audit"
MODE_ENFORCE = "enforce"
VALID_MODES = (MODE_AUDIT, MODE_ENFORCE)


class EgressError(Exception):
    """A forward target violated the egress policy. ``code`` → HTTP status (403)."""

    def __init__(self, message, code=403):
        super().__init__(message)
        self.code = code


def _host_of(url):
    """Extract a bare hostname/IP from a URL or plain host[:port] string."""
    url = (url or "").strip()
    if not url:
        return ""
    if "://" not in url:
        url = "//" + url  # treat "host:port" as netloc, not scheme
    host = urllib.parse.urlsplit(url).hostname or ""
    return host.rstrip(".").lower()


def _is_private_ip(host):
    """True iff ``host`` is an IP literal in a loopback/private/link-local range."""
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return (ip.is_loopback or ip.is_private or ip.is_link_local
            or ip.is_unspecified)


class EgressGuard:
    """Decides whether an adapter may dial a given upstream URL."""

    def __init__(self, *, mode=MODE_AUDIT, mesh_cidrs=(), allow_hosts=(),
                 mesh_domain="mesh"):
        if mode not in VALID_MODES:
            raise ValueError(f"bad egress mode: {mode!r}")
        self.mode = mode
        self.mesh_domain = (mesh_domain or "mesh").strip(".").lower()
        self._cidrs = []
        for c in mesh_cidrs or ():
            try:
                self._cidrs.append(ipaddress.ip_network(c, strict=False))
            except ValueError:
                pass
        self._allow = {h.strip().rstrip(".").lower()
                       for h in (allow_hosts or ()) if h and h.strip()}

    @property
    def enforcing(self):
        return self.mode == MODE_ENFORCE

    def _in_mesh_cidr(self, host):
        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            return False
        return any(ip in net for net in self._cidrs)

    def _decide(self, host):
        if host in self._allow:
            return True, "allow-listed host"
        if host in ("localhost", "localhost.localdomain"):
            return True, "loopback name"
        if host == self.mesh_domain or host.endswith("." + self.mesh_domain):
            return True, f"mesh name (.{self.mesh_domain})"
        if _is_private_ip(host):
            return True, "loopback/private/link-local IP"
        if self._in_mesh_cidr(host):
            return True, "within configured mesh CIDR"
        return False, "public/off-mesh target — data must not leave the mesh"

    def classify(self, url):
        """Return a decision dict WITHOUT raising (usable in either mode).

        Keys: host, allowed (bool), reason (str), mode, enforcing (bool).
        """
        host = _host_of(url)
        if not host:
            return {"host": "", "allowed": False, "reason": "no host in target",
                    "mode": self.mode, "enforcing": self.enforcing}
        allowed, reason = self._decide(host)
        return {"host": host, "allowed": allowed, "reason": reason,
                "mode": self.mode, "enforcing": self.enforcing}

    def check(self, url):
        """Enforce the policy for ``url``; return the decision dict.

        In ``enforce`` mode a disallowed target raises ``EgressError(403)``. In
        ``audit`` mode it never raises — the decision is returned for recording.
        """
        decision = self.classify(url)
        if self.enforcing and not decision["allowed"]:
            raise EgressError(
                f"egress denied: {decision['host'] or '(none)'} — "
                f"{decision['reason']}", 403)
        return decision


def _split(value):
    """Split a comma/space separated env value into a clean list."""
    if not value:
        return []
    return [p for p in value.replace(",", " ").split() if p]


def from_env(env=None):
    """Build an EgressGuard from NUFI_EGRESS_* env (audit by default)."""
    env = env if env is not None else os.environ
    mode = (env.get("NUFI_EGRESS_MODE") or MODE_AUDIT).strip().lower()
    if mode not in VALID_MODES:
        mode = MODE_AUDIT
    return EgressGuard(
        mode=mode,
        mesh_cidrs=_split(env.get("NUFI_MESH_CIDR", "")),
        allow_hosts=_split(env.get("NUFI_EGRESS_ALLOW", "")),
        mesh_domain=env.get("NUFI_MESH_DOMAIN", "mesh"))

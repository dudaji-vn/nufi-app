# SSO across LibreChat + Console (production)

LibreChat and the console must share one logged-in session. Auth in NPUOps is a JWT cookie issued by LibreChat. Whether that cookie reaches the console depends on how the two are hosted.

## Hosting options

| Layout | Cookie shared? | Effort |
|---|---|---|
| Same origin (`npuops.com/`, `npuops.com/console/`) | yes, automatic | path-routing in proxy |
| Subdomains (`npuops.com`, `console.npuops.com`) | only with proxy cookie rewrite | proxy + 1 line |
| Separate domains | no | not supported |

Pick **same origin** if you don't care about the URL.
Pick **subdomains** if branding wants `console.npuops.com` — the proxy rewrites `Set-Cookie` to add `Domain=.npuops.com` so the browser scopes the cookie across all subdomains.

## Caddy

### Same origin (path-routing, no cookie tricks needed)

```caddy
npuops.com {
  handle_path /console/* {
    reverse_proxy console:3000
  }
  handle {
    reverse_proxy librechat:3080
  }
}
```

### Subdomains (with cookie rewrite)

```caddy
npuops.com {
  reverse_proxy librechat:3080 {
    header_down Set-Cookie (.+) "{1}; Domain=.npuops.com"
  }
}

console.npuops.com {
  reverse_proxy console:3000
}
```

The `header_down` line appends `Domain=.npuops.com` to every `Set-Cookie` LibreChat emits, so the browser shares the cookie across subdomains. TLS certs via Let's Encrypt are automatic in both layouts.

## Traefik (subdomains)

Traefik does not rewrite `Set-Cookie` natively; you need the [rewrite-headers](https://plugins.traefik.io/plugins/628c9eb7ffc0cd18356a979b/rewrite-headers) plugin or a custom middleware. Sketch (compose labels):

```yaml
labels:
  - traefik.enable=true
  - traefik.http.routers.librechat.rule=Host(`npuops.com`)
  - traefik.http.routers.librechat.tls.certresolver=letsencrypt
  - traefik.http.middlewares.cookie-domain.plugin.rewriteHeaders.headers[0].name=Set-Cookie
  - traefik.http.middlewares.cookie-domain.plugin.rewriteHeaders.headers[0].regex=(.*)
  - traefik.http.middlewares.cookie-domain.plugin.rewriteHeaders.headers[0].replacement=$$1; Domain=.npuops.com
  - traefik.http.routers.librechat.middlewares=cookie-domain
```

For NPUOps, Caddy is the smaller-effort pick.

## Console-side: verify the shared JWT

The console backend does not need to call LibreChat. Compose already passes `JWT_REFRESH_SECRET` to both services. On every console request:

1. Read `refreshToken` cookie.
2. Verify with `JWT_REFRESH_SECRET` (`hono/jwt`, `jose`, `jsonwebtoken` — any).
3. Extract `userId` from the payload.
4. Use it for audit and scoping.

If the cookie is missing or invalid, redirect to `/` so LibreChat's login takes over.

## Cost

- Caddy is Apache-2.0, Traefik is MIT — no licence fee.
- TLS via Let's Encrypt — free.
- One extra container (~20 MB RAM idle for Caddy).
- DNS: one A record per hostname (whatever the registrar already charges).

No vendor licensing.

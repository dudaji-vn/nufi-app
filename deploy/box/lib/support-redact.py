#!/usr/bin/env python3
"""support-redact.py — the one .env parser `nufi-box support` uses, and the
two things built on it: the key list for env-keys.txt, and the value-layer
redaction every file in a support bundle gets put through before it is
tarred.

Why one parser. A line-by-line read of .env misses a value stored with real
newlines — the console's OIDC signing key is a PEM, written by
install-box.sh's render_env inside a double-quoted value because compose
does not expand \\n in a .env value (see install-box.sh's comment on
OIDC_PRIVATE_KEY_PEM). The first real bundle taken from the development box
shipped that key in compose.yml because the old redactor's line-by-line read
saw only the PEM's first line, with a stray quote on the front, and matched
nothing. `_parse_env` below is the fix, used by both callers here, so a box
that grows a second multi-line secret does not have to teach a second parser
about it.

Why env-keys.txt needed the same fix, not just compose.yml. A naive
`key = text-before-first-"="` treats every line of a quoted multi-line value
as its OWN key=value pair — and a PEM body line ending in `=`/`==` (base64
padding; most 2048-bit RSA keys have one) prints as
`qsSPj7S3hiUMU9EGKReiJQAOqg=<set>`, a real fragment of the private key,
sitting in the one file this bundle promises never carries a value. Walking
.env as ENTRIES, not lines, is what keeps env-keys.txt to names.

Why a quoted value ends at the first unescaped quote on ITS OWN line. A
hand-edited `.env` — the README tells an operator to edit it directly — can
read `KEY="value" # a note` or `KEY="value" ` (a trailing space from a
copy-paste). Ending the value at the LAST character of the line (the
earlier version's check) misreads both as "no closing quote on this line"
and reads on, swallowing every following line up to the next one that ends
in a quote — which, in a normal .env, is some unrelated later secret. The
fix: the value is whatever is between the opening quote and the first
unescaped quote after it, wherever on the line that falls; anything past it
on the same line is not part of the value and is not examined.

Secret pieces shorter than 4 characters are not matched — a value that
short is not worth the risk of blanking an unrelated occurrence of the same
short string elsewhere in a log line. Every secret this box generates itself
is `openssl rand hex` output, far longer than that; the floor only ever
excludes a value an operator set by hand.

The installer's own placeholders are not secrets either. install-box.sh
writes INFERENCE_API_KEY=ollama on every Ollama-profile box (LiteLLM wants
a non-empty key; Ollama ignores it) and `none` for a remote endpoint that
has no key. Taken as a secret, "ollama" was blanked everywhere it appeared
in the first real bundle — INFERENCE_PROFILE, the `ollama/` model prefix,
every compose reference to the ollama service, `langchain_ollama` in the
RAG log — and the one file meant to show the box's inference wiring no
longer did. The entry is still blanked by NAME in compose.yml; its value is
just not hunted for across the rest of the bundle.
"""
import re
import sys

SECRET_SUFFIXES = ("_KEY", "_SECRET", "_PASSWORD", "PEM", "TOKEN", "_IV")
MIN_SECRET_LEN = 4
PLACEHOLDER_VALUES = ("ollama", "none")


def _find_unescaped(s, ch, start):
    """Index of the first occurrence of `ch` in s[start:] not preceded by a
    backslash, or -1. A backslash itself escapes the next character (so a
    literal backslash is written doubled), matching how compose reads a
    quoted .env value."""
    i = start
    n = len(s)
    while i < n:
        c = s[i]
        if c == "\\":
            i += 2
            continue
        if c == ch:
            return i
        i += 1
    return -1


def parse_env(path):
    """Yield (key, value) for every entry in the .env at path, read close to
    how `docker compose` itself reads one:

      - a comment or blank line is skipped;
      - an unquoted value runs to the first " #" (a space, then a hash —
        compose's own inline-comment rule; a hash with no space before it
        is part of the value), minus trailing whitespace;
      - a double- or single-quoted value ends at the first unescaped
        matching quote — on the SAME line if there is one there, in which
        case anything after that quote on that line is ignored; a
        double-quoted value with no closing quote on its opening line
        continues, real newlines and all, until a later line supplies one
        (a single-quoted value never spans lines — nothing this box writes
        needs that, and treating an unmatched `'` as page-to-end-of-file
        would be worse than treating it as a literal character).
    """
    try:
        text = open(path).read()
    except OSError:
        return
    lines = text.split("\n")
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        i += 1
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        eq = line.find("=")
        if eq == -1:
            continue
        key = line[:eq].strip()
        rest = line[eq + 1:]
        if rest[:1] in ('"', "'"):
            quote = rest[0]
            close = _find_unescaped(rest, quote, 1)
            if close != -1:
                yield key, rest[1:close].replace("\\" + quote, quote)
                continue
            if quote == "'":
                yield key, rest
                continue
            body = [rest[1:]]
            closed = False
            while i < n:
                nxt = lines[i]
                i += 1
                close = _find_unescaped(nxt, quote, 0)
                if close != -1:
                    body.append(nxt[:close])
                    closed = True
                    break
                body.append(nxt)
            yield key, "\n".join(body).replace('\\"', '"')
            if not closed:
                return
            continue
        yield key, rest.split(" #", 1)[0].rstrip()


def secret_values(path):
    """Every secret-looking piece in the .env at path: the whole value of
    any key ending in SECRET_SUFFIXES, plus — for a multi-line value — each
    of its own lines, since compose renders a multi-line value as a block
    scalar, one line at a time, and each of those lines is on its own a
    piece of the secret."""
    values = []
    seen = set()
    for key, val in parse_env(path):
        if not key.endswith(SECRET_SUFFIXES) or val in PLACEHOLDER_VALUES:
            continue
        pieces = [val] if "\n" not in val else [val] + val.split("\n")
        for piece in pieces:
            piece = piece.strip()
            if len(piece) >= MIN_SECRET_LEN and piece not in seen:
                seen.add(piece)
                values.append(piece)
    return values


def redact_text(text, secrets):
    for value in sorted(secrets, key=len, reverse=True):
        text = text.replace(value, "<redacted>")
    return text


def redact_by_key(text):
    """compose.yml only: any environment ENTRY whose NAME looks like a
    secret is blanked, whatever its value renders as — belt to the value
    layer's braces, since `docker compose config` prints a service's own
    variable name, which need not be the .env key name that fed it, and
    because this catches a secret the value layer's 4-character floor
    would otherwise let through."""
    out = []
    lines = text.split("\n")
    i = 0
    n = len(lines)
    key_re = re.compile(r"^(\s+)([A-Za-z0-9_]+):\s*(.*)$")
    while i < n:
        m = key_re.match(lines[i])
        if m and m.group(2).upper().endswith(SECRET_SUFFIXES):
            indent = len(m.group(1))
            out.append("%s%s: <redacted>" % (m.group(1), m.group(2)))
            i += 1
            while i < n and lines[i].strip() and (len(lines[i]) - len(lines[i].lstrip())) > indent:
                i += 1
            continue
        out.append(lines[i])
        i += 1
    return "\n".join(out)


def cmd_keys(env_path):
    """env-keys.txt: every key in .env, and whether it has a value — never
    the value. One line per ENTRY (a multi-line value is still one key)."""
    rows = []
    for key, val in parse_env(env_path):
        rows.append("%s=%s" % (key, "<set>" if val else "<empty>"))
    for row in sorted(rows):
        print(row)


def cmd_redact(argv):
    """redact <env> <file>...: rewrite each file in place with every
    secret-looking .env value blanked. The value layer only — compose.yml's
    extra name layer is redact-compose's job, not this one's, so a plain
    text file (a log, doctor.txt) is not scanned for a YAML shape it does
    not have."""
    if not argv:
        return
    env_path = argv[0]
    secrets = secret_values(env_path)
    for path in argv[1:]:
        try:
            with open(path, "r", errors="replace") as f:
                text = f.read()
        except OSError:
            continue
        redacted = redact_text(text, secrets)
        if redacted != text:
            try:
                with open(path, "w") as f:
                    f.write(redacted)
            except OSError:
                pass


def cmd_redact_compose(env_path):
    """redact-compose <env>: `docker compose config` on stdin, both layers
    (value, then name) applied, written to stdout."""
    secrets = secret_values(env_path)
    text = redact_text(sys.stdin.read(), secrets)
    sys.stdout.write(redact_by_key(text))


def main(argv):
    if len(argv) < 3:
        sys.exit("usage: support-redact.py keys <env> | redact <env> <file>... | redact-compose <env>")
    cmd, env_path = argv[1], argv[2]
    if cmd == "keys":
        cmd_keys(env_path)
    elif cmd == "redact":
        cmd_redact(argv[2:])
    elif cmd == "redact-compose":
        cmd_redact_compose(env_path)
    else:
        sys.exit("support-redact.py: unknown command: %s" % cmd)


if __name__ == "__main__":
    main(sys.argv)

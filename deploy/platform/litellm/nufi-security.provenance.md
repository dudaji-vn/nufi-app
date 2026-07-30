# `nufi-security`, vendored

`litellm/nufi-security/` is a snapshot of another repository, copied into this
one. It is not our code. This file records where it came from, what was left
behind, and what is still unresolved.

| | |
|---|---|
| Upstream | `https://github.com/dudaji/nufi-security` (public) |
| Commit | `5eb9a027cbdd9c5d3142d4609782110a737c67e0` |
| Distribution | `nufi_egress` **0.10.0** (`VERSION`) |
| Snapshot taken | 2026-07-30 |
| Runtime dependencies | `PyYAML>=6.0`, `cryptography>=41.0` — that is all |
| Licence | **`license = "Proprietary"`, no LICENSE file. Unresolved.** |

The consumer is `guardrails/scanners/nufi_injection.py` and
`guardrails/scanners/nufi_pii.py` — two adapters behind the scanner interface
described in `docs/2026-07-27-llm-security-gateway-design.md` §5. Nothing else
in the gateway imports it.

## Why a snapshot instead of `pip install git+https://…`

The build previously installed the package from GitHub at this same commit. Two
measured problems ended that.

**A change to their code could not be made.** Reversible pseudonymization —
integration step 3, and one of the two features the upstream author asked for by
name — needs the surrogate delimiter to be selectable, because whether a token
comes back intact is a property of the deployed model and the prompt, not of the
library. Making it configurable is a small change to *their* file, and under a
git pin the only route to it is a pull request into a repository we do not own.
The feature stalled there.

(An earlier measurement put `⟦E1⟧` at 0/6 through `gemini-2.5-flash` and was
cited as a bug in that delimiter. A wider re-measurement on 2026-07-30 — seven
prompt shapes, three delimiters — returned **54/54 intact** and did not
reproduce it. The configurability argument above does not depend on that figure;
the claim that the default delimiter is broken did, and has been withdrawn. What
survives both rounds is the failure *shape*: when brackets are stripped,
`_LENIENT` will not match a bare `E1`, so restoration fails without raising.)

**The package reported the wrong version of itself.** `nufi/__init__.py` reads
`__version__` from the root `VERSION` file and falls back to `"0.0.0"` when the
file is absent. `[tool.setuptools] packages` lists seven packages and no data
files, so `pip install` never delivers `VERSION`. Measured in the running
container before this change:

```
version = '0.0.0'
VERSION file exists = False
```

0.10.0 identifying itself as 0.0.0, with nothing to say so — the failure shape
this whole subsystem exists to end. A source snapshot carries `VERSION`, so the
version is now the real one.

Two smaller consequences follow. The build no longer reaches the network or runs
`pip`, and `config/patterns.yaml` — which the wheel does not ship, and which had
to be hand-copied to `guardrails/nufi_patterns.yaml` for that reason — is now
present in-tree, so the copy can be checked byte-for-byte against its source
locally instead of over the network.

## What was left behind

| Excluded | Size | Why |
|---|---|---|
| `samples/gold/external_test.jsonl` | 71 MB | Evaluation corpus. Backs their 0.9908 Korean recall figure; not needed to run or test the library. Fetch from upstream to reproduce that number. |
| `samples/gold/external_dev.jsonl` | 47 MB | As above. |
| `demo_outputs/` | 80 KB | Generated artefacts, including a `.zip`. Reproducible from `scripts/demo_*.sh`. |
| `HANDOVER/` | — | Their repository's internal project-state and agent-operating notes. Accurate about their repo, and would go stale as a copy in ours. |

Everything else tracked at that commit is here: 424 files, 4.5 MB, 52,523 lines
of Python — of which 18,027 are their test suite, kept in full because it is the
evidence their detectors behave as claimed.

Their `.gitignore` came with the snapshot and applies to this subtree, which is
why `__pycache__/`, `.venv/` and `logs/` stay out on their own.

## What is present but not wired

Kept for fidelity — a future change of theirs should merge into this tree, not
fight a hand-pruned subset — but nothing in the gateway reaches any of it:

- `gateway/` — their FastAPI server. We consume the library in-process instead.
  A network hop would make the cheapest detector the slowest (41 ms p95
  in-process against ~103 ms for the Presidio round trip) and add a second
  thing that can fail open.
- `config/policy.yaml` — their policy file. Ours is OWASP-mapped and wired to
  alerting; two policy files means two places to look when a request is
  blocked, which is what deleting the `apps/chat` guardrails was for.
- `deploy/` — their Dockerfile, compose files and Helm chart.
- `scripts/`, `goldset/`, `examples/`, `.github/` — benchmarks and CI. Their
  `.github/` is inert here; GitHub only reads the repository root.

The image copies only the seven declared packages plus `VERSION`. See
`Dockerfile`.

## Local modifications

Every change we make to this subtree is a commit of its own, on top of the
pristine snapshot, so that upstream can review our diff rather than a merged
blob. To list them:

```bash
git log --oneline -- deploy/platform/litellm/nufi-security/
```

The first commit in that list is the snapshot itself and contains no changes of
ours.

## Verifying against upstream

```bash
git clone https://github.com/dudaji/nufi-security /tmp/nufi-security-upstream
git -C /tmp/nufi-security-upstream checkout 5eb9a027cbdd9c5d3142d4609782110a737c67e0
diff -r --brief \
  -x '.git' -x '__pycache__' -x 'HANDOVER' -x 'demo_outputs' \
  -x 'external_test.jsonl' -x 'external_dev.jsonl' \
  /tmp/nufi-security-upstream deploy/platform/litellm/nufi-security
```

Differences should be exactly our own commits, listed above.

## Licence

`pyproject.toml` declares `license = "Proprietary"` and the upstream repository
has no LICENSE file. Both organisations are Dudaji, and the snapshot exists
because its author wrote, on 2026-07-10:

> sooner or later, I want to merge my nufi-security repo to sun's codebase.
> Especially, I want to merge PII and pseudonymization feature for KR.

**Decided 2026-07-30** by the owner of this repository, who holds the authority
to make it: this subtree is first-party code, on the same footing as anything
else in `deploy/platform/`. It is not a third-party dependency and is not
treated as one. Earlier revisions of this file gated the branch on a LICENSE
file and the author's written agreement; that gate is lifted by that decision
and the record of it is here rather than removed.

Note what this does **not** settle. `pyproject.toml` still says `Proprietary`,
which is now a statement about our own code and should be reconciled with
whatever terms this monorepo settles on — the root has no LICENSE, while
`apps/chat` and `apps/admin-panel` each carry their own. Separately, the
platform's existing licence debt is untouched and unrelated: MongoDB SSPL, MinIO
AGPL and the Redis tri-license still block any SaaS launch.

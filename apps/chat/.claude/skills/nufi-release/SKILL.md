---
name: nufi-release
description: Cut a NUFI release for the dudaji-vn/nufichat fork — merge develop → fork/main, tag nufi-vX.Y.Z, and verify the GHCR image build fires. Triggers on "/nufi-release", "cut a release", "ship a release", "tag a release", "publish the image", "do the release flow", or when the user explicitly references the NUFI release pipeline. Optional arg: target version like "v0.0.5" or "0.0.5" — otherwise auto-bump patch from the latest nufi-v* tag.
---

# NUFI release flow

Cut a release for the NUFI fork. Production branch is `fork/main`; CI in `.github/workflows/build-image.yml` builds and publishes a Docker image to `ghcr.io/dudaji-vn/nufichat` on every push to `fork/main` *and* on every `nufi-v*` tag. A "release" is: merge `develop` → `fork/main`, then tag the resulting commit.

## Preconditions to verify before doing anything

Fail fast with a clear message if any of these aren't true:

1. **In the right repo.** `git remote get-url origin` ends in `dudaji-vn/nufichat.git` (or its old name `LibreChat.git` if not yet renamed).
2. **Working tree clean.** `git status --porcelain` is empty. If it's not, stop — ask whether to stash or commit first.
3. **`develop` and `fork/main` exist locally and on `origin`.** If a local branch is missing, fetch and create the tracking branch.
4. **All target PRs are merged into `develop`.** Run `gh pr list --repo dudaji-vn/nufichat --base develop --state open` and surface any open PRs the user might still want to land before the release. Don't block — just confirm with the user that they're intentionally leaving those out.

## Steps

Execute in order. After each, briefly tell the user what just happened.

### 1. Decide the version

- If the user passed a version arg (`v0.0.5` or `0.0.5`), use it. Strip a leading `v` if present, then prepend `nufi-v` to form the tag (e.g. `nufi-v0.0.5`).
- Otherwise auto-bump the patch:
  ```bash
  git fetch origin --tags --quiet
  git tag -l 'nufi-v*' --sort=-v:refname | head -1
  ```
  Take the highest existing tag (e.g. `nufi-v0.0.4`), bump the patch (`0.0.4` → `0.0.5`), confirm the chosen tag with the user before proceeding.
- Refuse to proceed if the target tag already exists locally or on the remote.

### 2. Sync `develop`

```bash
git switch develop
git pull origin develop
```

Show the user the new HEAD short-sha and the most recent merge commit subject.

### 3. Sync `fork/main` and compute the release diff

```bash
git switch fork/main
git pull origin fork/main
git log --oneline fork/main..develop
```

Show that log to the user — it's the changelog of this release. If the list is empty, stop: there's nothing to release.

### 4. Merge `develop` → `fork/main`

Use `--no-ff` so the merge commit is preserved as a release boundary. The commit body should summarize the PRs being shipped — derive them from the `fork/main..develop` log (`Merge pull request #N from …` subjects).

```bash
git merge develop --no-ff -m "🔀 merge: develop → fork/main for <tag> release

Brings in:
- <bullet per PR or commit summary>"
```

If merge has conflicts, **stop and surface them** — never auto-resolve. The user almost always wants to inspect `.github/workflows/*` conflicts in particular (the workflow file diverged once before with the `npuops/main` → `fork/main` rename).

### 5. Push `fork/main`

```bash
git push origin fork/main
```

This fires the `build-image.yml` workflow for the branch push. Mention the run will publish `ghcr.io/dudaji-vn/nufichat:main` and `:sha-<short>`.

### 6. Tag and push

```bash
git tag -a <tag> -m "Release <tag>

- <PR / changelog bullets>"
git push origin <tag>
```

This fires a second workflow run for the tag push, publishing `ghcr.io/dudaji-vn/nufichat:<version>` (without the `nufi-` prefix per the `type=match,pattern=nufi-(v.+),group=1` rule in the workflow) and `:latest`.

### 7. Verify CI fired

```bash
gh run list --repo dudaji-vn/nufichat --workflow build-image.yml --limit 4
```

Both runs (branch push + tag push) should appear as `queued` or `in_progress`. Tell the user the run IDs and the resulting image tags.

## Final report

End with a compact summary the user can paste into a release note. Include:

- The new tag and the merge commit short-sha on `fork/main`
- The list of PRs / commits shipped
- The two CI run IDs and their image-tag outputs
- ETA based on the previous tagged build (look it up if you don't know — `gh run list --workflow build-image.yml --status success --limit 1 --json durationMs` or eyeball the prior runtime)

## Guardrails

- **Never force-push `fork/main`** or any release tag. If something is wrong after the push, cut a new patch release rather than rewriting history.
- **Never delete a `nufi-v*` tag** without explicit user confirmation — published GHCR images reference these tags.
- **Don't bypass hooks** (`--no-verify`, `--no-gpg-sign`) on the merge or tag commits.
- If the user asks to release directly from a feature branch (skipping `develop`), refuse and explain the flow — features land on `develop` first so the integration is testable before it hits production.

## Related memory

If memory contains `feedback-release-flow` (the release flow rule), treat this skill as the executable version of that rule.

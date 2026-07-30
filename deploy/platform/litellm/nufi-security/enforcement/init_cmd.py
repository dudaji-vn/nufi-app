"""``nufi-egress init`` quick-start command (patch90 + CMP-341).

Initializes NuFi in a new project directory — generating config files,
.nufiignore, and optionally a pre-commit hook.

v0.7.6 additions (CMP-341):
  - ``nufi.yaml`` — 스캔 설정 (exclude 패턴, 정책, 포맷)
  - ``.pre-commit-config.yaml`` — pre-commit hook 추가 (이미 있으면 nufi 훅만 append)
  - ``.github/workflows/nufi-scan.yml`` — GitHub Actions CI 워크플로우
  - ``--ci github|gitlab`` — CI 플랫폼별 설정 자동 생성
  - ``--dry-run`` — 생성될 파일 미리보기
  - ``--default`` — 인터랙티브 프롬프트 없이 기본값 사용

Idempotent: running twice does not overwrite existing configs.
"""
from __future__ import annotations

import os
import stat
import textwrap
from pathlib import Path
from typing import List, Optional


# ---------------------------------------------------------------------------
# Template contents (minimal but functional defaults)
# ---------------------------------------------------------------------------

_POLICY_YAML = textwrap.dedent("""\
    # NuFi Egress Policy — default template
    # Entity-level actions: block | redact | pseudonymize | warn | allow
    version: 1

    default_action: warn
    blocking_actions: [block]

    entities:
      # Strong PII — block by default
      KR_RRN:            { action: block, severity: critical }
      CREDIT_CARD:       { action: block, severity: critical }
      SECRET:            { action: block, severity: critical }

      # Weak PII — pseudonymize
      KR_PHONE:          { action: pseudonymize, severity: medium }
      EMAIL:             { action: pseudonymize, severity: low }
      KR_PERSON:         { action: pseudonymize, severity: medium }
""")

_PII_ROUTING_YAML = textwrap.dedent("""\
    # PII Routing — default template
    # Routes requests containing PII to a local model.
    enabled: true
    local_model: nufi-local
    cloud_model: nufi-cloud
    fail_closed: true
    force_local_entities: null
    check_injection: false
""")

_INJECTION_PATTERNS_YAML = textwrap.dedent("""\
    # Custom injection patterns (append to built-in patterns).
    # Each entry: { id, pattern, severity, description }
    # severity: low | medium | high | critical
    patterns: []
""")

_NUFIIGNORE = textwrap.dedent("""\
    # .nufiignore — files/dirs excluded from NuFi scanning
    # Uses gitignore-style glob patterns.

    # Version control
    .git/

    # Dependencies
    node_modules/
    venv/
    .venv/
    __pycache__/

    # Build artifacts
    dist/
    build/
    *.egg-info/

    # Logs and temp
    logs/
    *.log
    *.tmp

    # Binaries and media
    *.png
    *.jpg
    *.gif
    *.pdf
    *.zip
    *.tar.gz
""")

_PRE_COMMIT_HOOK = textwrap.dedent("""\
    #!/usr/bin/env bash
    # NuFi pre-commit hook — scans staged files for PII leaks.
    # Installed by: nufi-egress init --install-hook

    set -e

    # Collect staged files (added/modified)
    FILES=$(git diff --cached --name-only --diff-filter=ACM)
    if [ -z "$FILES" ]; then
        exit 0
    fi

    echo "[nufi] Scanning staged files for PII..."
    nufi-egress scan . --fail-on-pii --pattern "$(echo $FILES | tr ' ' ',')" 2>/dev/null
    STATUS=$?
    if [ $STATUS -ne 0 ]; then
        echo "[nufi] PII detected in staged files. Commit blocked."
        echo "[nufi] Run 'nufi-egress scan .' to see details."
        exit 1
    fi
""")

# ---------------------------------------------------------------------------
# v0.7.6 templates (CMP-341)
# ---------------------------------------------------------------------------

_NUFI_YAML = textwrap.dedent("""\
    # nufi.yaml — NuFi 프로젝트 스캔 설정
    # 이 파일은 nufi-egress init 에 의해 생성되었습니다.
    version: 1

    scan:
      # 스캔 제외 패턴 (gitignore 스타일)
      exclude:
        - "*.pyc"
        - "__pycache__/"
        - ".git/"
        - "node_modules/"
        - "venv/"
        - ".venv/"
        - "dist/"
        - "build/"
        - "*.egg-info/"
        - "*.log"
        - "*.png"
        - "*.jpg"
        - "*.pdf"
        - "*.zip"

      # 스캔 대상 확장자 (비어 있으면 전체)
      include_extensions: []

      # 최대 파일 크기 (bytes, 0=무제한)
      max_file_size: 1048576

    policy:
      # 정책 파일 경로 (상대 경로)
      path: config/policy.yaml

    output:
      # 출력 포맷: text | json | sarif
      format: text
      # 컬러 출력
      color: true
""")

_PRE_COMMIT_CONFIG_YAML = textwrap.dedent("""\
    # .pre-commit-config.yaml — NuFi PII 스캔 pre-commit hook
    # See https://pre-commit.com for more information
    repos:
      - repo: local
        hooks:
          - id: nufi-scan
            name: NuFi PII Scan
            entry: nufi-egress scan . --fail-on-pii
            language: system
            pass_filenames: false
            always_run: true
""")

_PRE_COMMIT_NUFI_HOOK_ENTRY = textwrap.dedent("""\
      - repo: local
        hooks:
          - id: nufi-scan
            name: NuFi PII Scan
            entry: nufi-egress scan . --fail-on-pii
            language: system
            pass_filenames: false
            always_run: true
""")

_GITHUB_ACTIONS_WORKFLOW = textwrap.dedent("""\
    # .github/workflows/nufi-scan.yml — NuFi PII 스캔 CI 워크플로우
    # Generated by: nufi-egress init --ci github
    name: NuFi PII Scan

    on:
      pull_request:
        branches: [main, master]
      push:
        branches: [main, master]

    jobs:
      nufi-scan:
        runs-on: ubuntu-latest
        steps:
          - uses: actions/checkout@v4

          - name: Set up Python
            uses: actions/setup-python@v5
            with:
              python-version: "3.10"

          - name: Install NuFi
            run: pip install nufi-egress

          - name: Run NuFi Guard (CI mode)
            run: nufi-egress guard --ci
""")

_GITLAB_CI_YAML = textwrap.dedent("""\
    # .gitlab-ci.yml — NuFi PII 스캔 CI 파이프라인
    # Generated by: nufi-egress init --ci gitlab

    nufi-scan:
      stage: test
      image: python:3.10-slim
      before_script:
        - pip install nufi-egress
      script:
        - nufi-egress guard --ci
      rules:
        - if: '$CI_PIPELINE_SOURCE == "merge_request_event"'
        - if: '$CI_COMMIT_BRANCH == "main"'
        - if: '$CI_COMMIT_BRANCH == "master"'
""")


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def run_init(
    target_dir: str = ".",
    install_hook: bool = False,
    ci: Optional[str] = None,
    dry_run: bool = False,
) -> dict:
    """Initialize NuFi config in *target_dir*.

    Returns a dict with keys:
      created: list of files created
      skipped: list of files that already existed
      errors:  list of error messages (if any)
      dry_run: bool — True if dry-run mode
    """
    root = Path(target_dir).resolve()
    config_dir = root / "config"

    files_to_create = [
        (config_dir / "policy.yaml", _POLICY_YAML),
        (config_dir / "pii_routing.yaml", _PII_ROUTING_YAML),
        (config_dir / "injection_patterns.yaml", _INJECTION_PATTERNS_YAML),
        (root / ".nufiignore", _NUFIIGNORE),
        (root / "nufi.yaml", _NUFI_YAML),
    ]

    # .pre-commit-config.yaml: append nufi hook if exists, create new otherwise
    pre_commit_path = root / ".pre-commit-config.yaml"
    pre_commit_append = False
    if pre_commit_path.exists():
        existing = pre_commit_path.read_text(encoding="utf-8")
        if "nufi-scan" in existing:
            # Already has nufi hook — skip
            files_to_create.append((pre_commit_path, None))  # mark as skip
        else:
            pre_commit_append = True
    else:
        files_to_create.append((pre_commit_path, _PRE_COMMIT_CONFIG_YAML))

    # CI workflow
    if ci == "github":
        gh_dir = root / ".github" / "workflows"
        files_to_create.append((gh_dir / "nufi-scan.yml", _GITHUB_ACTIONS_WORKFLOW))
    elif ci == "gitlab":
        files_to_create.append((root / ".gitlab-ci.yml", _GITLAB_CI_YAML))

    created: List[str] = []
    skipped: List[str] = []
    errors: List[str] = []

    if dry_run:
        # Preview mode: just list what would be created
        for path, content in files_to_create:
            if content is None:
                skipped.append(str(path.relative_to(root)))
            elif path.exists():
                skipped.append(str(path.relative_to(root)))
            else:
                created.append(str(path.relative_to(root)))
        if pre_commit_append:
            created.append(str(pre_commit_path.relative_to(root)) + " (append nufi hook)")
        if install_hook:
            hook_path = _find_git_hook_path(root)
            if hook_path is None:
                errors.append("pre-commit hook: not a git repository (no .git found)")
            elif hook_path.exists():
                skipped.append(str(hook_path.relative_to(root)))
            else:
                created.append(str(hook_path.relative_to(root)))
        return {"created": created, "skipped": skipped, "errors": errors, "dry_run": True}

    # Ensure config directory exists
    config_dir.mkdir(parents=True, exist_ok=True)

    for path, content in files_to_create:
        if content is None:
            skipped.append(str(path.relative_to(root)))
            continue
        if path.exists():
            skipped.append(str(path.relative_to(root)))
        else:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
                created.append(str(path.relative_to(root)))
            except OSError as e:
                errors.append(f"{path.relative_to(root)}: {e}")

    # Append nufi hook to existing .pre-commit-config.yaml
    if pre_commit_append:
        try:
            with open(pre_commit_path, "a", encoding="utf-8") as f:
                f.write("\n" + _PRE_COMMIT_NUFI_HOOK_ENTRY)
            created.append(str(pre_commit_path.relative_to(root)) + " (append nufi hook)")
        except OSError as e:
            errors.append(f".pre-commit-config.yaml append: {e}")

    # Pre-commit hook (git hooks)
    if install_hook:
        hook_path = _find_git_hook_path(root)
        if hook_path is None:
            errors.append("pre-commit hook: not a git repository (no .git found)")
        elif hook_path.exists():
            skipped.append(str(hook_path.relative_to(root)))
        else:
            try:
                hook_path.parent.mkdir(parents=True, exist_ok=True)
                hook_path.write_text(_PRE_COMMIT_HOOK, encoding="utf-8")
                hook_path.chmod(hook_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
                created.append(str(hook_path.relative_to(root)))
            except OSError as e:
                errors.append(f"pre-commit hook: {e}")

    return {"created": created, "skipped": skipped, "errors": errors, "dry_run": False}


def _find_git_hook_path(root: Path) -> "Path | None":
    """Locate .git/hooks/pre-commit, handling worktrees."""
    git_dir = root / ".git"
    if git_dir.is_file():
        # git worktree — .git is a file pointing to actual git dir
        text = git_dir.read_text().strip()
        if text.startswith("gitdir:"):
            git_dir = Path(text.split(":", 1)[1].strip())
            if not git_dir.is_absolute():
                git_dir = (root / git_dir).resolve()
    if not git_dir.is_dir():
        return None
    return git_dir / "hooks" / "pre-commit"


def render_result(result: dict) -> str:
    """Human-readable summary of init result."""
    lines: List[str] = []
    prefix = "[dry-run] " if result.get("dry_run") else ""
    if result["created"]:
        lines.append(f"{prefix}{'Would create:' if result.get('dry_run') else 'Created:'}")
        for f in result["created"]:
            lines.append(f"  + {f}")
    if result["skipped"]:
        lines.append(f"{prefix}{'Would skip:' if result.get('dry_run') else 'Skipped (already exist):'}")
        for f in result["skipped"]:
            lines.append(f"  ~ {f}")
    if result["errors"]:
        lines.append("Errors:")
        for e in result["errors"]:
            lines.append(f"  ! {e}")
    if not lines:
        lines.append("Nothing to do.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI entry point (called from enforcement.cli)
# ---------------------------------------------------------------------------

def cmd_quickstart_init(args) -> int:
    """Handle `nufi-egress init` quick-start subcommand."""
    target = getattr(args, "dir", ".") or "."
    install_hook = getattr(args, "install_hook", False)
    ci = getattr(args, "ci", None)
    dry_run = getattr(args, "dry_run", False)

    result = run_init(target_dir=target, install_hook=install_hook, ci=ci, dry_run=dry_run)
    print(render_result(result))

    return 1 if result["errors"] else 0

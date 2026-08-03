"""``nufi-egress completions`` — shell completion script generation (patch109).

Usage:
  eval "$(nufi-egress completions bash)"
  eval "$(nufi-egress completions zsh)"
"""
from __future__ import annotations


# Canonical list of subcommands and their common flags.
SUBCOMMANDS: dict[str, list[str]] = {
    "scan":      ["--target", "--pattern", "--check-injection", "--json", "--format",
                  "--output", "--exclude", "--fail-on-pii", "--redact", "--dry-run",
                  "--no-backup", "--stats", "--parallel", "--profile",
                  "--summary-only", "--git-staged"],
    "route":     ["--text", "--file", "--stdin", "--summary", "--model",
                  "--local-model", "--cloud-model", "--check-injection",
                  "--min-severity", "--json"],
    "inspect":   ["--text", "--file", "--json"],
    "diff":      ["--base", "--fail-on-pii", "--check-injection", "--json"],
    "watch":     ["--interval", "--check-injection", "--pattern", "--once", "--webhook"],
    "init":      ["--list", "--dir", "--install-hook", "--out", "--base-dir",
                  "--set", "--force", "--dry-run"],
    "config":    [],
    "explain":   ["--text", "--json", "--min-severity"],
    "doctor":    ["--ner-backend", "--connect-timeout", "--json", "--no-json"],
    "version":   [],
    "report":    [],
    "benchmark": ["--only", "--json", "--json-out"],
    "stats":       ["--json"],
    "completions": ["bash", "zsh"],
    "serve":     ["--host", "--port", "--openapi"],
    "compare":   ["--json", "--format"],
    "pipeline":  ["--config", "--json", "--dry-run"],
    "playground": [],
    "lint":      ["--fix", "--json", "--config"],
    "generate":  ["--template", "--output", "--force"],
    "history":   ["--json", "--limit"],
    "summary":   ["--json", "--format"],
    "test":      ["--pattern", "--json", "--verbose"],
}

SUBCOMMAND_NAMES = sorted(SUBCOMMANDS.keys())


def _bash_script() -> str:
    cmds = " ".join(SUBCOMMAND_NAMES)
    # Per-subcommand flag completions
    cases = []
    for name, flags in sorted(SUBCOMMANDS.items()):
        if flags:
            cases.append(f'        {name})\n'
                         f'            COMPREPLY=( $(compgen -W "{" ".join(flags)}" -- "$cur") )\n'
                         f'            return 0\n'
                         f'            ;;')
    case_block = "\n".join(cases)

    return f'''\
# bash completion for nufi-egress  (patch109)
_nufi_egress_completions() {{
    local cur prev words cword
    _init_completion || return

    if [[ ${{cword}} -eq 1 ]]; then
        COMPREPLY=( $(compgen -W "{cmds}" -- "$cur") )
        return 0
    fi

    local subcmd="${{words[1]}}"
    case "$subcmd" in
{case_block}
    esac
}}
complete -F _nufi_egress_completions nufi-egress
complete -F _nufi_egress_completions nufi
'''


def _zsh_script() -> str:
    cmds_desc = []
    for name in SUBCOMMAND_NAMES:
        cmds_desc.append(f"        '{name}:nufi-egress {name}'")
    cmds_block = "\n".join(cmds_desc)

    # Per-subcommand flag completions
    cases = []
    for name, flags in sorted(SUBCOMMANDS.items()):
        if flags:
            flag_list = " ".join(f"'{f}'" for f in flags)
            cases.append(f'        {name})\n'
                         f'            _arguments {flag_list}\n'
                         f'            ;;')
    case_block = "\n".join(cases)

    return f'''\
#compdef nufi-egress nufi
# zsh completion for nufi-egress  (patch109)
_nufi_egress() {{
    local -a subcmds
    subcmds=(
{cmds_block}
    )

    if (( CURRENT == 2 )); then
        _describe 'subcommand' subcmds
        return
    fi

    local subcmd="${{words[2]}}"
    case "$subcmd" in
{case_block}
    esac
}}
_nufi_egress "$@"
'''


def generate(shell: str) -> str:
    """Return completion script for the given shell."""
    if shell == "bash":
        return _bash_script()
    if shell == "zsh":
        return _zsh_script()
    raise ValueError(f"Unsupported shell: {shell!r}  (supported: bash, zsh)")


def cmd_completions(args) -> int:
    """CLI handler for ``nufi-egress completions {bash|zsh}``."""
    print(generate(args.shell))
    return 0

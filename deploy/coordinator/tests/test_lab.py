"""Static checks on deploy/coordinator/lab — the NAT lab topology.

`lab/run.sh` is the real proof; it needs Docker, four minutes and two builds.
This file guards the parts of the lab that can go quietly wrong between runs:
the topology (subnets, isolation, capabilities, which service shares whose
network namespace), the pins, and the two contracts run.sh offers a caller
(`bash -n` clean, and `--dry-run` prints the plan without touching anything).

No Docker daemon needed — `docker compose config` only needs the CLI.

Run: cd deploy/coordinator && python3 -m pytest tests -q
"""

import json
import os
import pathlib
import subprocess

import pytest

COORD = pathlib.Path(__file__).resolve().parents[1]
LAB = COORD / "lab"
BASH = "/bin/bash"  # macOS ships 3.2 here; run.sh must run under it


def render():
    """`docker compose config` for the lab project, as run.sh invokes it."""
    out = subprocess.run(
        ["docker", "compose", "-f", str(LAB / "docker-compose.yml"), "config", "--format", "json"],
        cwd=str(LAB),
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(out.stdout)


def run_sh(*args, env_overrides=None):
    env = dict(os.environ)
    if env_overrides:
        env.update(env_overrides)
    return subprocess.run(
        [BASH, str(LAB / "run.sh"), *args],
        cwd=str(LAB),
        env=env,
        capture_output=True,
        text=True,
    )


@pytest.fixture(scope="module")
def cfg():
    return render()


# ---------------------------------------------------------------------------
# The project and its services
# ---------------------------------------------------------------------------


def test_project_name_cannot_collide_with_the_box_or_a_real_coordinator(cfg):
    # A developer Mac runs deploy/box as `nufi-box` and may run a real
    # coordinator as `nufi-coordinator`; the lab must never share a container,
    # network or volume with either.
    assert cfg["name"] == "nufi-lab"


def test_the_lab_is_the_real_coordinator_plus_the_lab_only_services(cfg):
    assert set(cfg["services"]) == {
        # included verbatim from ../docker-compose.yml
        "headscale",
        "caddy",
        # the lab's own
        "router-a",
        "router-b",
        "node-a",
        "node-b",
        "tools-a",
        "box-caddy",
        "box-samba",
    }


def test_images_are_pinned(cfg):
    svcs = cfg["services"]
    assert svcs["headscale"]["image"] == "ghcr.io/juanfont/headscale:v0.29.3"
    assert svcs["node-a"]["image"] == "tailscale/tailscale:v1.102.3"
    assert svcs["node-b"]["image"] == "tailscale/tailscale:v1.102.3"
    assert svcs["box-caddy"]["image"] == "caddy:2.10.0-alpine"
    # Same SMB server the box itself runs (deploy/box/docker-compose.linux.yml),
    # not a lookalike.
    assert svcs["box-samba"]["image"] == "ghcr.io/servercontainers/samba:a3.24.1-s4.23.8-r0"
    for name, svc in svcs.items():
        assert not svc["image"].endswith(":latest"), name


def test_every_service_restarts_and_has_a_healthcheck(cfg):
    for name, svc in cfg["services"].items():
        assert svc.get("restart") == "unless-stopped", name
        assert "healthcheck" in svc, name


# ---------------------------------------------------------------------------
# Topology
# ---------------------------------------------------------------------------


def _subnet(cfg, net):
    return cfg["networks"][net]["ipam"]["config"][0]["subnet"]


def test_three_networks_with_the_documented_subnets(cfg):
    assert _subnet(cfg, "wan") == "172.30.0.0/24"
    assert _subnet(cfg, "lan-a") == "10.10.0.0/24"
    assert _subnet(cfg, "lan-b") == "10.20.0.0/24"


def test_neither_lan_can_reach_the_world_except_through_its_router(cfg):
    # The isolation is `enable_ip_masquerade: "false"`, NOT `internal: true`.
    # Docker implements `internal` as a host-side rule dropping any frame
    # arriving on the bridge whose destination is outside the subnet, and with
    # br_netfilter loaded that applies to container-to-container frames on the
    # same bridge too — so a node's packet to its own router's WAN address is
    # dropped before the router sees it and nothing can ever leave. Without the
    # per-bridge masquerade the host will not translate these addresses, and
    # docker's own inter-bridge isolation already keeps them off `wan`, so the
    # only packets that get out are the ones the router re-emits on its WAN leg.
    for lan in ("lan-a", "lan-b"):
        opts = cfg["networks"][lan].get("driver_opts", {})
        assert opts.get("com.docker.network.bridge.enable_ip_masquerade") == "false", lan
        assert not cfg["networks"][lan].get("internal"), lan
    assert not cfg["networks"]["wan"].get("internal")


def test_each_node_sits_on_its_own_lan_only(cfg):
    assert list(cfg["services"]["node-a"]["networks"]) == ["lan-a"]
    assert list(cfg["services"]["node-b"]["networks"]) == ["lan-b"]
    assert cfg["services"]["node-a"]["networks"]["lan-a"]["ipv4_address"] == "10.10.0.3"
    assert cfg["services"]["node-b"]["networks"]["lan-b"]["ipv4_address"] == "10.20.0.3"


def test_each_router_straddles_the_wan_and_one_lan(cfg):
    a = cfg["services"]["router-a"]["networks"]
    b = cfg["services"]["router-b"]["networks"]
    assert set(a) == {"wan", "lan-a"} and set(b) == {"wan", "lan-b"}
    assert a["wan"]["ipv4_address"] == "172.30.0.11"
    assert b["wan"]["ipv4_address"] == "172.30.0.12"
    # The LAN legs are the default gateways the node entrypoints install.
    assert a["lan-a"]["ipv4_address"] == "10.10.0.2"
    assert b["lan-b"]["ipv4_address"] == "10.20.0.2"


def test_routers_can_route(cfg):
    for name in ("router-a", "router-b"):
        svc = cfg["services"][name]
        assert svc["cap_add"] == ["NET_ADMIN"], name
        assert svc["sysctls"]["net.ipv4.ip_forward"] == "1", name


def test_force_relay_reaches_both_routers(cfg):
    # run.sh sets LAB_FORCE_RELAY; the routers read FORCE_RELAY.
    for name in ("router-a", "router-b"):
        env = cfg["services"][name]["environment"]
        assert env["FORCE_RELAY"] == "0", name  # default when the var is unset
        assert env["STUN_PORT"] == "3478", name


def test_nodes_run_tailscale_in_kernel_mode(cfg):
    # Userspace mode would leave the container's own curl and smbclient off the
    # mesh, which is the whole thing the lab has to prove.
    for name in ("node-a", "node-b"):
        svc = cfg["services"][name]
        assert set(svc["cap_add"]) == {"NET_ADMIN", "NET_RAW"}, name
        assert [d["target"] for d in svc["devices"]] == ["/dev/net/tun"], name
        assert svc["environment"]["TS_USERSPACE"] == "false", name
        assert svc["environment"]["TS_ACCEPT_DNS"] == "true", name
        assert svc["environment"]["TS_STATE_DIR"] == "/var/lib/tailscale", name


def test_nodes_dial_the_lab_coordinator_and_trust_its_internal_ca(cfg):
    for name in ("node-a", "node-b"):
        env = cfg["services"][name]["environment"]
        assert "--login-server=https://coordinator.lab" in env["TS_EXTRA_ARGS"], name
        assert env["SSL_CERT_FILE"] == "/lab/keys/coordinator-ca.crt", name
        assert cfg["services"][name]["extra_hosts"] == ["coordinator.lab=172.30.0.10"], name


def test_nodes_do_not_advertise_tags(cfg):
    # headscale v0.29.3 rejects RequestTags for ANY pre-auth-key registration
    # (hscontrol/state/state.go: "PreAuthKey nodes get their tags from the key
    # itself, not from client requests"), with "requested tags [...] are
    # invalid or not permitted" regardless of tagOwners. The tag comes from
    # `preauthkeys create --tags`, which run.sh does.
    for name in ("node-a", "node-b"):
        assert "--advertise-tags" not in cfg["services"][name]["environment"]["TS_EXTRA_ARGS"], name


def test_the_box_stand_in_is_named_nufi_so_magicdns_gives_it_the_real_name(cfg):
    assert cfg["services"]["node-b"]["hostname"] == "nufi"
    assert "--hostname=nufi" in cfg["services"]["node-b"]["environment"]["TS_EXTRA_ARGS"]
    assert cfg["services"]["box-caddy"]["environment"]["BOX_MESH_HOST"] == "nufi.box.lab"


# ---------------------------------------------------------------------------
# Network namespaces
# ---------------------------------------------------------------------------


def test_the_member_tools_live_in_node_as_namespace(cfg):
    # curl and smbclient must use node-a's mesh address and routes, not a
    # docker bridge of their own.
    assert cfg["services"]["tools-a"]["network_mode"] == "service:node-a"
    assert "networks" not in cfg["services"]["tools-a"]


def test_the_box_services_live_in_node_bs_namespace(cfg):
    for name in ("box-caddy", "box-samba"):
        assert cfg["services"][name]["network_mode"] == "service:node-b", name
        assert "networks" not in cfg["services"][name], name


def test_the_lab_generates_nothing_outside_lab(cfg):
    # A lab run must not overwrite the rendered config of a real coordinator
    # sharing this machine (deploy/coordinator/tests asserts nothing but
    # bootstrap.sh ever writes there), so the lab reads its config from
    # lab/rendered/ instead.
    sources = [
        v["source"] for svc in ("headscale", "caddy") for v in cfg["services"][svc]["volumes"] if v["type"] == "bind"
    ]
    for src in sources:
        assert str(LAB) in src or src.endswith("/config/policy.hujson"), src
    assert any(src.endswith("/lab/rendered/headscale.yaml") for src in sources)
    assert any(src.endswith("/lab/rendered/Caddyfile") for src in sources)


def test_the_lab_mounts_the_same_things_the_coordinator_does():
    # coordinator.lab.yml replaces the two volume lists outright (`!override`),
    # so a mount added to ../docker-compose.yml would silently not reach the
    # lab. Compare the targets, which is what the containers actually care
    # about; only the two rendered-config *sources* are allowed to differ.
    base = json.loads(
        subprocess.run(
            ["docker", "compose", "-f", str(COORD / "docker-compose.yml"), "config", "--format", "json"],
            cwd=str(COORD),
            env={**os.environ, "MESH_SERVER_HOST": "x.example", "TLS_MODE": "internal", "ACME_EMAIL": ""},
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    )
    lab = render()
    for svc in ("headscale", "caddy"):
        base_targets = sorted(v["target"] for v in base["services"][svc]["volumes"])
        lab_targets = sorted(v["target"] for v in lab["services"][svc]["volumes"])
        assert base_targets == lab_targets, svc


def test_caddy_shares_headscales_namespace_so_the_coordinator_is_one_address(cfg):
    # 443/tcp (control + DERP) and 3478/udp (STUN) must answer on the single
    # address headscale puts in its DERP map, exactly as a VPS does.
    assert cfg["services"]["caddy"]["network_mode"] == "service:headscale"
    assert "networks" not in cfg["services"]["caddy"]
    assert cfg["services"]["headscale"]["networks"]["wan"]["ipv4_address"] == "172.30.0.10"


# ---------------------------------------------------------------------------
# Host ports
# ---------------------------------------------------------------------------


def test_the_lab_only_publishes_ports_the_developer_mac_has_free(cfg):
    published = set()
    for name, svc in cfg["services"].items():
        for p in svc.get("ports", []):
            published.add((str(p["published"]), p["protocol"]))
    # 8443 (Caddy) and 13478 (STUN) for the operator's own debugging; nothing
    # else. 80/443 would collide with deploy/box's Caddy, 8080 with the usual
    # dev servers, 445 and 3080 with the box's SMB and chat.
    assert published == {("8443", "tcp"), ("13478", "udp")}


def test_the_box_stand_in_publishes_nothing(cfg):
    # It is reachable over the mesh or not at all.
    for name in ("box-caddy", "box-samba", "node-a", "node-b", "tools-a"):
        assert not cfg["services"][name].get("ports"), name


# ---------------------------------------------------------------------------
# run.sh
# ---------------------------------------------------------------------------


def test_run_sh_is_bash_3_2_clean():
    r = subprocess.run([BASH, "-n", str(LAB / "run.sh")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_the_shell_helpers_are_bash_3_2_clean():
    for script in ("router/entrypoint.sh", "node/entrypoint.sh", "tools/entrypoint.sh"):
        r = subprocess.run(["/bin/sh", "-n", str(LAB / script)], capture_output=True, text=True)
        assert r.returncode == 0, f"{script}: {r.stderr}"


def test_dry_run_prints_the_plan_and_touches_nothing():
    before = sorted(p.name for p in LAB.iterdir())
    r = run_sh("--dry-run")
    assert r.returncode == 0, r.stderr
    out = r.stdout
    assert "NAT lab plan" in out
    assert "nufi-lab" in out
    for fragment in (
        "172.30.0.0/24",
        "10.10.0.0/24",
        "10.20.0.0/24",
        "coordinator.lab",
        "nufi.box.lab",
        "docker compose up -d node-a node-b",
        "tailscale ping",
        "smbclient",
    ):
        assert fragment in out, fragment
    # No keys minted, no rendered config, no containers: the directory listing
    # is unchanged and nothing was written into deploy/coordinator either.
    assert sorted(p.name for p in LAB.iterdir()) == before


def test_dry_run_reports_the_flags_it_was_given():
    plain = run_sh("--dry-run").stdout
    forced = run_sh("--dry-run", "--force-relay", "--keep").stdout
    assert "force-relay         0" in plain and "keep stack up       0" in plain
    assert "force-relay         1" in forced and "keep stack up       1" in forced


def test_unknown_arguments_are_refused():
    r = run_sh("--nope")
    assert r.returncode != 0
    assert "unknown argument" in r.stderr


def test_help_describes_the_table_it_prints():
    r = run_sh("--help")
    assert r.returncode == 0
    for check in ("join-a", "join-b", "path", "http-over-mesh", "smb-round-trip"):
        assert check in r.stdout, check


# ---------------------------------------------------------------------------
# day-at-home.sh
#
# The end-to-end harness needs a real box in a Lima VM, so CI can only guard
# the same two contracts it guards for run.sh: it parses under macOS bash 3.2,
# and --dry-run prints its plan without touching anything.
# ---------------------------------------------------------------------------


def day_at_home(*args):
    return subprocess.run(
        [BASH, str(LAB / "day-at-home.sh"), *args],
        cwd=str(LAB),
        env=dict(os.environ),
        capture_output=True,
        text=True,
    )


def test_day_at_home_is_bash_3_2_clean():
    r = subprocess.run([BASH, "-n", str(LAB / "day-at-home.sh")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_day_at_home_dry_run_prints_the_plan_and_touches_nothing():
    before = sorted(p.name for p in LAB.iterdir())
    r = day_at_home("--dry-run")
    assert r.returncode == 0, r.stderr
    out = r.stdout
    for fragment in (
        "nufi-lab",
        "nufi-ubuntu",          # the box is the VM, not a stand-in
        "FORCE_RELAY=1",        # the relay is not optional in this run
        "host-ports.yml",       # 443 + 3478 come from a generated override
        "NOT down -v",          # the node registrations have to survive
        "nufi-box mesh up",
        "disk floor",
    ):
        assert fragment in out, fragment
    # The generated override, the rendered config and the keys all come later:
    # --dry-run must not have created any of them.
    assert sorted(p.name for p in LAB.iterdir()) == before


def test_day_at_home_names_a_probe_that_is_new_every_run():
    """The fixed `contract.txt` made two of the eight rows unable to fail.

    `drive-write` gated on `test -s` at a path nothing ever removes, so a `put`
    refused with NT_STATUS_ACCESS_DENIED still found the previous run's file
    there; `drive-ingested` grepped a container log that survives a restart, so
    it matched the line an earlier run earned (the third acceptance run's
    `PASS (0s)`). Both are answered by the same thing: a probe belonging to
    this run alone.
    """
    first = day_at_home("--dry-run").stdout
    second = day_at_home("--dry-run").stdout
    probes = []
    for out in (first, second):
        line = next(l for l in out.splitlines() if l.strip().startswith("the probe"))
        probes.append(line.split()[2])   # "the probe   legal/contract-….txt  (…"
    assert all(p.startswith("legal/contract-") and p.endswith(".txt") for p in probes), probes
    assert probes[0] != probes[1], "two runs must not share a probe file"


def test_day_at_home_reports_the_routine_it_will_run():
    assert "routine             weekly" in day_at_home("--dry-run").stdout
    assert "routine             meeting" in day_at_home("--dry-run", "--routine", "meeting").stdout


def test_day_at_home_refuses_an_unknown_argument():
    r = day_at_home("--nope")
    assert r.returncode != 0
    assert "unknown argument" in r.stderr


def test_day_at_home_help_lists_the_checks_it_gates_on():
    r = day_at_home("--help")
    assert r.returncode == 0
    for check in ("box-on-mesh", "path", "health-over-mesh", "login-over-mesh",
                  "drive-write", "drive-ingested", "agent-cites-drive", "routine"):
        assert check in r.stdout, check


# ---------------------------------------------------------------------------
# The predicates day-at-home.sh's verdicts hang on
#
# Each is a single-line assignment in the script, extracted verbatim here and
# run for real, so what these tests pin is the string the harness uses and not
# a copy of it. Three of them replaced substring tests that could not fail:
# `grep -q 'sources: .*[^ ]'` matched run_box.py's literal `sources: none`,
# `*weekly*ok*` matched any output containing "broken", and the ingest check
# grepped the whole container log for a probe name that never changed.
# ---------------------------------------------------------------------------


def assignment(name):
    """The `name=...` line as day-at-home.sh really writes it."""
    for line in (LAB / "day-at-home.sh").read_text().splitlines():
        if line.startswith(f"{name}="):
            return line
    raise AssertionError(f"day-at-home.sh no longer defines {name} on one line")


def cited(tmp_path, body):
    """Run the shipped CITED_CMD against a box.md fixture."""
    md = tmp_path / "box.md"
    md.write_text(body)
    script = assignment("CITED_CMD") + '\nsh -c "$CITED_CMD" _ "$1"\n'
    return subprocess.run([BASH, "-c", script, "_", str(md)], capture_output=True, text=True)


# run_box.py renders `  - sources: {', '.join(q['sources']) or 'none'}`, so
# these are the two shapes it can produce.
CITED = "- **Q** → PASS (2.0 s)\n  - answer\n  - sources: 계약검토_표준조항.txt\n"
UNCITED = "- **Q** → PASS (2.0 s)\n  - answer\n  - sources: none\n"


def test_an_answer_that_names_a_file_counts_as_a_citation(tmp_path):
    r = cited(tmp_path, CITED)
    assert r.returncode == 0
    assert "계약검토_표준조항.txt" in r.stdout


def test_sources_none_is_not_a_citation(tmp_path):
    # The Critical this replaced: `grep -q 'sources: .*[^ ]'` matches this file,
    # so the one check that proves a drive document reached the agent used to
    # pass on an answer that cited nothing at all.
    r = cited(tmp_path, UNCITED)
    assert r.returncode != 0, "an answer whose only sources line is 'none' must not count"
    assert r.stdout.strip() == ""


def test_one_real_citation_among_uncited_answers_is_enough(tmp_path):
    # The recorded run's shape: four questions, two of which cited the file.
    r = cited(tmp_path, UNCITED + CITED + CITED + UNCITED)
    assert r.returncode == 0
    assert r.stdout.count("계약검토_표준조항.txt") == 2
    assert "none" not in r.stdout


def test_a_missing_evidence_file_is_not_a_citation(tmp_path):
    md = tmp_path / "box.md"
    script = assignment("CITED_CMD") + '\nsh -c "$CITED_CMD" _ "$1"\n'
    r = subprocess.run([BASH, "-c", script, "_", str(md)], capture_output=True, text=True)
    assert r.returncode != 0
    assert r.stdout.strip() == ""


# nufi-ingest writes `added <dept>/<file> → <id> (embedded=True)`
# (nufi_ingest.py:527), into a container log that survives a restart.
OLD_RUN_LOG = (
    "watching /drives every 20s\n"
    "added legal/contract-20260908-101500-1-1.txt → f-1 (embedded=True)\n"
    "added legal/계약검토_표준조항.txt → f-2 (embedded=True)\n"
)


def ingested(log, probe):
    """Run the shipped INGEST_CMD over a container log fixture."""
    script = assignment("INGEST_CMD") + '\nsh -c "$INGEST_CMD" _ "$1"\n'
    return subprocess.run([BASH, "-c", script, "_", probe],
                          input=log, capture_output=True, text=True).stdout.strip()


def test_an_earlier_runs_ingest_line_does_not_answer_for_this_run():
    # The Important this replaced. The row read PASS (0s) on the third
    # acceptance run by matching a line the second run had written: same probe
    # name, and nufi-ingest deduplicates by SHA-256 so it never writes another.
    assert ingested(OLD_RUN_LOG, "contract-20260909-131200-9-9.txt") == ""


def test_this_runs_ingest_line_is_found_in_the_whole_log():
    # Grepping all of it stays correct — a time filter would be the wrong fix,
    # since an unchanged file correctly produces no new line at all.
    new = "added legal/contract-20260909-131200-9-9.txt → f-3 (embedded=True)\n"
    line = ingested(OLD_RUN_LOG + new, "contract-20260909-131200-9-9.txt")
    assert "contract-20260909-131200-9-9.txt" in line
    assert "embedded=True" in line


def test_an_upload_that_did_not_embed_is_not_an_ingest():
    log = "added legal/contract-20260909-131200-9-9.txt → f-3 (embedded=False)\n"
    assert ingested(log, "contract-20260909-131200-9-9.txt") == ""


def smb_refused(output):
    """Run the shipped SMB_FAILED_RE over smbclient output."""
    script = assignment("SMB_FAILED_RE") + '\nprintf \'%s\\n\' "$1" | grep -qE "$SMB_FAILED_RE"\n'
    return subprocess.run([BASH, "-c", script, "_", output],
                          capture_output=True, text=True).returncode == 0


def test_the_refusal_the_acceptance_actually_hit_is_read_as_a_failure():
    # D1, verbatim from the first end-to-end run. smbclient's exit status was
    # printed and discarded, and `test -s` found the previous run's file, so
    # the row that proves the headline claim read PASS through this.
    assert smb_refused("NT_STATUS_ACCESS_DENIED opening remote file \\contract.txt")
    assert smb_refused("tree connect failed: NT_STATUS_BAD_NETWORK_NAME")


def test_a_successful_put_is_not_read_as_a_failure():
    assert not smb_refused(
        "putting file /tmp/home/contract-20260909-131200-9-9.txt as "
        "\\contract-20260909-131200-9-9.txt (12.3 kb/s) (average 12.3 kb/s)")


def routine_matches(var, flow, line):
    """Run the shipped ROUTINE_*_RE against one line of run_flows.py output."""
    script = (
        assignment(var)
        + f'\nprintf \'%s\\n\' "$1" | grep -qE "${{{var}/FLOW/{flow}}}"\n'
    )
    return subprocess.run([BASH, "-c", script, "_", line], capture_output=True, text=True).returncode == 0


# run_flows.py prints f"{name:9} {'DRIFT' if drift else 'ok   '} {secs:4.0f}s".
def test_a_finished_flow_reads_as_a_pass():
    assert routine_matches("ROUTINE_LINE_RE", "weekly", "weekly    ok      74s")
    assert routine_matches("ROUTINE_LINE_RE", "meeting", "meeting   ok       7s")


def test_a_drifted_flow_is_still_an_answer_and_is_flagged():
    assert routine_matches("ROUTINE_LINE_RE", "weekly", "weekly    DRIFT    12s")
    assert routine_matches("ROUTINE_DRIFT_RE", "weekly", "weekly    DRIFT    12s")
    assert not routine_matches("ROUTINE_DRIFT_RE", "weekly", "weekly    ok      74s")


def test_error_text_containing_ok_is_not_a_pass():
    # The Important this replaced: `*weekly*ok*` matches, because "broken"
    # contains "ok".
    assert not routine_matches("ROUTINE_LINE_RE", "weekly", "weekly result: broken pipe, no output")
    assert not routine_matches("ROUTINE_LINE_RE", "weekly", "weekly    FAIL HTTP 500  {'detail': 'broken'}")
    assert not routine_matches("ROUTINE_LINE_RE", "weekly", "NO ANSWER within 300s")
    assert not routine_matches("ROUTINE_LINE_RE", "weekly", "1/1 clean")


def test_another_flows_line_is_not_this_flows_answer():
    # The control runs `meeting`; its line must not mark `weekly` as answered.
    assert not routine_matches("ROUTINE_LINE_RE", "weekly", "meeting   ok       7s")


# ---------------------------------------------------------------------------
# Secrets
# ---------------------------------------------------------------------------


def test_keys_are_gitignored():
    r = subprocess.run(
        ["git", "check-ignore", "-q", str(LAB / "keys" / "node-a.key")],
        cwd=str(LAB),
        capture_output=True,
    )
    assert r.returncode == 0, "lab/keys/ must be gitignored — it holds pre-auth keys"


def test_no_key_material_is_committed():
    for path in LAB.rglob("*"):
        if path.is_file() and "keys" not in path.parts:
            assert path.suffix != ".key", path


def test_the_join_check_waits_the_way_every_other_wait_in_the_script_does():
    """The `online` gate replaced a check that could not fail — being LISTED
    survives between runs, because the lab keeps its headscale volume on
    purpose. It is right, and it is the one wait in this script that reads
    once: a second's lag between tailscaled holding an address and headscale's
    CLI reporting `online` turns a real join into a red row, and re-running
    costs a VM boot. Every other wait here is a bounded loop; so is this one.
    """
    code = "\n".join(
        line for line in (LAB / "day-at-home.sh").read_text().splitlines()
        if not line.lstrip().startswith("#")
    )
    assert "JOIN_TRIES=" in code and "JOIN_WAIT=" in code, (
        "the retry has to be named, so it can be read and changed without "
        "hunting through the block"
    )
    region = code[code.index("join_state="):code.index('case "$join_state"')]
    assert "JOIN_TRIES" in region and "sleep" in region, (
        "the state read must sit inside the bounded loop, not beside it"
    )

"""``nufi-egress`` CLI (CMP-94 트랙 B · 스펙 §8.1-2/5).

서브커맨드:
  version   버전 및 백엔드 정보 출력(NuFi/Python/KoELECTRA ONNX/패턴 수).
  render    집행 규칙 셋 텍스트 출력(적용 안 함, 비특권). 골든 검증·점검용.
  apply     규칙 셋 원자 적용(정적 사전 차단). root/CAP_NET_ADMIN 필요(없으면 dry-run).
  disable   킬스위치 — 전 규칙 즉시 제거(A8).
  status    현재 집행 상태(JSON).
  feedback  drop 로그(stdin/파일) → blocked_attempts 카운터 + flow 재유입.
  doctor    하이브리드 배선 1회 진단(5체크 PASS/WARN/FAIL · CMP-120).
  coverage  '내 트래픽 중 X% 게이트웨이 통과' 커버리지 보증 리포트(CMP-133).
  monitor   게이트웨이 우회 상시 모니터링/임계 알림(suppression 포함 · CMP-133).
  init      파이프라인 프리셋에서 운영 config 구체화(CMP-121, fail-closed).
  audit     비동기 감사 봇(report/daemon/once) + §4 감사로그 조회(query · CMP-141).
  targets   capture_targets.yaml 파생/조회 + BPF 필터 출력(CMP-87 캡처 레이어 · CMP-143).
  flow-tap  public 목적지 flow tap(우회 탐지) — --simulate 리플레이/--live 캡처(CMP-143).
  policy    정책 운영 자동화 — 다중 프로파일·묶기·버전/되돌리기·변경 감사(CMP-144 B1).
  report    규정준수 리포트 산출(기존 측정 재사용, 새 측정 없음 · CMP-150 C1). trends(patch149), diff(patch153), coverage-map(patch166) 포함.
  benchmark 정확도(커밋 산출물 게이트) + 가명화 품질(라이브) 벤치마크 단일 재현(CMP-201 I5).
  inspect   통합 보안 분석 — PII + 인젝션 + 라우팅 + 위험도 한 번에 출력(patch78).
  pipeline  체인 파이프라인 — detect→decide→transform→route 한 번에(patch139).
  history   최근 활동 로그 조회 — 스캔·차단·라우팅 이벤트(patch141).
  route     PII 라우팅 결정 테스트 — 텍스트의 PII 감지·모델 라우팅 판정 출력(CMP-270).
  playground 인터랙티브 PII 분석 REPL — 실시간 텍스트 분석·마스킹·리댁션 실험(patch145).
  summary   프로젝트 헬스 대시보드 — 설정·활동·위험·닥터·버전 한 화면 요약(patch147).

설치형 진입점(pyproject.toml console_scripts): ``pip install -e .`` 후 ``nufi-egress``
(별칭 ``nufi``) 로 PATH 에서 직접 실행. 레거시 ``python3 -m enforcement.cli`` 동치 유지.

예) 데모 승격: ``nufi-egress apply`` ↔ ``nufi-egress disable``.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from enforcement.applier import Applier            # noqa: E402
from enforcement.feedback import DropFeedback       # noqa: E402
from enforcement.rule_builder import load_enforcement_config  # noqa: E402


def _applier(args) -> Applier:
    cfg = load_enforcement_config(getattr(args, "policy", None))
    if getattr(args, "fail_mode", None):
        cfg.fail_mode = args.fail_mode
    dry = True if getattr(args, "dry_run", False) else None
    return Applier(cfg=cfg, dry_run=dry,
                   routing_path=getattr(args, "routing", None))


def cmd_render(args) -> int:
    ap = _applier(args)
    try:
        print(ap.render(), end="")
    except ValueError as e:
        print(f"[render] 거부: {e}", file=sys.stderr)
        return 2
    return 0


def cmd_apply(args) -> int:
    ap = _applier(args)
    res = ap.apply()
    print(f"[apply] ok={res.ok} mode={res.mode} backend={res.backend} — {res.detail}",
          file=sys.stderr)
    if args.show_rules and res.rule_text:
        print(res.rule_text, end="")
    # fail-open/closed 는 "적용 실패" 지만 의도된 폴백 — exit 0(킬/모니터가 판단).
    return 0 if res.ok or res.mode in ("fail-open", "fail-closed", "dry-run") else 1


def cmd_disable(args) -> int:
    ap = _applier(args)
    res = ap.disable()
    print(f"[disable] ok={res.ok} mode={res.mode} — {res.detail}", file=sys.stderr)
    return 0 if res.ok else 1


def cmd_status(args) -> int:
    ap = _applier(args)
    print(json.dumps(ap.status(), ensure_ascii=False, indent=2))
    return 0


def cmd_doctor(args) -> int:
    # 자가진단 (11체크 PASS/WARN/FAIL). doctor 모듈에 위임(CMP-120 + CMP-341).
    from enforcement.doctor import (DoctorContext, run_checks, build_report,
                                    render_human)
    ctx = DoctorContext(routing_path=getattr(args, "routing", None),
                        policy_path=getattr(args, "policy", None),
                        ner_backend=args.ner_backend,
                        connect_timeout=args.connect_timeout)
    report = build_report(run_checks(ctx))
    # --format takes precedence over --json/--no-json
    out_fmt = getattr(args, "output_format", None)
    use_json = (out_fmt == "json") or (not out_fmt and args.json)
    use_text_only = (out_fmt == "text") or (not out_fmt and args.no_json)
    if use_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_human(report))
        if not use_text_only:
            print("\n--- JSON ---")
            print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report["summary"]["fail"] else 0


def cmd_coverage(args) -> int:
    # 커버리지 보증 리포트 — '내 트래픽 중 X% 가 게이트웨이를 통과'(CMP-133 O2 (a)(b)).
    # flow_tap 의 via_gateway/bypass 분류를 상시 집계(capture/coverage.py).
    import tempfile
    from capture.flow_tap import FlowTap
    from capture.coverage import CoverageAggregator, render_coverage_human, FAIL

    if args.simulate:
        # 데모/CI: 리플레이를 격리 디렉터리로 분류·적재 후 집계(운영 로그 미오염).
        with tempfile.TemporaryDirectory(prefix="nufi-coverage-") as td:
            tap = FlowTap(targets_path=args.targets, base_dir=td)
            tap.simulate(args.simulate)
            flows = tap.read_flows()
    else:
        tap = FlowTap(targets_path=args.targets, base_dir=args.out)
        flows = tap.read_flows()

    agg = CoverageAggregator.from_flows(flows, pass_min=args.pass_min,
                                        fail_below=args.fail_below,
                                        state_path=args.state)
    if args.state:
        agg.persist()  # 상시 집계: 누적 상태를 경량 영속.
    snap = agg.snapshot()

    if args.json:
        print(json.dumps(snap.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(render_coverage_human(snap))
        if not args.no_json:
            print("\n--- JSON ---")
            print(json.dumps(snap.to_dict(), ensure_ascii=False, indent=2))
    return 1 if snap.status == FAIL else 0


def cmd_monitor(args) -> int:
    # 우회 상시 모니터링/임계 알림(suppression 포함 · CMP-133 O2 (c)).
    import tempfile
    from capture.flow_tap import FlowTap
    from capture.bypass_monitor import BypassMonitor, render_monitor_human, FAIL

    mon = BypassMonitor(threshold=args.threshold, window_sec=args.window,
                        cooldown_sec=args.cooldown, alerts_path=args.alerts)
    if args.simulate:
        with tempfile.TemporaryDirectory(prefix="nufi-monitor-") as td:
            tap = FlowTap(targets_path=args.targets, base_dir=td)
            tap.simulate(args.simulate)
            events = mon.observe_many(tap.read_flows())
    else:
        tap = FlowTap(targets_path=args.targets, base_dir=args.out)
        events = mon.observe_many(tap.read_flows())

    report = mon.report()
    if args.json:
        print(json.dumps({**report, "events": [e.to_dict() for e in events]},
                         ensure_ascii=False, indent=2))
    else:
        print(render_monitor_human(report, events))
    return 1 if report["status"] == FAIL else 0


def cmd_feedback(args) -> int:
    fb = DropFeedback(counter_path=args.counter, flow_dir=args.flow_dir)
    if args.log and args.log != "-":
        lines = Path(args.log).read_text(encoding="utf-8").splitlines()
    else:
        lines = sys.stdin.read().splitlines()
    stats = fb.ingest(lines, reinject=not args.no_reinject)
    print(json.dumps(stats, ensure_ascii=False))
    return 0


def cmd_init(args) -> int:
    # Quick-start mode: no preset and not --list → new project init (patch90 + CMP-341).
    if not getattr(args, "list", False) and not getattr(args, "preset", None):
        from enforcement.init_cmd import cmd_quickstart_init
        return cmd_quickstart_init(args)
    # Legacy preset mode: `nufi init <preset>` 와 동일 엔진(egress_audit.init_cli)에 위임.
    from egress_audit.init_cli import cmd_init as _init
    return _init(args)


def cmd_audit(args) -> int:
    # 비동기 감사 봇(producer/consumer) + §4 감사로그 집계를 통합 CLI 로 편입(CMP-141).
    # 기존 모듈 진입점(``python3 -m egress_audit.audit_bot``)은 하위호환으로 그대로 유지.
    action = args.action
    if action in ("report", "daemon", "once"):
        from egress_audit.audit_bot import main as _audit_main
        argv: List[str] = [f"--{action}"]
        if getattr(args, "profiles", None):
            argv += ["--profiles", args.profiles]
        if getattr(args, "ner_backend", None):
            argv += ["--ner-backend", args.ner_backend]
        return _audit_main(argv)
    if action == "query":
        return _audit_query(args)
    if action == "verify":
        from enforcement.audit_cmd import cmd_audit_verify
        # Map --log to log_path for audit_cmd
        args.log_path = getattr(args, "log", None)
        return cmd_audit_verify(args)
    print("usage: nufi-egress audit {report|daemon|once|query|verify} …", file=sys.stderr)
    return 2


def _audit_query(args) -> int:
    # §4 감사로그 조회 — 기존 raw heredoc(INTEGRATION_GUIDE)을 1급 명령으로 대체.
    # outcome 분포 + 차단 건의 엔티티별 집계, 옵션 해시 체인 무결성 검증(M5 §4.3).
    import collections
    from egress_audit.audit import AuditLogger, verify_chain_records

    logger = AuditLogger(path=getattr(args, "log", None) or None)
    records = logger.read_all()
    blocked = [r for r in records if r.get("outcome") == "blocked"]
    by_entity: "collections.Counter[str]" = collections.Counter()
    for r in blocked:
        for f in r.get("findings", []) or []:
            et = f.get("entity_type") or f.get("type") or "UNKNOWN"
            by_entity[et] += 1
    by_outcome = collections.Counter(r.get("outcome", "unknown") for r in records)
    result = {
        "log": str(logger.path),
        "total": len(records),
        "by_outcome": dict(by_outcome),
        "blocked": len(blocked),
        "blocked_by_entity": dict(by_entity.most_common()),
    }
    if args.verify_chain:
        result["chain"] = verify_chain_records(records)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"감사 로그: {result['log']}  (총 {result['total']}행)")
        print(f"  outcome 분포: {result['by_outcome'] or '{}'}")
        print(f"  차단 {result['blocked']}건 — 엔티티별:")
        if by_entity:
            for et, n in by_entity.most_common():
                print(f"    {et:<20} {n}")
        else:
            print("    (없음)")
        if "chain" in result:
            ch = result["chain"]
            ok = ch.get("ok")
            tail = "" if ok else f" — {ch.get('error')} @seq {ch.get('broken_seq')}"
            print(f"  해시 체인: {'OK' if ok else 'BROKEN'} ({ch.get('count')}행){tail}")
    # 관측 명령 — 체인 검증을 요청했고 깨졌으면 비0(CI 변조탐지 게이트).
    if args.verify_chain and not result["chain"]["ok"]:
        return 1
    return 0


def cmd_targets(args) -> int:
    # 캡처 레이어 운영 명령(capture_targets.yaml 파생/조회)을 통합 CLI 로 편입(CMP-143).
    # 기존 모듈 진입점(``python3 -m capture.targets``)은 하위호환으로 그대로 유지.
    from capture.targets import _main as _targets_main
    argv: List[str] = []
    if getattr(args, "refresh", False):
        argv.append("--refresh")
    if getattr(args, "targets_routing", None):
        argv += ["--routing", args.targets_routing]
    if getattr(args, "out", None):
        argv += ["--out", args.out]
    if getattr(args, "bpf", False):
        argv.append("--bpf")
    return _targets_main(argv)


# --- 정책 운영 자동화 (v0.0.5 B1 · CMP-144) -------------------------------- #
def _actor(args) -> str:
    import getpass
    a = getattr(args, "actor", None)
    if a:
        return a
    import os
    try:
        return os.environ.get("NUFI_ACTOR") or getpass.getuser()
    except Exception:
        return "operator"


def _policy_manager(args):
    from enforcement.policy_ops import ProfileRegistry, PolicyOpsManager
    reg = ProfileRegistry(routing_path=getattr(args, "routing", None))
    return PolicyOpsManager(registry=reg)



def cmd_policy_list(args) -> int:
    mgr = _policy_manager(args)
    st = mgr.status()
    if args.json:
        print(json.dumps(st, ensure_ascii=False, indent=2))
        return 0
    print(f"기본 프로파일: {st['default_profile']}")
    print("프로파일:")
    for p in st["profiles"]:
        av = p["active_version"]
        print(f"  - {p['name']:<10} 활성버전={'v'+str(av) if av else '—'} "
              f"버전수={p['version_count']}  {p['description']}")
    print("묶기(경로/테넌트 → 프로파일):")
    if st["bindings"]:
        for route, prof in sorted(st["bindings"].items()):
            print(f"  {route:<20} → {prof}")
    else:
        print("  (없음 — 전부 기본 프로파일)")
    return 0


def cmd_policy_bind(args) -> int:
    mgr = _policy_manager(args)
    try:
        rec = mgr.bind(args.route, args.profile, actor=_actor(args))
    except KeyError as e:
        print(f"[policy bind] 거부: {e}", file=sys.stderr)
        return 2
    print(f"[policy bind] {args.route} → {args.profile} (by {rec['actor']})")
    return 0


def cmd_policy_snapshot(args) -> int:
    mgr = _policy_manager(args)
    try:
        pv = mgr.snapshot(args.profile, actor=_actor(args), note=args.note or "")
    except KeyError as e:
        print(f"[policy snapshot] 거부: {e}", file=sys.stderr)
        return 2
    print(f"[policy snapshot] {args.profile} v{pv.version} 적재 "
          f"(fingerprint={pv.fingerprint}, by {pv.actor})")
    return 0


def cmd_policy_versions(args) -> int:
    mgr = _policy_manager(args)
    vers = mgr.versions.versions(args.profile)
    if args.json:
        print(json.dumps([v.__dict__ for v in vers], ensure_ascii=False, indent=2))
        return 0
    if not vers:
        print(f"(프로파일 {args.profile} 에 적재된 버전 없음 — policy snapshot 먼저)")
        return 0
    print(f"프로파일 {args.profile} 버전 이력:")
    for v in vers:
        mark = " *활성" if v.active else ""
        print(f"  v{v.version:<3} {v.created_at}  by {v.actor:<16} "
              f"fp={v.fingerprint}  {v.note}{mark}")
    return 0


def cmd_policy_rollback(args) -> int:
    mgr = _policy_manager(args)
    try:
        out = mgr.rollback(args.profile, actor=_actor(args), to_version=args.to)
    except (KeyError, ValueError) as e:
        print(f"[policy rollback] 거부: {e}", file=sys.stderr)
        return 2
    if not out.applied:
        print(f"[policy rollback] 거부(fail-closed): {out.error} "
              f"— 직전 룰셋 유지(generation {out.generation_before})", file=sys.stderr)
        return 1
    print(f"[policy rollback] {args.profile} v{out.from_version}→v{out.to_version} "
          f"무재기동 적용 (generation {out.generation_before}→{out.generation_after}, "
          f"fingerprint={out.fingerprint})")
    return 0


def cmd_policy_audit(args) -> int:
    mgr = _policy_manager(args)
    records = mgr.audit.read_all()
    chain = mgr.audit.verify_chain() if args.verify_chain else None
    if args.json:
        out = {"log": str(mgr.audit.path), "total": len(records), "records": records}
        if chain is not None:
            out["chain"] = chain
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(f"변경 감사 로그: {mgr.audit.path}  (총 {len(records)}건)")
        for r in records:
            fv, tv = r.get("from_version"), r.get("to_version")
            ver = (f" v{fv}→v{tv}" if fv is not None else (f" v{tv}" if tv is not None else ""))
            print(f"  [{r['ts']}] {r['actor']:<16} {r['action']:<13} "
                  f"{r['profile']}{ver}  {r.get('note','')}")
        if chain is not None:
            tail = "" if chain["ok"] else f" — {chain.get('error')} @seq {chain.get('broken_seq')}"
            print(f"해시 체인: {'OK' if chain['ok'] else 'BROKEN'} ({chain['count']}건){tail}")
    return 1 if chain is not None and not chain["ok"] else 0


def cmd_policy_inspect(args) -> int:
    mgr = _policy_manager(args)
    profile = mgr.registry.profile_for_route(args.route)
    res = mgr.inspect(args.route, args.text)
    s = res.summary
    out = {"route": args.route, "profile": profile, "blocked": bool(s.get("blocked")),
           "action_counts": dict(s.get("action_counts", {})),
           "finding_count": int(s.get("finding_count", 0))}
    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        verdict = "차단(blocked)" if out["blocked"] else "통과(allow/transform)"
        print(f"경로 {args.route} → 프로파일 {profile}: {verdict} "
              f"(findings={out['finding_count']}, actions={out['action_counts']})")
    return 1 if out["blocked"] else 0


def cmd_flow_tap(args) -> int:
    # 캡처 레이어 운영 명령(public 목적지 flow tap·우회 탐지)을 통합 CLI 로 편입(CMP-143).
    # 기존 모듈 진입점(``python3 -m capture.flow_tap``)은 하위호환으로 그대로 유지.
    from capture.flow_tap import _main as _flow_tap_main
    argv: List[str] = []
    if getattr(args, "simulate", None):
        argv += ["--simulate", args.simulate]
    if getattr(args, "live", False):
        argv.append("--live")
    if getattr(args, "iface", None):
        argv += ["--iface", args.iface]
    if getattr(args, "duration", None) is not None:
        argv += ["--duration", str(args.duration)]
    if getattr(args, "targets", None):
        argv += ["--targets", args.targets]
    if getattr(args, "out", None):
        argv += ["--out", args.out]
    return _flow_tap_main(argv)



def cmd_diff(args) -> int:
    """git diff 변경 파일만 PII/인젝션 스캔 (patch104)."""
    from enforcement.diff_cmd import cmd_diff as _diff
    return _diff(args)


def cmd_config(args) -> int:
    """설정 파일 검증 (patch105)."""
    from enforcement.config_cmd import cmd_config as _config
    return _config(args)


def cmd_scan(args) -> int:
    """파일/디렉터리 PII + 인젝션 스캔 (patch83)."""
    from enforcement.scan_cmd import cmd_scan as _scan
    return _scan(args)


def cmd_watch(args) -> int:
    """디렉터리 PII 감시 (patch92)."""
    from enforcement.watch_cmd import cmd_watch as _watch
    return _watch(args)


def cmd_compare(args) -> int:
    """스캔 결과 비교 (patch133)."""
    from enforcement.compare_cmd import cmd_compare as _compare
    return _compare(args)


def cmd_test(args) -> int:
    """자가 검증 (patch135)."""
    from enforcement.selftest_cmd import cmd_test as _test
    return _test(args)


def cmd_lint(args) -> int:
    """보안 안티패턴 검사 (patch130)."""
    from enforcement.lint_cmd import cmd_lint as _lint
    return _lint(args)


def cmd_generate(args) -> int:
    """샘플 PII 데이터 생성 (patch131)."""
    from enforcement.generate_cmd import cmd_generate as _generate
    return _generate(args)


def cmd_export(args) -> int:
    """탐지 패턴 내보내기 (patch122)."""
    from enforcement.export_cmd import cmd_export as _export
    return _export(args)


def cmd_guard(args) -> int:
    """통합 CI 게이트 — scan + policy + pseudonymize (v0.7.1)."""
    from enforcement.guard_cmd import cmd_guard as _guard
    return _guard(args)


def cmd_pseudonymize(args) -> int:
    """가역 가명화 / 원복 (v0.6.0)."""
    from enforcement.pseudonymize_cmd import cmd_pseudonymize as _pseudo
    return _pseudo(args)


def cmd_mask(args) -> int:
    """텍스트 PII 마스킹 (patch124)."""
    from enforcement.transform_cmd import cmd_mask as _mask
    return _mask(args)


def cmd_redact_text(args) -> int:
    """텍스트 PII 리댁션 (patch124)."""
    from enforcement.transform_cmd import cmd_redact as _redact
    return _redact(args)


def cmd_pipeline(args) -> int:
    """파이프라인 체인 처리 (patch139)."""
    from enforcement.pipeline_cmd import cmd_pipeline as _pipeline
    return _pipeline(args)


def cmd_history(args) -> int:
    """활동 로그 조회 (patch141)."""
    from enforcement.history_cmd import cmd_history as _history
    return _history(args)


def cmd_playground(args) -> int:
    """인터랙티브 PII 분석 REPL (patch145)."""
    from enforcement.playground_cmd import cmd_playground as _playground
    return _playground(args)


def cmd_summary(args) -> int:
    """프로젝트 헬스 대시보드 (patch147)."""
    from enforcement.summary_cmd import cmd_summary as _summary
    return _summary(args)


def cmd_dashboard(args) -> int:
    """ASCII 터미널 보안 대시보드 (patch174)."""
    from enforcement.dashboard_cmd import cmd_dashboard as _dashboard
    return _dashboard(args)


def cmd_serve(args) -> int:
    """HTTP API 서버 (patch155)."""
    from enforcement.serve_cmd import cmd_serve as _serve
    return _serve(args)


def cmd_explain(args) -> int:
    """텍스트 탐지 결과 상세 설명 (patch116)."""
    from enforcement.explain_cmd import explain_text, render_human

    if not args.text:
        print("오류: --text 를 지정해야 합니다.", file=sys.stderr)
        return 1

    result = explain_text(args.text)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(render_human(result))

    return 0


def cmd_inspect(args) -> int:
    """통합 보안 분석 — PII + 인젝션 + 라우팅 + 위험도 (patch78)."""
    from enforcement.inspect_cmd import inspect_text, render_human

    texts: List[str] = []
    if args.text:
        texts = [args.text]
    elif args.file:
        p = Path(args.file)
        if not p.exists():
            print(f"오류: 파일을 찾을 수 없습니다: {args.file}", file=sys.stderr)
            return 1
        texts = [line for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]
    else:
        print("오류: --text 또는 --file 을 지정해야 합니다.", file=sys.stderr)
        return 1

    results = [inspect_text(t) for t in texts]

    if args.json:
        output = results if len(results) > 1 else results[0]
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        for r in results:
            print(render_human(r))
            if len(results) > 1:
                print("---")

    # Exit code: non-zero if any result is blocked
    return 1 if any(r["blocked"] for r in results) else 0


def cmd_route(args) -> int:
    """PII 라우팅 결정을 CLI에서 테스트한다(CMP-270)."""
    from gateway.pii_router import PiiRouter

    router = PiiRouter(
        local_model=getattr(args, "local_model", "nufi-local"),
        cloud_model=getattr(args, "cloud_model", "nufi-cloud"),
    )

    # Prompt injection detector (patch61, patch69-severity)
    injection_detector = None
    if getattr(args, "check_injection", False):
        from egress_audit.detectors.prompt_injection import PromptInjectionDetector
        min_sev = getattr(args, "min_severity", "low")
        injection_detector = PromptInjectionDetector(min_severity=min_sev)

    # --stdin: stdin 라인별 처리
    if getattr(args, "stdin", False):
        return _route_stdin(router, args, injection_detector=injection_detector)

    # --file: 파일 라인별 처리
    file_path = getattr(args, "file", None)
    if file_path:
        return _route_file(router, args, file_path, injection_detector=injection_detector)

    if not args.text:
        print("오류: --text, --file, --stdin 중 하나를 지정해야 합니다.", file=__import__('sys').stderr)
        return 1

    decision = router.route(args.text, requested_model=args.model)

    # Check injection if flag is set
    injection_findings = []
    if injection_detector:
        injection_findings = injection_detector.detect(args.text)

    if args.json:
        out = decision.to_dict()
        if injection_findings:
            out["injection_findings"] = [
                {"entity_type": f.entity_type, "text": f.text, "score": f.score}
                for f in injection_findings
            ]
            out["injection_detected"] = True
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        status = "🔒 로컬 라우팅" if decision.routed_to_local else "☁️  클라우드 허용"
        print(f"입력: {args.text}")
        print(f"판정: {status}")
        print(f"  대상 모델:  {decision.target_model}")
        print(f"  사유:       {decision.reason}")
        print(f"  PII 감지:   {decision.pii_detected}")
        if decision.findings:
            types = sorted({f.entity_type for f in decision.findings})
            print(f"  엔티티:     {', '.join(types)}")
        if injection_findings:
            print(f"  ⚠ 인젝션 탐지: {len(injection_findings)}건")
            for ijf in injection_findings:
                print(f"    - [{ijf.score:.1f}] {ijf.text}")
        print(f"  지연(ms):   {decision.latency_ms:.2f}")
    return 0


def _route_file(router, args, file_path: str, injection_detector=None) -> int:
    """파일을 라인별로 PII 라우팅 처리한다."""
    path = Path(file_path)
    if not path.exists():
        print(f"오류: 파일을 찾을 수 없습니다: {file_path}", file=__import__('sys').stderr)
        return 1

    lines = path.read_text(encoding="utf-8").splitlines()
    decisions = []
    local_count = 0
    cloud_count = 0
    all_entity_types: set = set()

    for idx, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        decision = router.route(line.strip(), requested_model=args.model)
        verdict = "local" if decision.routed_to_local else "cloud"
        entity_types = sorted({f.entity_type for f in decision.findings})
        all_entity_types.update(entity_types)
        if decision.routed_to_local:
            local_count += 1
        else:
            cloud_count += 1
        entry = {
            "line": idx,
            "text": line.strip(),
            "verdict": verdict,
            "entity_types": entity_types,
            **decision.to_dict(),
        }
        if injection_detector:
            ijf = injection_detector.detect(line.strip())
            if ijf:
                entry["injection_detected"] = True
                entry["injection_findings"] = [
                    {"entity_type": f.entity_type, "text": f.text, "score": f.score}
                    for f in ijf
                ]
        decisions.append(entry)

    show_summary = getattr(args, "summary", False)
    total = local_count + cloud_count

    if args.json:
        output: dict = {"decisions": decisions}
        if show_summary:
            output["summary"] = {
                "total_lines": total,
                "local_count": local_count,
                "local_pct": round(local_count / total * 100, 1) if total else 0.0,
                "cloud_count": cloud_count,
                "cloud_pct": round(cloud_count / total * 100, 1) if total else 0.0,
                "unique_entity_types": sorted(all_entity_types),
            }
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        for d in decisions:
            icon = "🔒" if d["verdict"] == "local" else "☁️ "
            ent = f" [{', '.join(d['entity_types'])}]" if d["entity_types"] else ""
            print(f"  {d['line']:>4}: {icon} {d['verdict']}{ent}")

        if show_summary:
            print()
            print("── 요약 ──")
            print(f"  처리 라인:  {total}")
            local_pct = round(local_count / total * 100, 1) if total else 0.0
            cloud_pct = round(cloud_count / total * 100, 1) if total else 0.0
            print(f"  로컬 라우팅: {local_count} ({local_pct}%)")
            print(f"  클라우드:    {cloud_count} ({cloud_pct}%)")
            if all_entity_types:
                print(f"  엔티티 종류: {', '.join(sorted(all_entity_types))}")

    return 0


def _route_stdin(router, args, injection_detector=None) -> int:
    """stdin 에서 라인별로 PII 라우팅 처리한다 (--stdin)."""
    lines = sys.stdin.read().splitlines()
    decisions = []
    local_count = 0
    cloud_count = 0
    all_entity_types: set = set()

    for idx, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        decision = router.route(line.strip(), requested_model=args.model)
        verdict = "local" if decision.routed_to_local else "cloud"
        entity_types = sorted({f.entity_type for f in decision.findings})
        all_entity_types.update(entity_types)
        if decision.routed_to_local:
            local_count += 1
        else:
            cloud_count += 1
        entry = {
            "line": idx,
            "text": line.strip(),
            "verdict": verdict,
            "entity_types": entity_types,
            **decision.to_dict(),
        }
        if injection_detector:
            ijf = injection_detector.detect(line.strip())
            if ijf:
                entry["injection_detected"] = True
                entry["injection_findings"] = [
                    {"entity_type": f.entity_type, "text": f.text, "score": f.score}
                    for f in ijf
                ]
        decisions.append(entry)

    show_summary = getattr(args, "summary", False)
    total = local_count + cloud_count

    if args.json:
        output: dict = {"decisions": decisions}
        if show_summary:
            output["summary"] = {
                "total_lines": total,
                "local_count": local_count,
                "local_pct": round(local_count / total * 100, 1) if total else 0.0,
                "cloud_count": cloud_count,
                "cloud_pct": round(cloud_count / total * 100, 1) if total else 0.0,
                "unique_entity_types": sorted(all_entity_types),
            }
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        for d in decisions:
            icon = "🔒" if d["verdict"] == "local" else "☁️ "
            ent = f" [{', '.join(d['entity_types'])}]" if d["entity_types"] else ""
            print(f"  {d['line']:>4}: {icon} {d['verdict']}{ent}")

        if show_summary:
            print()
            print("── 요약 ──")
            print(f"  처리 라인:  {total}")
            local_pct = round(local_count / total * 100, 1) if total else 0.0
            cloud_pct = round(cloud_count / total * 100, 1) if total else 0.0
            print(f"  로컬 라우팅: {local_count} ({local_pct}%)")
            print(f"  클라우드:    {cloud_count} ({cloud_pct}%)")
            if all_entity_types:
                print(f"  엔티티 종류: {', '.join(sorted(all_entity_types))}")

    return 0


def _report_write(text: str, out: Optional[str]) -> None:
    if out:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_text(text, encoding="utf-8")
        print(f"[report] 기록: {out}")
    else:
        print(text)



def cmd_report(args) -> int:
    # 기존 측정 산출물·감사 로그를 기간별 제출용 리포트로 묶는다(새 측정 없음).
    if args.report_kind == "posture":
        from enforcement.posture_cmd import cmd_report_posture
        return cmd_report_posture(args)

    from enforcement import report as _rpt
    fmt = args.format
    flow_paths = [args.flow] if getattr(args, "flow", None) else None

    if args.report_kind == "compliance":
        rep = _rpt.build_compliance_report(
            audit_path=args.audit, change_log_path=args.change_log,
            flow_dir=getattr(args, "flow_dir", None), flow_paths=flow_paths,
            customer=args.customer, title=args.title,
            controls=not getattr(args, "no_controls", False),
            catalog_path=getattr(args, "catalog", None),
            frameworks=(getattr(args, "framework", None) or None))
        _report_write(_rpt.render(rep, fmt), args.out)
        # 해시체인 변조가 탐지되면 비0(무결성 게이트).
        return 0 if rep["integrity_ok"] else 1

    if args.report_kind == "security":
        from enforcement.security_report import cmd_report_security
        return cmd_report_security(args)

    if args.report_kind == "trends":
        from enforcement.trends_cmd import cmd_report_trends
        return cmd_report_trends(args)

    if args.report_kind == "diff":
        from enforcement.report_diff_cmd import cmd_report_diff
        return cmd_report_diff(args)

    if args.report_kind == "executive":
        from enforcement.executive_report import cmd_report_executive
        return cmd_report_executive(args)

    if args.report_kind == "badge":
        from enforcement.badge_cmd import cmd_report_badge
        return cmd_report_badge(args)

    if args.report_kind == "coverage-map":
        from enforcement.coverage_map import cmd_report_coverage_map
        return cmd_report_coverage_map(args)

    print("usage: nufi-egress report {compliance|security|trends|diff|executive|badge|coverage-map|posture} …", file=sys.stderr)
    return 2


def cmd_benchmark(args) -> int:
    # 정확도(커밋 측정 산출물 게이트) + 가명화(라이브 하니스)를 단일 명령으로 재현.
    # 모델 재실행 없음: 정확도는 봉인 골드셋 측정 JSON 을 목표선에 대조, 가명화는 결정적 하니스.
    from enforcement import benchmark as _bench
    report = _bench.run_benchmarks(only=getattr(args, "only", None))
    if getattr(args, "json", False):
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(_bench.render(report))
    if getattr(args, "json_out", None):
        Path(args.json_out).write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # 게이트 판정: 전체 PASS 면 0, 하나라도 미달이면 1(CI/데모/제출 게이트).
    return 0 if report["overall_pass"] else 1


def cmd_version(args) -> int:
    """NuFi 버전 및 백엔드 정보 출력(patch81)."""
    import platform

    # NuFi version
    version_file = _ROOT / "VERSION"
    nufi_version = version_file.read_text().strip() if version_file.exists() else "unknown"

    # Python version
    python_version = platform.python_version()

    # KoELECTRA ONNX availability
    try:
        import optimum.onnxruntime  # noqa: F401
        koelectra_onnx = "yes"
    except ImportError:
        koelectra_onnx = "no"

    # Injection patterns count
    from egress_audit.detectors.prompt_injection import _PATTERN_DEFS
    pattern_count = len(_PATTERN_DEFS)

    print(f"NuFi version: {nufi_version}")
    print(f"Python: {python_version}")
    print(f"KoELECTRA ONNX: {koelectra_onnx}")
    print(f"Injection patterns: {pattern_count}")
    return 0


class _GroupedHelpFormatter(argparse.RawDescriptionHelpFormatter):
    """서브커맨드를 카테고리별로 묶어 표시하는 헬프 포매터."""
    pass


_HELP_EPILOG = """\
서브커맨드 (카테고리별):

  [탐지]
    scan            파일/디렉터리 PII + 인젝션 스캔
    inspect         통합 보안 분석 (PII + 인젝션 + 라우팅 + 위험도)
    explain         텍스트 탐지 결과 상세 설명 (디버깅/교육용)
    pipeline        체인 파이프라인 (detect→decide→transform→route 한 번에)
    route           PII 라우팅 결정 테스트
    diff            git 변경 파일만 PII/인젝션 스캔
    compare         두 스캔 결과 비교 (new/resolved/unchanged)

  [운영]
    export          탐지 패턴 내보내기 (YAML/JSON/regex)
    watch           디렉터리 PII 실시간 감시
    init            프로젝트 초기화 또는 프리셋 구체화
    config          설정 파일 검증
    doctor          하이브리드 배선 진단
    test            자가 검증 (PII·인젝션·라우팅·Guard·설정·버전)
    history         최근 활동 로그 조회 (스캔·차단·라우팅)
    summary         프로젝트 헬스 대시보드 (설정·활동·위험·닥터·버전)
    stats           NuFi 설정·탐지 역량 요약 통계

  [보고]
    report          규정준수 리포트 산출
    benchmark       정확도 + 가명화 벤치마크

  [정보]
    version         버전 및 백엔드 정보 출력
    completions     셸 자동완성 스크립트 출력

각 서브커맨드의 상세 도움말: nufi-egress <subcommand> --help
"""


def main(argv: Optional[List[str]] = None) -> int:
    # Read VERSION for --version flag
    _ver_file = _ROOT / "VERSION"
    _version_str = _ver_file.read_text().strip() if _ver_file.exists() else "unknown"

    ap = argparse.ArgumentParser(
        prog="nufi-egress",
        description="NuFi Egress Enforcement CLI — LLM 이그레스 보안 관제 도구",
        epilog=_HELP_EPILOG,
        formatter_class=_GroupedHelpFormatter,
    )
    ap.add_argument("--version", action="version", version=f"nufi-egress {_version_str}")
    ap.add_argument("--routing", default=None, help="routing.yaml 경로")
    ap.add_argument("--policy", default=None, help="policy.yaml 경로")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("version", help="버전 및 백엔드 정보 출력")
    p.set_defaults(func=cmd_version)

    p = sub.add_parser("render", help="집행 규칙 셋 출력(적용 안 함)")
    p.set_defaults(func=cmd_render)

    p = sub.add_parser("apply", help="규칙 원자 적용(정적 사전 차단)")
    p.add_argument("--fail-mode", choices=["open", "closed"], default=None)
    p.add_argument("--dry-run", action="store_true", help="commit 생략(텍스트만)")
    p.add_argument("--show-rules", action="store_true")
    p.set_defaults(func=cmd_apply)

    p = sub.add_parser("disable", help="킬스위치(전 규칙 제거)")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_disable)

    p = sub.add_parser("status", help="집행 상태(JSON)")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("feedback", help="drop 로그 → blocked_attempts + flow 재유입")
    p.add_argument("--log", default="-", help="drop 로그 파일(기본 stdin)")
    p.add_argument("--counter", default=None, help="카운터 JSON 경로")
    p.add_argument("--flow-dir", default=None, help="flow 재유입 디렉터리")
    p.add_argument("--no-reinject", action="store_true", help="카운터만, flow 미기록")
    p.set_defaults(func=cmd_feedback)

    p = sub.add_parser("doctor", help="자가진단 (11체크 PASS/WARN/FAIL)")
    p.add_argument("--ner-backend", default="gazetteer",
                   help="탐지 NER 백엔드(기본 gazetteer — 결정론적·경량)")
    p.add_argument("--connect-timeout", type=float, default=2.0,
                   help="도달성 점검 TCP 타임아웃(초)")
    p.add_argument("--format", choices=["text", "json"], default=None,
                   dest="output_format",
                   help="출력 포맷 (text | json)")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--json", action="store_true", help="기계용 JSON 만 출력")
    g.add_argument("--no-json", action="store_true", help="사람읽기만 출력(JSON 생략)")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("coverage",
                       help="'내 트래픽 중 X%% 게이트웨이 통과' 커버리지 보증 리포트")
    p.add_argument("--simulate", metavar="REPLAY.jsonl",
                   help="flow 리플레이로 집계(에어갭/CI · 운영 로그 미오염)")
    p.add_argument("--targets", default=None, help="capture_targets.yaml 경로")
    p.add_argument("--out", default=None, help="flow 로그 base_dir(기본 logs/packets)")
    p.add_argument("--state", default=None, help="경량 영속 카운터 JSON 경로(상시 누적)")
    p.add_argument("--pass-min", type=float, default=1.0,
                   help="PASS 최소 커버리지 비율(기본 1.0=100%%, 우회 0건)")
    p.add_argument("--fail-below", type=float, default=0.90,
                   help="FAIL 임계 커버리지 비율(기본 0.90)")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--json", action="store_true", help="기계용 JSON 만 출력")
    g.add_argument("--no-json", action="store_true", help="사람읽기만 출력(JSON 생략)")
    p.set_defaults(func=cmd_coverage)

    p = sub.add_parser("monitor",
                       help="게이트웨이 우회 상시 모니터링/임계 알림(suppression)")
    p.add_argument("--simulate", metavar="REPLAY.jsonl",
                   help="flow 리플레이로 우회 모니터 1회 실행(에어갭/CI)")
    p.add_argument("--threshold", type=int, default=1,
                   help="알림 발화 임계 우회 횟수(키별 윈도 내, 기본 1)")
    p.add_argument("--window", type=float, default=60.0, help="임계 누적 롤링 윈도(초)")
    p.add_argument("--cooldown", type=float, default=300.0,
                   help="발화 후 동일 키 억제(디바운스) 기간(초)")
    p.add_argument("--alerts", default=None, help="알림 출력 경로(기본 logs/alerts.jsonl)")
    p.add_argument("--targets", default=None, help="capture_targets.yaml 경로")
    p.add_argument("--out", default=None, help="flow 로그 base_dir(기본 logs/packets)")
    p.add_argument("--json", action="store_true", help="기계용 JSON 만 출력")
    p.set_defaults(func=cmd_monitor)

    p = sub.add_parser("init", help="프로젝트 초기화(quick-start) 또는 프리셋 구체화")
    p.add_argument("preset", nargs="?", help="프리셋 이름(생략 시 quick-start 초기화)")
    p.add_argument("--list", action="store_true", help="사용 가능한 프리셋 목록")
    p.add_argument("--dir", default=".", help="초기화 대상 디렉터리(기본 현재 디렉터리)")
    p.add_argument("--install-hook", action="store_true",
                   help="git pre-commit hook 설치(PII 스캔)")
    p.add_argument("--ci", choices=["github", "gitlab"], default=None,
                   help="CI 플랫폼별 워크플로우 자동 생성 (github | gitlab)")
    p.add_argument("--default", action="store_true", dest="use_default",
                   help="인터랙티브 프롬프트 없이 기본값으로 설정 생성")
    p.add_argument("--out", default="config", help="config 출력 디렉터리(기본 ./config)")
    p.add_argument("--base-dir", default=None, help="오버레이 베이스 config 디렉터리")
    p.add_argument("--set", action="append", metavar="KEY=VALUE", help="허용된 노브 override")
    p.add_argument("--force", action="store_true", help="기존 config 덮어쓰기")
    p.add_argument("--dry-run", action="store_true", help="생성될 파일 미리보기(실제 생성 안함)")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("audit",
                       help="비동기 감사 봇 + §4 감사로그 조회")
    p.add_argument("action", choices=["report", "daemon", "once", "query", "verify"],
                   help="report=지연 p95 · daemon=상시 폴 · once=큐 1회 드레인 · "
                        "query=감사로그 집계(outcome/엔티티/체인) · "
                        "verify=해시 체인 무결성 검증(patch120)")
    p.add_argument("--profiles", default=None,
                   help="audit_profiles.yaml 경로(report/daemon/once)")
    p.add_argument("--ner-backend", default="gazetteer",
                   help="탐지 NER 백엔드(report/daemon/once · 기본 gazetteer)")
    p.add_argument("--log", default=None,
                   help="query: 감사 JSONL 경로(기본 logs/egress_audit.jsonl)")
    p.add_argument("--verify-chain", action="store_true",
                   help="query: 추가전용 해시 체인 무결성 검증(M5 §4.3 변조탐지)")
    p.add_argument("--json", action="store_true",
                   help="query: 기계용 JSON 출력")
    p.set_defaults(func=cmd_audit)

    p = sub.add_parser("targets",
                       help="capture_targets.yaml 파생/조회 + BPF 필터(캡처 레이어)")
    p.add_argument("--refresh", action="store_true",
                   help="routing.yaml 에서 목적지를 재파생해 capture_targets.yaml 기록")
    # 최상위 --routing(집행용)과 충돌 없이 서브커맨드 전용으로 보존(dest=targets_routing).
    p.add_argument("--routing", dest="targets_routing", default=None,
                   metavar="ROUTING", help="routing.yaml 경로")
    p.add_argument("--out", default=None, help="capture_targets.yaml 출력 경로")
    p.add_argument("--bpf", action="store_true", help="BPF 필터 문자열 출력")
    p.set_defaults(func=cmd_targets)

    p = sub.add_parser("flow-tap",
                       help="public 목적지 flow tap + 우회 탐지(--simulate 리플레이/--live)")
    p.add_argument("--simulate", metavar="REPLAY.jsonl",
                   help="미리 만든 flow 로그 리플레이(root 없이 재현 — 에어갭/CI)")
    p.add_argument("--live", action="store_true", help="tcpdump 라이브 캡처(root 필요)")
    p.add_argument("--iface", default="any", help="라이브 캡처 인터페이스")
    p.add_argument("--duration", type=int, default=None, help="라이브 캡처 지속(초)")
    p.add_argument("--targets", default=None, help="capture_targets.yaml 경로")
    p.add_argument("--out", default=None, help="flow 로그 출력 base_dir(기본 logs/packets)")
    p.set_defaults(func=cmd_flow_tap)

    p = sub.add_parser("policy",
                       help="정책 운영 자동화: 다중 프로파일·묶기·버전/되돌리기·변경 감사")
    psub = p.add_subparsers(dest="policy_action", required=True)

    pp = psub.add_parser("list", help="프로파일·묶기·활성 버전 요약")
    pp.add_argument("--json", action="store_true")
    pp.set_defaults(func=cmd_policy_list)

    pp = psub.add_parser("bind", help="경로/테넌트 → 프로파일 묶기(런타임 오버레이)")
    pp.add_argument("route", help="경로/테넌트 키")
    pp.add_argument("profile", help="프로파일 이름")
    pp.add_argument("--actor", default=None, help="변경 주체(기본 $NUFI_ACTOR/현재 사용자)")
    pp.set_defaults(func=cmd_policy_bind)

    pp = psub.add_parser("snapshot", help="현재 프로파일 정책을 새 불변 버전으로 적재")
    pp.add_argument("profile", help="프로파일 이름")
    pp.add_argument("--note", default=None, help="버전 메모")
    pp.add_argument("--actor", default=None)
    pp.set_defaults(func=cmd_policy_snapshot)

    pp = psub.add_parser("versions", help="프로파일 버전 이력")
    pp.add_argument("profile", help="프로파일 이름")
    pp.add_argument("--json", action="store_true")
    pp.set_defaults(func=cmd_policy_versions)

    pp = psub.add_parser("rollback", help="이전(또는 --to) 버전으로 무재기동 되돌리기")
    pp.add_argument("profile", help="프로파일 이름")
    pp.add_argument("--to", type=int, default=None, help="되돌릴 버전(기본: 활성 직전)")
    pp.add_argument("--actor", default=None)
    pp.set_defaults(func=cmd_policy_rollback)

    pp = psub.add_parser("audit", help="변경 감사 로그(누가·언제·무엇을) 조회")
    pp.add_argument("--verify-chain", action="store_true", help="추가전용 해시 체인 무결성 검증")
    pp.add_argument("--json", action="store_true")
    pp.set_defaults(func=cmd_policy_audit)

    pp = psub.add_parser("inspect", help="경로가 어느 프로파일로 묶이고 어떻게 결정되는지 확인")
    pp.add_argument("route", help="경로/테넌트 키")
    pp.add_argument("text", help="검사할 텍스트")
    pp.add_argument("--json", action="store_true")
    pp.set_defaults(func=cmd_policy_inspect)

    # --- 규정준수 리포팅 (CMP-150) ------------------------------------------- #
    p = sub.add_parser("report",
                       help="규정준수 리포트 산출(기존 측정 재사용, 새 측정 없음)")
    rsub = p.add_subparsers(dest="report_kind", required=True)

    rp = rsub.add_parser("compliance",
                         help="정책 변경 감사(+해시체인) · 차단/가명화 · 우회 요약 + "
                              "점검항목 커버리지(control coverage)")
    rp.add_argument("--audit", default=None,
                    help="감사 JSONL 경로(기본 logs/egress_audit.jsonl)")
    rp.add_argument("--change-log", default=None,
                    help="정책 변경 감사 JSONL(기본 logs/policy_changes.jsonl)")
    rp.add_argument("--controls", action="store_true",
                    help="점검항목 커버리지 섹션 포함(기본 상시 포함 — 명시용)")
    rp.add_argument("--no-controls", action="store_true",
                    help="점검항목 커버리지 섹션 생략")
    rp.add_argument("--catalog", default=None,
                    help="통제 카탈로그 YAML 오버라이드(기본 동봉 catalog)")
    rp.add_argument("--framework", action="append", default=None,
                    metavar="ID",
                    help="규제 프레임워크 정보성 필터(반복 허용): "
                         "fsec-ai|net-sep|pipa|cia|isms-p. 지정 시 해당 규제 행만 "
                         "렌더(롤업도 필터 기준). 종료코드 불변(무결성 게이트만).")
    rp.add_argument("--flow", default=None, help="flow tap JSONL(우회 요약)")
    rp.add_argument("--flow-dir", default=None, help="flow tap 로그 디렉터리")
    rp.add_argument("--customer", default=None, help="고객명(리포트 헤더)")
    rp.add_argument("--title", default=None, help="리포트 제목 override")
    rp.add_argument("--format", choices=["md", "html", "json"], default="md",
                    help="출력 형식(기본 md)")
    rp.add_argument("--out", default=None, help="출력 파일 경로(생략 시 stdout)")
    rp.set_defaults(func=cmd_report)

    rp = rsub.add_parser("security",
                         help="보안 포스처 요약 리포트 — PII/인젝션 스캔 + 위험도 평가")
    rp.add_argument("directory", nargs="?", default=".",
                    help="스캔할 디렉터리 경로(기본 현재 디렉터리)")
    rp.add_argument("--pattern", default=None,
                    help="파일 glob 패턴(쉼표 구분, 예: '*.py,*.md')")
    rp.add_argument("--exclude", default=None,
                    help="제외할 glob 패턴(쉼표 구분)")
    rp.add_argument("--format", choices=["md", "json", "html"], default="md",
                    help="출력 형식(기본 md)")
    rp.add_argument("--output", default=None, metavar="PATH",
                    help="출력 파일 경로(생략 시 stdout)")
    rp.set_defaults(func=cmd_report)

    rp = rsub.add_parser("trends",
                         help="PII 탐지 트렌드 — 기간별 이벤트·차단·PII 유형 추이 (patch149)")
    rp.add_argument("--period", type=int, default=7,
                    help="표시할 최근 일수(기본 7)")
    rp.add_argument("--audit", default=None,
                    help="감사 JSONL 경로(기본 logs/egress_audit.jsonl)")
    rp.add_argument("--json", action="store_true", help="기계용 JSON 출력")
    rp.set_defaults(func=cmd_report)

    rp = rsub.add_parser("diff",
                         help="스캔 결과 비교 diff 리포트 — 마크다운/JSON/HTML 출력 (patch153)")
    rp.add_argument("before", help="이전 스캔 결과 파일(SARIF 또는 NuFi JSON)")
    rp.add_argument("after", help="이후 스캔 결과 파일(SARIF 또는 NuFi JSON)")
    rp.add_argument("--format", choices=["md", "json", "html"], default="md",
                    help="출력 형식(기본 md)")
    rp.add_argument("--output", default=None, metavar="PATH",
                    help="출력 파일 경로(생략 시 stdout)")
    rp.set_defaults(func=cmd_report)

    rp = rsub.add_parser("executive",
                         help="경영진용 1페이지 보안 요약 — 등급/지표/위험/권고 (patch163)")
    rp.add_argument("directory", nargs="?", default=".",
                    help="스캔할 디렉터리 경로(기본 현재 디렉터리)")
    rp.add_argument("--format", choices=["text", "json", "md"], default="text",
                    help="출력 형식(기본 text)")
    rp.add_argument("--output", default=None, metavar="PATH",
                    help="출력 파일 경로(생략 시 stdout)")
    rp.set_defaults(func=cmd_report)

    rp = rsub.add_parser("badge",
                         help="SVG 배지 생성 — README/CI 대시보드용 (patch164)")
    rp.add_argument("--type", dest="badge_type", default="grade",
                    choices=["grade", "recall", "injection", "tests"],
                    help="배지 종류(기본 grade)")
    rp.add_argument("--output", default=None, metavar="PATH",
                    help="SVG 파일 출력 경로(생략 시 stdout)")
    rp.set_defaults(func=cmd_report)

    rp = rsub.add_parser("coverage-map",
                         help="PII 엔티티 커버리지 맵 — 파일별 PII 유형 노출 현황 (patch166)")
    rp.add_argument("directory", nargs="?", default=".",
                    help="스캔할 디렉터리 경로(기본 현재 디렉터리)")
    rp.add_argument("--pattern", default=None,
                    help="파일 glob 패턴(쉼표 구분, 예: '*.py,*.md')")
    rp.add_argument("--exclude", default=None,
                    help="제외할 glob 패턴(쉼표 구분)")
    rp.add_argument("--format", choices=["text", "json", "csv"], default="text",
                    help="출력 형식(기본 text)")
    rp.add_argument("--output", default=None, metavar="PATH",
                    help="출력 파일 경로(생략 시 stdout)")
    rp.set_defaults(func=cmd_report)

    rp = rsub.add_parser("posture",
                         help="보안 포스처 스냅샷 — 시간 경과 추적용 (patch168)")
    rp.add_argument("directory", nargs="?", default=".",
                    help="스캔할 디렉터리 경로(기본 현재 디렉터리)")
    rp.add_argument("--save", action="store_true",
                    help="포스처 히스토리 파일에 저장")
    rp.add_argument("--compare", action="store_true",
                    help="마지막 저장된 포스처와 비교")
    rp.add_argument("--json", action="store_true",
                    help="기계용 JSON 출력")
    rp.add_argument("--history", default=None, metavar="PATH",
                    help="히스토리 파일 경로(기본 .nufi_posture_history.jsonl)")
    rp.set_defaults(func=cmd_report)

    p = sub.add_parser("scan",
                       help="파일/디렉터리 PII + 인젝션 스캔(CI/pre-commit · patch83)")
    p.add_argument("target", nargs="?", default=None, help="스캔할 파일 또는 디렉터리 경로")
    p.add_argument("--pattern", default=None,
                   help="파일 glob 패턴(쉼표 구분, 예: '*.py,*.md,*.txt')")
    p.add_argument("--check-injection", action="store_true",
                   help="프롬프트 인젝션 패턴도 함께 탐지")
    p.add_argument("--json", action="store_true", help="기계용 JSON 출력 (--format json 과 동일)")
    p.add_argument("--format", default=None, choices=["text", "json", "sarif", "csv"],
                   help="출력 포맷 (text: 기본 | json: 구조화 JSON | sarif: SARIF 2.1.0 | csv: CSV)")
    p.add_argument("--output", default=None, metavar="PATH",
                   help="결과를 파일에 기록(stdout 대신). --format 미지정 시 JSON Lines 기본")
    p.add_argument("--exclude", default=None,
                   help="제외할 glob 패턴(쉼표 구분, 예: '*.log,node_modules/**,venv/**')")
    p.add_argument("--fail-on-pii", action="store_true",
                   help="PII 발견 시 exit code 1 (CI 게이트)")
    p.add_argument("--redact", action="store_true",
                   help="PII 를 [REDACTED:TYPE] 으로 치환하여 파일 재작성")
    p.add_argument("--dry-run", action="store_true",
                   help="redact 모드에서 실제 파일 수정 없이 결과만 출력")
    p.add_argument("--no-backup", action="store_true",
                   help="redact 시 .bak 백업 파일 생성 생략")
    p.add_argument("--stats", action="store_true",
                   help="스캔 후 요약 통계 출력(엔티티별·위험도별 집계)")
    p.add_argument("--parallel", type=int, default=1, metavar="N",
                   help="멀티스레드 스캔 워커 수(기본 1 = 순차)")
    p.add_argument("--profile", default=None, metavar="NAME",
                   help="스캔 프로파일 적용(development/ci/strict 등, config/scan_profiles.yaml)")
    p.add_argument("--summary-only", action="store_true",
                   help="요약만 출력(파일별 상세 없음, CI 빠른 체크용)")
    p.add_argument("--verbose", action="store_true",
                   help="발견 항목별 상세 출력(파일/줄/컬럼/엔티티/점수/탐지방법/전후 컨텍스트)")
    p.add_argument("--git-staged", action="store_true",
                   help="git staged 파일만 스캔(pre-commit 훅 통합용, target 불필요)")
    p.add_argument("--ignore-file", default=None, metavar="PATH",
                   help="false positive 억제 파일 경로(기본 .nufi_ignore_findings.yaml)")
    p.add_argument("--baseline", default=None, metavar="PATH",
                   help="베이스라인 파일(JSON/JSONL)과 비교하여 신규 발견만 출력")
    p.add_argument("--count-only", action="store_true",
                   help="발견 건수만 출력(상세 없음, CI 빠른 상태 체크용)")
    p.add_argument("--min-score", type=float, default=0.0, metavar="THRESHOLD",
                   help="최소 신뢰도 점수 (0.0~1.0); 이하 발견 제외 (기본: 0.0)")
    p.add_argument("--only-types", default=None, metavar="TYPES",
                   help="특정 엔티티 타입만 보고(쉼표 구분, 예: KR_RRN,SECRET,CREDIT_CARD)")
    p.add_argument("--pseudonymize", action="store_true",
                   help="PII 발견 시 가명화된 텍스트도 함께 출력; --output 시 가명화 파일 저장 (v0.6.0)")
    p.add_argument("--watch", action="store_true",
                   help="디렉터리 실시간 감시 모드 — 파일 생성/수정 시 자동 스캔 (v0.7.3)")
    p.add_argument("--watch-interval", type=float, default=1.0, metavar="SECONDS",
                   help="--watch 폴링 간격(초, 기본 1.0)")
    p.add_argument("--diff", nargs="?", const="HEAD", default=None, metavar="REF",
                   help="git diff 기반 변경 행만 스캔 (기본 HEAD=staged, 예: HEAD~1, main) (v0.7.5)")
    p.add_argument("--summary", action="store_true",
                   help="스캔 후 집계 대시보드 출력 (타입별·심각도별 ASCII 바 차트, v0.7.7)")
    p.add_argument("-r", "--recursive", action="store_true",
                   help="디렉터리 재귀 스캔 + 집계 리포트 (v0.7.4)")
    p.add_argument("--include", default=None,
                   help="포함 패턴만 스캔(쉼표 구분, 예: '*.py,*.md') (v0.7.4)")
    p.set_defaults(func=cmd_scan)

    p = sub.add_parser("diff",
                       help="git 변경 파일만 PII/인젝션 스캔(PR 리뷰·pre-commit · patch104)")
    p.add_argument("--base", default="HEAD",
                   help="비교 기준 git ref(기본 HEAD = 미커밋 변경)")
    p.add_argument("--fail-on-pii", action="store_true",
                   help="PII 발견 시 exit code 1 (CI 게이트)")
    p.add_argument("--check-injection", action="store_true",
                   help="프롬프트 인젝션 패턴도 함께 탐지")
    p.add_argument("--json", action="store_true", help="기계용 JSON 출력")
    p.add_argument("--pseudonymize", action="store_true",
                   help="PII 발견 시 가명화 결과도 함께 출력 (v0.6.1)")
    p.set_defaults(func=cmd_diff)

    p = sub.add_parser("compare",
                       help="두 스캔 결과(SARIF/JSON) 비교 — new/resolved/unchanged (patch133)")
    p.add_argument("before", help="이전 스캔 결과 파일(SARIF 또는 NuFi JSON)")
    p.add_argument("after", help="이후 스캔 결과 파일(SARIF 또는 NuFi JSON)")
    p.add_argument("--json", action="store_true", help="기계용 JSON 출력")
    p.add_argument("--fail-on-new", action="store_true",
                   help="신규 발견 시 exit 1 (CI 게이트)")
    p.set_defaults(func=cmd_compare)

    p = sub.add_parser("test",
                       help="자가 검증 — PII·인젝션·라우팅·Guard·설정·버전 6체크 (patch135)")
    p.add_argument("--json", action="store_true", help="기계용 JSON 출력")
    p.set_defaults(func=cmd_test)

    p = sub.add_parser("config",
                       help="설정 파일 검증/조회(syntax·필수 필드·regex · patch105, patch187)")
    csub = p.add_subparsers(dest="config_action", required=True)
    cp = csub.add_parser("validate", help="모든 NuFi 설정 파일 유효성 검증")
    cp.add_argument("--config-dir", default=None,
                    help="설정 디렉터리 경로(기본 config/)")
    cp.add_argument("--json", action="store_true", help="기계용 JSON 출력")
    cp.set_defaults(func=cmd_config)
    cs = csub.add_parser("show", help="현재 유효 설정 표시(defaults 적용 후)")
    cs.add_argument("--config-dir", default=None,
                    help="설정 디렉터리 경로(기본 config/)")
    cs.add_argument("--json", action="store_true", help="기계용 JSON 출력")
    cs.set_defaults(func=cmd_config)

    p = sub.add_parser("watch",
                       help="디렉터리 PII 실시간 감시(폴링 · patch92)")
    p.add_argument("directory", help="감시할 디렉터리 경로")
    p.add_argument("--interval", type=float, default=5.0,
                   help="폴링 간격(초, 기본 5)")
    p.add_argument("--check-injection", action="store_true",
                   help="프롬프트 인젝션 패턴도 함께 탐지")
    p.add_argument("--pattern", default=None,
                   help="파일 glob 패턴(쉼표 구분, 예: '*.py,*.md')")
    p.add_argument("--once", action="store_true",
                   help="1회 스캔 후 종료(테스트/CI 용)")
    p.add_argument("--webhook", default=None,
                   help="PII 탐지 시 JSON 페이로드를 POST 할 URL(Slack/Teams 연동)")
    p.set_defaults(func=cmd_watch)

    p = sub.add_parser("lint",
                       help="보안 안티패턴 검사 — 하드코딩 키/디버그/HTTP/eval 탐지 (patch130)")
    p.add_argument("target", help="검사할 파일 또는 디렉터리 경로")
    p.add_argument("--fix", action="store_true",
                   help="자동 수정 가능한 항목 적용(예: http→https)")
    p.add_argument("--fix-report", action="store_true",
                   help="수정 가능 항목을 before/after 미리보기로 출력(수정 미적용)")
    p.add_argument("--json", action="store_true", help="기계용 JSON 출력")
    p.add_argument("--exclude", default=None,
                   help="제외할 glob 패턴(쉼표 구분)")
    p.set_defaults(func=cmd_lint)

    p = sub.add_parser("generate",
                       help="샘플 PII 데이터 생성 — 테스트용 한국어 PII 텍스트 생성 (patch131)")
    p.add_argument("--count", type=int, default=10,
                   help="생성할 샘플 수(기본 10)")
    p.add_argument("--include-injection", action="store_true",
                   help="인젝션 시도 샘플도 포함")
    p.add_argument("--output", default=None, metavar="PATH",
                   help="출력 파일 경로(생략 시 stdout)")
    p.add_argument("--format", choices=["jsonl", "text"], default="jsonl",
                   help="출력 형식(기본 jsonl: 메타데이터 포함, text: 텍스트만)")
    p.add_argument("--seed", type=int, default=None,
                   help="랜덤 시드(재현 가능한 생성)")
    p.set_defaults(func=cmd_generate)

    p = sub.add_parser("inspect",
                       help="통합 보안 분석 — PII + 인젝션 + 라우팅 + 위험도 (patch78)")
    p.add_argument("--text", default=None, help="분석할 텍스트")
    p.add_argument("--file", default=None, help="분석할 파일 경로(라인별 처리)")
    p.add_argument("--json", action="store_true", help="기계용 JSON 출력")
    p.set_defaults(func=cmd_inspect)

    # --- Export (patch122) ---------------------------------------------------- #
    p = sub.add_parser("export",
                       help="탐지 패턴 내보내기(YAML/JSON/regex)")
    esub = p.add_subparsers(dest="export_action", required=True)
    ep = esub.add_parser("patterns", help="PII + 인젝션 탐지 패턴 내보내기")
    ep.add_argument("--format", choices=["yaml", "json", "regex"], default="yaml",
                    help="출력 형식(기본 yaml)")
    ep.set_defaults(func=cmd_export)

    # --- Text transform: mask / redact (patch124) ----------------------------- #
    p = sub.add_parser("mask",
                       help="텍스트 PII 마스킹 — PII를 asterisk(*)로 가림 (patch124)")
    p.add_argument("--text", default=None, help="마스킹할 텍스트")
    p.add_argument("--file", default=None, help="마스킹할 파일 경로(라인별 처리)")
    p.add_argument("--output", default=None, metavar="PATH",
                   help="결과를 파일에 기록(stdout 대신)")
    p.set_defaults(func=cmd_mask)

    p = sub.add_parser("redact",
                       help="텍스트 PII 리댁션 — PII를 타입 태그([TYPE])로 교체 (patch124)")
    p.add_argument("--text", default=None, help="리댁션할 텍스트")
    p.add_argument("--file", default=None, help="리댁션할 파일 경로(라인별 처리)")
    p.add_argument("--output", default=None, metavar="PATH",
                   help="결과를 파일에 기록(stdout 대신)")
    p.set_defaults(func=cmd_redact_text)

    # --- Guard (v0.7.1) ------------------------------------------------------- #
    p = sub.add_parser("guard",
                       help="통합 CI 게이트 — scan + 정책 판정 + 가명화를 한 번에 수행 (v0.7.1)")
    p.add_argument("target", nargs="?", default=None,
                   help="스캔할 파일 경로(생략 시 stdin)")
    p.add_argument("--policy", dest="policy_action_guard",
                   choices=["block", "warn", "pseudonymize"],
                   default="warn",
                   help="PII 발견 시 정책 액션(기본: warn)")
    p.add_argument("--format", choices=["text", "json"], default="text",
                   help="출력 포맷(기본: text)")
    p.add_argument("--output", default=None, metavar="FILE",
                   help="가명화 결과 파일 출력(기본 stdout)")
    p.add_argument("--strict", action="store_true",
                   help="warn을 block으로 승격")
    p.add_argument("--ci", action="store_true",
                   help="CI 파이프라인 모드 — git diff 스캔 + GitHub Actions annotation 출력 (v0.7.5)")
    p.add_argument("--diff-ref", default=None, metavar="REF",
                   help="--ci 모드에서 비교 기준 ref (기본 HEAD=staged, 예: HEAD~1, main) (v0.7.5)")
    p.add_argument("--check-injection", action="store_true",
                   help="프롬프트 인젝션 패턴도 함께 탐지 (--ci 모드)")
    p.set_defaults(func=cmd_guard)

    # --- Pseudonymize (v0.6.0) ----------------------------------------------- #
    p = sub.add_parser("pseudonymize",
                       help="가역 가명화 — PII를 surrogate 토큰(⟦P1⟧)으로 치환, 세션 ID로 원복 가능 (v0.6.0)")
    p.add_argument("text", nargs="?", default=None,
                   help="가명화할 텍스트(인라인)")
    p.add_argument("--file", default=None, metavar="PATH",
                   help="가명화할 입력 파일 경로")
    p.add_argument("--output", default=None, metavar="PATH",
                   help="결과를 파일에 기록(stdout 대신)")
    p.add_argument("--restore", action="store_true",
                   help="surrogate → 원본 복원 모드")
    p.add_argument("--session", default=None, metavar="ID",
                   help="세션 ID(--restore 시 필수, 가명화 시 자동생성)")
    p.add_argument("--json", action="store_true",
                   help="기계용 JSON 출력")
    p.add_argument("--format", default=None, choices=["text", "json"],
                   help="출력 형식(text: 기본, json: JSON)")
    p.add_argument("--check", action="store_true",
                   help="파일별 PII 체크 — PII 발견 시 exit 1 + 가명화 제안 (pre-commit용)")
    p.add_argument("--quality-report", action="store_true",
                   help="품질 메트릭 리포트 출력 (커버리지·역변환 정확도·타입별 통계)")
    p.add_argument("--stream", action="store_true",
                   help="스트리밍 원복 모드 — stdin 에서 청크를 읽어 실시간 역치환 (--session 필수)")
    p.set_defaults(func=cmd_pseudonymize)

    p = sub.add_parser("explain",
                       help="텍스트 탐지 결과 상세 설명 — PII·인젝션·정책·라우팅 근거 출력 (patch116)")
    p.add_argument("--text", required=True, help="분석할 텍스트")
    p.add_argument("--json", action="store_true", help="기계용 JSON 출력")
    p.set_defaults(func=cmd_explain)

    p = sub.add_parser("pipeline",
                       help="체인 파이프라인 — detect→decide→transform→route 한 번에 (patch139)")
    p.add_argument("--text", required=True, help="처리할 텍스트")
    p.add_argument("--actions", default=None,
                   help="실행할 액션(쉼표 구분: detect,mask,redact,pseudonymize,route,block-check). "
                        "생략 시 전체 실행")
    p.add_argument("--json", action="store_true", help="기계용 JSON 출력")
    p.set_defaults(func=cmd_pipeline)

    p = sub.add_parser("route",
                       help="PII 라우팅 결정 테스트 — 텍스트의 PII 감지·모델 라우팅 판정 출력")
    p.add_argument("--text", default=None, help="라우팅 판정할 텍스트")
    p.add_argument("--file", default=None,
                   help="라인별 PII 라우팅할 입력 파일 경로")
    p.add_argument("--stdin", action="store_true",
                   help="stdin 에서 라인별로 읽어 PII 라우팅(파이프 용도)")
    p.add_argument("--summary", action="store_true",
                   help="--file/--stdin 사용 시 요약 통계 출력")
    p.add_argument("--model", default=None,
                   help="요청 모델명(기본: cloud_model)")
    p.add_argument("--local-model", default="nufi-local",
                   help="PII 감지 시 라우팅할 로컬 모델명(기본 nufi-local)")
    p.add_argument("--cloud-model", default="nufi-cloud",
                   help="PII 미감지 시 허용할 클라우드 모델명(기본 nufi-cloud)")
    p.add_argument("--check-injection", action="store_true",
                   help="프롬프트 인젝션 탐지도 함께 수행")
    p.add_argument("--min-severity", default="low",
                   choices=["low", "medium", "high", "critical"],
                   help="인젝션 탐지 최소 심각도(기본: low)")
    p.add_argument("--json", action="store_true", help="기계용 JSON 출력")
    p.set_defaults(func=cmd_route)

    p = sub.add_parser("benchmark",
                       help="정확도(커밋 산출물 게이트)+가명화(라이브) 벤치마크 단일 재현 "
                            "— 전체 PASS 시 exit 0, 미달 시 1")
    p.add_argument("--only", choices=["accuracy", "pseudonymize", "injection"], default=None,
                   help="한 축만 실행(기본: 셋 다)")
    p.add_argument("--json", action="store_true",
                   help="사람 친화 요약 대신 원시 JSON 리포트 출력")
    p.add_argument("--json-out", default=None,
                   help="JSON 리포트를 파일로도 기록(경로)")
    p.set_defaults(func=cmd_benchmark)

    # --- History (patch141) -------------------------------------------------- #
    p = sub.add_parser("history",
                       help="최근 활동 로그 조회 — 스캔·차단·라우팅 이벤트 (patch141)")
    p.add_argument("--last", type=int, default=20,
                   help="최근 N개 이벤트 표시(기본 20)")
    p.add_argument("--type", choices=["scan", "block", "route", "all"], default="all",
                   help="이벤트 유형 필터(기본 all)")
    p.add_argument("--json", action="store_true", help="기계용 JSON 출력")
    p.set_defaults(func=cmd_history)

    # --- Playground (patch145) ------------------------------------------------ #
    p = sub.add_parser("playground",
                       help="인터랙티브 PII 분석 REPL — 실시간 텍스트 분석 실험 (patch145)")
    p.add_argument("--text", default=None, help="분석할 텍스트(비인터랙티브)")
    p.add_argument("--mode", choices=["inspect", "mask", "redact"], default="inspect",
                   help="출력 모드(기본 inspect)")
    p.add_argument("--no-emoji", action="store_true", default=False,
                   help="이모지 대신 텍스트 대체 출력 (NUFI_NO_EMOJI=1 환경변수도 지원)")
    p.set_defaults(func=cmd_playground)

    # --- Summary (patch147) -------------------------------------------------- #
    p = sub.add_parser("summary",
                       help="프로젝트 헬스 대시보드 — 설정·활동·위험·닥터·버전 한 화면 요약 (patch147)")
    p.add_argument("--json", action="store_true", help="기계용 JSON 출력")
    p.set_defaults(func=cmd_summary)

    # --- Dashboard (patch174) ------------------------------------------------ #
    p = sub.add_parser("dashboard",
                       help="ASCII 터미널 보안 대시보드 — 등급·테스트·위험·닥터·인젝션 한 화면 (patch174)")
    p.add_argument("--json", action="store_true", help="기계용 JSON 출력")
    p.set_defaults(func=cmd_dashboard)

    # --- Serve (patch155) ---------------------------------------------------- #
    p = sub.add_parser("serve",
                       help="HTTP API 서버 — REST 엔드포인트로 탐지 기능 제공 (patch155)")
    p.add_argument("--host", default="localhost",
                   help="바인드 호스트(기본 localhost)")
    p.add_argument("--port", type=int, default=8000,
                   help="바인드 포트(기본 8000)")
    p.add_argument("--openapi", action="store_true", default=False,
                   help="OpenAPI JSON 스펙을 stdout으로 출력 후 종료")
    p.set_defaults(func=cmd_serve)

    # --- Stats (patch112) ---------------------------------------------------- #
    from enforcement.stats_cmd import cmd_stats
    p = sub.add_parser("stats",
                       help="NuFi 설정·탐지 역량 요약 통계")
    p.add_argument("--json", action="store_true", help="기계용 JSON 출력")
    p.set_defaults(func=cmd_stats)

    # --- Shell completions (patch109) ---------------------------------------- #
    from enforcement.completions_cmd import cmd_completions
    p = sub.add_parser("completions",
                       help="셸 자동완성 스크립트 출력(bash/zsh)")
    p.add_argument("shell", choices=["bash", "zsh"],
                   help="대상 셸(bash 또는 zsh)")
    p.set_defaults(func=cmd_completions)

    try:
        args = ap.parse_args(argv)
    except SystemExit as exc:
        # argparse calls sys.exit on error; re-raise with the same code
        # but the error message has already been printed by argparse.
        raise

    # ── Friendly pre-flight checks (patch144) ─────────────────────────── #
    cmd = getattr(args, "cmd", None)
    if cmd == "scan" and not getattr(args, "target", None) and not getattr(args, "git_staged", False):
        print("Error: please specify a path to scan.\n"
              "Usage: nufi-egress scan <path>", file=sys.stderr)
        return 1
    if cmd == "route":
        has_input = (getattr(args, "text", None)
                     or getattr(args, "file", None)
                     or getattr(args, "stdin", False))
        if not has_input:
            print("Error: please specify --text, --file, or --stdin.\n"
                  "Usage: nufi-egress route --text <text>", file=sys.stderr)
            return 1
    if cmd == "explain" and not getattr(args, "text", None):
        print("Error: please specify --text.\n"
              "Usage: nufi-egress explain --text <text>", file=sys.stderr)
        return 1

    # ── Global exception handler (patch144) ─────────────────────────── #
    try:
        return args.func(args)
    except FileNotFoundError as exc:
        print(f"Error: file not found: {exc}", file=sys.stderr)
        return 1
    except PermissionError as exc:
        print(f"Error: permission denied: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130
    except BrokenPipeError:
        return 0
    except Exception as exc:
        print(f"Error: {exc}\n"
              "Run with --help for usage information.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

"""E2E 가명화 품질 벤치마크 파이프라인 (CMP-351).

원문→LLM→원문응답 vs 가명화→LLM→원복응답을 자동 비교하는 벤치마크.
CMP-350 PII QA 평가셋(data/pii_qa_eval.jsonl)을 입력으로 사용.

LLM 백엔드:
  - mock (기본): 미리 정의된 expected_answer 기반 — API 키 불필요.
  - claude: Anthropic SDK (ANTHROPIC_API_KEY 필요).
  - openai: OpenAI SDK (OPENAI_API_KEY 필요).

실행:
  python3 scripts/bench_pseudonymize_e2e.py                           # mock 모드
  python3 scripts/bench_pseudonymize_e2e.py --llm claude              # Claude API
  python3 scripts/bench_pseudonymize_e2e.py --llm openai              # OpenAI 호환
  python3 scripts/bench_pseudonymize_e2e.py --json-out docs/reports/pseudonymize-e2e-quality.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from egress_audit import MappingVault, ReversibleEgress  # noqa: E402
from egress_audit.surrogate import REVERSIBLE_ENTITIES, LB, RB  # noqa: E402

SEED = 20260708
EVAL_SET = ROOT / "data" / "pii_qa_eval.jsonl"

# ── 품질 목표 ─────────────────────────────────────────────────────────────
TARGETS = {
    "rouge_l": 0.90,           # Utility Retention (ROUGE-L) ≥ 0.90
    "pii_protection_rate": 1.0,  # 원본 PII 가 pseudonymized_q 에 0% 잔존
    "roundtrip_fidelity": 0.95,  # PII 원복 정확도 ≥ 0.95
}


# ── ROUGE-L (외부 의존 없이 자체 구현) ────────────────────────────────────
def _lcs_length(x: List[str], y: List[str]) -> int:
    """최장 공통 부분수열(LCS) 길이."""
    m, n = len(x), len(y)
    if m == 0 or n == 0:
        return 0
    # 공간 O(n) DP
    prev = [0] * (n + 1)
    for i in range(1, m + 1):
        curr = [0] * (n + 1)
        for j in range(1, n + 1):
            if x[i - 1] == y[j - 1]:
                curr[j] = prev[j - 1] + 1
            else:
                curr[j] = max(prev[j], curr[j - 1])
        prev = curr
    return prev[n]


def _tokenize(text: str) -> List[str]:
    """공백·구두점 기준 토큰화 (한국어 + 영어 혼합 대응)."""
    return [t for t in re.findall(r'\S+', text) if t]


def rouge_l(reference: str, hypothesis: str) -> float:
    """ROUGE-L F1 점수 (0~1)."""
    ref_tokens = _tokenize(reference)
    hyp_tokens = _tokenize(hypothesis)
    if not ref_tokens or not hyp_tokens:
        return 1.0 if ref_tokens == hyp_tokens else 0.0
    lcs = _lcs_length(ref_tokens, hyp_tokens)
    precision = lcs / len(hyp_tokens)
    recall = lcs / len(ref_tokens)
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def exact_match(reference: str, hypothesis: str) -> bool:
    """정규화 후 정확 일치."""
    return reference.strip() == hypothesis.strip()


# ── 평가셋 로드 ──────────────────────────────────────────────────────────
@dataclass
class QASample:
    id: str
    question: str
    expected_answer: str
    pii_entities: List[dict]
    category: str


def load_eval_set(path: Path = EVAL_SET) -> List[QASample]:
    samples = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            samples.append(QASample(
                id=obj["id"],
                question=obj["question"],
                expected_answer=obj["expected_answer"],
                pii_entities=obj.get("pii_entities", []),
                category=obj.get("category", ""),
            ))
    return samples


# ── LLM 백엔드 ───────────────────────────────────────────────────────────
class MockLLM:
    """Mock LLM: question→expected_answer 매핑 기반. API 불필요.

    핵심 가정: 실제 LLM 이 surrogate 토큰을 그대로 에코한다고 가정.
    가명화된 질문을 받으면 expected_answer 의 PII 부분을 동일한 surrogate 로 치환해 반환.
    """

    def __init__(self, eval_set: List[QASample]):
        self._by_question: Dict[str, QASample] = {}
        for s in eval_set:
            self._by_question[s.question] = s

    def generate(self, prompt: str) -> str:
        # 정확 매칭 → expected_answer 반환 (원문 경로).
        if prompt in self._by_question:
            return self._by_question[prompt].expected_answer
        # 가명화된 질문 → PII entity 값을 사용해 정확 매핑 추출.
        return self._generate_pseudo_response(prompt)

    def _generate_pseudo_response(self, pseudo_q: str) -> str:
        """가명화된 질문에서 원본 샘플을 찾아 expected_answer 의 PII→surrogate 치환."""
        # 원본 샘플 식별: 각 샘플의 PII 값을 surrogate 로 바꾸면 pseudo_q 가 되는 샘플.
        best_sample = None
        best_score = -1.0
        for sample in self._by_question.values():
            score = rouge_l(sample.question, pseudo_q)
            if score > best_score:
                best_score = score
                best_sample = sample
        if not best_sample or best_score < 0.3:
            return pseudo_q

        # PII value→surrogate 매핑 추출: 원본 질문의 PII 위치에 있는 surrogate 를 찾음.
        mapping = self._extract_pii_mapping(best_sample, pseudo_q)
        # expected_answer 에서 PII 를 surrogate 로 치환 (긴 값 우선)
        answer = best_sample.expected_answer
        for pii_val, sur in sorted(mapping.items(), key=lambda x: -len(x[0])):
            answer = answer.replace(pii_val, sur)
        return answer

    def _extract_pii_mapping(self, sample: QASample, pseudo_q: str) -> Dict[str, str]:
        """PII entity 의 알려진 위치를 이용해 원본 PII→surrogate 매핑 추출.

        원본 질문에서 entity 가 (start, end) 위치에 있었으므로,
        가명화 후 텍스트에서 해당 위치 주변의 surrogate 토큰을 찾는다.
        오프셋 드리프트(PII→surrogate 치환으로 인한 길이 변화)를 추적한다.
        """
        mapping: Dict[str, str] = {}
        sur_pattern = re.compile(r'⟦[A-Z]{1,2}\d+⟧')

        # 엔티티를 시작 위치 순으로 정렬
        entities = sorted(sample.pii_entities, key=lambda e: e["start"])
        # 가명화 텍스트에서 모든 surrogate 위치 추출
        surrogates = list(sur_pattern.finditer(pseudo_q))

        # 간단한 순서 매칭: i번째 entity → i번째 surrogate
        for i, ent in enumerate(entities):
            if i < len(surrogates):
                mapping[ent["value"]] = surrogates[i].group()

        return mapping


class ClaudeLLM:
    """Anthropic Claude API 백엔드."""

    def __init__(self, model: str = "claude-sonnet-4-20250514"):
        try:
            import anthropic
        except ImportError:
            raise ImportError("anthropic 패키지 필요: pip install anthropic")
        self.client = anthropic.Anthropic()
        self.model = model

    def generate(self, prompt: str) -> str:
        msg = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text


class ClaudeCLI:
    """Claude CLI (claude --print) 백엔드 — Paperclip 등 이미 인증된 환경에서 사용."""

    def __init__(self):
        if not shutil.which("claude"):
            raise RuntimeError("claude CLI 미설치 또는 PATH 에 없음")

    def generate(self, prompt: str) -> str:
        result = subprocess.run(
            ["claude", "--print", "-p", prompt],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            raise RuntimeError(f"claude CLI 실패: {result.stderr[:200]}")
        return result.stdout.strip()


class OpenAILLM:
    """OpenAI 호환 API 백엔드."""

    def __init__(self, model: str = "gpt-4o-mini"):
        try:
            import openai
        except ImportError:
            raise ImportError("openai 패키지 필요: pip install openai")
        self.client = openai.OpenAI()
        self.model = model

    def generate(self, prompt: str) -> str:
        resp = self.client.chat.completions.create(
            model=self.model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.choices[0].message.content


# ── 벤치마크 파이프라인 ───────────────────────────────────────────────────
@dataclass
class SampleResult:
    id: str
    category: str
    # 원문 경로
    original_response: str
    # 가명화 경로
    pseudonymized_question: str
    pseudo_response: str
    restored_response: str
    # PII 보호
    pii_entities: List[dict]
    pii_leaked: List[str]              # pseudonymized_q 에 남은 원본 PII
    pii_restored: List[str]            # restored_response 에서 정확 원복된 PII
    pii_total: int
    # 지표
    rouge_l: float
    exact_match: bool
    pii_protection: float              # 1.0 - (leaked / total)
    roundtrip_fidelity: float          # restored / total
    latency_pseudo_ms: float
    latency_restore_ms: float
    # 실패 여부
    degraded: bool                     # ROUGE-L < 목표


def run_benchmark(
    llm_backend: str = "mock",
    eval_path: Path = EVAL_SET,
    llm_model: Optional[str] = None,
) -> dict:
    """E2E 벤치마크 실행. 결과 dict 반환."""
    samples = load_eval_set(eval_path)
    if not samples:
        raise ValueError(f"평가셋 비어 있음: {eval_path}")

    # LLM 초기화
    mock_fallback = False
    if llm_backend == "mock":
        llm = MockLLM(samples)
    elif llm_backend == "claude":
        if not os.environ.get("ANTHROPIC_API_KEY"):
            print("⚠ ANTHROPIC_API_KEY 미설정 → mock 모드로 폴백하여 파이프라인만 검증")
            llm = MockLLM(samples)
            mock_fallback = True
        else:
            llm = ClaudeLLM(model=llm_model or "claude-sonnet-4-20250514")
    elif llm_backend == "claude-cli":
        llm = ClaudeCLI()
    elif llm_backend == "openai":
        if not os.environ.get("OPENAI_API_KEY"):
            print("⚠ OPENAI_API_KEY 미설정 → mock 모드로 폴백하여 파이프라인만 검증")
            llm = MockLLM(samples)
            mock_fallback = True
        else:
            llm = OpenAILLM(model=llm_model or "gpt-4o-mini")
    else:
        raise ValueError(f"지원하지 않는 LLM 백엔드: {llm_backend}")

    results: List[SampleResult] = []
    rev = ReversibleEgress()

    for idx, sample in enumerate(samples):
        sid = f"e2e-{idx}"

        # A. 원문 경로: LLM(question)
        original_response = llm.generate(sample.question)

        # B. 가명화 경로
        t0 = time.perf_counter()
        pseudo_result = rev.pseudonymize(sample.question, sid)
        t_pseudo = (time.perf_counter() - t0) * 1000

        pseudo_q = pseudo_result.transformed_text

        # PII 보호 검사: pseudonymized_q 에 원본 PII 가 남아있는지
        pii_leaked = []
        for ent in sample.pii_entities:
            if ent["value"] in pseudo_q:
                pii_leaked.append(ent["value"])

        # LLM(pseudonymized_question)
        pseudo_response = llm.generate(pseudo_q)

        # 원복
        t0 = time.perf_counter()
        restored_response, stats = rev.deanonymize(pseudo_response, sid)
        t_restore = (time.perf_counter() - t0) * 1000

        # PII 원복 검사: restored_response 에서 원본 PII 가 정확히 원복되었는지
        pii_restored = []
        for ent in sample.pii_entities:
            if ent["value"] in restored_response:
                pii_restored.append(ent["value"])

        pii_total = len(sample.pii_entities)
        pii_prot = 1.0 - (len(pii_leaked) / pii_total) if pii_total > 0 else 1.0
        rt_fidelity = len(pii_restored) / pii_total if pii_total > 0 else 1.0

        # C. 비교
        rl = rouge_l(original_response, restored_response)
        em = exact_match(original_response, restored_response)

        sr = SampleResult(
            id=sample.id,
            category=sample.category,
            original_response=original_response,
            pseudonymized_question=pseudo_q,
            pseudo_response=pseudo_response,
            restored_response=restored_response,
            pii_entities=sample.pii_entities,
            pii_leaked=pii_leaked,
            pii_restored=pii_restored,
            pii_total=pii_total,
            rouge_l=rl,
            exact_match=em,
            pii_protection=pii_prot,
            roundtrip_fidelity=rt_fidelity,
            latency_pseudo_ms=round(t_pseudo, 2),
            latency_restore_ms=round(t_restore, 2),
            degraded=rl < TARGETS["rouge_l"],
        )
        results.append(sr)
        rev.end_session(sid)

    return _aggregate(results, llm_backend, mock_fallback)


def _aggregate(results: List[SampleResult], llm_backend: str, mock_fallback: bool = False) -> dict:
    """개별 결과를 집계."""
    n = len(results)
    if n == 0:
        return {"error": "no samples"}

    # PII 포함 샘플만 (control 제외)
    pii_samples = [r for r in results if r.pii_total > 0]
    control_samples = [r for r in results if r.pii_total == 0]

    # 전체 지표
    avg_rouge = round(sum(r.rouge_l for r in results) / n, 4)
    em_count = sum(1 for r in results if r.exact_match)
    em_rate = round(em_count / n, 4)

    # PII 보호율
    total_pii = sum(r.pii_total for r in pii_samples)
    total_leaked = sum(len(r.pii_leaked) for r in pii_samples)
    pii_protection_rate = round(1.0 - (total_leaked / total_pii), 4) if total_pii > 0 else 1.0

    # 원복 충실도
    total_restored = sum(len(r.pii_restored) for r in pii_samples)
    roundtrip_fidelity = round(total_restored / total_pii, 4) if total_pii > 0 else 1.0

    # 레이턴시
    pseudo_latencies = [r.latency_pseudo_ms for r in results]
    restore_latencies = [r.latency_restore_ms for r in results]
    pseudo_latencies.sort()
    restore_latencies.sort()

    def _percentile(arr, p):
        if not arr:
            return 0.0
        idx = int(len(arr) * p)
        idx = min(idx, len(arr) - 1)
        return round(arr[idx], 2)

    # 타입별 분석
    by_type: Dict[str, dict] = {}
    for r in pii_samples:
        for ent in r.pii_entities:
            et = ent["type"]
            d = by_type.setdefault(et, {"total": 0, "leaked": 0, "restored": 0})
            d["total"] += 1
            if ent["value"] in r.pseudonymized_question:
                d["leaked"] += 1
            if ent["value"] in r.restored_response:
                d["restored"] += 1
    for et, d in by_type.items():
        d["protection_rate"] = round(1.0 - d["leaked"] / d["total"], 4) if d["total"] > 0 else 1.0
        d["roundtrip_fidelity"] = round(d["restored"] / d["total"], 4) if d["total"] > 0 else 1.0

    # 카테고리별 분석
    by_category: Dict[str, dict] = {}
    for r in results:
        d = by_category.setdefault(r.category, {"n": 0, "rouge_l_sum": 0.0, "em": 0})
        d["n"] += 1
        d["rouge_l_sum"] += r.rouge_l
        d["em"] += 1 if r.exact_match else 0
    for cat, d in by_category.items():
        d["avg_rouge_l"] = round(d["rouge_l_sum"] / d["n"], 4)
        d["em_rate"] = round(d["em"] / d["n"], 4)
        del d["rouge_l_sum"]

    # 실패 케이스
    degraded = [
        {
            "id": r.id,
            "category": r.category,
            "rouge_l": r.rouge_l,
            "pii_leaked": r.pii_leaked,
            "pii_restored": r.pii_restored,
            "pii_total": r.pii_total,
        }
        for r in results if r.degraded
    ]

    # 게이트 판정
    acceptance = {
        f"rouge_l>={TARGETS['rouge_l']}": avg_rouge >= TARGETS["rouge_l"],
        f"pii_protection_rate=={TARGETS['pii_protection_rate']}": pii_protection_rate >= TARGETS["pii_protection_rate"],
        f"roundtrip_fidelity>={TARGETS['roundtrip_fidelity']}": roundtrip_fidelity >= TARGETS["roundtrip_fidelity"],
    }

    report = {
        "benchmark": "pseudonymize-e2e-quality",
        "llm_backend": llm_backend,
        "mock_fallback": mock_fallback,
        "eval_set": str(EVAL_SET.relative_to(ROOT)),
        "n_samples": n,
        "n_pii_samples": len(pii_samples),
        "n_control_samples": len(control_samples),
        "seed": SEED,
        "targets": TARGETS,
        "scores": {
            "utility_retention_rouge_l": avg_rouge,
            "exact_match_rate": em_rate,
            "exact_match_n": f"{em_count}/{n}",
            "pii_protection_rate": pii_protection_rate,
            "pii_protection_n": f"{total_pii - total_leaked}/{total_pii}",
            "roundtrip_fidelity": roundtrip_fidelity,
            "roundtrip_fidelity_n": f"{total_restored}/{total_pii}",
        },
        "latency": {
            "pseudonymize_ms": {
                "p50": _percentile(pseudo_latencies, 0.5),
                "p95": _percentile(pseudo_latencies, 0.95),
                "p99": _percentile(pseudo_latencies, 0.99),
            },
            "deanonymize_ms": {
                "p50": _percentile(restore_latencies, 0.5),
                "p95": _percentile(restore_latencies, 0.95),
                "p99": _percentile(restore_latencies, 0.99),
            },
        },
        "by_type": dict(sorted(by_type.items())),
        "by_category": dict(sorted(by_category.items())),
        "degraded_samples": degraded,
        "acceptance": acceptance,
        "acceptance_pass": all(acceptance.values()),
    }
    return report


# ── CLI ───────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="E2E 가명화 품질 벤치마크 (CMP-351)")
    ap.add_argument("--llm", default="mock", choices=["mock", "claude", "claude-cli", "openai"],
                    help="LLM 백엔드 (기본: mock)")
    ap.add_argument("--llm-model", default=None,
                    help="LLM 모델 이름 오버라이드")
    ap.add_argument("--eval-set", default=str(EVAL_SET),
                    help="평가셋 경로")
    ap.add_argument("--json-out", default=None,
                    help="JSON 리포트 출력 경로")
    args = ap.parse_args()

    report = run_benchmark(
        llm_backend=args.llm,
        eval_path=Path(args.eval_set),
        llm_model=args.llm_model,
    )

    # 콘솔 요약
    scores = report["scores"]
    print("=" * 60)
    print("E2E 가명화 품질 벤치마크 결과")
    print("=" * 60)
    print(f"  LLM 백엔드:       {report['llm_backend']}")
    print(f"  샘플 수:          {report['n_samples']} (PII: {report['n_pii_samples']}, Control: {report['n_control_samples']})")
    print()
    print("  [지표]                          달성값     목표      판정")
    rl_key = "rouge_l>=" + str(TARGETS["rouge_l"])
    pp_key = "pii_protection_rate==" + str(TARGETS["pii_protection_rate"])
    rf_key = "roundtrip_fidelity>=" + str(TARGETS["roundtrip_fidelity"])
    rl_pass = "PASS" if report["acceptance"][rl_key] else "FAIL"
    pp_pass = "PASS" if report["acceptance"][pp_key] else "FAIL"
    rf_pass = "PASS" if report["acceptance"][rf_key] else "FAIL"
    print(f"  Utility (ROUGE-L):              {scores['utility_retention_rouge_l']:.4f}    >={TARGETS['rouge_l']:.2f}    {rl_pass}")
    print(f"  Exact Match:                    {scores['exact_match_rate']:.4f}    -         ({scores['exact_match_n']})")
    print(f"  PII Protection Rate:            {scores['pii_protection_rate']:.4f}    =={TARGETS['pii_protection_rate']:.2f}    {pp_pass}")
    print(f"  Roundtrip Fidelity:             {scores['roundtrip_fidelity']:.4f}    >={TARGETS['roundtrip_fidelity']:.2f}    {rf_pass}")
    print()

    # 타입별
    if report["by_type"]:
        print("  [타입별 분석]")
        for et, d in report["by_type"].items():
            print(f"    {et:20s}  보호={d['protection_rate']:.4f}  원복={d['roundtrip_fidelity']:.4f}  (n={d['total']})")
        print()

    # 레이턴시
    lat = report["latency"]
    print(f"  [레이턴시 오버헤드]")
    print(f"    가명화 p50={lat['pseudonymize_ms']['p50']:.1f}ms  p95={lat['pseudonymize_ms']['p95']:.1f}ms")
    print(f"    원복   p50={lat['deanonymize_ms']['p50']:.1f}ms  p95={lat['deanonymize_ms']['p95']:.1f}ms")
    print()

    # 실패 케이스
    if report["degraded_samples"]:
        print(f"  [품질 저하 샘플] ({len(report['degraded_samples'])}건)")
        for d in report["degraded_samples"][:10]:
            print(f"    {d['id']} ({d['category']}): ROUGE-L={d['rouge_l']:.4f}"
                  f"  leaked={d['pii_leaked']}  restored={d['pii_restored']}/{d['pii_total']}")
        if len(report["degraded_samples"]) > 10:
            print(f"    ... 외 {len(report['degraded_samples']) - 10}건")
        print()

    verdict = "PASS" if report["acceptance_pass"] else "FAIL"
    print(f"  종합: {verdict}")
    print("=" * 60)

    # JSON 출력
    out = json.dumps(report, ensure_ascii=False, indent=2)
    if args.json_out:
        Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_out).write_text(out + "\n", encoding="utf-8")
        print(f"\n리포트 저장: {args.json_out}")

    return 0 if report["acceptance_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())

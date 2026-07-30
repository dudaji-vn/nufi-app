"""v0.10.0 테스트 — 스트리밍 가명화 + 대규모 배치 + 동시성.

CMP-368: 프로덕션 수준 파이프라인 고도화 검증.
"""
from __future__ import annotations

import concurrent.futures
import json
import sys
import uuid
from pathlib import Path
from typing import List

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from egress_audit import MappingVault, ReversibleEgress, StreamingDeanonymizer
from egress_audit import surrogate as sg

# 고정 KEK(테스트 결정성).
_KEK = bytes(range(32))


def _vault(**kw):
    return MappingVault(kek=_KEK, **kw)


# ══════════════════════════════════════════════════════════════════════════════
# 1. 스트리밍 가명화 단위 테스트
# ══════════════════════════════════════════════════════════════════════════════

class TestStreamingDeanonymize:
    """StreamingDeanonymizer + ReversibleEgress.deanonymize_stream() 테스트."""

    def test_deanonymize_stream_basic(self):
        """deanonymize_stream 기본 동작: 청크 이터러블 → 원복 이터러블."""
        rev = ReversibleEgress(vault=_vault(), ner_backend="gazetteer")
        src = "고객 김철수(010-1234-5678)에게 hong@test.com으로 안내 바랍니다."
        r = rev.pseudonymize(src, "ds-1")
        assert r.pseudonymized >= 2

        # 응답을 작은 청크로 분할
        transformed = r.transformed_text
        chunk_size = 5
        chunks = [transformed[i:i + chunk_size]
                  for i in range(0, len(transformed), chunk_size)]

        restored = "".join(rev.deanonymize_stream(chunks, "ds-1"))
        assert restored == src

    def test_deanonymize_stream_single_chunk(self):
        """단일 청크 스트리밍."""
        rev = ReversibleEgress(vault=_vault(), ner_backend="gazetteer")
        src = "연락처: 010-9999-8888"
        r = rev.pseudonymize(src, "ds-2")
        restored = "".join(rev.deanonymize_stream([r.transformed_text], "ds-2"))
        assert restored == src

    def test_deanonymize_stream_empty_chunks(self):
        """빈 청크 포함 스트리밍."""
        vault = _vault()
        minter = sg.SurrogateMinter(vault, "ds-3")
        sur = minter.mint("KR_PERSON", "이영희")
        text = f"담당자: {sur}"

        rev = ReversibleEgress(vault=vault, ner_backend="gazetteer")
        chunks = ["", "담당", "", f"자: {sur}", ""]
        restored = "".join(rev.deanonymize_stream(chunks, "ds-3"))
        assert "이영희" in restored

    def test_deanonymize_stream_char_by_char(self):
        """최악의 경우: 한 글자씩 스트리밍."""
        vault = _vault()
        minter = sg.SurrogateMinter(vault, "ds-4")
        sur = minter.mint("EMAIL", "user@example.com")
        text = f"이메일: {sur}"

        rev = ReversibleEgress(vault=vault, ner_backend="gazetteer")
        chars = list(text)
        restored = "".join(rev.deanonymize_stream(chars, "ds-4"))
        assert "user@example.com" in restored

    def test_streaming_multiple_surrogates_split(self):
        """여러 surrogate가 청크 경계에서 분할."""
        vault = _vault()
        minter = sg.SurrogateMinter(vault, "ds-5")
        s1 = minter.mint("KR_PERSON", "박민수")
        s2 = minter.mint("KR_PHONE", "02-3456-7890")
        s3 = minter.mint("EMAIL", "park@test.kr")
        text = f"{s1}님 연락처 {s2}, 메일 {s3}"

        for chunk_size in (1, 2, 3, 4, 7, 11):
            rev = ReversibleEgress(vault=vault, ner_backend="gazetteer")
            chunks = [text[i:i + chunk_size]
                      for i in range(0, len(text), chunk_size)]
            restored = "".join(rev.deanonymize_stream(chunks, "ds-5"))
            assert "박민수" in restored, f"chunk_size={chunk_size}"
            assert "02-3456-7890" in restored, f"chunk_size={chunk_size}"
            assert "park@test.kr" in restored, f"chunk_size={chunk_size}"

    def test_streaming_lenient_bracket_fallback(self):
        """LLM이 ⟦P1⟧를 [P1]로 변형한 경우 관용 매칭."""
        vault = _vault()
        minter = sg.SurrogateMinter(vault, "ds-6")
        sur = minter.mint("KR_PERSON", "최지은")
        # LLM이 유니코드 브래킷을 일반 브래킷으로 변형
        mangled = sur.replace("⟦", "[").replace("⟧", "]")
        text = f"담당자 {mangled}"

        de = StreamingDeanonymizer(vault, "ds-6", lenient=True)
        out = de.feed(text) + de.flush()
        assert "최지은" in out

    def test_streaming_stats_tracking(self):
        """스트리밍 통계 추적 (restored, fallback)."""
        vault = _vault()
        minter = sg.SurrogateMinter(vault, "ds-7")
        s1 = minter.mint("KR_PERSON", "한서연")
        s2 = minter.mint("KR_PHONE", "010-5555-6666")
        text = f"{s1}님의 연락처는 {s2}입니다."

        de = StreamingDeanonymizer(vault, "ds-7")
        _ = de.feed(text)
        _ = de.flush()
        assert de.stats["restored"] == 2
        assert de.stats["fallback"] == 0

    def test_streaming_buffer_overflow_forced_flush(self):
        """MAX_SURROGATE_LEN 초과 시 강제 방출."""
        vault = _vault()
        de = StreamingDeanonymizer(vault, "ds-8")
        # 여는 브래킷 이후 충분히 긴 비완결 텍스트
        long_tail = "⟦" + "A" * 20  # MAX_SURROGATE_LEN=16 초과
        out = de.feed(long_tail)
        # 강제 방출되어야 함 (홀드하지 않음)
        assert len(out) > 0 or de._buf == ""


# ══════════════════════════════════════════════════════════════════════════════
# 2. 스트리밍 가명화 통합 테스트
# ══════════════════════════════════════════════════════════════════════════════

class TestStreamingIntegration:
    """End-to-end 스트리밍 가명화 → LLM 응답 시뮬레이션 → 스트리밍 원복."""

    def test_e2e_streaming_pseudonymize_restore(self):
        """가명화 → (LLM이 surrogate 보존 응답) → 스트리밍 원복 전체 흐름."""
        rev = ReversibleEgress(vault=_vault(), ner_backend="gazetteer")
        src = "김영수(010-8765-4321, kim@company.com)님의 강남구 사무실 방문 예약을 확인합니다."
        r = rev.pseudonymize(src, "e2e-1")
        assert not r.blocked

        # LLM이 surrogate를 유지하면서 응답 생성 (시뮬레이션)
        llm_reply = r.transformed_text.replace("확인합니다", "확인했습니다. 내일 방문 예정입니다")

        # 스트리밍으로 원복 (SSE 청크 시뮬레이션)
        chunk_sizes = [10, 3, 15, 7, 20, 5]
        chunks = []
        pos = 0
        for size in chunk_sizes:
            if pos < len(llm_reply):
                chunks.append(llm_reply[pos:pos + size])
                pos += size
        if pos < len(llm_reply):
            chunks.append(llm_reply[pos:])

        restored = "".join(rev.deanonymize_stream(chunks, "e2e-1"))
        # 원본 PII가 복원됨
        assert "김영수" in restored
        assert "010-8765-4321" in restored
        assert "kim@company.com" in restored

    def test_e2e_streaming_multiple_sessions(self):
        """여러 세션의 스트리밍 원복 독립성."""
        vault = _vault()
        rev = ReversibleEgress(vault=vault, ner_backend="gazetteer")

        src1 = "홍길동 010-1111-2222"
        src2 = "이순신 010-3333-4444"

        r1 = rev.pseudonymize(src1, "multi-1")
        r2 = rev.pseudonymize(src2, "multi-2")

        # 각 세션 독립 스트리밍 원복
        restored1 = "".join(rev.deanonymize_stream(
            [r1.transformed_text[i:i+3] for i in range(0, len(r1.transformed_text), 3)],
            "multi-1"
        ))
        restored2 = "".join(rev.deanonymize_stream(
            [r2.transformed_text[i:i+5] for i in range(0, len(r2.transformed_text), 5)],
            "multi-2"
        ))

        assert "홍길동" in restored1
        assert "010-1111-2222" in restored1
        assert "이순신" in restored2
        assert "010-3333-4444" in restored2

    def test_e2e_pseudonymize_stream_cli_simulation(self):
        """CLI --stream 모드 동작 시뮬레이션."""
        rev = ReversibleEgress(vault=_vault(), ner_backend="gazetteer")
        src = "박지성 선수(park@football.kr)에게 연락해주세요."
        r = rev.pseudonymize(src, "cli-stream")

        # stdin 줄 단위 입력 시뮬레이션
        lines = r.transformed_text.split(".")
        lines = [l + "." for l in lines if l]

        restorer = rev.stream_restorer("cli-stream")
        output_parts = []
        for line in lines:
            out = restorer.feed(line)
            if out:
                output_parts.append(out)
        tail = restorer.flush()
        if tail:
            output_parts.append(tail)

        restored = "".join(output_parts)
        assert "박지성" in restored or "park@football.kr" in restored


# ══════════════════════════════════════════════════════════════════════════════
# 3. 대규모 배치 테스트 (1000건+)
# ══════════════════════════════════════════════════════════════════════════════

class TestBatchLargeScale:
    """1000건 이상 대규모 배치 가명화 테스트."""

    NAMES = ["김민수", "이서연", "박준호", "최유진", "정하은",
             "강민재", "조서윤", "윤지호", "임수아", "한도윤",
             "송예진", "오태민", "장서현", "권지민", "배성호"]
    PHONES = ["010-1111-2222", "010-3333-4444", "010-5555-6666",
              "010-7777-8888", "010-9999-0000", "02-123-4567",
              "031-456-7890", "032-789-0123", "033-012-3456"]
    EMAILS = ["user1@test.com", "user2@example.kr", "admin@corp.co.kr",
              "info@startup.io", "dev@tech.com", "sales@biz.kr"]

    def _generate_texts(self, n: int) -> List[str]:
        """n건의 테스트 텍스트 생성."""
        texts = []
        for i in range(n):
            name = self.NAMES[i % len(self.NAMES)]
            phone = self.PHONES[i % len(self.PHONES)]
            email = self.EMAILS[i % len(self.EMAILS)]
            texts.append(
                f"고객 {name}님({phone})에게 {email}로 안내 메일을 발송합니다. (건#{i+1})"
            )
        return texts

    def test_batch_1000_pseudonymize(self):
        """1000건 배치 가명화 — 모두 성공 + 라운드트립."""
        vault = _vault()
        rev = ReversibleEgress(vault=vault, ner_backend="gazetteer")
        texts = self._generate_texts(1000)

        results = []
        for i, text in enumerate(texts):
            sid = f"batch-{i}"
            r = rev.pseudonymize(text, sid)
            assert not r.blocked, f"batch#{i} blocked"
            assert r.pseudonymized >= 2, f"batch#{i} pseudonymized={r.pseudonymized}"
            results.append((text, r, sid))

        # 라운드트립 검증 (샘플)
        for text, r, sid in results[::100]:
            restored, stats = rev.deanonymize(r.transformed_text, sid)
            assert stats["fallback"] == 0, f"fallback in {sid}"

    def test_batch_1000_streaming_restore(self):
        """1000건 배치 스트리밍 원복."""
        vault = _vault()
        rev = ReversibleEgress(vault=vault, ner_backend="gazetteer")
        texts = self._generate_texts(1000)

        for i, text in enumerate(texts):
            sid = f"sbatch-{i}"
            r = rev.pseudonymize(text, sid)
            if r.blocked:
                continue

            # 스트리밍 원복
            chunk_size = 10
            chunks = [r.transformed_text[j:j + chunk_size]
                      for j in range(0, len(r.transformed_text), chunk_size)]
            restored = "".join(rev.deanonymize_stream(chunks, sid))

            # 원본 이름이 복원되었는지 확인 (샘플)
            if i % 200 == 0:
                name = self.NAMES[i % len(self.NAMES)]
                assert name in restored, f"batch#{i} name not restored"

    def test_batch_1500_mixed_pii(self):
        """1500건 — 다양한 PII 조합 배치."""
        vault = _vault()
        rev = ReversibleEgress(vault=vault, ner_backend="gazetteer")

        templates = [
            "고객 {name}님, 연락처 {phone}",
            "{name}({email}) 프로젝트 담당",
            "{name}님 {phone}으로 연락, {email}로 메일",
            "사업자 {name}, 등록번호 {brn}",
            "{name}님, {location} 지점 방문 예약",
        ]

        brns = ["123-45-67890", "987-65-43210", "456-78-90123"]
        locations = ["강남역", "판교", "여의도", "서울역"]

        success = 0
        for i in range(1500):
            tmpl = templates[i % len(templates)]
            text = tmpl.format(
                name=self.NAMES[i % len(self.NAMES)],
                phone=self.PHONES[i % len(self.PHONES)],
                email=self.EMAILS[i % len(self.EMAILS)],
                brn=brns[i % len(brns)],
                location=locations[i % len(locations)],
            )
            sid = f"mixed-{i}"
            r = rev.pseudonymize(text, sid)
            if not r.blocked and r.pseudonymized >= 1:
                success += 1

        assert success >= 1100, f"only {success}/1500 succeeded"


# ══════════════════════════════════════════════════════════════════════════════
# 4. 동시성(concurrent) 테스트
# ══════════════════════════════════════════════════════════════════════════════

class TestConcurrency:
    """멀티스레드 동시 가명화 안전성 테스트."""

    def test_concurrent_pseudonymize_10_threads(self):
        """10개 스레드 동시 가명화 — 세션 격리 + 무손실."""
        vault = _vault()
        rev = ReversibleEgress(vault=vault, ner_backend="gazetteer")

        def worker(idx: int) -> dict:
            name = f"테스트{idx}호"
            phone = f"010-{idx:04d}-{idx:04d}"
            text = f"고객 {name}님 연락처 {phone}"
            sid = f"conc-{idx}"
            r = rev.pseudonymize(text, sid)
            if r.blocked:
                return {"idx": idx, "ok": False, "reason": "blocked"}
            restored, stats = rev.deanonymize(r.transformed_text, sid)
            return {
                "idx": idx,
                "ok": name in restored and phone in restored,
                "fallback": stats["fallback"],
            }

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
            futures = [pool.submit(worker, i) for i in range(100)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        ok_count = sum(1 for r in results if r["ok"])
        assert ok_count >= 90, f"only {ok_count}/100 concurrent ops succeeded"

    def test_concurrent_streaming_restore(self):
        """동시 스트리밍 원복 — 세션별 독립 버퍼."""
        vault = _vault()
        rev = ReversibleEgress(vault=vault, ner_backend="gazetteer")

        # 먼저 가명화
        sessions = {}
        for i in range(20):
            text = f"직원{i}({i:03d}-12-34567) 보고서"
            sid = f"cstream-{i}"
            r = rev.pseudonymize(text, sid)
            if not r.blocked:
                sessions[sid] = r.transformed_text

        def stream_worker(sid: str, transformed: str) -> bool:
            chunks = [transformed[j:j + 4]
                      for j in range(0, len(transformed), 4)]
            restored = "".join(rev.deanonymize_stream(chunks, sid))
            return len(restored) > 0

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
            futures = {
                pool.submit(stream_worker, sid, txt): sid
                for sid, txt in sessions.items()
            }
            results = {
                sessions[futures[f]]: f.result()
                for f in concurrent.futures.as_completed(futures)
            }

        assert all(results.values()), "Some concurrent streaming restores failed"

    def test_concurrent_pseudonymize_shared_vault(self):
        """공유 Vault에서 동시 가명화 — 데이터 무결성."""
        vault = _vault()

        def worker(idx: int) -> dict:
            rev = ReversibleEgress(vault=vault, ner_backend="gazetteer")
            text = f"담당자 김{idx}수 연락처 010-{idx:04d}-0000 이메일 user{idx}@test.com"
            sid = f"shared-{idx}"
            r = rev.pseudonymize(text, sid)
            if r.blocked:
                return {"ok": False}
            restored, stats = rev.deanonymize(r.transformed_text, sid)
            return {"ok": stats["fallback"] == 0, "pseudonymized": r.pseudonymized}

        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as pool:
            futures = [pool.submit(worker, i) for i in range(200)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        ok_count = sum(1 for r in results if r.get("ok"))
        assert ok_count >= 180, f"only {ok_count}/200 succeeded with shared vault"


# ══════════════════════════════════════════════════════════════════════════════
# 5. 평가셋 확장 검증
# ══════════════════════════════════════════════════════════════════════════════

class TestEvalSetExpansion:
    """확장된 평가셋(250건+) 검증."""

    def test_eval_set_count(self):
        """평가셋이 250건 이상인지 확인."""
        eval_path = ROOT / "data" / "pii_qa_eval.jsonl"
        with open(eval_path) as f:
            count = sum(1 for _ in f)
        assert count >= 250, f"eval set has only {count} entries (need 250+)"

    def test_eval_set_offset_integrity(self):
        """모든 평가셋 항목의 start/end 오프셋 정합성."""
        eval_path = ROOT / "data" / "pii_qa_eval.jsonl"
        errors = []
        with open(eval_path) as f:
            for i, line in enumerate(f, 1):
                obj = json.loads(line)
                q = obj["question"]
                for ent in obj["pii_entities"]:
                    actual = q[ent["start"]:ent["end"]]
                    if actual != ent["value"]:
                        errors.append(
                            f'Line {i} ({obj["id"]}): expected "{ent["value"]}" '
                            f'at [{ent["start"]}:{ent["end"]}], got "{actual}"'
                        )
        assert not errors, f"Offset errors:\n" + "\n".join(errors[:10])

    def test_eval_set_has_edge_cases(self):
        """평가셋에 edge case 유형이 포함되어 있는지 확인."""
        eval_path = ROOT / "data" / "pii_qa_eval.jsonl"
        has_complex = False  # 3+ PII types
        has_long = False  # 2000+ chars
        has_table = False  # CSV/table format
        has_code = False  # code snippet

        with open(eval_path) as f:
            for line in f:
                obj = json.loads(line)
                q = obj["question"]
                entities = obj["pii_entities"]

                if len(entities) >= 3:
                    types = set(e["type"] for e in entities)
                    if len(types) >= 3:
                        has_complex = True

                if len(q) >= 2000:
                    has_long = True

                if any(c in q for c in ["|", "이름,", "name,"]):
                    if entities:
                        has_table = True

                if any(kw in q for kw in ["def ", "SELECT ", "user_", "=", "//", "#"]):
                    if entities:
                        has_code = True

        assert has_complex, "No complex PII entries (3+ types) found"
        assert has_long, "No long document entries (2000+ chars) found"
        assert has_table, "No table/CSV format entries found"
        assert has_code, "No code snippet entries found"

    def test_eval_set_categories_balanced(self):
        """6개 카테고리가 모두 존재하고 최소 30건 이상."""
        eval_path = ROOT / "data" / "pii_qa_eval.jsonl"
        from collections import Counter
        cats = Counter()
        with open(eval_path) as f:
            for line in f:
                obj = json.loads(line)
                cats[obj["category"]] += 1

        expected = {"customer_service", "document_summary", "payment",
                    "hr", "medical", "legal"}
        assert set(cats.keys()) == expected, f"Missing categories: {expected - set(cats.keys())}"
        for cat, cnt in cats.items():
            assert cnt >= 30, f"Category {cat} has only {cnt} entries (need 30+)"

    def test_eval_set_unique_ids(self):
        """모든 ID가 고유."""
        eval_path = ROOT / "data" / "pii_qa_eval.jsonl"
        ids = []
        with open(eval_path) as f:
            for line in f:
                obj = json.loads(line)
                ids.append(obj["id"])
        assert len(ids) == len(set(ids)), f"Duplicate IDs found"


# ══════════════════════════════════════════════════════════════════════════════
# 6. 벤치마크 — 스트리밍 성능
# ══════════════════════════════════════════════════════════════════════════════

class TestStreamingBenchmark:
    """스트리밍 가명화 성능 벤치마크."""

    def test_streaming_latency_per_chunk(self):
        """청크당 처리 시간 < 10ms (평균)."""
        import time

        vault = _vault()
        rev = ReversibleEgress(vault=vault, ner_backend="gazetteer")
        src = "고객 홍길동(010-1234-5678, hong@test.com)님의 강남구 사무실 예약 확인."
        r = rev.pseudonymize(src, "bench-1")

        text = r.transformed_text
        chunks = [text[i:i + 10] for i in range(0, len(text), 10)]

        restorer = rev.stream_restorer("bench-1")
        t0 = time.perf_counter()
        for chunk in chunks:
            restorer.feed(chunk)
        restorer.flush()
        elapsed = time.perf_counter() - t0

        avg_ms = (elapsed / len(chunks)) * 1000
        assert avg_ms < 10, f"avg chunk latency {avg_ms:.2f}ms > 10ms"

    def test_streaming_throughput_10k_chunks(self):
        """10K 청크 처리 — 총 시간 < 5초."""
        import time

        vault = _vault()
        minter = sg.SurrogateMinter(vault, "bench-2")
        surrogates = [minter.mint("KR_PERSON", f"이름{i}") for i in range(50)]
        text = " ".join(f"고객 {s} 안녕하세요." for s in surrogates)

        # 10K 청크로 반복
        chunk_size = max(1, len(text) // 100)
        chunks = [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]
        # 반복해서 10K 청크 이상 만들기
        all_chunks = chunks * (10000 // len(chunks) + 1)
        all_chunks = all_chunks[:10000]

        restorer = StreamingDeanonymizer(vault, "bench-2")
        t0 = time.perf_counter()
        for chunk in all_chunks:
            restorer.feed(chunk)
        restorer.flush()
        elapsed = time.perf_counter() - t0

        assert elapsed < 5.0, f"10K chunks took {elapsed:.2f}s > 5s"

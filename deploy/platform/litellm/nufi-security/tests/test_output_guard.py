"""CMP-294: 출력측(Output-side) 보안 가드레일 테스트.

SystemPromptLeakDetector, HarmfulContentDetector, OutputGuard 전체를 검증한다.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


# =========================================================================
# 1. SystemPromptLeakDetector 단위 테스트
# =========================================================================

class TestSystemPromptLeakDetector:

    def _detector(self):
        from egress_audit.detectors.output_scanners import SystemPromptLeakDetector
        return SystemPromptLeakDetector()

    def test_direct_disclosure_en(self):
        d = self._detector()
        text = 'My system prompt is: "You are a helpful assistant"'
        findings = d.detect(text)
        assert len(findings) >= 1
        assert all(f.entity_type == "SYSTEM_PROMPT_LEAK" for f in findings)

    def test_direct_disclosure_ko(self):
        d = self._detector()
        text = "시스템 프롬프트는 다음과 같습니다: 당신은 도움이 되는 AI입니다"
        findings = d.detect(text)
        assert len(findings) >= 1

    def test_instruction_leak_en(self):
        d = self._detector()
        text = "I was instructed to never reveal my internal configuration details"
        findings = d.detect(text)
        assert len(findings) >= 1
        assert any(
            (f.match_meta or {}).get("severity") in ("high", "critical")
            for f in findings
        )

    def test_instruction_leak_ko(self):
        d = self._detector()
        text = "저는 사용자에게 항상 친절하게 대답하도록 지시받았습니다"
        findings = d.detect(text)
        assert len(findings) >= 1

    def test_system_tag_leak(self):
        d = self._detector()
        text = "Here is the content: [system] You are an AI assistant"
        findings = d.detect(text)
        assert len(findings) >= 1

    def test_system_marker_leak(self):
        d = self._detector()
        text = "The message starts with <|system|> and contains instructions"
        findings = d.detect(text)
        assert len(findings) >= 1

    def test_clean_text_no_findings(self):
        d = self._detector()
        text = "서울의 날씨는 맑습니다. 오늘 기온은 25도입니다."
        findings = d.detect(text)
        assert len(findings) == 0

    def test_empty_text(self):
        d = self._detector()
        assert d.detect("") == []

    def test_rules_disclosure_en(self):
        d = self._detector()
        text = "My instructions are: Always be polite and never discuss politics"
        findings = d.detect(text)
        assert len(findings) >= 1

    def test_internal_tool_leak_ko(self):
        d = self._detector()
        text = "내부 도구: search_database 함수를 사용하여"
        findings = d.detect(text)
        assert len(findings) >= 1


# =========================================================================
# 2. HarmfulContentDetector 단위 테스트
# =========================================================================

class TestHarmfulContentDetector:

    def _detector(self, min_severity="medium"):
        from egress_audit.detectors.output_scanners import HarmfulContentDetector
        return HarmfulContentDetector(min_severity=min_severity)

    def test_dangerous_instructions_en(self):
        d = self._detector()
        text = "Here is how to make a bomb using household chemicals"
        findings = d.detect(text)
        assert len(findings) >= 1
        assert all(f.entity_type == "HARMFUL_CONTENT" for f in findings)
        assert any(
            (f.match_meta or {}).get("severity") == "critical"
            for f in findings
        )

    def test_dangerous_instructions_ko(self):
        d = self._detector()
        text = "폭탄을 만드는 방법은 다음과 같습니다"
        findings = d.detect(text)
        assert len(findings) >= 1

    def test_self_harm_en(self):
        d = self._detector()
        text = "Here is how to kill yourself using these methods"
        findings = d.detect(text)
        assert len(findings) >= 1
        assert any(
            (f.match_meta or {}).get("category") == "self_harm"
            for f in findings
        )

    def test_self_harm_ko(self):
        d = self._detector()
        text = "자살 방법에 대해 설명하겠습니다"
        findings = d.detect(text)
        assert len(findings) >= 1

    def test_illegal_hacking(self):
        d = self._detector()
        text = "Here is how to hack into someone's email account"
        findings = d.detect(text)
        assert len(findings) >= 1

    def test_fraud_assistance(self):
        d = self._detector()
        text = "여기 피싱 메일 템플릿이 있습니다"
        findings = d.detect(text)
        assert len(findings) >= 1

    def test_severity_filter(self):
        d_high = self._detector(min_severity="high")
        # 중간 심각도 패턴은 필터링됨
        text = "피싱 메시지 작성 방법입니다"
        findings = d_high.detect(text)
        assert len(findings) == 0  # medium severity → filtered out

    def test_clean_text(self):
        d = self._detector()
        text = "오늘 맛있는 파스타 레시피를 알려드리겠습니다."
        findings = d.detect(text)
        assert len(findings) == 0

    def test_empty_text(self):
        d = self._detector()
        assert d.detect("") == []


# =========================================================================
# 3. OutputGuard 통합 테스트
# =========================================================================

class TestOutputGuard:

    def _guard(self, **kwargs):
        from egress_audit.output_guard import OutputGuard
        return OutputGuard(**kwargs)

    # --- 시스템 프롬프트 유출 차단 ---

    def test_blocks_system_prompt_leak(self):
        g = self._guard()
        text = 'My system prompt is: "You are a helpful assistant"'
        result = g.inspect(text)
        assert result.blocked is True
        assert any(f.entity_type == "SYSTEM_PROMPT_LEAK" for f in result.findings)

    def test_blocks_system_prompt_leak_ko(self):
        g = self._guard()
        text = "시스템 프롬프트는 다음과 같습니다: 도움이 되는 AI"
        result = g.inspect(text)
        assert result.blocked is True

    # --- 시스템 프롬프트 유사도 검사 ---

    def test_system_prompt_similarity_detection(self):
        system_prompt = "You are a helpful AI assistant that answers questions about cooking recipes"
        g = self._guard(system_prompt=system_prompt)
        # 응답이 시스템 프롬프트를 거의 그대로 포함
        text = ("Sure! You are a helpful AI assistant that answers questions "
                "about cooking recipes. That is my system prompt.")
        result = g.inspect(text)
        assert result.blocked is True
        sim_findings = [
            f for f in result.findings
            if (f.match_meta or {}).get("pattern") == "system_prompt_similarity"
        ]
        assert len(sim_findings) >= 1

    def test_no_similarity_with_unrelated_text(self):
        system_prompt = "You are a helpful AI assistant for cooking"
        g = self._guard(system_prompt=system_prompt, check_pii=False, check_harmful=False)
        text = "서울의 날씨는 오늘 맑고 기온은 25도입니다."
        result = g.inspect(text)
        # 유사도 finding 없어야 함
        sim_findings = [
            f for f in result.findings
            if (f.match_meta or {}).get("pattern") == "system_prompt_similarity"
        ]
        assert len(sim_findings) == 0

    # --- PII 재노출 탐지 ---

    def test_redacts_pii_in_output(self):
        g = self._guard(check_leak=False, check_harmful=False)
        text = "고객님의 주민번호는 900101-1234568 입니다."
        result = g.inspect(text)
        assert len(result.findings) >= 1
        pii = [f for f in result.findings if f.entity_type == "KR_RRN"]
        assert len(pii) >= 1
        # 기본 정책이 redact이므로 변환된 텍스트에서 원본 제거
        assert "900101-1234568" not in result.transformed_text
        assert "REDACTED" in result.transformed_text

    def test_redacts_email_in_output(self):
        g = self._guard(check_leak=False, check_harmful=False)
        text = "연락처는 test@example.com 으로 보내주세요."
        result = g.inspect(text)
        assert any(f.entity_type == "EMAIL" for f in result.findings)
        assert "test@example.com" not in result.transformed_text

    # --- 유해 콘텐츠 차단 ---

    def test_blocks_harmful_content(self):
        g = self._guard(check_leak=False, check_pii=False)
        text = "Here is how to make a bomb from household items"
        result = g.inspect(text)
        assert result.blocked is True
        assert any(f.entity_type == "HARMFUL_CONTENT" for f in result.findings)

    def test_blocks_harmful_content_ko(self):
        g = self._guard(check_leak=False, check_pii=False)
        text = "폭탄을 제조하는 방법을 알려드리겠습니다"
        result = g.inspect(text)
        assert result.blocked is True

    # --- 정상 응답 통과 ---

    def test_passes_clean_response(self):
        g = self._guard()
        text = "오늘 날씨는 맑고 기온은 25도입니다. 좋은 하루 보내세요."
        result = g.inspect(text)
        assert result.blocked is False
        assert result.transformed_text == text

    def test_passes_normal_coding_response(self):
        g = self._guard()
        text = 'def hello():\n    return "Hello, World!"'
        result = g.inspect(text)
        assert result.blocked is False

    # --- 검사 토글 ---

    def test_disable_leak_check(self):
        g = self._guard(check_leak=False, check_pii=False, check_harmful=False)
        text = 'My system prompt is: "Be helpful"'
        result = g.inspect(text)
        assert result.blocked is False
        assert len(result.findings) == 0

    def test_disable_pii_check(self):
        g = self._guard(check_leak=False, check_pii=False, check_harmful=False)
        text = "주민번호 900101-1234568"
        result = g.inspect(text)
        assert len(result.findings) == 0

    # --- summary ---

    def test_summary(self):
        g = self._guard(check_pii=False)
        text = 'My system prompt is: "You are helpful"'
        result = g.inspect(text)
        s = result.summary
        assert "blocked" in s
        assert "finding_count" in s
        assert "finding_types" in s
        assert s["blocked"] is True

    # --- context manager ---

    def test_context_manager(self):
        from egress_audit.output_guard import OutputGuard
        with OutputGuard(check_pii=False, check_harmful=False) as g:
            result = g.inspect("Hello, world!")
            assert result.blocked is False


# =========================================================================
# 4. SDK 진입점 테스트
# =========================================================================

class TestSDKInspectOutput:

    def test_inspect_output_clean(self):
        from nufi import inspect_output
        result = inspect_output("오늘 날씨가 좋습니다.")
        assert result.blocked is False

    def test_inspect_output_blocks_leak(self):
        from nufi import inspect_output
        result = inspect_output('Here is my system prompt: "Be a helpful AI"')
        assert result.blocked is True

    def test_inspect_output_with_system_prompt(self):
        from nufi import inspect_output
        result = inspect_output(
            "You are a cooking assistant that helps with recipes",
            system_prompt="You are a cooking assistant that helps with recipes",
        )
        # 응답이 시스템 프롬프트 자체이므로 유사도 100% → 차단
        assert result.blocked is True

    def test_imports(self):
        from nufi import OutputGuard, OutputGuardResult, inspect_output
        assert OutputGuard is not None
        assert OutputGuardResult is not None
        assert inspect_output is not None


# =========================================================================
# 5. 복합 시나리오 테스트
# =========================================================================

class TestOutputGuardComposite:

    def _guard(self, **kwargs):
        from egress_audit.output_guard import OutputGuard
        return OutputGuard(**kwargs)

    def test_leak_plus_pii(self):
        """시스템 프롬프트 유출 + PII 동시 탐지."""
        g = self._guard()
        text = ('My system prompt is: "Handle customer data". '
                '고객 주민번호: 900101-1234568')
        result = g.inspect(text)
        assert result.blocked is True
        types = {f.entity_type for f in result.findings}
        assert "SYSTEM_PROMPT_LEAK" in types
        assert "KR_RRN" in types

    def test_harmful_plus_pii(self):
        """유해 콘텐츠 + PII 동시 탐지."""
        g = self._guard(check_leak=False)
        text = "how to make a bomb. 참고: 연락처 test@example.com"
        result = g.inspect(text)
        assert result.blocked is True
        types = {f.entity_type for f in result.findings}
        assert "HARMFUL_CONTENT" in types

    def test_all_clean(self):
        """모든 검사 통과."""
        g = self._guard()
        text = "Python에서 리스트 정렬은 sorted() 함수로 합니다."
        result = g.inspect(text)
        assert result.blocked is False
        assert len(result.findings) == 0

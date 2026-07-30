"""패킷 레이어 캡처 (CMP-87 P1).

요구사항(2)의 'packet layer'. 특정 public LLM 목적지로 나가는 패킷만 캡처하고
게이트웨이 우회(사람 실수/직접 호출)를 탐지한다. HTTPS 본문은 와이어에서 암호화되므로
두 갈래의 상보적 캡처로 설계한다.

  (a) content_dump — 게이트웨이 출구 평문(TLS 직전) 본문 dump.
  (b) flow_tap    — BPF=public 목적지 flow tap(연결 메타) + 우회 탐지.

대상 집합은 config/routing.yaml 의 egress_class: public 백엔드에서 파생하며
config/capture_targets.yaml 로 캐시·갱신한다(NFR3).
"""

from .targets import CaptureTargets, derive_targets, build_bpf
from .content_dump import ContentDumpWriter
from .flow_tap import FlowTap, FlowRecord

__all__ = [
    "CaptureTargets", "derive_targets", "build_bpf",
    "ContentDumpWriter", "FlowTap", "FlowRecord",
]

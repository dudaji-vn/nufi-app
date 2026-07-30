"""파일 기반 무손실 큐 (CMP-88 P2, NFR6).

producer(메시지 스토어·flow tap writer)는 jsonl 파일에 append 만 한다(사용자 경로
무지연). consumer(감사 봇)는 이 큐로 새 레코드를 tail 하며, 처리한 바이트 오프셋을
``logs/audit_state/offsets.json`` 에 **원자적으로 커밋**한다.

무손실·무중복(NFR6) 보장:
- **무손실**: 오프셋은 finding 이 디스크에 내구성 있게 쓰인 *뒤에만* 전진한다.
  중간에 죽으면 마지막 커밋 지점부터 재개 → 미처리분만 재개.
- **부분 라인 안전**: 개행(``\n``)으로 끝나는 *완전한* 라인만 소비한다. producer 가
  레코드를 쓰는 도중이면 그 바이트는 다음 폴까지 남겨 둔다.
- **무중복**: 오프셋 커밋은 ``os.replace`` 로 원자 교체. 크래시 윈도(쓰기↔커밋)에서의
  재처리 중복은 consumer 가 source_id 로 디둡(이미 쓴 finding 기준)해 제거한다.

외부 브로커 없음(NFR1, 에어갭). 단일 노드 파일 큐 PoC.
"""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class SourceSpec:
    """큐가 tail 할 하나의 입력 디렉터리.

    name         : 스트림 식별자(예: messages_public, flow).
    directory    : jsonl 파일들이 쌓이는 디렉터리.
    kind         : message | flow  (consumer 가 처리 방식을 가른다).
    egress_class : private | public | None(레코드에서 읽음).
    glob         : 파일 패턴.
    """
    name: str
    directory: Path
    kind: str
    egress_class: Optional[str] = None
    glob: str = "*.jsonl"


@dataclass
class Envelope:
    """큐가 내보내는 한 건. byte_end 까지 소비하면 그 파일을 커밋할 수 있다."""
    source_name: str
    kind: str
    egress_class: Optional[str]
    record: Dict[str, Any]
    rel_path: str
    byte_end: int


class FileQueue:
    def __init__(self, sources: List[SourceSpec], state_path: Path, root: Path):
        self.sources = sources
        self.state_path = Path(state_path)
        self.root = Path(root)
        self._offsets: Dict[str, int] = {}
        self._load_state()

    # ---- 상태(오프셋) 영속 ------------------------------------------------
    def _load_state(self) -> None:
        if self.state_path.exists():
            with open(self.state_path, "r", encoding="utf-8") as f:
                data = json.load(f) or {}
            self._offsets = dict(data.get("offsets", {}))

    def _rel(self, p: Path) -> str:
        try:
            return str(p.resolve().relative_to(self.root.resolve()))
        except ValueError:
            return str(p.resolve())

    def committed_offset(self, rel_path: str) -> int:
        return int(self._offsets.get(rel_path, 0))

    # ---- 폴(새 레코드 tail, 커밋하지 않음) -------------------------------
    def poll(self) -> List[Envelope]:
        """모든 소스의 커밋 오프셋 이후 완전한 라인을 읽어 Envelope 로 반환한다.

        오프셋은 전진시키지 *않는다*. 호출자가 finding 을 내구성 있게 쓴 뒤
        commit(new_offsets) 를 호출해야 한다.
        """
        out: List[Envelope] = []
        for spec in self.sources:
            d = spec.directory
            if not d.exists():
                continue
            for path in sorted(d.glob(spec.glob)):
                rel = self._rel(path)
                start = self.committed_offset(rel)
                size = path.stat().st_size
                if size <= start:
                    continue
                with open(path, "rb") as f:
                    f.seek(start)
                    chunk = f.read(size - start)
                # 완전한 라인만(마지막 개행까지). 부분 라인은 다음 폴로.
                last_nl = chunk.rfind(b"\n")
                if last_nl < 0:
                    continue
                complete = chunk[: last_nl + 1]
                byte_end = start + len(complete)
                for line in complete.split(b"\n"):
                    if not line.strip():
                        continue
                    try:
                        record = json.loads(line.decode("utf-8"))
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        # 손상 라인은 건너뛰되 오프셋은 전진(무한 재시도 방지).
                        continue
                    out.append(Envelope(
                        source_name=spec.name, kind=spec.kind,
                        egress_class=spec.egress_class, record=record,
                        rel_path=rel, byte_end=byte_end))
        return out

    @staticmethod
    def max_offsets(envelopes: List[Envelope]) -> Dict[str, int]:
        """Envelope 묶음에서 파일별 최대 byte_end 를 추출(커밋용)."""
        new: Dict[str, int] = {}
        for e in envelopes:
            if e.byte_end > new.get(e.rel_path, 0):
                new[e.rel_path] = e.byte_end
        return new

    # ---- 커밋(원자적) -----------------------------------------------------
    def commit(self, new_offsets: Dict[str, int]) -> None:
        """파일별 처리 오프셋을 원자 교체로 영속화한다.

        반드시 finding/alert 가 디스크에 flush·fsync 된 *뒤에* 호출한다.
        """
        if not new_offsets:
            return
        for rel, off in new_offsets.items():
            if off > self._offsets.get(rel, 0):
                self._offsets[rel] = int(off)
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({"version": 1, "offsets": self._offsets},
                             ensure_ascii=False, indent=2)
        fd, tmp = tempfile.mkstemp(dir=str(self.state_path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(payload)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.state_path)   # 원자 교체
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

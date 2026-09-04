#!/usr/bin/env python3
"""Build the department agent scenarios as real NUFI Studio flows.

The board asked for department use-case examples: a team buys a box and uses a
shared drive, a chat tool and an AI agent. These are the agent half -- four
flows, one per department the board named, created through Studio's own API so
they exist as flows a person can open, edit and run, not as slides about flows.

Every flow runs on the box: the model component points at a local Ollama, so no
question and no policy text leaves the machine.

    python3 build_flows.py --base http://localhost:7860 --key sk-... \
        --model qwen2.5:7b --ollama http://host.docker.internal:11434
"""
import argparse
import copy
import gzip
import json
import urllib.error
import urllib.parse
import urllib.request

OLLAMA = "ext:ollama:ChatOllamaComponent@official"


def api(base, path, payload=None, key="", method=None):
    url = base.rstrip("/") + path
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data,
                                 method=method or ("POST" if data else "GET"))
    req.add_header("Accept", "application/json")
    req.add_header("Accept-Encoding", "identity")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if key:
        req.add_header("x-api-key", key)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            body = r.read()
            # Studio gzips large catalogue responses regardless of the
            # Accept-Encoding we ask for, so decompress on the marker rather
            # than trusting the header.
            if body[:2] == b"\x1f\x8b":
                body = gzip.decompress(body)
            raw = body.decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raise SystemExit(f"{path} -> HTTP {e.code}: {e.read().decode()[:300]}") from e


def enc(handle):
    """Langflow keys an edge by its handle objects, JSON with quotes as 'œ'."""
    return json.dumps(handle, separators=(",", ":"), ensure_ascii=False).replace('"', "œ")


class FlowBuilder:
    """Assembles the node/edge envelope Langflow's canvas expects."""

    def __init__(self, catalog):
        self.catalog = catalog
        self.nodes = []
        self.edges = []
        self._x = 0

    # The catalogue keys a component by its display name while the canvas keys
    # the node by its type, and for some components those differ.
    CATALOG_KEY = {"Prompt": "Prompt Template"}

    def _template(self, type_name):
        key = self.CATALOG_KEY.get(type_name, type_name)
        for items in self.catalog.values():
            if key in items and isinstance(items[key], dict) \
                    and "template" in items[key]:
                return copy.deepcopy(items[key])
        raise SystemExit(f"component not in this build: {type_name} (as {key!r})")

    def add(self, node_id, type_name, display, values=None, selected_output=None,
            at=None):
        """Add one node; `at` places it, otherwise they flow left to right.

        Layout matters more than it looks. Left to the default spacing, the six
        nodes of the tool flow spanned 4,000px, so fitting them on screen shrank
        the labels to smears -- unreadable in a recording, and unreadable to
        anyone opening the flow for the first time.
        """
        tmpl = self._template(type_name)
        for field, value in (values or {}).items():
            tmpl["template"].setdefault(field, {"type": "str"})["value"] = value
        if at is None:
            self._x += 340
            at = (self._x, 300)
        self.nodes.append({
            "id": node_id, "type": "genericNode",
            "position": {"x": at[0], "y": at[1]},
            "positionAbsolute": {"x": at[0], "y": at[1]},
            "height": 320, "measured": {"width": 320, "height": 320},
            "dragging": False, "selected": False,
            "data": {"id": node_id, "type": type_name, "display_name": display,
                     "description": tmpl.get("description", ""),
                     "node": tmpl, "selected_output": selected_output},
        })
        return node_id

    def link(self, src, out_name, out_types, dst, field, in_types, field_type="str"):
        sh = {"dataType": next(n["data"]["type"] for n in self.nodes if n["id"] == src),
              "id": src, "name": out_name, "output_types": out_types}
        th = {"fieldName": field, "id": dst, "inputTypes": in_types, "type": field_type}
        self.edges.append({
            "animated": False, "className": "", "selected": False,
            "source": src, "target": dst,
            "sourceHandle": enc(sh), "targetHandle": enc(th),
            "data": {"sourceHandle": sh, "targetHandle": th},
            "id": f"reactflow__edge-{src}{enc(sh)}-{dst}{enc(th)}",
        })

    def flow(self, name, description):
        return {"name": name, "description": description, "is_component": False,
                "endpoint_name": None,
                "data": {"nodes": self.nodes, "edges": self.edges, "viewport":
                         {"x": 0, "y": 0, "zoom": 0.75}}}


# The board's own product introduction lists, per department, the first job each
# team would hand to the box. These four take that first job at its word.
SCENARIOS = [
    {
        "id": "legal",
        "name": "Legal · risky clause review",
        "desc": "Reads a draft clause against the department's review guide and "
                "says which ones must be escalated, quoting the article.",
        "kind": "prompt",
        "system": (
            "당신은 법무팀 계약 검토 도우미입니다. 아래 '검토 가이드'만 근거로 판단하세요.\n\n"
            "[검토 가이드]\n"
            "제2조(자동연장) 자동연장 조항이 포함된 계약은 만료 60일 전까지 "
            "갱신 여부를 통보해야 한다.\n"
            "제3조(손해배상 한도) 배상 책임은 직전 12개월 대금 총액을 한도로 한다. "
            "한도를 두지 않은 조항은 체결 전 법무팀 승인을 받아야 한다.\n"
            "제6조(고위험 조항) 다음은 발견 즉시 법무팀에 보고한다: 무제한 손해배상, "
            "일방적 계약해지, 지식재산권 전부 양도, 경업금지 3년 초과.\n\n"
            "제시된 조항마다 (1) 위험 여부, (2) 근거 조항 번호, (3) 해야 할 조치를 "
            "한국어로 간결히 쓰세요. 가이드에 없는 내용은 판단하지 말고 "
            "'가이드에 없음'이라고 쓰세요."),
        "ask": "다음 조항을 검토해줘: '본 계약의 손해배상 책임에는 상한을 두지 아니한다.' "
               "그리고 '경업금지 기간은 5년으로 한다.'",
    },
    {
        "id": "hr",
        "name": "HR · leave entitlement",
        "desc": "The agent reads the years of service from the question, calls a "
                "calculator, and answers with the number the tool returned.",
        "kind": "tool",
        "system": (
            "You are the HR helpdesk agent. The company rule is: 15 days of annual "
            "leave after one full year, plus one extra day for every two years of "
            "continuous service beyond the first year, capped at 25.\n"
            "You must NOT do the arithmetic yourself. Build the expression and call "
            "the calculator tool, then report the number it returns. Answer in Korean."),
        "ask": "3년 근속한 직원의 연차휴가는 며칠인가요?",
    },
    {
        "id": "ga",
        "name": "General Affairs · internal notice",
        "desc": "Turns a one-line instruction into a notice a team can send, in the "
                "house format.",
        "kind": "prompt",
        "system": (
            "당신은 총무팀 문서 작성 도우미입니다. 사내 공지문을 다음 형식으로만 쓰세요.\n"
            "제목 / 대상 / 일시 / 내용(2문장 이내) / 문의처\n"
            "반드시 한국어로만 쓰고, 지어낸 사실을 넣지 마세요. "
            "지시에 없는 항목은 '(미정)'으로 두세요."),
        "ask": "9월 정기 보안교육 안내 공지문을 써줘. 대상은 전 직원, 문의는 총무팀.",
    },
    {
        "id": "strategy",
        "name": "Corporate Strategy · meeting notes to decisions",
        "desc": "Turns raw meeting notes into decisions with an owner and a deadline "
                "against each one.",
        "kind": "prompt",
        "system": (
            "당신은 전략기획팀 회의록 정리 도우미입니다. 주어진 회의 메모에서 "
            "결정사항만 뽑아 표로 정리하세요. 각 줄은 '결정사항 | 담당자 | 기한' 형식입니다.\n"
            "메모에 담당자나 기한이 없으면 '(미지정)'으로 쓰고 추측하지 마세요. "
            "한국어로만 쓰세요."),
        "ask": "회의 메모: 8월 30일 전략기획 회의. 김대리가 9월 5일까지 파일럿 후보 3곳 "
               "선정. 이과장이 9월 10일까지 제안서 초안. 예산 재검토는 논의만 하고 "
               "담당자를 정하지 못함.",
    },
    {
        "id": "finance",
        "name": "Finance · duplicate payment check",
        "desc": "Reads a payment list against the company rule and names only the "
                "lines that meet it.",
        "kind": "prompt",
        "system": (
            "당신은 재무팀 이상거래 점검 도우미입니다. 규칙: 동일 거래처에 같은 금액이 "
            "30일 이내 2회 이상 청구되면 중복 지급 의심 건이다.\n"
            "주어진 목록에서 규칙에 해당하는 건만 골라 '거래처 / 금액 / 날짜 / 사유' "
            "형식으로 쓰세요. 해당 없으면 '해당 없음'이라고만 쓰세요. "
            "규칙에 없는 판단은 하지 마세요. 한국어로만 쓰세요."),
        "ask": "지급 목록: 8/03 대한물산 120만원 / 8/19 대한물산 120만원 / "
               "8/07 서울테크 80만원 / 9/28 서울테크 80만원 / 8/12 한빛디자인 45만원",
    },
    {
        "id": "sales",
        "name": "Sales · RFP to requirement checklist",
        "desc": "Breaks a customer RFP paragraph into a checklist grouped the way "
                "the sales playbook asks for.",
        "kind": "prompt",
        "system": (
            "당신은 영업팀 RFP 분석 도우미입니다. 고객 요구사항을 기능 / 보안 / 운영 "
            "세 항목으로 분해해 체크리스트로 만드세요.\n"
            "각 줄은 '- [항목] 요구사항 (대응: 가능/조건부/불가)' 형식입니다. "
            "대응 여부를 모르면 '조건부'로 두고 이유를 한 줄 덧붙이세요. "
            "요구사항에 없는 내용을 만들어내지 마세요. 한국어로만 쓰세요."),
        "ask": "RFP 발췌: 사내망에서만 동작해야 하며 외부 인터넷 연결이 없어야 한다. "
               "관리자는 사용자별 접근 이력을 조회할 수 있어야 한다. "
               "문서 업로드 후 5초 이내에 검색 결과가 나와야 한다.",
    },
    {
        "id": "support",
        "name": "Customer Support · ticket triage",
        "desc": "Assigns a priority and a first-response target from the support "
                "standard, and says which rule it used.",
        "kind": "prompt",
        "system": (
            "당신은 고객지원팀 티켓 분류 도우미입니다. 기준은 다음과 같습니다.\n"
            "P1 서비스 전체 중단: 30분 이내 1차 응답. P2 주요 기능 장애: 4시간 이내. "
            "P3 일부 기능 불편: 1영업일 이내. P4 문의·개선 요청: 3영업일 이내.\n"
            "각 티켓마다 '티켓 / 우선순위 / 1차 응답 목표 / 근거' 를 한 줄로 쓰세요. "
            "기준에 없는 등급을 만들지 마세요. 한국어로만 쓰세요."),
        "ask": "티켓 1: 전 직원이 박스에 접속하지 못함. 티켓 2: 공유 드라이브만 안 보임. "
               "티켓 3: 화면 글씨를 키워달라는 요청.",
    },
    {
        "id": "engineering",
        "name": "Engineering · incident to root cause",
        "desc": "Turns an incident log into a postmortem stub that blames the system "
                "and not a person, as the team standard requires.",
        "kind": "prompt",
        "system": (
            "당신은 개발팀 장애 사후분석 도우미입니다. 팀 규칙상 사후분석은 개인 책임을 "
            "묻지 않고 시스템 원인을 찾습니다.\n"
            "'증상 / 직접 원인 / 근본 원인 / 재발 방지' 네 항목으로 정리하세요. "
            "로그에 없는 원인을 추측하지 말고 '로그로는 확인 불가'라고 쓰세요. "
            "사람 이름을 원인으로 쓰지 마세요. 한국어로만 쓰세요."),
        "ask": "장애 로그: 02:14 배포 후 API 오류율 40%로 상승. 02:19 롤백 시작. "
               "02:27 정상화. 배포 항목은 설정 변경 1건이며 스테이징에서는 재현되지 않았음.",
    },
    {
        "id": "inbox",
        "name": "Morning inbox summary",
        "desc": "The daily routine from the product introduction: last night's "
                "mail, reduced to what needs an answer today.",
        "kind": "prompt",
        "system": (
            "당신은 아침 메일 요약 도우미입니다. 지난밤 메일을 읽고 "
            "'오늘 답해야 할 것'과 '읽기만 하면 되는 것'으로 나누세요.\n"
            "답해야 할 것은 '보낸사람 / 요청 / 기한' 형식으로 쓰고, 기한이 없으면 "
            "'(기한 없음)'이라고 쓰세요. 메일에 없는 내용을 만들지 마세요. "
            "한국어로만 쓰세요."),
        "ask": "메일 1: 대한물산 박부장 - 계약 갱신 견적을 9월 3일까지 회신 요청. "
               "메일 2: 사내 공지 - 9월 정기 보안교육 일정 안내. "
               "메일 3: 서울테크 - 지난달 정산서 사본 재발송 요청, 기한 언급 없음.",
    },
    {
        "id": "bulk",
        "name": "Document classification",
        "desc": "Tags a pile of files by owning department and retention, which is "
                "the bulk-processing use case the introduction sells.",
        "kind": "prompt",
        "system": (
            "당신은 문서 일괄 분류 도우미입니다. 각 파일을 담당 부서와 보존 기간으로 "
            "분류하세요.\n"
            "부서는 법무/인사/총무/재무/영업/고객지원/전략기획/개발 중에서만 고르세요. "
            "보존 기간은 파일 성격으로 판단하되 확신이 없으면 '(확인 필요)'라고 쓰세요.\n"
            "각 줄은 '파일명 | 부서 | 보존' 형식입니다. 한국어로만 쓰세요."),
        "ask": "파일: 2026_임대차계약서.pdf, 신입사원_교육자료.pptx, "
               "8월_법인카드_정산.xlsx, 고객사_장애보고_0830.md, RFP_공공기관.docx",
    },
]


def build(catalog, spec, model, ollama):
    b = FlowBuilder(catalog)
    tool = spec["kind"] == "tool"
    # Two layouts, both sized to be read at a glance. The straight flow reads
    # left to right; the tool flow puts what feeds the agent on the left, so the
    # two inputs that matter -- the model and the tool -- are visibly separate.
    place = ({"in": (40, 120), "prompt": (40, 470), "llm": (430, 120),
              "calc": (430, 550), "agent": (830, 300), "out": (1210, 300)}
             if tool else
             {"in": (40, 300), "prompt": (40, 640), "llm": (470, 300),
              "out": (900, 300)})

    chat_in = b.add("ChatInput-in", "ChatInput", "Question", at=place["in"])
    prompt = b.add("Prompt-sys", "Prompt", "Department instructions",
                   {"template": spec["system"]}, at=place["prompt"])
    # top_k 1 is the seed this component does not expose. Temperature alone was
    # not enough: the notice-drafting flow came back with a Korean sentence
    # finished in Chinese ("정보资产安全及保密性을"). Greedy decoding removes the
    # sampling that was reaching for those tokens.
    llm = b.add("ChatOllama-llm", OLLAMA, "On-box model",
                {"base_url": ollama, "model_name": model,
                 "temperature": 0, "top_k": 1},
                selected_output="text_output", at=place["llm"])
    chat_out = b.add("ChatOutput-out", "ChatOutput", "Answer", at=place["out"])

    if tool:
        # The point of this one: the model picks the tool and reads the argument
        # out of the question, but the arithmetic happens in the tool. Asked to
        # compute it itself, the same model answers 20 where the rule gives 16.
        b.nodes[2]["data"]["selected_output"] = "model_output"
        # CalculatorComponent only emits JSON; the one that can be handed to an
        # agent is CalculatorTool, through its api_build_tool output. Wiring the
        # other one fails the run with "has no matched type".
        calc = b.add("Calculator-tool", "CalculatorTool", "Calculator (tool)",
                     selected_output="api_build_tool", at=place["calc"])
        agent = b.add("ToolCallingAgent-agent", "ToolCallingAgent",
                      "Tool-calling agent", at=place["agent"])
        b.link(llm, "model_output", ["LanguageModel"], agent, "model", ["LanguageModel"], "model")
        b.link(calc, "api_build_tool", ["Tool"], agent, "tools", ["Tool"], "other")
        b.link(chat_in, "message", ["Message"], agent, "input_value", ["Message"])
        b.link(prompt, "prompt", ["Message"], agent, "system_prompt", ["Message"])
        b.link(agent, "response", ["Message"], chat_out, "input_value",
               ["Data", "JSON", "DataFrame", "Table", "Message"], "other")
    else:
        b.link(chat_in, "message", ["Message"], llm, "input_value", ["Message"])
        b.link(prompt, "prompt", ["Message"], llm, "system_message", ["Message"])
        b.link(llm, "text_output", ["Message"], chat_out, "input_value",
               ["Data", "JSON", "DataFrame", "Table", "Message"], "other")

    return b.flow(spec["name"], spec["desc"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:7860")
    ap.add_argument("--key", required=True)
    ap.add_argument("--model", default="qwen2.5:7b")
    ap.add_argument("--ollama", default="http://host.docker.internal:11434")
    ap.add_argument("--out", default="flows.json")
    a = ap.parse_args()

    catalog = api(a.base, "/api/v1/all", key=a.key)
    # The listing comes back as a bare list on some builds and paginated on
    # others; accept either rather than depend on which one this box has.
    listed = api(a.base, "/api/v1/flows/?page=1&size=100", key=a.key) or []
    if isinstance(listed, dict):
        listed = listed.get("items", [])
    existing = {f["name"]: f["id"] for f in listed if f.get("name")}

    # Rebuilding creates new ids, so every earlier attempt is left behind. A
    # Studio holding thirty-seven near-identical drafts is not something to show
    # anyone, so clear ours out before making this round.
    ours = {sp["name"] for sp in SCENARIOS}
    stale = [(n, i) for n, i in existing.items()
             if n in ours or n.startswith("Scenario ") or n.startswith("부서 업무 루틴")
             or " · " in n]
    for _name, fid in stale:
        api(a.base, f"/api/v1/flows/{fid}", key=a.key, method="DELETE")
    if stale:
        print(f"  cleared {len(stale)} earlier flow(s)")

    built = {}
    for spec in SCENARIOS:
        flow = build(catalog, spec, a.model, a.ollama)
        made = api(a.base, "/api/v1/flows/", flow, key=a.key)
        built[spec["id"]] = {"id": made["id"], "name": spec["name"],
                             "ask": spec["ask"], "kind": spec["kind"]}
        print(f"  {spec['id']:9} {made['id']}  {spec['name']}")

    with open(a.out, "w") as fh:
        json.dump(built, fh, ensure_ascii=False, indent=2)
    print(f"\nwrote {a.out}")


if __name__ == "__main__":
    main()

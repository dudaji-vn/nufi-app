// The narration, in both languages. Kept out of the recorder so the wording can
// be argued about without touching the machinery that verifies it.
export const SCRIPT = {
  en: {
    dir: 'ltr',
    font: '"IBM Plex Sans","Helvetica Neue",Arial,sans-serif',
    title: {
      eyebrow: 'NUFI TEAM · ON-PREM AI APPLIANCE',
      head: 'One box. The department&rsquo;s work stays inside it.',
      sub: ['A shared drive, an assistant that answers from your own documents,',
            'and a wall that is enforced rather than promised.',
            'Every answer in this recording is live.'],
    },
    arch: {
      eyebrow: 'HOW IT IS WIRED',
      head: 'Two products, one seam.',
      sub: ['MeshBox is the box: network, portal, drives, console. It runs no model.',
            'NuFi is the AI. Three adapters translate between them &mdash; that is the whole integration.'],
    },
    seam: {
      head: 'The seam, answering for itself.',
      body: 'Each adapter reports what it is really talking to. Nothing here is configured optimism.',
      cap: ['Three adapters, three upstreams.',
            'Chat and RAG reach a model on this machine; the agent reaches a flow engine on this machine.'],
    },
    status: {
      head: 'The console will not flatter the box.',
      cap: ['available, and only because it answered a probe.',
            'An unwired module reads not_connected. There is no configured green here.'],
    },
    drive: {
      head: 'The work already lives on the drive.',
      cap: ['Eight departments, eight shares.',
            'The same folder a laptop mounts as a network drive &mdash; and the same folder the AI answers from.'],
    },
    ask: {
      head: 'Ask the box about your own policy.',
      cap: ['&ldquo;What is the single-transaction limit on the corporate card?&rdquo;',
            'Asked in Korean, as the department would. The answer must come from the uploaded document.'],
      done: ['Answered from the department&rsquo;s own policy.',
             'The model ran on this machine. The document never left the box to be read.'],
    },
    refuse: {
      head: 'Now ask something the documents do not cover.',
      cap: ['&ldquo;Where do I return my laptop when I leave?&rdquo;',
            'Nothing on this box says. This is the question that separates a useful box from a dangerous one.'],
      done: ['It declines instead of inventing.',
             'For Legal or HR, a confident wrong answer is worse than no answer at all.'],
    },
    wall: {
      eyebrow: 'THE PART A BUYER SHOULD TEST',
      head: 'The wall is enforced, not promised.',
      sub: ['Same adapter, same department text, pointed at a public destination.'],
      cap: ['403. The software will not carry it off the mesh.',
            'Not a sentence in a brochure &mdash; a refusal you can reproduce with one request.'],
    },
    close: {
      eyebrow: 'WHAT YOU JUST WATCHED',
      head: 'Answers from your documents. Refusals you can trust.',
      sub: ['Eight departments, thirty-two checks, all passing &mdash; and two runs that differ in none of them.',
            'The transcript is committed next to this recording.'],
    },
  },
  ko: {
    dir: 'ltr',
    font: '"IBM Plex Sans KR","Apple SD Gothic Neo","Malgun Gothic",sans-serif',
    title: {
      eyebrow: 'NUFI TEAM · 부서 협업 AI 어플라이언스',
      head: '박스 한 대. 부서의 일이 그 안에서 끝납니다.',
      sub: ['공유 드라이브, 우리 문서로 답하는 도우미,',
            '그리고 말이 아니라 실제로 집행되는 경계.',
            '이 영상의 모든 답변은 실제 실행 결과입니다.'],
    },
    arch: {
      eyebrow: '어떻게 연결되어 있나',
      head: '두 제품, 하나의 이음매.',
      sub: ['MeshBox는 박스입니다 &mdash; 네트워크, 포털, 드라이브, 콘솔. 추론은 하지 않습니다.',
            'NuFi가 AI입니다. 어댑터 3개가 둘 사이를 번역합니다. 통합은 그게 전부입니다.'],
    },
    seam: {
      head: '이음매가 스스로 답합니다.',
      body: '각 어댑터는 자기가 실제로 무엇과 대화하는지 보고합니다.',
      cap: ['어댑터 3개, 상대 3개.',
            'Chat과 RAG는 이 장비의 모델에, 에이전트는 이 장비의 플로우 엔진에 닿습니다.'],
    },
    status: {
      head: '콘솔은 박스를 미화하지 않습니다.',
      cap: ['available &mdash; 프로브에 실제로 응답했기 때문입니다.',
            '연결되지 않은 모듈은 not_connected로 표시됩니다. 설정만으로 켜지는 초록은 없습니다.'],
    },
    drive: {
      head: '일은 이미 드라이브에 있습니다.',
      cap: ['8개 부서, 8개 공유함.',
            '노트북이 네트워크 드라이브로 붙는 그 폴더가, AI가 근거로 삼는 그 폴더입니다.'],
    },
    ask: {
      head: '우리 규정을 박스에 물어봅니다.',
      cap: ['&ldquo;법인카드 1회 사용 한도는 얼마인가요?&rdquo;',
            '답은 반드시 업로드한 문서에서 나와야 합니다.'],
      done: ['부서 자기 문서에서 답했습니다.',
             '추론은 이 장비에서 돌았습니다. 문서는 답을 얻기 위해 박스를 떠나지 않았습니다.'],
    },
    refuse: {
      head: '이번엔 문서에 없는 것을 물어봅니다.',
      cap: ['&ldquo;퇴사할 때 노트북은 어디에 반납하나요?&rdquo;',
            '이 박스의 어떤 문서에도 없습니다. 쓸모 있는 박스와 위험한 박스를 가르는 질문입니다.'],
      done: ['지어내지 않고 모른다고 답합니다.',
             '법무·인사에서는 자신 있게 틀린 답이 답이 없는 것보다 나쁩니다.'],
    },
    wall: {
      eyebrow: '구매자가 직접 확인해야 할 부분',
      head: '경계는 약속이 아니라 집행입니다.',
      sub: ['같은 어댑터, 같은 부서 문장, 목적지만 외부로.'],
      cap: ['403. 소프트웨어가 메시 밖으로 실어 나르지 않습니다.',
            '소개서의 한 문장이 아니라, 요청 한 번으로 재현되는 거절입니다.'],
    },
    close: {
      eyebrow: '방금 보신 것',
      head: '우리 문서에서 나온 답변, 믿을 수 있는 거절.',
      sub: ['8개 부서, 32개 확인 전부 통과 &mdash; 두 번 실행해도 답변이 하나도 달라지지 않았습니다.',
            '실행 기록은 이 영상 옆에 함께 커밋되어 있습니다.'],
    },
  },
};

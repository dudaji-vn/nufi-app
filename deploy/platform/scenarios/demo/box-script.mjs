// The narration for the box cut, in both languages. Kept out of the recorder so
// the wording can be argued about without touching the machinery that verifies
// it -- same split as script.mjs and week.mjs.
//
// Several captions in here come in pairs -- `q1Drift`/`q1Answered`,
// `q2`/`q2Drift` (with `q2Retry` between the attempts), `newCited`/`newDrift`,
// and `studioEmpty`/`studioFlows`. The recorder reads the screen first and then
// picks the one that is true of what it read. Neither half is a prediction, and
// the recorder never picks one without having read the thing it describes.
//
// `{n}` and `{max}` are filled in by the recorder with attempts it actually
// counted, so a caption can say how many tries a question took without anyone
// having to guess in advance.
export const BOX = {
  en: {
    font: '"IBM Plex Sans","Helvetica Neue",Arial,sans-serif',
    title: {
      eyebrow: 'NuFi APP · WEEK OF 2026-09-08',
      head: 'A NuFi box on a spare PC.',
      sub: ['One command installs the whole product on a machine a department already owns.',
            'Then that department&rsquo;s drive becomes its agent&rsquo;s knowledge &mdash; a file in, a cited answer out.',
            'Everything in this recording ran on this Mac while the camera was on.'],
    },

    install: {
      eyebrow: 'ONE COMMAND',
      head: '<code>./install-box.sh --yes</code>',
      sub: ['Four questions, then a banner. The banner is the whole result:',
            'four URLs, one login, and the folder each department drops its files into.'],
    },
    installCap: ['Seventy-five seconds, on a machine that already has the images.',
                 'That figure is the box&rsquo;s own README, not re-timed for the camera. The four URLs beside it were asked live, just now, and every one answered.'],

    login: ['The app, on the box&rsquo;s own name and the box&rsquo;s own certificate.',
            'No cloud account was created to reach this screen, and no certificate warning stood in front of it.'],
    model: ['The model in the corner is the one on this machine.',
            '<b>qwen2.5-7b</b>, served by Ollama on the host. It is the only model this box offers, and it never leaves the box.'],

    drive: {
      eyebrow: 'THE DRIVE IS THE INTERFACE',
      head: 'A department&rsquo;s knowledge goes in through a folder.',
      sub: ['No upload dialog, no admin screen, no per-file permission to grant.',
            'A file written into <code>data/drives/legal</code> is the Legal agent&rsquo;s knowledge a minute later.'],
    },
    askNew: ['Now a question only the new file can answer.',
             '&ldquo;Subcontract payments &mdash; within how many days of acceptance?&rdquo; That clause exists in the addendum and nowhere else on this box.'],
    newCited: ['It answers out of the file that landed on the drive a minute ago.',
               'The name above the answer is the addendum, not the old guide. Nothing was restarted, re-indexed by hand, or configured between the copy and this answer. The drive really is the whole interface.'],
    newDrift: ['It did not answer from the new file.',
               'Same agent, same drive, one more document on it &mdash; and the model either leaked its tool call again or read the older guide instead. The ingest is not in doubt; the daemon logged the embedding a minute ago. Choosing between two documents is what a 7B model is bad at, and a larger one on a GPU box is the lever.'],
    driveCap: ['A new Legal document, written into the drive while you watch.',
               'A subcontracting addendum to the department&rsquo;s clause guide. Nothing else about the box was touched to put it there.'],
    waiting: ['The watcher scans the drives every twenty seconds.',
              'It waits for a file to stop changing before it touches it, so a document still being written is never half-ingested. That costs one extra scan.'],
    ingested: ['<code>embedded=True</code> &mdash; and that is the whole ceremony.',
               'The daemon created the department&rsquo;s team and agent when the folder first appeared, and uploads every file to that agent as it lands. Nobody clicked anything.'],

    ask: ['Now the question the acceptance run asks the Legal agent first.',
          '&ldquo;A contract with an auto-renewal clause &mdash; how many days before expiry must notice be given?&rdquo; The answer is in the guide: sixty.'],
    q1Drift: ['The model leaked its tool call instead of making it.',
              'It printed the <code>file_search</code> call as prose, so retrieval never ran and no answer came back. This is one of the twenty-two failures, filmed rather than cut around.'],
    q1Answered: ['Sixty days, from the department&rsquo;s own guide.',
                 'The number was retrieved from the file on the drive, not recalled from training.'],
    ask2: ['Same agent, same drive, a question it does answer.',
           '&ldquo;How long does an NDA&rsquo;s confidentiality obligation survive the contract?&rdquo;'],
    q2Retry: ['It leaked the tool call again. Asking a second time.',
              'Attempt {n} of {max}. Nothing is being changed between tries &mdash; same agent, same drive, same question. A 7B model is simply not reliable about calling its tools.'],
    q2: ['Three years &mdash; and the file it read is named above the answer.',
         'Look at the passage it retrieved: Article 2 of that same guide is the one that says <b>sixty days</b>. The question before this one had that page a single tool call away, and never made the call.'],
    q2Drift: ['{max} attempts, {max} leaked tool calls.',
              'This is the ten-out-of-thirty-two, live and undisguised. The drive ingested, the agent exists, retrieval is wired &mdash; and a 7B model on CPU still will not reliably call the tool in front of it. That is the model, and a bigger one on a GPU box is the fix.'],

    sso: {
      eyebrow: 'ONE LOGIN',
      head: 'Four products, one account.',
      sub: ['The app, the console, the admin panel and Studio share the box&rsquo;s own identity.',
            'A member signs in once, on the box, and never sees a second password.'],
    },
    console: ['The console, opened from the app&rsquo;s own account menu.',
              'Same session, no second sign-in. This is the box&rsquo;s identity authority &mdash; it is what the other three ask.'],
    choose: ['&ldquo;You are already signed in.&rdquo; &mdash; the console&rsquo;s own words, not ours.',
             'One card, one click, and Studio opens on the same session.'],
    studioEmpty: ['NUFI Studio opens signed in, and empty.',
                  'The installer ships the four products, not the flows. Putting the department recipes into a fresh box &mdash; <code>build_flows.py --box</code> &mdash; is the next piece of work, and it is not done.'],
    studioFlows: ['NUFI Studio opens signed in, with the department flows already there.',
                  'The same account, the same box, a canvas a person can open and change.'],

    breadth: {
      eyebrow: 'WHAT IT SCORES',
      head: 'Eight departments, thirty-two questions, ten right.',
      sub: ['At temperature 0 with a fixed seed, and identical across two back-to-back runs &mdash; no answer differed.',
            'Every department ingested. Retrieval found the passage. The citation was right whenever one appeared.',
            'The mechanism holds; the score is the model&rsquo;s. A larger model on a GPU box is the lever that moves it &mdash; not more prompt tuning.'],
    },

    close: {
      eyebrow: 'NEXT',
      head: 'From home.',
      sub: ['A join file and a mesh, so the same box answers from an LTE hotspot with no public IP and no open port.',
            'Being built now. Nothing in this recording claims it works yet.'],
    },
  },

  ko: {
    font: '"IBM Plex Sans KR","IBM Plex Sans",-apple-system,sans-serif',
    title: {
      eyebrow: 'NuFi APP · 2026-09-08 주간',
      head: '남는 PC 한 대에 올린 NuFi 박스.',
      sub: ['부서가 이미 가지고 있는 장비에 명령 한 줄로 제품 전체가 설치됩니다.',
            '그다음부터는 부서 드라이브가 그 부서 에이전트의 지식이 됩니다 &mdash; 파일을 넣으면 출처가 붙은 답이 나옵니다.',
            '이 영상의 모든 장면은 촬영 중에 이 맥에서 실제로 실행됐습니다.'],
    },

    install: {
      eyebrow: '명령 한 줄',
      head: '<code>./install-box.sh --yes</code>',
      sub: ['질문 네 개, 그리고 배너 하나. 그 배너가 결과 전부입니다:',
            'URL 네 개, 로그인 하나, 그리고 부서가 파일을 넣는 폴더.'],
    },
    installCap: ['이미지가 이미 있는 장비 기준 75초.',
                 '이 숫자는 박스 README에 적힌 값이며 촬영을 위해 다시 재지 않았습니다. 옆의 URL 네 개는 방금 실제로 호출했고 전부 응답했습니다.'],

    login: ['박스 자신의 이름과 박스 자신의 인증서로 열리는 앱입니다.',
            '이 화면에 오기 위해 만든 클라우드 계정도, 앞을 가로막는 인증서 경고도 없습니다.'],
    model: ['오른쪽 위 모델은 이 장비에서 도는 모델입니다.',
            '호스트의 Ollama가 서빙하는 <b>qwen2.5-7b</b>. 이 박스가 제공하는 유일한 모델이고, 박스를 떠나지 않습니다.'],

    drive: {
      eyebrow: '드라이브가 곧 인터페이스',
      head: '부서 지식은 폴더로 들어갑니다.',
      sub: ['업로드 창도, 관리자 화면도, 파일마다 부여할 권한도 없습니다.',
            '<code>data/drives/legal</code>에 쓰인 파일은 1분 뒤 법무 에이전트의 지식입니다.'],
    },
    askNew: ['이제 새 파일만이 답할 수 있는 질문입니다.',
             '&ldquo;하도급 대금은 검수 완료 후 며칠 이내에 지급하나요?&rdquo; 이 조항은 방금 넣은 부속서에만 있고, 이 박스의 다른 어디에도 없습니다.'],
    newCited: ['1분 전 드라이브에 떨어진 그 파일에서 답이 나옵니다.',
               '답 위에 붙은 이름은 예전 가이드가 아니라 방금 넣은 부속서입니다. 복사와 이 답 사이에 재시작도, 수동 색인도, 설정 변경도 없었습니다. 드라이브가 정말로 인터페이스 전부입니다.'],
    newDrift: ['새 파일에서 답하지 못했습니다.',
               '같은 에이전트, 같은 드라이브, 문서 하나만 더 늘었을 뿐 &mdash; 그런데 모델이 또 도구 호출을 흘리거나 예전 가이드를 읽었습니다. 색인은 의심의 여지가 없습니다. 1분 전에 데몬이 임베딩을 로그로 남겼으니까요. 문서 두 개 중에 고르는 일이 7B 모델이 못하는 일이고, 지렛대는 GPU 박스 위의 더 큰 모델입니다.'],
    driveCap: ['새 법무 문서를 보시는 앞에서 드라이브에 씁니다.',
               '부서 표준 조항 가이드의 하도급 부속서입니다. 이걸 넣기 위해 박스의 다른 설정은 아무것도 건드리지 않았습니다.'],
    waiting: ['감시 데몬은 20초마다 드라이브를 훑습니다.',
              '파일이 더 이상 변하지 않는 것을 확인한 뒤에야 손을 대기 때문에, 아직 쓰는 중인 문서가 반쯤 색인되는 일이 없습니다. 대신 스캔 한 번을 더 씁니다.'],
    ingested: ['<code>embedded=True</code> &mdash; 의식은 이게 전부입니다.',
               '폴더가 처음 생겼을 때 데몬이 그 부서의 팀과 에이전트를 만들었고, 이후 들어오는 파일을 그 에이전트에 올립니다. 사람이 누른 버튼은 없습니다.'],

    ask: ['이제 인수 테스트가 법무 에이전트에게 가장 먼저 던지는 질문입니다.',
          '&ldquo;자동연장 조항이 있는 계약은 만료 며칠 전까지 통보해야 하나요?&rdquo; 가이드에 답이 있습니다 &mdash; 60일.'],
    q1Drift: ['모델이 도구 호출을 실행하지 않고 그대로 출력해 버렸습니다.',
              '<code>file_search</code> 호출을 글자로 찍어냈고, 그래서 검색은 아예 돌지 않았고 답도 없습니다. 22개 실패 중 하나이며, 잘라내지 않고 그대로 촬영했습니다.'],
    q1Answered: ['60일 &mdash; 부서 자기 가이드에서 나온 숫자입니다.',
                 '학습에서 떠올린 값이 아니라 드라이브의 파일에서 검색해 온 값입니다.'],
    ask2: ['같은 에이전트, 같은 드라이브, 이번엔 실제로 답하는 질문입니다.',
           '&ldquo;NDA의 비밀유지 의무는 계약 종료 후 몇 년간 존속하나요?&rdquo;'],
    q2Retry: ['또 도구 호출을 그대로 뱉었습니다. 다시 물어봅니다.',
              '{max}번 중 {n}번째 시도입니다. 시도 사이에 바꾼 것은 없습니다 &mdash; 같은 에이전트, 같은 드라이브, 같은 질문. 7B 모델은 도구 호출을 안정적으로 하지 못합니다.'],
    q2: ['3년 &mdash; 그리고 읽은 파일 이름이 답 위에 붙어 있습니다.',
         '검색해 온 본문을 보십시오. 같은 가이드의 제2조가 바로 <b>60일</b>을 말하는 조항입니다. 바로 앞 질문도 도구 호출 한 번이면 닿는 자리에 그 페이지가 있었고, 모델이 그 호출을 하지 않았을 뿐입니다.'],
    q2Drift: ['{max}번 시도, {max}번 모두 도구 호출 유출.',
              '32개 중 10개라는 숫자가 그대로 화면에 있습니다. 드라이브는 색인됐고, 에이전트는 있고, 검색은 연결돼 있습니다 &mdash; 그런데 CPU 위의 7B 모델은 눈앞의 도구조차 안정적으로 부르지 못합니다. 이건 모델의 문제이고, 해법은 GPU 박스 위의 더 큰 모델입니다.'],

    sso: {
      eyebrow: '로그인 한 번',
      head: '제품 넷, 계정 하나.',
      sub: ['앱, 콘솔, 어드민 패널, 스튜디오가 박스 자신의 신원을 공유합니다.',
            '구성원은 박스에서 한 번 로그인하고, 두 번째 비밀번호를 볼 일이 없습니다.'],
    },
    console: ['앱의 계정 메뉴에서 그대로 연 콘솔입니다.',
              '같은 세션, 재로그인 없음. 나머지 셋이 신원을 물어보는 곳이 바로 여기입니다.'],
    choose: ['&ldquo;이미 로그인되어 있습니다&rdquo; &mdash; 우리 말이 아니라 콘솔이 하는 말입니다.',
             '카드 하나, 클릭 한 번이면 같은 세션으로 스튜디오가 열립니다.'],
    studioEmpty: ['NUFI 스튜디오는 로그인된 채로, 그리고 비어 있는 채로 열립니다.',
                  '설치 프로그램은 제품 넷을 올릴 뿐 플로우는 넣지 않습니다. 새 박스에 부서 레시피를 함께 넣는 일 &mdash; <code>build_flows.py --box</code> &mdash; 이 다음 작업이고, 아직 되어 있지 않습니다.'],
    studioFlows: ['NUFI 스튜디오가 로그인된 채로, 부서 플로우와 함께 열립니다.',
                  '같은 계정, 같은 박스, 사람이 열어서 고칠 수 있는 캔버스.'],

    breadth: {
      eyebrow: '점수는 이렇습니다',
      head: '8개 부서, 32개 질문, 10개 정답.',
      sub: ['온도 0에 시드 고정, 연속 두 번 실행에서 답이 하나도 달라지지 않았습니다.',
            '모든 부서가 색인됐고, 검색은 해당 본문을 찾아냈고, 출처가 붙은 경우 출처는 늘 옳았습니다.',
            '구조는 버팁니다. 점수는 모델의 몫입니다. 이걸 움직이는 지렛대는 프롬프트 튜닝이 아니라 GPU 박스 위의 더 큰 모델입니다.'],
    },

    close: {
      eyebrow: '다음',
      head: '집에서.',
      sub: ['조인 파일 하나와 메시. 공인 IP도 열린 포트도 없이 LTE 핫스팟에서 같은 박스가 답하게 하는 것.',
            '지금 만들고 있습니다. 이 영상은 그게 된다고 주장하지 않습니다.'],
    },
  },
};

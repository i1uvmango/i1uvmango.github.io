---
title: "Bridge X — AI가 위기를 감지하면 사람을 부른다"
lede: "챗봇이 상담을 대신하지 않는다. 자해·자살 신호를 잡는 순간 Webex 미팅을 자동으로 열고 사람에게 넘긴다. 그 골든타임을 코드로 어떻게 구현했는가."
category: ai
order: 2
award: "🏆 Cisco 3rd"
tags: ["NestJS", "Next.js", "Gemini", "Webex API"]
repo: "https://github.com/i1uvmango/Bridge_X"
thumb: /assets/bridge_x.jpg
hero: /assets/bridge_x.jpg
hero_alt: "Bridge X의 Webex 긴급 상담 알림 화면"
hero_caption: "위기 감지 시 생성되는 Webex 상담방. 호스트가 아직 없어도 아이가 먼저 들어갈 수 있다."
summary: "Gemini 챗봇이 분쟁지역 청소년과 대화하다 위기 신호를 감지하면 Webex 화상 미팅을 자동 생성해 전문 상담사에게 연결하는 NestJS 플랫폼. Cisco 주관 프로젝트 3위."
---

## 왜 만들었나

분쟁지역이나 재난 상황의 청소년은 극심한 트라우마를 겪지만 심리 상담 인프라가 없다. UNHCR 기준으로 난민 중 정신건강 서비스를 받는 비율은 **5% 미만**이다.

여기서 흔한 접근은 "AI 상담사"를 만드는 것이다. 그런데 그건 위험하다. 자살 위험이 있는 아이에게 챗봇이 상담을 끝까지 하는 구조는 만들면 안 된다.

그래서 역할을 이렇게 잘랐다.

> **AI는 다리의 입구다. 다리를 건너면 사람이 기다린다.**

AI가 하는 일은 두 가지뿐이다 — **24시간 즉각 응답**과 **위기 신호 감지**. 감지하는 순간 AI는 빠지고 전문 상담사와의 화상 연결이 열린다. 이름의 Bridge는 연결, X는 무한 가능성이자 We**b**e**X**다.

## 위기 감지를 어떻게 구현했나

핵심은 **LLM 응답 자체에 제어 신호를 실어 보내는 것**이다.

`CHAT_SYSTEM_PROMPT`는 Gemini에게 세 가지를 시킨다 — 2~3문장으로 짧게, 사용자가 쓴 언어 그대로, 그리고 **위기 징후가 보이면 응답 맨 앞에 `[RISK_DETECTED]`를 붙여라.** few-shot 예시 3개로 판단 기준을 고정했다.

백엔드는 응답을 받아 이 태그를 찾는다. 있으면 태그를 잘라내 사용자에게는 보이지 않게 하고, 동시에 미팅 생성 경로를 탄다.

```
사용자 메시지 → Gemini(gemini-2.5-flash)
  → 응답에 [RISK_DETECTED] 있음?
      ├ 예 → 태그 제거 + WebexService.createCounselingMeeting(isUrgent=true)
      │        → meeting_url을 채팅 응답 JSON에 동봉
      │        → 프론트가 "🚨 [긴급 상담 연결] 상담실 입장하기" 메시지 삽입
      └ 아니오 → 그냥 대화 계속
```

별도 분류 모델을 붙이지 않고 같은 호출 안에서 처리하므로 **추가 지연이 0**이다. 위기 상황에서 초 단위가 의미 있다는 전제에서 나온 선택이다.

트리거는 실제로 세 갈래다.

<div class="tw" markdown="1">

| 경로 | 발동 조건 | 긴급 |
|---|---|---|
| 채팅 중 감지 | 응답에 `[RISK_DETECTED]` | ✓ `[긴급] 심리 상담 세션` |
| 감정 요약 | `SummaryService`가 `risk_flag=true` 판정 | ✓ |
| 사용자 요청 | `POST /api/counseling/request` | ✗ `[상담 요청]` |

</div>

## Webex 미팅 옵션이 곧 기획이다

미팅을 만드는 코드에서 가장 중요한 줄은 이것이다.

```
enabledJoinBeforeHost: true
joinBeforeHostMinutes: 5
```

**호스트(상담사)가 아직 방에 없어도 아이가 먼저 들어갈 수 있다.** 일반적인 화상회의 설정에서는 호스트가 시작해야 참가자가 입장한다. 그 기본값을 그대로 뒀다면 위기 상황의 아이는 "호스트를 기다리는 중" 화면을 보게 된다. "골든타임 확보"라는 기획 문장이 실제로 구현된 지점은 여기 한 줄이다.

나머지 옵션도 목적에 맞춰 정했다.

<div class="tw" markdown="1">

| 옵션 | 값 | 이유 |
|---|---|---|
| `start` / `end` | 지금 즉시 / +60분 | 예약이 아니라 즉시 개설 |
| `publicMeeting` | `false` | 링크를 아는 사람만 |
| `enabledAutoRecordMeeting` | `false` | 상담 내용 녹화하지 않음 |
| `allowAnyUserToBeCoHost` | `false` | 제3자 권한 상승 차단 |

</div>

## 익명성을 스키마로 강제했다

프라이버시를 "설계 원칙"으로만 두지 않고 **데이터 모델에서 불가능하게** 만들었다.

**대화 원문을 저장하는 컬럼이 아예 없다.** `ai_summaries` 엔티티가 가진 건 감정 태그(jsonb), 지배 감정, 반복 주제(jsonb), `risk_flag`, `intensity_score`뿐이다. 요약을 만든 직후 `chatService.clearSession()`으로 메모리에서 대화를 지운다. 유출될 원문이 애초에 존재하지 않는다.

감정 분석 프롬프트에도 **"원문 대화 내용을 포함하지 마세요"**를 명시했다. LLM이 요약 JSON에 원문을 흘리는 경로까지 막은 것이다.

위기 경로는 한 발 더 간다. 미팅을 만들 때 넘기는 사용자 식별자가 실제 유저가 아니라 **`anonymous-{세션ID 8자}`**이고, summaryId는 `'crisis-auto-generated'` 문자열이다. **DB에 사용자 등록을 하지 않아도 상담방이 열린다.** 회원가입이 위기 대응의 장애물이 되지 않게 한 선택이다.

여기에 중복 방지가 붙는다. `sessionCrisisStore`라는 별도 `Map`으로 **세션당 미팅을 1회만** 생성한다. 대화가 길어지며 위기 신호가 반복 감지될 때 상담방이 여러 개 열리는 걸 막는다. 코드 주석에는 고민 흔적이 그대로 남아 있다 — *"But for safety, maybe we allow multiple?"*

## Bot 토큰으로는 미팅을 못 만든다

기획 단계에서는 Webex **Bot**이 미팅을 만들고 상담사에게 푸시 알림을 보내는 그림이었다. 실제로는 그렇게 되지 않았고, 저장소에 그 검증 로그가 남아 있다.

`backend/test-output.txt` — 봇 계정(`webex.siri@webex.bot`)으로 People API는 통과했지만 **Meeting Creation에서 에러**.
`backend/result.json` — User Token(`type: person`)으로 바꾸자 *"✅ Good: This is a USER token."* 이후 미팅 생성 성공. 실제로 만들어진 미팅 번호 `26422739161`.

그래서 최종 구조는 `WEBEX_ACCESS_TOKEN`(User Token)으로 `https://webexapis.com/v1/meetings`를 호출하는 방식이 됐다. Webex Bot은 메시징 API에는 접근하지만 **Meetings API 권한 범위가 다르다**는 걸 실패 로그로 확인한 셈이다.

미팅 상태는 웹훅으로 동기화한다 — `meeting.started → in_progress`, `meeting.ended → completed`.

## AI가 죽어도 서비스는 죽지 않게

정신건강 서비스에서 500 에러는 특히 나쁘다. `GEMINI_API_KEY`가 없거나 초기화에 실패하면 `isAvailable=false`로 두고 **사과 문구를 반환**한다. 감정 요약도 예외를 던지지 않고 `{tags:[], dominant:'unknown', risk_flag:false, intensity:0}` 기본값을 돌려준다.

에러 메시지에 `API key` / `quota` / `404`가 들어 있는지로 원인을 분기한다. 문자열 매칭이라 견고하진 않지만, 최소한 어떤 실패든 사용자에게는 "지금은 답하기 어렵다"는 문장으로 도달한다.

## 프로토타입에서 아직 안 된 것

문서가 그리는 그림과 코드가 갈리는 지점이 몇 군데 있다. 정리해둔다.

- **상담사 푸시 알림이 미구현이다.** 미팅은 생성되고 URL도 나오지만, Webex Messages API로 상담사에게 알림을 보내는 코드가 저장소에 없다. 현재는 링크가 아이에게만 전달된다. 이게 가장 큰 구멍이다.
- **웹훅 서명 검증이 비어 있다.** `verifyWebhookSignature()`가 `return true;` 고정이고 주석에 *"In production, implement proper signature verification"*이 붙어 있다.
- **세션 저장소가 전역 `Map`이다.** TTL도 없고 프로세스가 재시작되면 유실되며 다중 인스턴스에서는 공유되지 않는다. 코드 주석도 *"production should use Redis"*라고 인정하고 있다.
- **`intensity_score`의 범위가 문서마다 다르다.** 보고서는 1–10, 프롬프트는 0.0–1.0, 엔티티는 `float default 0`. 실사용 전에 통일이 필요하다.
- 모델명 마이그레이션 잔재도 있다. 코드는 `gemini-2.5-flash`를 쓰는데 초기화 로그는 여전히 `gemini-1.5-flash`를 출력한다.

## 기술 스택

NestJS 11 + TypeORM + PostgreSQL 백엔드, Next.js + React 프론트엔드, `@google/generative-ai`로 Gemini 호출, Webex Meetings REST API. 모듈은 `user / chat / summary / counseling / webex / admin`으로 나눴고, `ChatModule ↔ WebexModule`이 서로를 필요로 해 `forwardRef()`로 순환 의존을 풀었다.

CORS는 `localhost:3000|3001`만 허용하고, 글로벌 `ValidationPipe`에 `whitelist`와 `forbidNonWhitelisted`를 걸어 정의되지 않은 필드가 들어오면 요청 자체를 거부한다.

---

Cisco 주관 프로젝트 3위. MIT License.

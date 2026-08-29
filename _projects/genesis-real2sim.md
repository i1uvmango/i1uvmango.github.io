---
title: "Genesis Real2Sim — 경로를 따라가는 것과, 벗어난 뒤 돌아오는 것"
lede: "주행을 nominal과 off-nominal 두 갈래로 쪼갰다. 평상시는 실측 역동역학 테이블 + Stanley로, 이탈했을 때는 복구 경로 플래너로. MPPI는 실시간 제어기가 아니라 라벨 생성기 자리로 물러났다."
category: robotics
order: 1
tags: ["Flagship", "Genesis", "MPPI", "Stanley", "Residual RL"]
repo: "https://github.com/i1uvmango/Genesis_AI_Sim2real_Real2sim"
thumb: /assets/genesis.gif
hero: /assets/genesis.gif
hero_alt: "Genesis viewer에서 차량이 경로를 추종하며 주행하는 장면"
hero_caption: "Genesis viewer. 회색이 GT 경로, 파란 선이 수정된 참조 경로, 빨간 궤적이 차량이 실제로 그린 선이다."
summary: "Genesis 물리엔진 위에서 주행을 nominal(Sweep+Stanley+RL)과 off-nominal(Recovery Path Planner) 두 갈래로 나눠 푸는 연구. Real2Sim–Sim2Real 정책 전이로 확장한다."
---

## 문제를 두 갈래로 나눴다

경로 추종을 하나의 문제로 놓고 풀면 정책이 애매해진다. **경로 위에 잘 있을 때 해야 할 일**과 **경로에서 벗어났을 때 해야 할 일**은 목적 함수가 다르기 때문이다. 전자는 오차를 0 근처로 유지하는 문제고, 후자는 지금 자세와 속도에서 **다시 붙을 수 있는 궤적을 새로 만드는** 문제다.

그래서 GT 경로 하나에서 두 축을 갈랐다.

<figure>
  <img loading="lazy" src="{{ '/assets/genesis/two-branch.png' | relative_url }}" alt="GT path에서 nominal driving과 off-nominal recovery 두 갈래로 갈리는 구조도">
  <figcaption>GT path → nominal(Tracking / Generalization)은 Sweep + Stanley + RL로, off-nominal(Recovery)은 Recovery Path Planner로. 복구된 경로는 다시 GT path로 합류한다.</figcaption>
</figure>

<div class="tw" markdown="1">

| 축 | 상황 | 담당 |
|---|---|---|
| **Nominal** | 경로 위, 추종·일반화 | Sweep Table + Stanley + RL |
| **Off-nominal** | 이탈 상태, 복구 | Recovery Path Planner |

</div>

## MPPI는 주행기가 아니라 라벨 생성기다

Genesis 위에서 MPPI는 매 스텝 **2048개 후보 궤적을 병렬 env로 동시에 굴려** 비용 최소 궤적 하나를 고른다. 물리적으로 최적에 가까운 제어를 얻는 방법이다.

<figure>
  <img loading="lazy" src="{{ '/assets/genesis/mppi-fan.gif' | relative_url }}" alt="MPPI가 2048개 후보 궤적을 부채꼴로 전개하고 그중 하나만 실행하는 장면">
  <figcaption>반투명 고스트가 2048개의 "상상한 미래"(imagination rollout)이고, 실제로 주행하는 건 비용 최소 후보 하나(golden T, S)다.</figcaption>
</figure>

문제는 비용이다. **매 스텝 이 최적화를 반복해야 하고, 오프라인 마이닝에 30분 + Optuna 튜닝에 3~10시간**이 든다. 실시간 주행에 그대로 얹을 수 있는 물건이 아니다.

그래서 MPPI를 **제어기 자리에서 내리고 라벨 생성기 자리에 두는** 것이 이 프로젝트의 출발점이 됐다. 최적성은 오프라인에서 취하고, 실주행은 훨씬 싼 것으로 한다.

## Nominal — 실측 테이블과 Stanley

실주행을 맡는 쪽은 두 부분이다.

<figure>
  <img loading="lazy" src="{{ '/assets/genesis/sweep-stanley.png' | relative_url }}" alt="Sweep Table과 Stanley 제어기의 구조 및 수식">
  <figcaption>왼쪽 Sweep Table — 오프라인 실측 역동역학. 오른쪽 Stanley — 폐루프 피드백 제어기.</figcaption>
</figure>

**Sweep Table — 오프라인으로 재둔 역동역학.** 동일 초기조건 `(v, pitch, roll)`에서 조향 S를 고정하고 **2초 롤아웃**을 굴려 결과 `(a, ω)`를 측정한다. 이 측정값 한 칸 한 칸이 테이블이 된다.

```
사전 측정:  (v, pitch, roll, T, S)  →  (a, ω)
주행 시:    (v, pitch, roll, 목표 a·ω)  →  (T, S)     ← 역조회
```

해석적 차량 모델을 세워 역산하는 대신 **엔진이 실제로 내놓은 값을 표로 갖고 있다가 거꾸로 찾는다.** 지형 경사(pitch, roll)가 인덱스에 들어가 있어서, 오르막과 내리막에서 같은 목표 가속도라도 다른 스로틀이 나온다.

**Stanley — 목표 `(a, ω)`를 만드는 폐루프.** 경로까지의 수직 거리 CTE(`e`)와 헤딩 오차 HE(`ψ = ψ_path − ψ_veh`)를 받아 목표 각속도와 가속도를 낸다.

```
ω_target = k_ψ · ψ − atan( k · e / (v + c) )     ← 헤딩 항 + 횡오차 항
a_target = k_v · (V_ref − v)                      ← 속도 추종 항
```

<div class="tw" markdown="1">

| 파라미터 | 값 |
|---|---|
| `k_ψ` (헤딩 게인) | 4.0 ~ 9.0 (v 8~20 m/s 구간에서 스케줄) |
| `k` (횡오차 게인) | 3.0 |
| `k_v` (속도 게인) | 2.0 |
| 조향각 한계 | `\|δ\| ≤ 0.7 rad` |
| lookahead `la` | `clamp(0.25·v, 0.8, 2.0)` m |

</div>

lookahead가 속도에 비례하되 0.8–2.0 m로 잘려 있다. 저속에서 너무 가까운 점을 보면 진동하고, 고속에서 너무 먼 점을 보면 코너를 잘라 먹기 때문이다.

Stanley가 목표 `(a, ω)`를 내면 Sweep Table이 그걸 `(T, S)`로 바꾼다. **제어 로직과 차량 동역학이 완전히 분리**되어 있어서, 차량이 바뀌면 테이블만 다시 재면 된다.

<figure>
  <img loading="lazy" src="{{ '/assets/genesis/plan-p120.gif' | relative_url }}" alt="Stanley 제어로 경로를 추종하며 주행하는 장면">
  <figcaption>시나리오 p120. HUD에 <code>ctrl STN</code>(Stanley), 도달 오차 <code>arr 0.01 m</code>가 찍힌다. 회색이 GT 경로, 파랑이 수정된 참조 경로, 빨강이 차량 궤적. 빨간 박스는 정적 장애물, 주황 박스는 이동 장애물이다.</figcaption>
</figure>

## Off-nominal ① — 처음 시도: RL 기반 복구 (Switch Policy)

처음 접근은 **정책을 갈아 끼우는** 것이었다. 정상 주행은 Nominal Controller + residual RL이 맡고, disturbance로 경로를 이탈하면 **RL_recovery로 model switch**, 정상 범위로 복귀하면 다시 nominal로 돌아온다.

이 복구 정책이 보는 관측을 7개로 설계했다. 좌표계에 의존하는 절대값 대신 **경로와 차량의 상대 관계**로 구성한 게 요점이다.

<figure>
  <img loading="lazy" src="{{ '/assets/genesis/obs-features.png' | relative_url }}" alt="차량과 목표점 사이의 7가지 관측 피처를 표시한 그림">
  <figcaption>RL_recovery의 관측 — ① 거리 d ② bearing ③ align ④ approach speed ⑤ velocity ⑥ yaw rate ⑦ steering.</figcaption>
</figure>

<div class="tw" markdown="1">

| # | 피처 | 의미 |
|---|---|---|
| ① | `d` | 목표점까지의 거리 |
| ② | bearing | 차량 기준 목표점 방위 |
| ③ | align | 목표점에서의 경로 방향과 접근 방향의 정렬 |
| ④ | approach speed | 목표점을 향해 줄어드는 속도 성분 |
| ⑤ | velocity | 차량 속도 벡터 |
| ⑥ | yaw rate | 요 각속도 — 오버/언더스티어 감지 |
| ⑦ | steering | 현재 조향 입력 |

</div>

②와 ③을 분리한 게 의도적이다. bearing만 있으면 "목표점이 어느 쪽인가"는 알지만 **도착했을 때 어느 방향을 보고 있어야 하는가**를 모른다. align이 그 자세 조건을 담는다. ⑥ yaw rate는 복구 상황에서 특히 중요하다 — 차체가 이미 돌기 시작했는지를 알려주는 신호이기 때문이다.

이 방식은 **경로를 새로 만들지 않고 주행 policy만으로** 복구한다. 실제로 대부분의 시나리오에서 돌아왔다.

<figure>
  <img loading="lazy" src="{{ '/assets/genesis/recovery-grid.png' | relative_url }}" alt="RL 기반 복구 시나리오 궤적 결과 그리드, 대부분 초록 테두리이고 하나가 빨강">
  <figcaption>RL 기반 복구의 시나리오별 결과. 초록이 성공, 빨강이 실패. 직선·급커브·원형 순환로·8자·직각 코너까지 대부분 통과했지만 <b>실패가 남는다.</b></figcaption>
</figure>

그런데 남은 빨간 칸이 문제였다. **왜 실패했는지 정책 안을 들여다볼 방법이 없다.** 고치려면 보상을 다시 설계하고 재학습을 돌린 뒤, 다른 시나리오가 망가지지 않았는지 전부 다시 확인해야 한다. 복구 정책은 blackbox였다.

## Off-nominal ② — 현재: 복구는 제어가 아니라 계획 문제다

그래서 정책을 바꾸는 대신 **경로를 만들기로** 했다. 경로에서 크게 벗어났을 때 필요한 건 더 센 피드백이 아니라, 지금 자세와 속도에서 **물리적으로 갈 수 있는 새 경로**다. 그 경로만 있으면 주행은 이미 검증된 nominal 스택이 그대로 한다.

<figure>
  <img loading="lazy" src="{{ '/assets/genesis/recovery-modes.gif' | relative_url }}" alt="spawn pose, lateral kick, spin 세 가지 외란 상황에서의 복구 주행">
  <figcaption>세 가지 외란 상황 — spawn pose(소환 자세 이상), lateral kick(충돌에 의한 횡방향 shift), spin(주행 중 스핀). 각각에서 복구 경로를 생성해 GT 경로로 돌아온다.</figcaption>
</figure>

<figure>
  <img loading="lazy" src="{{ '/assets/genesis/recovery-flow.png' | relative_url }}" alt="Recovery Supervisor에서 MERGE까지의 복구 파이프라인">
  <figcaption>Recovery Supervisor → SETTLE → Recovery Planner → Recovery Reference → MERGE.</figcaption>
</figure>

**SETTLE이 먼저 온다.** 이탈 직후는 자세와 속도가 요동치는 상태라, 그 위에서 세운 계획은 곧 무효가 된다. 그래서 계획을 세우기 전에 상태를 안정화시키는 단계를 명시적으로 둔다.

플래너 내부는 네 단계다.

<figure>
  <img loading="lazy" src="{{ '/assets/genesis/replan-steps.png' | relative_url }}" alt="Feasibility Test 1, Candidate Generation, Feasibility Test 2, Cost Evaluation 4단계">
  <figcaption>Replan / Planner Steps — 후보 생성 <b>앞뒤로</b> feasibility 검사가 한 번씩 들어간다.</figcaption>
</figure>

<div class="tw" markdown="1">

| 단계 | 하는 일 |
|---|---|
| **Feasibility Test 1** | 현재 상태에서 복구 자체가 가능한지 사전 판정 |
| **Candidate Generation** | 복구 후보 궤적 생성 |
| **Feasibility Test 2** | 생성된 후보가 물리적으로 실행 가능한지 검사 |
| **Cost Evaluation** | 통과한 후보 중 비용 최소 선택 |

</div>

feasibility 검사가 **후보 생성 앞뒤로 두 번** 들어간 게 이 구조의 핵심이다. 앞의 검사는 "지금 복구가 되는 상황인가"를 걸러 헛계획을 막고, 뒤의 검사는 "만든 후보가 실제로 굴러가는가"를 본다. 앞의 것만 있으면 실행 불가능한 궤적이 나오고, 뒤의 것만 있으면 전부 탈락할 상황에서 계산만 태운다.

선택된 궤적은 **Recovery Reference**가 되고 **MERGE**에서 원래 GT 경로로 합류한다. 복구가 끝나면 다시 nominal 축으로 돌아가는 것이다.

## RL 기반에서 Path Planner 기반으로 — 무엇이 달라졌나

같은 이탈 상황에서 두 방식을 나란히 돌렸다.

<figure>
  <img loading="lazy" src="{{ '/assets/genesis/plan-p120-compare.gif' | relative_url }}" alt="learning-based recovery와 recovery path planner의 나란한 비교">
  <figcaption>왼쪽 learning-based recovery, 오른쪽 recovery path planner. 같은 이탈 상황에서 두 방식이 그리는 복구 궤적을 비교한다.</figcaption>
</figure>

<div class="tw" markdown="1">

| | RL 기반 복구 | **Recovery Path Planner 기반** |
|---|---|---|
| 복구 방식 | 정책의 경험적 선택 | 물리적 feasibility 제약으로 생성 |
| 설명 가능성 | blackbox | 후보·feasibility·cost **역추적 가능** |
| 기존 스택 | Recovery 전용 RL 학습 필요 | **nominal 스택 그대로 사용** |
| 실패 대응 | 보상 재설계 + 재학습 | **rule 수정만으로 해결** |

</div>

RL 기반에서 실패로 남았던 scene도 플래너 기반에서는 **어느 제약이 잘못 걸렸는지 역추적해서 그 규칙만 고치는** 것으로 해결됐다. 재학습이 없었다.

## 스케일 — 지형과 병렬 환경

지형은 **3 km × 3 km** 규모다. 차량 길이 4.5 m와 비교하면 스케일 차이가 크다.

<figure>
  <img loading="lazy" src="{{ '/assets/genesis/t3k-flyover.gif' | relative_url }}" alt="T3k 3km x 3km 지형과 99개 학습 경로 플라이오버">
  <figcaption>T3k 지형 플라이오버. 노란 선이 타일 경계, 회색이 99개 학습 경로다. 구역(T0~T8)마다 mesh 특성이 다르다.</figcaption>
</figure>

<figure>
  <img loading="lazy" src="{{ '/assets/genesis/t3k-terrain.png' | relative_url }}" alt="3km 지형 전체, 100m 줌, 차량 근접 뷰 3단 비교">
  <figcaption>지형 전체(위) → 약 100 m 줌(가운데) → 차량(아래). 접지 검증값 <code>z_car − z_terrain = 0.06 m</code>, <code>v = 10.7 m/s</code>.</figcaption>
</figure>

`z_car − z_terrain = 0.06 m`는 **차량이 지형에 떠 있거나 파묻히지 않았다**는 접지 검증값이다. 이런 규모의 하이트필드에서는 이 값이 조용히 어긋나면서 물리가 망가지는 일이 흔하다.

병렬 환경 수에 따른 처리량도 재봤다.

<figure>
  <img loading="lazy" src="{{ '/assets/genesis/gpu-cpu.png' | relative_url }}" alt="병렬 환경 수에 따른 CPU와 GPU 처리량 비교 그래프">
  <figcaption>병렬 L3 환경 수 N에 대한 처리량(env-steps/s). 300~400 구간에서 GPU가 확실히 앞선다.</figcaption>
</figure>

<div class="tw" markdown="1">

| N | CPU | GPU |
|---|---|---|
| 30 | 2.5k | 2.1k |
| 100 | 5.7k | 6.4k |
| 200 | 7.3k | 6.3k |
| **400** | 8.7k | **14.4k (1.66×)** |

</div>

작은 배치에서는 **GPU 런치 오버헤드가 이득을 먹어버린다.** N=30에서는 오히려 CPU가 빠르고, 200까지도 뒤집힌다. 배치를 300~400까지 넓혀 고정 오버헤드가 분산되고 나서야 GPU가 1.66배로 벌린다.

이건 "GPU가 빠르다"가 아니라 **"몇 대부터 GPU로 넘길 것인가"**의 문제다. 학습 환경 수를 정할 때 그냥 최대로 올리는 게 아니라, 이 곡선의 어느 지점에 서 있는지를 보고 정해야 한다.

<figure>
  <img loading="lazy" src="{{ '/assets/genesis/blender-path.png' | relative_url }}" alt="Blender에서 렌더링한 지형과 경로를 따르는 차량들">
  <figcaption>Blender 쪽 지형·경로. 이 정합이 성립하면 그 자리에 실제 현실을 치환한다 — 그게 Real2Sim이다.</figcaption>
</figure>

## Real2Sim의 관문 — inverse-dynamics mapper

현실을 넣으려면 문제가 하나 더 있다. **현실 주행 데이터에는 제어 입력이 없다.** 차가 어떤 궤적을 그렸는지는 관측되지만, 그 순간 스티어를 몇 도 꺾고 브레이크를 얼마나 밟았는지는 로그에 남지 않는다. 있다 해도 그 값을 Genesis에 그대로 넣으면 같은 궤적이 나오지 않는다.

그래서 **정책 학습을 시작하기 *전에*** 두 가지를 복원한다.

<div class="tw" markdown="1">

| 복원 대상 | 하는 일 |
|---|---|
| **Trajectory→Controls mapper** | 관측된 궤적에서 잠재 제어 입력 (Steer, Brake)을 역산 |
| **Inverse-dynamics 보정항** | 그 제어를 Genesis에 넣었을 때 실제 롤아웃과 어긋나는 차이를 보정 |

</div>

도메인 randomization으로 간극을 덮는 대신 **간극 자체를 먼저 측정하고 좁힌 뒤** 그 위에서 학습한다. Sweep Table이 시뮬레이터 안에서 역동역학을 표로 갖는 방식이라면, 이건 같은 발상을 시뮬레이터–현실 사이에 적용한 것이다.

그래도 해석적으로 안 맞는 잔차는 남는다. 지형 접촉, 하중 이동에 따른 서스펜션 응답 같은 것들이다. 이 부분은 **학습된 보정항(Neural Physics)**으로 흡수한다 — 물리 엔진을 신경망으로 대체하는 게 아니라, 엔진이 계산한 값 위에 보정을 얹는다.

## 지금 상태

<div class="tw" markdown="1">

| 항목 | 상태 |
|---|---|
| Sim2Sim 정합 (Blender ↔ Genesis) | 완료 |
| MPPI 골든 라벨 채굴 | 완료 |
| Sweep Table + Stanley (nominal) | 완료 |
| 장애물 회피 (정적 / 이동) | 동작 |
| Recovery Path Planner (off-nominal) | 시나리오 그리드 검증, 실패 1건 |
| 학습 기반 복구 vs 플래너 비교 | 진행 |
| Residual RL | 진행 |
| Inverse-dynamics mapper | 진행 |
| Neural Physics | 진행 |
| Multi-agent (3v3, MARL) | 랩 병행 축 |
| Sim2Real | 최종 목표 |

</div>

## 기술 스택

Python · PyTorch · **Genesis** · Isaac Lab · Blender. 제어는 Stanley + Sweep Table 실측 역동역학, 최적화는 MPPI(오프라인 라벨) + Optuna, 학습은 behavior cloning → residual RL(PPO) 계열, 멀티에이전트 축은 QMIX 계열이다.

<div class="callout" markdown="1">
저장소에는 연구 기록 <b>50여 편</b>이 <code>car_test/docs/</code> 아래 쌓여 있다. ray-wheel 충돌 모델, Pacejka 타이어 모델, MPPI warm-start 파라미터, 보상 함수 설계 같은 세부는 그쪽에 정리되어 있다.

소속 랩의 공식 프로젝트 소개는 <a href="https://korfriend.github.io/Projects/real2sim-sim2real/">DIGLAB — Real2Sim &amp; Sim2Real</a>에 있다.
</div>

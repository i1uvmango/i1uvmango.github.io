---
title: "Genesis Real2Sim — 외란 복구 주행"
lede: "경로를 잘 따라가기만 하면 된다. 벗어나면 새 경로를 만들어 다시 붙는다. MPPI+MLP를 Sweep Table+Stanley로 갈아치우고, RL 복구를 경로 플래너로 바꾼 기록."
category: robotics
order: 1
tags: ["Flagship", "Genesis", "Residual RL", "Path Planning", "DIGLAB"]
repo: "https://github.com/i1uvmango/Genesis_AI_Sim2real_Real2sim"
thumb: /assets/genesis.gif
hero: /assets/genesis.gif
hero_alt: "Genesis viewer에서 차량이 경로를 추종하며 주행하는 장면"
hero_caption: "Genesis viewer. 회색이 GT 경로, 파란 선이 수정된 참조 경로, 빨간 궤적이 차량이 실제로 그린 선이다."
summary: "Genesis 물리엔진 위에서 nominal 주행(Sweep Table + Stanley + Residual RL)과 외란 복구(Recovery Path Planner)를 함께 푸는 DIGLAB 연구. 지형 다양성으로 unseen 환경 CTE 8.89 cm를 얻었다."
---

## 문제 정의 — Disturbance Recovery Driving

이 프로젝트가 푸는 문제는 두 개다.

1. **다양한 환경·지형에서 nominal driving** — 경로 추종
2. **disturbance condition에서 off-nominal driving** — 복구 경로 planner

그 밑에 원칙이 하나 깔려 있다. **경로를 잘 따라가기만 하면 된다 — Path2ST.** 어디로 갈지는 경로가 이미 알고 있으니, 정책은 "주어진 경로를 물리적으로 어떻게 따라가는가"만 풀면 된다. 그리고 VLA로 disturbance를 회피하지 못했을 때, 그때가 복구 주행의 자리다.

<figure>
  <img loading="lazy" src="{{ '/assets/genesis/two-branch.png' | relative_url }}" alt="GT path에서 nominal driving과 off-nominal recovery 두 갈래로 갈리는 구조도">
  <figcaption>GT path → nominal(Tracking / Generalization)은 Sweep + Stanley + RL, off-nominal(Recovery)은 Recovery Path Planner. 복구 경로는 다시 GT path로 합류한다.</figcaption>
</figure>

---

## Path2ST — MPPI + MLP에서 Sweep Table + Stanley로

<figure>
  <img loading="lazy" src="{{ '/assets/genesis/mppi-fan.png' | relative_url }}" alt="MPPI가 2048개 후보 궤적을 부채꼴로 전개하고 그중 하나만 실행하는 장면">
  <figcaption>기존 방식. 반투명 고스트가 2048개의 imagination rollout, 실제로 주행하는 건 비용 최소 후보 하나(golden T, S)다.</figcaption>
</figure>

**기존 — MPPI + MLP.** 병렬 환경에서 실제로 시뮬레이션을 굴려 가중치 기반 최적화를 돌린다. 시뮬레이터 물리·상황·경로·오차를 모두 반영한 비용 기반 최적화로 **golden (T, S)**를 산출하고, 그걸 MLP로 지도학습해서 Blender에서의 움직임을 Genesis로 옮기며 솔버의 물리를 이해시키는 구조였다.

두 가지가 발목을 잡았다.

- **offline golden (T, S) 마이닝의 시간 비용이 매우 크다** (마이닝 30분 + Optuna 3~10시간)
- **고속 주행에서 최적화가 어렵다**

**현재 — Sweep Table + Stanley.** 최적화를 매번 푸는 대신, Genesis 엔진에 주행에 필요한 state를 넣어 **사전 측정 표**를 만들어 둔다. **Black-box Inverse Dynamics**다.

<figure>
  <img loading="lazy" src="{{ '/assets/genesis/sweep-stanley.png' | relative_url }}" alt="Sweep Table과 Stanley 제어기의 구조 및 수식">
  <figcaption>왼쪽 Sweep Table — 오프라인 실측 역동역학. 오른쪽 Stanley — 폐루프 피드백 제어기.</figcaption>
</figure>

동일 초기조건 `(v, pitch, roll)`에서 조향 S를 고정하고 **2초 롤아웃**을 굴려 결과 `(a, ω)`를 측정한다. 측정값 한 칸 한 칸이 테이블이 된다.

```
사전 측정:  (v, pitch, roll, T, S)  →  (a, ω)
주행 시:    (v, pitch, roll, 목표 a·ω)  →  (T, S)     ← 역조회
```

해석적 차량 모델을 세워 역산하는 대신 **엔진이 실제로 내놓은 값을 표로 갖고 있다가 거꾸로 찾는다.** 지형 경사(pitch, roll)가 인덱스에 들어가 있어서 오르막과 내리막에서 같은 목표 가속도라도 다른 스로틀이 나온다. 측정 비용은 MPPI 마이닝보다 훨씬 싸다. 대신 **nominal 제어기 튜닝이 필요해졌다.**

목표 `(a, ω)`는 Stanley가 만든다. 경로까지의 수직 거리 CTE(`e`)와 헤딩 오차 HE(`ψ = ψ_path − ψ_veh`)를 받는다.

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

**제어 로직과 차량 동역학이 분리**되어 있다는 게 이 구성의 이점이다. 차량이 바뀌면 테이블만 다시 재면 된다.

---

## Residual RL — 지형 다양성으로 unseen까지 일반화

nominal 제어기 위에 residual RL(PPO)을 얹는다. 여기서 던진 질문은 **"경험을 어디서 넓힐 것인가"**였다. 같은 지형에서 경로와 perturbation을 다양화할 것인가, 아니면 지형 자체를 다양화할 것인가.

두 조건을 만들어 붙였다.

<div class="tw" markdown="1">

| | **A — single terrain** | **B — multi terrain** |
|---|---|---|
| 규모 | 500 m × 500 m | 3 km × 3 km |
| 경로 수 | 동일 mesh, **42개** | 구역별 다른 mesh, **99개** |
| perturbation | 경로에 state perturbation **부여** | 시작 state perturbation **없음** |
| 노리는 것 | local state coverage 확대 | trajectory distribution 자체 확대 |

</div>

<figure>
  <img loading="lazy" src="{{ '/assets/genesis/t3k-overview.png' | relative_url }}" alt="T3k 3km 지형 전체와 99개 학습 경로">
  <figcaption>B 조건의 T3k 지형. 노란 선이 타일 경계, 회색이 99개 학습 경로다. 구역마다 mesh 특성이 다르다.</figcaption>
</figure>

정책 구조·보상·base nominal controller는 동일하게 두고 학습 환경만 바꿨다. 그리고 **2×2 cross evaluation** — 각자의 home과 서로의 unseen 환경에서 평가했다.

<div class="tw" markdown="1">

| 학습 모델 | 평가 환경 | 완주 | CTE (횡방향 오차) |
|---|---|---|---|
| A (500 m) | A (Home) | 42/42 | 9.85 cm |
| A (500 m) | **B (Unseen)** | 99/99 | **10.41 cm** |
| B (3 km) | B (Home) | 99/99 | **8.75 cm** |
| B (3 km) | **A (Unseen)** | 42/42 | **8.89 cm** |

</div>

읽는 방법은 이렇다. **A의 home 주행이 9.85 cm인데, B가 그 A 환경(unseen)에서 8.89 cm를 냈다.** 처음 보는 지형에서, 그 지형을 학습한 모델보다 잘 따라간 것이다.

그런데 학습량을 보면 결과가 더 뒤집힌다.

<div class="tw" markdown="1">

| 항목 | A — Single Terrain | B — Multi-Terrain |
|---|---|---|
| Train Env × Horizon | 4096 × 128 | 96 × 1536 |
| 총 학습 경험량 | **157.3M** | 44.2M |
| 학습 시간 | 4h 08m | **2h 14m** |

</div>

**A가 3.5배 더 많은 경험을, 2배 가까운 시간을 들여 했는데도 B가 이겼다.** 환경 다양성이 unseen generalization에 효과적이라는 근거로 B를 채택했다.

<div class="callout" markdown="1">
<b>수치 해석 조건.</b> CTE는 경로별로 평균을 낸 뒤 전체 scene에 대해 다시 평균한 값이라, 경로 길이가 달라도 씬 당 한 표씩 균등 가중된다. <b>3 seed 평균</b>이다. 다만 각 경로의 episode 길이가 달라 <b>완벽한 ablation은 아니다.</b>
</div>

---

## GPU friendly Batched Training

질문은 단순했다. **CPU backend로 episode를 빠르게 돌릴 것인가, GPU에서 많은 env를 동시에 돌릴 것인가. 분기점은 어디인가.**

<figure>
  <img loading="lazy" src="{{ '/assets/genesis/gpu-cpu.png' | relative_url }}" alt="병렬 환경 수에 따른 CPU와 GPU 처리량 비교 그래프">
  <figcaption>병렬 L3 환경 수 N에 대한 처리량(env-steps/s). RTX 4090 · VehicleSDK 기준이며 terrain mesh 복잡도에 의존한다.</figcaption>
</figure>

<div class="tw" markdown="1">

| N | CPU | GPU |
|---|---|---|
| 30 | 2.5k | 2.1k |
| 100 | 5.7k | 6.4k |
| 200 | 7.3k | 6.3k |
| **400** | 8.7k | **14.4k (1.66×)** |

</div>

작은 배치에서는 **GPU 런치 오버헤드가 이득을 먹는다.** N=30에서는 CPU가 빠르고 200까지도 뒤집힌다. 300~400 구간에서 고정 오버헤드가 분산되고 나서야 GPU가 1.66배로 벌린다. 결론은 **env를 300 이상 쓴다.**

그렇다면 그 예산을 env에 쓸 것인가 horizon에 쓸 것인가. Genesis에서 **env는 GPU 병렬 처리이고 horizon은 sequential 처리**다. 같은 총 스텝으로 맞춰 재봤다.

<div class="tw" markdown="1">

| | **Wide Env** | Long Horizon |
|---|---|---|
| Env × Horizon | **512 × 256** | 128 × 1024 |
| Buffer | 131,072 | 131,072 |
| Total Steps | 39.3M | 39.3M |
| Training Time | **27.2 min** | 90.6 min |
| env 처리량 | **24.1k/s** | 7.2k/s |
| 품질 | 동등 | 동등 |

</div>

**같은 스텝, 같은 품질인데 시간이 3.3배 차이 난다.** horizon이 sequential이라 늘려봐야 병렬화가 안 되기 때문이다. 정리하면 — **env를 늘리고 horizon은 줄인다. horizon은 잘라서 minibatch로 처리한다.**

---

## Off-Nominal ① — 기존 방식: RL 기반 복구 (Switch Policy)

처음 접근은 **정책을 갈아 끼우는** 것이었다.

```
Nominal Controller + residual_RL  ↔  RL_recovery
```

1. 정상 주행은 Nominal Controller + residual RL이 맡는다
2. disturbance로 경로를 이탈하면 **RL_recovery로 model switch**
3. RL_recovery는 강화학습으로 차량을 경로에 복귀시킨다
4. 정상 범위로 돌아오면 다시 nominal로 switch

이 복구 정책이 보는 관측을 7개로 설계했다. 좌표계 절대값 대신 **경로와 차량의 상대 관계**로 구성한 게 요점이다.

<figure>
  <img loading="lazy" src="{{ '/assets/genesis/obs-features.png' | relative_url }}" alt="차량과 목표점 사이의 7가지 관측 피처를 표시한 그림">
  <figcaption>① 거리 d ② bearing ③ align ④ approach speed ⑤ velocity ⑥ yaw rate ⑦ steering.</figcaption>
</figure>

②와 ③을 분리한 게 의도적이다. bearing만 있으면 "목표점이 어느 쪽인가"는 알지만 **도착했을 때 어느 방향을 보고 있어야 하는가**를 모른다. align이 그 자세 조건을 담는다. ⑥ yaw rate는 스핀 복구에서 특히 중요하다 — 차체가 이미 돌기 시작했는지를 알려주는 신호다.

이 방식은 **경로를 새로 만들지 않고 주행 policy만으로 복구**한다. 돌아가긴 하는데, 문제가 있었다.

<figure>
  <img loading="lazy" src="{{ '/assets/genesis/recovery-grid.png' | relative_url }}" alt="복구 시나리오 궤적 결과 그리드, 대부분 초록 테두리이고 하나가 빨강">
  <figcaption>RL 기반 복구의 시나리오별 결과. 대부분 통과하지만 <b>실패가 남는다</b>(붉은 칸). 그리고 왜 실패했는지 정책 안을 들여다볼 방법이 없다.</figcaption>
</figure>

---

## Off-Nominal ② — 현재 방식: Recovery Path Planner

정책을 바꾸는 대신 **경로를 만들기로** 했다.

```
Nominal Controller + residual_RL  →  Recovery Path Planner
```

1. 정상 주행은 Nominal Controller + residual RL이 담당
2. disturbance로 경로 이탈 시 **Recovery Path Planner가 복구 경로를 생성**
3. **Nominal Controller가 그 복구 경로를 주행**한 뒤 GT path로 복귀

핵심은 3번이다. 복구 전용 제어기를 따로 만들지 않는다. 경로만 새로 그려주면 **이미 있는 nominal 스택이 그대로 주행한다.** Path2ST 원칙이 여기서 값을 한다 — 경로에서 이탈하더라도 결국 "경로를 따라가는 문제"로 되돌리는 것이다.

외란은 세 종류로 정의하고 **8 Hz**로 복구 경로를 생성한다.

<figure>
  <img loading="lazy" src="{{ '/assets/genesis/recovery-generation.png' | relative_url }}" alt="spawn pose, lateral kick, spin 세 가지 외란에 대한 복구 경로 생성">
  <figcaption>하늘색이 생성된 Recovery Path, 회색이 기존 ground truth path.</figcaption>
</figure>

<div class="tw" markdown="1">

| 외란 | 상황 |
|---|---|
| **spawn pose** | 차량 소환 자세 이상에 따른 복구 |
| **lateral kick** | 외부 요인(충돌)에 의한 횡방향 shift |
| **spin** | 주행 중 스핀 |

</div>

### 설계

<figure>
  <img loading="lazy" src="{{ '/assets/genesis/recovery-flow.png' | relative_url }}" alt="Recovery Supervisor에서 MERGE까지의 복구 파이프라인">
  <figcaption>Recovery Supervisor → SETTLE → Recovery Planner → Recovery Reference → MERGE.</figcaption>
</figure>

**off-nominal 주행 흐름**

1. Disturbance Condition에 의해 경로 이탈
2. **settle 구간 — 브레이크.** 자세와 속도가 요동치는 상태 위에서 세운 계획은 곧 무효가 되므로, 계획 전에 상태를 가라앉힌다
3. Recovery Path Planner가 경로를 생성하고 기존 경로에 merge
4. Nominal Controller가 그 경로를 주행

**Recovery Path Planning 4단계**

<figure>
  <img loading="lazy" src="{{ '/assets/genesis/replan-steps.png' | relative_url }}" alt="Feasibility Test 1, Candidate Generation, Feasibility Test 2, Cost Evaluation 4단계">
  <figcaption>후보 생성 <b>앞뒤로</b> feasibility 검사가 한 번씩 들어간다.</figcaption>
</figure>

<div class="tw" markdown="1">

| 단계 | 내용 |
|---|---|
| **1차 feasibility 검증** | 후보 공간 제약 — 합류 가능 범위, 가용 거리, 제동 가능성 |
| **Path candidate Generation** | **Frenet Quintic & Dubins** |
| **2차 feasibility 검증** | 차량 제약 조건 — steering limit, braking distance |
| **Cost 최소 경로 선택** | 통과한 후보 중 비용 최소 |

</div>

검사를 두 번 나눈 이유가 각 단계 이름에 그대로 있다. 1차는 **공간**이 되는지(합류할 자리가 있는가, 설 거리가 있는가), 2차는 **차량**이 되는지(조향각·제동거리 안에 들어오는가)를 본다. 성격이 다른 제약이라 한 번에 걸 수 없다.

<figure>
  <img loading="lazy" src="{{ '/assets/genesis/plan-p120-compare.gif' | relative_url }}" alt="learning-based recovery와 recovery path planner의 나란한 비교">
  <figcaption>왼쪽 learning-based recovery, 오른쪽 recovery path planner. 같은 이탈 상황에서 두 방식이 그리는 복구 궤적.</figcaption>
</figure>

---

## 왜 바꿨나 — 학습 기반 복구 vs 경로 기반 복구

<div class="tw" markdown="1">

| | 강화학습 기반 복구 | **Recovery Path Planner 기반 복구** |
|---|---|---|
| 복구 방식 | 정책의 경험적 선택 | **물리적 feasibility 기반 제약으로 생성** |
| explainability | blackbox | 후보·feasibility·cost 역추적 가능, **glassbox** |
| 기존 스택 유지 | Recovery용 RL 학습 필요 | **기존 Nominal Driving 스택 사용 가능** |

</div>

정리하면 네 가지 이득이다.

- **Path2ST 원칙 유지** — 이탈하더라도 path planner를 통해 복구 경로를 만들면 다시 추종 문제가 된다
- **Robustness** — 학습 기반의 OOD(out of distribution)를 걱정하지 않아도 된다
- **Explainability** — 실패 분석이 쉽다
- **시간 비용** — rule 수정만으로 빠르게 튜닝 결과를 확인할 수 있고, **새로운 RL 학습·보수 비용이 들지 않는다**

마지막 항목이 실제로 증명된 장면이 있다.

<figure>
  <img loading="lazy" src="{{ '/assets/genesis/rl-vs-planner-grid.png' | relative_url }}" alt="RL 기반에서 실패한 scene이 Recovery Path Planner의 rule 수정으로 전부 통과한 그리드 비교">
  <figcaption>왼쪽 — 강화학습 기반에서 실패한 scene(붉은 칸). 오른쪽 — Recovery Path Planner 기반에서 <b>rule 수정만으로 해결</b>. 재학습이 없었다.</figcaption>
</figure>

RL 방식이었다면 이 한 칸을 고치려고 보상을 다시 설계하고 재학습을 돌린 뒤, 다른 시나리오가 망가지지 않았는지 전부 다시 봐야 했다. 규칙 기반에서는 어느 제약이 잘못 걸렸는지 역추적해서 그것만 고친다.

<figure>
  <img loading="lazy" src="{{ '/assets/genesis/plan-p120.gif' | relative_url }}" alt="Stanley 제어로 경로를 추종하며 주행하는 장면">
  <figcaption>시나리오 p120. HUD에 <code>ctrl STN</code>(Stanley), 도달 오차 <code>arr 0.01 m</code>. 회색이 GT 경로, 파랑이 수정된 참조 경로, 빨강이 차량 궤적. 빨간 박스는 정적 장애물, 주황 박스는 이동 장애물이다.</figcaption>
</figure>

---

## Next Step — Cost를 무엇으로 볼 것인가

플래너의 마지막 단계는 후보 중 하나를 고르는 일이다. 지금은 아래 항목의 가중치를 조절해 최적 경로를 고른다.

<div class="tw" markdown="1">

| Cost 항목 | 의미 |
|---|---|
| Recovery Path length | 복귀 경로 길이 |
| Merge distance | 현재 위치에서 merge 위치까지의 거리 |
| band | 곡률 부담 |
| Steering effort | 조향 부담 — 얼마나 핸들을 많이 꺾어야 하는가 |
| Speed loss | 속도 손실 — 얼마나 브레이크를 밟아야 하는가 |
| `max_a_lat` | 최대 횡가속 — 얼마나 차량 한계에 붙어 도는가 |

</div>

가중치를 손으로 맞추는 단계라, 다음 목표는 **VLA(alphamayo) 도입 시 지형과 장애물까지 고려해 이 선택 과정 자체를 최적화하는 것**이다.

## 지형 스케일

<figure>
  <img loading="lazy" src="{{ '/assets/genesis/t3k-terrain.png' | relative_url }}" alt="3km 지형 전체, 100m 줌, 차량 근접 뷰 3단 비교">
  <figcaption>T3k 지형 전체(위) → 약 100 m 줌(가운데) → 차량(아래). 접지 검증값 <code>z_car − z_terrain = 0.06 m</code>, <code>v = 10.7 m/s</code>.</figcaption>
</figure>

`z_car − z_terrain = 0.06 m`는 **차량이 지형에 떠 있거나 파묻히지 않았다**는 접지 검증값이다. 3 km 규모 하이트필드에서는 이 값이 조용히 어긋나면서 물리가 망가지는 일이 흔하다.

<figure>
  <img loading="lazy" src="{{ '/assets/genesis/blender-path.png' | relative_url }}" alt="Blender에서 렌더링한 지형과 경로를 따르는 차량들">
  <figcaption>A 조건(500 m × 500 m)의 Blender 지형·경로. 이 정합이 성립하면 그 자리에 실제 현실을 치환한다 — 그게 Real2Sim이다.</figcaption>
</figure>

## 지금 상태

<div class="tw" markdown="1">

| 항목 | 상태 |
|---|---|
| Sim2Sim 정합 (Blender ↔ Genesis) | 완료 |
| Sweep Table + Stanley (Path2ST) | 완료 |
| Residual RL — multi-terrain 채택 | 완료 (unseen CTE 8.89 cm) |
| GPU batched training 튜닝 | 완료 (env ≥ 300, wide env) |
| Recovery Path Planner | 동작 — RL 실패 scene을 rule 수정으로 해결 |
| Cost 가중치 자동화 (VLA alphamayo) | 다음 단계 |
| Inverse-dynamics mapper · Neural Physics | 진행 |
| Sim2Real | 최종 목표 |

</div>

## 기술 스택

Python · PyTorch · **Genesis** · Isaac Lab · Blender. 제어는 Stanley + Sweep Table(black-box inverse dynamics), 학습은 residual RL(PPO), 경로 생성은 Frenet Quintic & Dubins. 학습·측정은 RTX 4090 기준이다.

<div class="callout" markdown="1">
저장소에는 연구 기록 <b>50여 편</b>이 <code>car_test/docs/</code> 아래 쌓여 있다. ray-wheel 충돌 모델, Pacejka 타이어 모델, MPPI warm-start 파라미터, 보상 함수 설계 같은 세부는 그쪽에 정리되어 있다.

소속 랩의 공식 프로젝트 소개는 <a href="https://korfriend.github.io/Projects/real2sim-sim2real/">DIGLAB — Real2Sim &amp; Sim2Real</a>에 있다.
</div>

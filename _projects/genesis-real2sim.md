---
title: "Genesis Real2Sim — 물리로 채굴한 라벨로 주행 정책 만들기"
lede: "MPPI를 실시간 제어기가 아니라 라벨 생성기로 쓴다. 2048개 병렬 물리 롤아웃이 만든 골든 제어 라벨을 경량 mapper로 증류하고, 그 위에 residual RL을 얹었다."
category: robotics
order: 1
tags: ["Flagship", "Genesis", "MPPI", "Residual RL", "Neural Physics"]
repo: "https://github.com/i1uvmango/Genesis_AI_Sim2real_Real2sim"
thumb: /assets/genesis.jpg
thumb_video:
  - {src: /assets/genesis.webm, type: video/webm}
  - {src: /assets/genesis.mp4, type: video/mp4}
hero: /assets/genesis.jpg
hero_video:
  - {src: /assets/genesis.webm, type: video/webm}
  - {src: /assets/genesis.mp4, type: video/mp4}
hero_alt: "Genesis viewer에서 MPPI가 경로를 추종하며 주행하는 장면"
hero_caption: "Genesis viewer. 회색이 GT 경로, 파란 선이 수정된 참조 경로, 빨간 궤적이 차량이 실제로 그린 선이다."
summary: "Genesis 물리엔진 위에서 MPPI가 채굴한 골든 제어 라벨로 Path→(Steer, Throttle, Brake) mapper를 학습하고 residual RL을 얹는다. inverse-dynamics mapper·neural physics로 Real2Sim까지 확장하는 DIGLAB 연구 프로젝트."
---

## 왜 이런 구조를 택했나

MPPI(Model Predictive Path Integral)는 강력한 최적 제어기다. 문제는 **연산량**이다. 매 스텝마다 수천 개의 후보 제어 시퀀스를 물리적으로 전개하고 평가해야 하는데, 이걸 실차에 그대로 얹을 수는 없다.

그래서 역할을 뒤집었다. MPPI를 **실시간 제어기가 아니라 오프라인 라벨 생성기**로 쓴다. 최적성은 시뮬레이션 안에서 마음껏 취하고, 배포는 단일 신경망 추론 한 번으로 끝낸다. 대규모 병렬 최적화의 성능을 실차 수준의 연산 예산으로 끌어오는 것이 이 프로젝트의 골자다.

<div class="callout" markdown="1">
<b>dynamic-first 원칙.</b> 학습 데이터가 이상적인 kinematic 궤적이면 지형 경사·하중 이동·타이어 접지·서스펜션 응답이 전부 빠진다. 그런 데이터로 학습한 정책은 실물에서 일반화되지 않는다. 그래서 reference 궤적조차 위치를 강제 이식하지 않고, 차량이 <b>순수 물리 주행</b>으로 만든 것만 쓴다.
</div>

## 파이프라인 4단계

<figure>
  <img loading="lazy" src="https://raw.githubusercontent.com/i1uvmango/Genesis_AI_Sim2real_Real2sim/main/car_test/res_wjdaksry/0712/rl_pipeline.png" alt="Reference 생성부터 Residual RL까지의 전체 파이프라인">
  <figcaption>Reference 생성 → MPPI 라벨 채굴 → BC mapper → Residual RL로 이어지는 전체 흐름.</figcaption>
</figure>

**1. Reference 생성.** 한국 도로공사 표준 기반 지형 위에서 차량이 순수 물리 주행으로 만든 궤적을 추출한다.

**2. 골든 라벨 채굴 (sim2sim).** Genesis의 ray-wheel 차량 물리 위에서 MPPI가 이 reference를 재추종한다. 매 스텝 **2048개 병렬 환경**에서 후보 제어 시퀀스를 실제 물리로 전개·평가하고 최적 입력 하나를 고른다. 이렇게 *(주행 상태 → Throttle, Steer, Brake)* 전문가 라벨이 쌓인다. **34개 기동 시나리오**를 돌렸고 최저 CTE는 **0.11 m**였다. 저장소의 티저 GIF를 보면 반투명 고스트로 그려진 2048개의 "상상한 미래" 중 하나만 실제로 실행되는 게 보인다.


**3. Path→(ST) Mapper 학습.** 채굴한 라벨을 BC + DAgger로 지도학습한다. 입력은 오차 피드백, 현재 물리 상태, 미래 경로(곡률·가속), 과거 경향성의 미분. 출력은 단일 스텝 제어가 아니라 **미래 프레임의 제어 시퀀스** — 액션 청크 방식이다. 배포 시에는 2048-env 최적화 없이 신경망 추론만으로 실시간 경로 추종이 된다.

**4. BC freeze + Residual RL.** 학습된 BC mapper를 **동결**하고 그 위에 PPO residual 항을 얹는다. 처음부터 정책을 학습하는 대신 검증된 base 위의 보정만 학습하므로 표본 효율과 안정성이 높다. 동시에 brake를 행동 공간에 추가해 (Steer, Throttle, Brake) 완전 정책으로 확장한다.

<figure>
  <img loading="lazy" src="https://raw.githubusercontent.com/i1uvmango/Genesis_AI_Sim2real_Real2sim/main/car_test/res_wjdaksry/0712/rl_p142_position_rl_iter600.gif" alt="RL iteration 600 시점의 주행 결과">
  <figcaption>시나리오 p142, RL iteration 600. 위치(position) 기준 추종 결과.</figcaption>
</figure>

## BC만으로는 왜 부족한가

BC는 전문가 라벨의 분포 안에서만 안전하다. 실제 주행은 폐루프이므로 작은 오차가 누적되며 정책이 학습 분포 밖으로 밀려나고(covariate shift), 여기에 미모델링 동역학이 겹치면 복구가 안 된다. DAgger가 이 문제를 완화하지만 완전히 없애지는 못한다.

Residual RL은 이 지점을 정확히 겨냥한다. base 정책의 출력을 신뢰하되, 폐루프에서만 드러나는 오차를 보정하는 항만 따로 학습한다.

## Real2Sim의 관문 — inverse-dynamics mapper

지금까지는 시뮬레이터 안에서 닫혀 있다. 현실을 넣으려면 문제가 하나 더 있다.

**현실 주행 데이터에는 제어 입력이 없다.** 차가 어떤 궤적을 그렸는지는 관측되지만, 그 순간 운전자가 스티어를 몇 도 꺾고 브레이크를 얼마나 밟았는지는 로그에 남지 않는다. 있다 해도 그 값을 Genesis에 그대로 넣으면 같은 궤적이 나오지 않는다 — 타이어 모델도, 지면 마찰도, 서스펜션 응답도 실물과 다르기 때문이다.

그래서 **정책 학습을 시작하기 *전에*** 두 가지를 복원하는 단계를 둔다.

<div class="tw" markdown="1">

| 복원 대상 | 하는 일 |
|---|---|
| **Trajectory→Controls mapper** | 관측된 궤적에서 잠재 제어 입력 (Steer, Brake)을 역산 |
| **Inverse-dynamics 보정항** | 그 제어를 Genesis에 넣었을 때 실제 롤아웃과 어긋나는 차이를 보정하는 함수 |

</div>

순서가 핵심이다. 정책을 먼저 학습한 뒤 sim-to-real 간극을 도메인 randomization으로 덮는 접근과 달리, **간극 자체를 먼저 명시적으로 측정하고 좁힌 뒤** 그 위에서 학습한다. 시뮬레이터를 현실 롤아웃에 정렬시켜 놓고 시작하는 것이다.

## Neural Physics — 못 맞추는 부분은 배운다

정렬을 아무리 해도 해석적 모델로는 안 맞는 영역이 남는다. 지형과의 접촉, 하중 이동에 따른 서스펜션 응답, 노면 상태 변화 같은 것들이다.

이 잔차를 **학습된 보정항**으로 흡수한다. 물리 엔진을 신경망으로 대체하는 게 아니라, 엔진이 계산한 값 위에 지형·접촉·서스펜션 항의 보정을 얹는 방식이다. 앞의 residual RL이 *정책* 위에 보정을 얹었다면, 이건 *물리* 위에 보정을 얹는다 — 같은 발상을 한 층 아래에 적용한 셈이다.

## 같은 파이프라인의 다른 축 — 멀티에이전트

이 프로젝트는 [DIGLAB의 Real2Sim·Sim2Real 연구](https://korfriend.github.io/Projects/real2sim-sim2real/)의 한 갈래다. 같은 Genesis 기반 파이프라인이 향하는 다른 축이 하나 더 있다.

**3v3 전차전 시뮬레이션.** 커리큘럼 기반 MARL로 **수천 개 병렬 월드**까지 확장하는 대규모 멀티에이전트 학습이다. 단일 차량의 경로 추종이 "물리적으로 정확한 제어를 어떻게 배우는가"의 문제라면, 이쪽은 그 위에 협조와 적대가 얹힌다.

두 축이 공유하는 건 전제다 — **학습 데이터가 이상적 궤적이 아니라 물리 롤아웃에서 나와야 한다**는 것.

## 지금 상태와 남은 것

<div class="tw" markdown="1">

| 방향 | 내용 | 상태 |
|---|---|---|
| Sim2Sim 정합 | Blender ↔ Genesis | 완료 |
| MPPI 골든 라벨 채굴 | 2048 롤아웃 × 34 시나리오 | 완료 |
| Path→(ST, B) Mapper | BC + DAgger, 액션 청크 | 완료 |
| Residual RL | BC freeze + PPO 보정항 | 완료 |
| Inverse-dynamics mapper | 잠재 제어 + 보정항 복원 | 진행 |
| Neural Physics | 지형·접촉·서스펜션 보정항 학습 | 진행 |
| Multi-agent (3v3, MARL) | 커리큘럼 + 수천 병렬 월드 | 랩 병행 축 |
| Sim2Real | 실차 전이 | 최종 목표 |

</div>

랩 페이지 기준 residual learning은 최적화된 환경에서 **sub-millimeter 궤적 드리프트**를 보고하고 있다.

한계도 분명하다. 현재 mapper 출력은 (Steer, Throttle) 2차원이고 **brake는 물리 검증만 된 상태**다. 급경사 하강처럼 throttle만으로 부족한 상황은 RL 단계에서 해소한다.

그리고 지금의 Blender→Genesis 정합은 그 자체가 목적이 아니다. Blender는 **"이상적 현실의 대리자"**이고, 이 정합 방법론이 성립하면 그 자리에 실제 현실을 치환한다 — 그게 Real2Sim이다.

## 기술 스택

Python · PyTorch · **Genesis** · Isaac Lab · Blender. 정책 학습은 PPO(단일 차량 residual RL)와 QMIX(멀티에이전트) 계열을 쓰고, 그 앞단에 behavior cloning과 DAgger가 붙는다.

<div class="callout" markdown="1">
저장소에는 연구 기록 <b>50여 편</b>이 <code>car_test/docs/</code> 아래 쌓여 있다. ray-wheel 충돌 모델, Pacejka 타이어 모델, MPPI warm-start 파라미터, 보상 함수 설계 같은 세부는 그쪽에 정리되어 있다.

소속 랩의 공식 프로젝트 소개는 <a href="https://korfriend.github.io/Projects/real2sim-sim2real/">DIGLAB — Real2Sim &amp; Sim2Real</a>에 있다.
</div>

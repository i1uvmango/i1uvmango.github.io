---
title: "ViT는 왜 CIFAR-10에서 CNN에게 지는가"
lede: "구조 문제인가, 데이터 문제인가. patch·capacity·head·conv stem·augmentation·distillation까지 8개 가설을 전부 실험으로 갈랐다. 결론은 셋이 반증됐다."
category: mldl
order: 1
tags: ["PyTorch", "Ablation Report", "CIFAR-10"]
repo: "https://github.com/i1uvmango/vit"
thumb: /assets/vit.jpg
hero: /assets/vit.jpg
hero_alt: "ViT baseline과 Hybrid의 attention rollout 비교"
hero_caption: "ViT baseline vs Hybrid의 attention rollout. conv stem은 attention을 공간적으로 더 집중시키지만, 어려운 오답 자체는 고치지 못했다."
summary: "Patch size·capacity·Hybrid CNN+ViT 구조 변형이 성능에 미치는 영향을 직접 실험·플롯으로 근거화한 분석 리포트. 결정적 레버는 augmentation과 작은 patch 두 개였다."
---

## 질문

CNN은 국소 수용영역과 translation equivariance라는 **강한 inductive bias**를 구조에 내장한다. ViT는 그런 가정이 거의 없는 대신 더 많은 데이터를 요구한다. CIFAR-10은 32×32 저해상도에 소규모라 이 차이가 크게 벌어진다.

그래서 질문은 하나로 좁혀진다. **ViT의 CIFAR-10 결손은 구조 문제인가, 데이터·정규화 문제인가?**

## 출발점: 14.1%p의 격차

<div class="tw" markdown="1">

| 모델 | params | test acc | train–val gap |
|---|---|---|---|
| CNN (CIFAR ResNet) | 2.78M | **0.8365** | 0.159 |
| ViT baseline | 3.20M | 0.6951 | **0.305** |

</div>

CNN이 **더 적은 파라미터로 14.1%p 앞선다.** 그리고 ViT의 train acc는 **1.0000** — 완전 암기다. gap 0.305는 순수한 과적합이다.

<figure>
  <img loading="lazy" src="https://raw.githubusercontent.com/i1uvmango/vit/main/res/fig05b_confusion_compare.png" alt="CNN과 ViT의 confusion matrix 비교">
  <figcaption>ViT의 최대 혼동쌍은 dog→cat 213, cat→dog 179. CNN은 같은 쌍이 117/116으로 절반 수준이다.</figcaption>
</figure>

모든 실험은 조건을 고정했다. epoch 30, batch 256, lr 3e-4 (cosine annealing + 3-epoch warmup), AdamW, seed 42, RTX 4090. **baseline부터 실험 5까지는 augmentation을 일부러 끄고** 돌렸다 — 과적합 격차를 숨기지 않고 노출시키기 위해서다.

## 실험 1 — patch size: 토큰이 곧 성능

<div class="tw" markdown="1">

| patch | 토큰 수 (CLS 포함) | test acc | 학습 시간 |
|---|---|---|---|
| 2 | 257 | **0.7348** | 579s |
| 4 | 65 | 0.6924 | 64s |
| 8 | 17 | 0.6093 | 33s |
| 16 | 5 | 0.5384 | 33s |

</div>

patch 16 → 2로 **+19.6%p**. 단조 증가다. 다만 patch 2는 patch 4의 **9배** 시간을 먹는다. 그리고 token 수와 연산량이 함께 움직이므로 "토큰이 많아서 좋아진 것"인지 "연산을 더 써서 좋아진 것"인지는 이 실험만으로 분리되지 않는다.

## 실험 2 — capacity: 키운다고 좋아지지 않는다

<div class="tw" markdown="1">

| depth × embed | params | test acc | gap |
|---|---|---|---|
| d2 × e128 | 281K | 0.6565 | **0.139** |
| d4 × e128 | 546K | **0.6769** | 0.246 |
| d6 × e128 | 811K | 0.6684 | 0.301 |
| d2 × e256 | 1.09M | 0.6586 | 0.341 |
| d4 × e256 | 2.14M | 0.6838 | 0.312 |
| d6 × e256 | 3.20M | 0.6924 | 0.299 |

</div>

**비단조다.** 546K짜리 d4_e128이 811K와 1.09M을 모두 이긴다. 그리고 용량을 키우는 동안 test acc는 0.66→0.69로 찔끔 오르는데 gap은 0.139→0.34로 폭증한다. **추가 용량이 일반화가 아니라 암기로 갔다.**

head 수는 어떨까. embed를 고정하면 head 수는 param-neutral이라 구조 효과만 격리된다.

<div class="tw" markdown="1">

| heads | head_dim | params | test acc | gap | time |
|---|---|---|---|---|---|
| 4 | 64 | 3,195,146 | 0.6966 | 0.299 | 57s |
| 8 | 32 | 3,195,146 | 0.6924 | 0.299 | 64s |
| 16 | 16 | 3,195,146 | **0.6980** | 0.299 | 93s |

</div>

세 run의 파라미터 수가 **정확히 같고**, gap도 소수점 세 자리까지 같다. acc spread는 0.56%p — 노이즈 수준이다. head_dim을 16까지 줄여도 저하가 없었고, heads=16은 정확도 이득 없이 **시간만 +63%**였다.

## Twist ① — conv stem을 이식하면 될까 (반증)

CNN 우위가 tokenization 때문이라면, patch embedding을 경량 conv stem으로 갈아끼우면 격차가 줄어야 한다. conv stem은 일부러 **36K params**로 얇게 설계했다 — 전체가 3.22M(ViT 대비 +0.74%)이 되어야 "차이 = 파라미터 증가"가 아니라 **"차이 = locality"**로 귀속이 깨끗해진다.

결과는 **0.6709**. baseline 0.6951보다 **낮다.** gap도 0.332로 더 나빠졌다. epoch 1–2만 앞서다가 **epoch 4부터 ViT가 추월**했다.

<figure>
  <img loading="lazy" src="https://raw.githubusercontent.com/i1uvmango/vit/main/res/fig10_twist.png" alt="Hybrid와 ViT baseline의 accuracy, gap, 학습 곡선 비교">
  <figcaption>locality는 초기 최적화를 살짝 돕지만 최종 일반화는 바꾸지 못했다.</figcaption>
</figure>

해석: 단일 conv stem은 국소 평활성만 주입한다. CNN의 본질은 **전 계층에 걸친 conv hierarchy** — 다단계 translation equivariance, 공간 pooling, 다중 스케일이다. 그 한 층을 앞에 붙였다고 재현되지 않는다.

## 실험 3 — augmentation: 진짜 레버

crop + flip만 켰다. 2×2 ablation이다.

<div class="tw" markdown="1">

| | no-aug | +aug | Δ |
|---|---|---|---|
| ViT | 0.6951 (gap 0.305) | **0.7923** (gap 0.090) | **+9.7%p** |
| Hybrid | 0.6709 (gap 0.332) | 0.7676 (gap 0.136) | +9.7%p |

</div>

CNN(0.8365)과의 격차가 **14.1%p → 4.4%p**로 줄었다. 단일 레버로는 patch4→patch2(+4.3%p)의 두 배 이상이다.

그리고 여기서 Twist ①이 한 번 더 반증된다. conv stem이 만든 Δ는 no-aug에서 **−0.0242**, aug에서 **−0.0247**. 거의 완전히 같다. **Hybrid의 열세는 과적합의 부산물이 아니라 구조적 성질**이라는 뜻이다.

## Twist ② — knowledge distillation (두 번 반증)

DeiT hard distillation을 붙였다. CNN teacher는 gap 0.159로 ViT보다 일반화가 좋으니 이상적인 convnet teacher다. `L = 0.5·CE(CLS, y_true) + 0.5·CE(distill, argmax teacher)`.

**무증강 조건: 0.6997 vs 0.6951 = +0.46%p.** 사실상 없다.

원인은 per-head 정확도가 그대로 보여준다. CLS **0.699** ≈ distill **0.700** ≈ avg **0.700**.

<figure>
  <img loading="lazy" src="https://raw.githubusercontent.com/i1uvmango/vit/main/res/fig12e_head_acc.png" alt="CLS head와 distillation head의 정확도가 동일함을 보이는 막대그래프">
  <figcaption>세 head가 같은 값이라는 건 distillation 채널이 <b>처음부터 비어 있었다</b>는 직접 증거다.</figcaption>
</figure>

teacher가 train set을 암기(train acc 1.0)했으니 무증강 hard 라벨은 참라벨과 거의 같다. 즉 이 실험은 반증이 아니라 **아무것도 측정하지 못한 probe**였다.

그래서 teacher를 augmentation으로 재학습해 암기를 깼다. teacher CNN+Aug는 test **0.9083**, train 0.984. 이제 dark knowledge가 흐를까?

**ViT+Aug+KD 0.7936 vs ViT+Aug 0.7923 = +0.13%p.** 여전히 없다. per-head도 0.796 / 0.793 / 0.794로 똑같다.

<div class="callout" markdown="1">
<b>왜 안 되는가.</b> student도 <b>같은 augmented sample</b>을 본다. 그 페어 위에서는 teacher 예측이 여전히 참라벨에 정렬되어 있다. "teacher의 train 암기를 깼다"는 것과 "student가 보는 페어 위에 dark knowledge가 있다"는 것은 다른 얘기였다. 이건 지식 전이가 무력하다는 증거가 아니라, <b>이 setup의 hard-distillation이 채널을 열지 못한 사례</b>다.
</div>

## 결론

**ViT의 CIFAR-10 결손은 본질적으로 데이터·정규화 문제다.**

<div class="tw" markdown="1">

| 레버 | 효과 |
|---|---|
| augmentation (crop+flip) | **+9.7%p** |
| patch 4 → 2 | +4.3%p |
| capacity 확대 | 비단조, gap만 폭증 |
| head 수 | ±0.56%p (노이즈) |
| conv stem 이식 | **−2.4%p** |
| knowledge distillation | +0.13 ~ +0.46%p |

</div>

성능을 실제로 움직인 건 데이터 쪽 레버 두 개였고, 구조를 건드린 세 가지(capacity·conv stem·KD)는 전부 격차를 좁히지 못했다.

## 남은 한계

- patch 2는 시간 비용 때문에 더 긴 학습을 못 했다. token 수와 연산량이 공변해 단독 귀속이 안 된다.
- 두 아키텍처를 **param 수로만** 맞췄다. FLOPs는 다르고, CNN은 SGD에서 더 높을 여지가 있다.
- conv stem이 1개층으로 얕다. 더 깊은 stem은 다른 결과일 수 있다.
- augmentation은 crop+flip만 썼다. RandAugment는 미시험.
- KD는 α=0.5 · hard · 30 epoch 단일 조건. soft KD와 temperature 스윕, teacher–student 용량 차 통제는 안 했다.
- 30 epoch · 단일 seed. run-to-run RNG 노이즈가 **±0.003**이라 절대 수치는 ±1% 변동 가능하다.

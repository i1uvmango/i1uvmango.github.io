---
title: "Laplacian Blending에 준 세 개의 Twist"
lede: "교과서 구현은 두 이미지 전체를 반반 섞는다. 여기선 ROI만, 마스크를 그리지 않고, 색을 잃지 않고 섞어야 했다. 그 세 지점에서 무엇을 바꿨는가."
category: cv
order: 2
tags: ["NumPy", "PIL", "no OpenCV"]
repo: "https://github.com/i1uvmango/image_blending"
thumb: /assets/image_blending.jpg
hero: /assets/image_blending.jpg
hero_alt: "HE, AHE, CLAHE 비교 이미지"
summary: "OpenCV 없이 NumPy·PIL만으로 Laplacian Pyramid 블렌딩을 구현하되, 교과서 구현에 세 개의 twist를 넣었다 — ROI 국소 합성, Laplacian 자기 마스크, YUV 전 채널 처리."
---

## 출발점: 교과서 구현이 풀지 않는 것

Burt & Adelson(1983)의 Laplacian Pyramid Blending은 정석이 있다. 사과와 오렌지를 반으로 갈라 붙이는 그 그림 — **두 이미지를 같은 크기로 놓고, 좌/우를 나누는 이진 마스크를 만들고, 레벨별로 섞은 뒤 collapse**한다.

이번 과제는 손바닥 사진의 **지정한 사각 영역에 눈 이미지를 합성**하는 것이었고, OpenCV의 `seamlessClone` 같은 고수준 함수는 쓸 수 없었다. NumPy와 PIL만.

교과서 구현을 그대로 옮기면 세 군데에서 막힌다. 각각이 twist가 됐다.

```python
roi_eye_blend(hand_path, eye_path,
              roi_coords=(318, 416, 224, 393),   # (y0, y1, x0, x1)
              levels=5, sigma=1.0, sigma_blur=3.0)
```

---

## Twist 1 — 전체가 아니라 ROI만 피라미드에 올린다

**교과서:** 두 이미지 전체로 피라미드를 쌓는다.

**여기서 필요한 것:** 손바닥은 그대로 두고 169×98 픽셀짜리 영역만 바꾼다.

이미지 전체(640×480)로 피라미드를 쌓으면 두 가지가 낭비다. 연산량도 그렇지만, 더 중요하게 **레벨을 깊게 갈수록 ROI가 몇 픽셀로 뭉개진다.** ROI가 전체의 5%인데 5레벨을 내려가면 그 안에 남는 정보가 없다.

그래서 **ROI를 먼저 잘라내고, 잘라낸 조각을 독립된 이미지처럼 취급해 피라미드를 쌓는다.** 그 안에서 블렌딩을 끝낸 뒤 원본에 되돌려 넣는다. 피라미드의 "전체 이미지"가 곧 ROI가 되므로 5레벨이 의미를 갖는다.

여기서 첫 함정을 만났다. 처음엔 안전하게 padding을 두고 잘랐는데 **ROI 경계에서 색상 차이가 두드러졌다.** padding 영역이 블렌딩 계산에 섞여 들어가 경계값을 오염시킨 것이다. **padding을 완전히 없애고 정확히 ROI 크기로만** 자르니 해결됐다.

eye 이미지는 ROI 크기에 **비율을 무시하고 강제로 리사이즈**한다. hand는 EXIF orientation을 제거하고 640×480으로 **비율을 유지**해 리사이즈했는데, 여기선 반대다. 배경은 원본을 보존하고 삽입물은 자리에 맞춘다 — 의도적인 비대칭이다.

<div class="callout" markdown="1">
<b>이 twist의 대가.</b> ROI <b>내부</b>는 완벽하게 섞이지만, 블렌딩된 조각을 원본에 다시 붙이는 순간 <b>ROI 바깥 경계</b>가 새로 생긴다. 피라미드가 풀어주지 않는 문제다 — 아래 Twist 3 다음에 다시 나온다.
</div>

---

## Twist 2 — 마스크를 그리지 않고, 이미지가 스스로 만들게 한다

**교과서:** 사람이 마스크를 정의한다. 좌우 이진 마스크든 손으로 그린 알파 맵이든.

**여기서 필요한 것:** 눈 이미지에서 **눈 윤곽만** 가져오고 배경은 버려야 한다.

ROI 사각형 전체를 섞으면 눈 이미지의 배경까지 손바닥에 얹혀서 **사각형 자국**이 남는다. 그렇다고 눈 모양 마스크를 손으로 그리면 이미지가 바뀔 때마다 다시 그려야 한다.

여기서 관찰 하나가 문제를 풀었다. **이미 만들어둔 Laplacian 피라미드 자체가 마스크의 재료다.**

Laplacian은 해당 스케일에서의 **변화량**이다. 절댓값이 클수록 그 지점에 엣지가 있다는 뜻이다. 그리고 눈 이미지에서 변화량이 가장 큰 곳은 — 당연히 **눈 윤곽**이다. 배경은 평탄하니 Laplacian이 0에 가깝다.

그래서 마스크를 이렇게 만든다.

1. eye의 각 레벨 Laplacian **절댓값을 합산**해 edge map 생성
2. normalize
3. `sigma_blur=3.0`으로 **Gaussian blur**
4. 이걸 다시 Mask Pyramid로 쌓아 레벨별 블렌딩에 사용

```
blended = eye · mask + hand · (1 − mask)
```

<figure>
  <img loading="lazy" src="https://raw.githubusercontent.com/i1uvmango/image_blending/main/test2/step4_edge_mask/edge_mask.png" alt="eye 이미지의 Laplacian 절댓값으로 만든 edge mask">
  <figcaption>수동으로 그리지 않은 마스크. 눈 윤곽만 흰색으로 살아남았다. 3단계 Laplacian 피라미드의 부산물이 4단계의 입력이 된다.</figcaption>
</figure>

3번 blur가 없으면 안 된다. edge map을 그대로 쓰면 마스크 경계가 **너무 날카로워** 합성 결과가 오려 붙인 것처럼 보인다. `sigma_blur`가 작으면 날카롭고, 크면 눈 영역이 과도하게 번진다 — 이 값 하나가 결과를 좌우한다.

### 대조군을 따로 돌렸다

이 twist가 실제로 이득인지 확인하려면 비교 대상이 필요했다. 그래서 파이프라인을 두 벌 돌렸다.

<div class="tw" markdown="1">

| 실행 | 마스크 | 성격 |
|---|---|---|
| `test2/` | **Laplacian edge mask** (Twist 2) | 이미지가 스스로 만든 마스크 |
| `test3/` | **Ellipse mask** (`create_ellipse_mask`) | 사람이 형태를 지정한 기하학적 마스크 |

</div>

`src/roi_eye_blending.py`와 `src/test3_blending.py`는 마스크 생성 함수만 다르고 나머지 파이프라인이 동일하다. 즉 **마스크 전략 하나만 바뀐 통제 실험**이다. 두 결과의 `step6_final/comparison.png`를 나란히 놓으면 자동 마스크가 눈 윤곽을 얼마나 따라가는지, 타원 마스크가 어디서 배경을 끌고 들어오는지가 보인다.

---

## Twist 3 — RGB를 버리고 YUV로, 그리고 음수를 지킨다

**교과서:** 대개 그레이스케일이거나, RGB 3채널을 똑같이 처리한다고 넘어간다.

**여기서 벌어진 일:** 색이 망가졌다.

Gaussian Pyramid를 만들자 결과물의 색상이 왜곡됐다. 원인이 둘이었고, 두 번째가 훨씬 미묘했다.

**원인 1 — Y 채널만 섞고 있었다.** 밝기만 블렌딩하고 색상은 hand 것을 그대로 뒀으니 눈의 색이 손바닥 색으로 덮였다. RGB에서 직접 섞으면 채널 간 상관 때문에 다른 방식으로 색이 틀어진다. 그래서 **YUV로 변환해 밝기(Y)와 색상(U, V)을 분리하고, 세 채널 전부를 같은 방식으로** 처리하도록 고쳤다.

**원인 2 — U, V는 음수를 가진다.** 이게 진짜 버그였다.

Y는 0–255지만 U, V는 **0을 중심으로 음수와 양수를 오간다.** 그런데 대부분의 리사이즈 함수는 0–255 uint8을 가정한다. 음수가 섞인 U/V 배열을 그대로 업샘플링에 넘기면 **음수 영역이 조용히 잘려나간다.** 에러도 경고도 없고, 결과 이미지의 색만 이상해진다.

고친 순서는 이렇다.

```
정규화 → 리사이즈 → 원래 범위로 복원
```

이 프로젝트에서 가장 배울 게 많았던 지점이다. "왜 YUV를 쓰는가"는 교과서에 있지만, **"왜 U/V의 음수값이 리사이즈를 망가뜨리는가"**는 직접 부딪혀야 알 수 있다.

---

## Twist 1의 청구서 — 끝내 남은 바깥 경계

세 twist로 ROI 내부는 깨끗해졌다. 그런데 Twist 1에서 예고한 문제가 마지막에 돌아왔다. 블렌딩된 ROI 조각을 원본 hand에 삽입하는 순간 **ROI와 hand 사이의 경계선**이 눈에 보인다.

두 가지 해법을 만들어 비교했다.

<div class="tw" markdown="1">

| 방법 | 방식 | 결과 |
|---|---|---|
| Gaussian Blur | ROI 삽입 후 경계 영역에 선택적 blur | 경계는 부드러워지지만 전체가 약간 흐릿해짐 |
| Feathering | ROI 경계에 그라데이션 마스크 적용 | 경계가 자연스럽고 **디테일 보존에 유리** |

</div>

<figure>
  <img loading="lazy" src="https://raw.githubusercontent.com/i1uvmango/image_blending/main/test2/step6_final/comparison.png" alt="경계 처리 없음, Gaussian Blur, Feathering 세 가지 결과 비교">
  <figcaption>왼쪽부터 경계 처리 없음 / Gaussian Blur / Feathering.</figcaption>
</figure>

승자를 정하지 않고 둘 다 출력한다. 선명도와 경계 자연스러움 사이의 트레이드오프이고, 이미지에 따라 답이 달라진다. **Twist 1(국소 합성)을 택한 대가로 남은 미해결 문제**다.

---

## 전체 파이프라인

<div class="tw" markdown="1">

| 단계 | 하는 일 | 관련 twist |
|---|---|---|
| 1 | ROI crop (padding 없음), eye 강제 리사이즈, RGB→YUV | 1·3 |
| 2 | Gaussian Pyramid — Y, U, V 전 채널, `levels=5` | 3 |
| 3 | Laplacian Pyramid = 현재 레벨 − 업샘플된 다음 레벨 | — |
| 4 | eye Laplacian 절댓값 → edge mask → blur → Mask Pyramid | 2 |
| 5 | 레벨별 `eye·mask + hand·(1−mask)` | 2 |
| 6 | Collapse → YUV→RGB → 원본에 삽입 → 경계 처리 2안 | 1 |

</div>

전 단계 중간 산출물을 **전부 PNG로 저장**하도록 만들었다. 색상 왜곡 버그를 잡은 것도 Step 2와 Step 5의 레벨별 이미지를 눈으로 비교해서였다.

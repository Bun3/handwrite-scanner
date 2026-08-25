"""업로드 사진을 템플릿 기준 이미지 좌표계로 정합."""
import io

from PIL import Image

try:
    import cv2
    import numpy as np
except ImportError:  # opencv 휠이 없는 환경: 리사이즈 폴백만 사용
    cv2 = None


DETECT_MIN_SCORE = 40  # 자동 판별 채택 최소 인라이어 수


def to_reference(photo_bytes: bytes, ref_png_path) -> tuple[Image.Image, bool]:
    """반환: (기준 좌표계로 맞춘 이미지, 정합 성공 여부). 실패 시 단순 리사이즈."""
    photo = Image.open(io.BytesIO(photo_bytes)).convert("RGB")
    ref = Image.open(ref_png_path)
    if cv2 is not None:
        warped, _ = _orb_align(photo, ref)
        if warped is not None:
            return warped, True
    return photo.resize(ref.size), False


def best_template(photo_bytes: bytes, candidates: list) -> tuple[dict | None, Image.Image | None]:
    """어떤 양식인지 자동 판별. candidates: [(template dict, reference 경로)].

    전 템플릿과 정합을 시도해 인라이어 수가 가장 높고 임계값 이상인 것을 채택.
    ponytail: 템플릿마다 ORB 재계산 — 템플릿 수십 개 넘어가면 photo 특징점 캐싱.
    """
    if cv2 is None:
        return None, None
    photo = Image.open(io.BytesIO(photo_bytes)).convert("RGB")
    best_tpl, best_img, best_score = None, None, DETECT_MIN_SCORE - 1
    for tpl, ref_path in candidates:
        warped, score = _orb_align(photo, Image.open(ref_path))
        if warped is not None and score > best_score:
            best_tpl, best_img, best_score = tpl, warped, score
    return best_tpl, best_img


def _orb_align(photo: Image.Image, ref: Image.Image) -> tuple[Image.Image | None, int]:
    img = cv2.cvtColor(np.array(photo), cv2.COLOR_RGB2GRAY)
    ref_g = cv2.cvtColor(np.array(ref.convert("RGB")), cv2.COLOR_RGB2GRAY)
    orb = cv2.ORB_create(4000)
    k1, d1 = orb.detectAndCompute(img, None)
    k2, d2 = orb.detectAndCompute(ref_g, None)
    if d1 is None or d2 is None:
        return None, 0
    matches = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True).match(d1, d2)
    matches = sorted(matches, key=lambda m: m.distance)[:500]
    if len(matches) < 20:
        return None, 0
    src = np.float32([k1[m.queryIdx].pt for m in matches]).reshape(-1, 1, 2)
    dst = np.float32([k2[m.trainIdx].pt for m in matches]).reshape(-1, 1, 2)
    H, mask = cv2.findHomography(src, dst, cv2.RANSAC, 5.0)
    if H is None or mask.sum() < 15:
        return None, 0
    warped = cv2.warpPerspective(np.array(photo), H, ref.size,
                                 borderValue=(255, 255, 255))
    return Image.fromarray(warped), int(mask.sum())

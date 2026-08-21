"""업로드 사진을 템플릿 기준 이미지 좌표계로 정합."""
import io

from PIL import Image

try:
    import cv2
    import numpy as np
except ImportError:  # opencv 휠이 없는 환경: 리사이즈 폴백만 사용
    cv2 = None


def to_reference(photo_bytes: bytes, ref_png_path) -> tuple[Image.Image, bool]:
    """반환: (기준 좌표계로 맞춘 이미지, 정합 성공 여부). 실패 시 단순 리사이즈."""
    photo = Image.open(io.BytesIO(photo_bytes)).convert("RGB")
    ref = Image.open(ref_png_path)
    if cv2 is not None:
        warped = _orb_align(photo, ref)
        if warped is not None:
            return warped, True
    return photo.resize(ref.size), False


def _orb_align(photo: Image.Image, ref: Image.Image) -> Image.Image | None:
    img = cv2.cvtColor(np.array(photo), cv2.COLOR_RGB2GRAY)
    ref_g = cv2.cvtColor(np.array(ref.convert("RGB")), cv2.COLOR_RGB2GRAY)
    orb = cv2.ORB_create(4000)
    k1, d1 = orb.detectAndCompute(img, None)
    k2, d2 = orb.detectAndCompute(ref_g, None)
    if d1 is None or d2 is None:
        return None
    matches = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True).match(d1, d2)
    matches = sorted(matches, key=lambda m: m.distance)[:500]
    if len(matches) < 20:
        return None
    src = np.float32([k1[m.queryIdx].pt for m in matches]).reshape(-1, 1, 2)
    dst = np.float32([k2[m.trainIdx].pt for m in matches]).reshape(-1, 1, 2)
    H, mask = cv2.findHomography(src, dst, cv2.RANSAC, 5.0)
    if H is None or mask.sum() < 15:
        return None
    warped = cv2.warpPerspective(np.array(photo), H, ref.size,
                                 borderValue=(255, 255, 255))
    return Image.fromarray(warped)

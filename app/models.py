"""인식 모델 카탈로그·선택·다운로드.

선택 상태는 data/settings.json 에 저장. 설정이 없으면 시스템 RAM에 맞는
추천 모델이 기본값이 된다 (첫 실행 다운로드 대상도 이것).
"""
import json
import threading

from app import config

CATALOG = [
    {"id": "qwen3vl-2b", "label": "Qwen3-VL 2B (초경량)",
     "repo": "Qwen/Qwen3-VL-2B-Instruct-GGUF",
     "model": "Qwen3VL-2B-Instruct-Q4_K_M.gguf",
     "mmproj": "mmproj-Qwen3VL-2B-Instruct-F16.gguf",
     "bytes": 1_922_000_000, "min_ram_gb": 4,
     "desc": "저사양 PC용. 인식률이 낮아 후보목록·검수 의존도가 큼"},
    {"id": "qwen3vl-4b", "label": "Qwen3-VL 4B (경량)",
     "repo": "Qwen/Qwen3-VL-4B-Instruct-GGUF",
     "model": "Qwen3VL-4B-Instruct-Q4_K_M.gguf",
     "mmproj": "mmproj-Qwen3VL-4B-Instruct-F16.gguf",
     "bytes": 3_340_000_000, "min_ram_gb": 8,
     "desc": "램 8GB PC용 균형점"},
    {"id": "qwen3vl-8b", "label": "Qwen3-VL 8B (표준)",
     "repo": "Qwen/Qwen3-VL-8B-Instruct-GGUF",
     "model": "Qwen3VL-8B-Instruct-Q4_K_M.gguf",
     "mmproj": "mmproj-Qwen3VL-8B-Instruct-F16.gguf",
     "bytes": 6_190_000_000, "min_ram_gb": 16,
     "desc": "기본 권장. 한글 수기 인식 검증 완료"},
    {"id": "qwen3vl-30b", "label": "Qwen3-VL 30B-A3B (고성능)",
     "repo": "Qwen/Qwen3-VL-30B-A3B-Instruct-GGUF",
     "model": "Qwen3VL-30B-A3B-Instruct-Q4_K_M.gguf",
     "mmproj": "mmproj-Qwen3VL-30B-A3B-Instruct-F16.gguf",
     "bytes": 19_640_000_000, "min_ram_gb": 32,
     "desc": "램 32GB 이상. MoE 구조라 속도는 4B급, 정확도 최상"},
]

SETTINGS = config.DATA_DIR / "settings.json"
_downloads: dict[str, threading.Thread] = {}
_download_errors: dict[str, str] = {}


def entry(model_id: str) -> dict | None:
    return next((e for e in CATALOG if e["id"] == model_id), None)


def total_ram_gb() -> int:
    import ctypes

    class MemStatus(ctypes.Structure):
        # MEMORYSTATUSEX: DWORD 2개 + DWORDLONG 7개 = 64바이트 (크기가 틀리면 호출 실패)
        _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong)] + [
                    (f"u{i}", ctypes.c_ulonglong) for i in range(6)]

    st = MemStatus()
    st.dwLength = ctypes.sizeof(st)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st))
    return round(st.ullTotalPhys / 2 ** 30)


def recommended_id(ram_gb: int | None = None) -> str:
    """RAM에 들어가는 가장 큰 모델. (같은 min_ram이면 카탈로그 순)"""
    ram = ram_gb if ram_gb is not None else total_ram_gb()
    fits = [e for e in CATALOG if e["min_ram_gb"] <= ram]
    return (fits[-1] if fits else CATALOG[0])["id"]


def paths(e: dict) -> tuple:
    d = config.ENGINE_DIR / "models"
    return d / e["model"], d / e["mmproj"]


def installed(e: dict) -> bool:
    m, p = paths(e)
    return m.exists() and p.exists()


def current() -> dict:
    try:
        mid = json.loads(SETTINGS.read_text(encoding="utf-8"))["model"]
        e = entry(mid)
        if e:
            return e
    except (OSError, ValueError, KeyError):
        pass
    rec = entry(recommended_id())
    if installed(rec):
        return rec
    have = [e for e in CATALOG if installed(e)]
    if have:
        return have[-1]  # 설치된 것 중 가장 큰 모델
    return rec  # 아무것도 없음 → 첫 실행 다운로드 대상 = 추천 모델


def select(model_id: str) -> dict:
    e = entry(model_id)
    if not e:
        raise ValueError("알 수 없는 모델")
    if not installed(e):
        raise ValueError("설치되지 않은 모델입니다. 먼저 다운로드하세요.")
    SETTINGS.write_text(json.dumps({"model": model_id}), encoding="utf-8")
    from app import llm
    llm.restart()  # 다음 인식부터 새 모델로
    return e


def _downloaded_bytes(e: dict) -> int:
    total = 0
    for p in paths(e):
        part = p.with_name(p.name + ".part")
        if p.exists():
            total += p.stat().st_size
        elif part.exists():
            total += part.stat().st_size
    return total


def start_download(model_id: str) -> None:
    e = entry(model_id)
    if not e or installed(e):
        return
    if model_id in _downloads and _downloads[model_id].is_alive():
        return

    def run():
        from app.engine_setup import _download
        try:
            _download_errors.pop(model_id, None)
            for p, fname in zip(paths(e), (e["model"], e["mmproj"])):
                if not p.exists():
                    p.parent.mkdir(parents=True, exist_ok=True)
                    _download(f"https://huggingface.co/{e['repo']}/resolve/main/{fname}",
                              p, fname)
        except Exception as ex:
            _download_errors[model_id] = str(ex)

    t = threading.Thread(target=run, daemon=True)
    _downloads[model_id] = t
    t.start()


def status_list() -> dict:
    ram = total_ram_gb()
    rec = recommended_id(ram)
    cur = current()["id"]
    out = []
    for e in CATALOG:
        downloading = (e["id"] in _downloads and _downloads[e["id"]].is_alive())
        out.append({
            "id": e["id"], "label": e["label"], "desc": e["desc"],
            "size_gb": round(e["bytes"] / 2 ** 30, 1),
            "min_ram_gb": e["min_ram_gb"],
            "installed": installed(e), "active": e["id"] == cur,
            "recommended": e["id"] == rec,
            "downloading": downloading,
            "progress": min(99, _downloaded_bytes(e) * 100 // e["bytes"])
                        if downloading else None,
            "error": _download_errors.get(e["id"]),
        })
    return {"ram_gb": ram, "models": out}

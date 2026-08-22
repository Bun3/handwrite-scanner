"""첫 실행 시 인식 엔진(llama.cpp + 모델) 자동 다운로드. 콘솔에 진행률 표시."""
import shutil
import zipfile

import httpx

from app import config

LLAMA_ZIP = "https://github.com/ggml-org/llama.cpp/releases/download/b10549/llama-b10549-bin-win-cpu-x64.zip"
HF = "https://huggingface.co/Qwen/Qwen3-VL-8B-Instruct-GGUF/resolve/main/"


def _download(url: str, dest, label: str) -> None:
    tmp = dest.with_name(dest.name + ".part")
    with httpx.stream("GET", url, follow_redirects=True, timeout=60) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        done = last = 0
        with open(tmp, "wb") as f:
            for chunk in r.iter_bytes(1 << 20):
                f.write(chunk)
                done += len(chunk)
                pct = done * 100 // total if total else 0
                if pct >= last + 5:
                    last = pct
                    print(f"  {label}: {pct}% ({done // (1 << 20)}MB)", flush=True)
    tmp.replace(dest)


def ensure_engine() -> None:
    """엔진 구성 요소가 없으면 내려받는다 (최초 1회, 약 6GB)."""
    if not config.LLAMA_SERVER.exists():
        print("llama.cpp 다운로드 중...", flush=True)
        config.ENGINE_DIR.mkdir(parents=True, exist_ok=True)
        zip_path = config.ENGINE_DIR / "llama-cpu.zip"
        _download(LLAMA_ZIP, zip_path, "llama.cpp")
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(config.ENGINE_DIR / "llama")
        zip_path.unlink()
    for path in (config.MODEL, config.MMPROJ):
        if not path.exists():
            print(f"모델 다운로드 중: {path.name} (수 GB, 오래 걸립니다)", flush=True)
            path.parent.mkdir(parents=True, exist_ok=True)
            _download(HF + path.name, path, path.name)
    print("엔진 준비 완료.", flush=True)


def free_disk_ok() -> bool:
    return shutil.disk_usage(config.BASE_DIR).free > 8 * (1 << 30)

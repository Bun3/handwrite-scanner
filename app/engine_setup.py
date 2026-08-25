"""첫 실행 시 인식 엔진(llama.cpp + 모델) 자동 다운로드.

curl(Windows 10+ 기본 탑재)로 받아서 진행률 표시·재시도·이어받기를 지원한다.
중간에 끊겨도 다시 실행하면 받던 지점부터 이어받는다.
"""
import shutil
import subprocess
import zipfile

from app import config

LLAMA_ZIP = "https://github.com/ggml-org/llama.cpp/releases/download/b10549/llama-b10549-bin-win-cpu-x64.zip"


def _download(url: str, dest, label: str) -> None:
    tmp = dest.with_name(dest.name + ".part")
    curl = shutil.which("curl")
    if curl:
        # -C - : 이어받기 / --retry : 일시적 네트워크 오류 자동 재시도
        r = subprocess.run([curl, "-L", "-C", "-", "--retry", "10",
                            "--retry-delay", "3", "--connect-timeout", "30",
                            "-o", str(tmp), url])
        if r.returncode != 0:
            raise RuntimeError(
                f"{label} 다운로드 실패 (curl 종료코드 {r.returncode}). "
                "네트워크를 확인하고 프로그램을 다시 실행하면 받던 지점부터 이어받습니다.")
    else:  # curl이 없는 환경 폴백
        import httpx
        done = tmp.stat().st_size if tmp.exists() else 0
        headers = {"Range": f"bytes={done}-"} if done else {}
        with httpx.stream("GET", url, headers=headers, follow_redirects=True,
                          timeout=60) as resp:
            resp.raise_for_status()
            mode = "ab" if resp.status_code == 206 else "wb"
            last = done
            with open(tmp, mode) as f:
                for chunk in resp.iter_bytes(1 << 20):
                    f.write(chunk)
                    done += len(chunk)
                    if done - last >= 100 * (1 << 20):  # 100MB마다 표시
                        last = done
                        print(f"  {label}: {done // (1 << 20)}MB 수신", flush=True)
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
    from app import models
    e = models.current()  # 설정된 모델, 없으면 시스템 RAM 기준 추천 모델
    for path, fname in zip(models.paths(e), (e["model"], e["mmproj"])):
        if not path.exists():
            print(f"모델 다운로드 중: {fname} — {e['label']} (수 GB, 아래 진행률 참고. "
                  "중간에 꺼져도 재실행하면 이어받습니다)", flush=True)
            path.parent.mkdir(parents=True, exist_ok=True)
            _download(f"https://huggingface.co/{e['repo']}/resolve/main/{fname}",
                      path, fname)
    print(f"엔진 준비 완료. (모델: {e['label']})", flush=True)


def free_disk_ok() -> bool:
    return shutil.disk_usage(config.BASE_DIR).free > 8 * (1 << 30)

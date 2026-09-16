"""사용자 안내와 진단용 상세 내용을 분리한다."""
import errno
import json

import httpx
from PIL import UnidentifiedImageError


class UserError(Exception):
    def __init__(self, code, message, action):
        super().__init__(message)
        self.code, self.message, self.action = code, message, action


def explain(exc):
    if isinstance(exc, UserError):
        return {"code": exc.code, "message": exc.message, "action": exc.action}
    if isinstance(exc, MemoryError):
        code, message, action = 'memory', '작업에 필요한 메모리가 부족합니다.', '다른 프로그램을 닫거나 더 작은 인식 모델을 선택한 뒤 이어하기를 누르세요.'
    elif isinstance(exc, PermissionError):
        code, message, action = 'permission', '파일을 읽거나 저장할 권한이 없습니다.', '설치 폴더의 쓰기 권한과 보안 프로그램의 차단 여부를 확인하세요. 사용 중인 출력 파일도 닫아 주세요.'
    elif isinstance(exc, OSError) and (exc.errno == errno.ENOSPC or getattr(exc, 'winerror', None) == 112):
        code, message, action = 'disk_full', '저장 공간이 부족합니다.', '설치 폴더가 있는 드라이브의 여유 공간을 확보한 뒤 이어하기를 누르세요.'
    elif isinstance(exc, FileNotFoundError):
        code, message, action = 'file_missing', '필요한 파일 또는 폴더를 찾을 수 없습니다.', '아래 상세 내용의 경로를 확인하고 파일을 복원하세요. Google Drive 파일은 이 컴퓨터에 다운로드되어 있어야 합니다.'
    elif isinstance(exc, httpx.TimeoutException):
        code, message, action = 'engine_timeout', '인식 엔진의 응답을 기다리다 제한 시간을 넘었습니다.', '다른 프로그램을 닫거나 작은 모델을 사용해 보세요. 완료된 페이지는 이어하기로 유지할 수 있습니다.'
    elif isinstance(exc, httpx.TransportError):
        code, message, action = 'engine_connection', '인식 엔진과 연결이 끊어졌습니다.', '프로그램을 다시 실행한 뒤 이어하기를 누르세요. 반복되면 더 작은 모델을 사용해 보세요.'
    elif isinstance(exc, httpx.HTTPStatusError):
        code, message, action = 'engine_response', '인식 엔진이 요청을 처리하지 못했습니다.', '이어하기로 다시 시도하세요. 반복되면 모델 파일과 메모리 여유를 확인하고 상세 내용을 전달해 주세요.'
    elif isinstance(exc, UnidentifiedImageError):
        code, message, action = 'image_invalid', '이미지 파일을 읽을 수 없습니다.', '파일이 정상적으로 열리는지 확인하고 PNG 또는 JPG로 다시 저장해 등록하세요.'
    elif isinstance(exc, json.JSONDecodeError):
        code, message, action = 'data_invalid', '저장된 설정이나 결과의 형식이 올바르지 않습니다.', '아래 상세 내용을 확인하세요. 템플릿은 다시 저장하거나 백업에서 복원해 주세요.'
    else:
        code, message, action = 'unexpected', '작업을 처리하는 중 예상하지 못한 문제가 발생했습니다.', '아래 상세 내용을 복사해 전달해 주세요. 완료된 페이지가 있으면 이어하기로 다시 시도할 수 있습니다.'
    return dict(code=code, message=message, action=action)

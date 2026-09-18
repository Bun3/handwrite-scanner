"""자료 이동 API. 가져오기는 명시적 확인 후 등록하고 자동 실행하지 않는다."""
import re

from fastapi import APIRouter, UploadFile
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool

from app import transfer, jobs, job_context, models
from app.transfer_archive import require

router = APIRouter(prefix='/api/transfer')


@router.post('/export')
def export(body: dict):
    path = transfer.export_bundle(body.get('jobs', []), body.get('templates', []), body.get('pages'))
    return {'url': '/api/transfer/download/' + path.stem, 'filename': 'handwrite-data.hscan', 'bytes': path.stat().st_size}


@router.get('/download/{token}')
def download(token: str, filename: str = 'handwrite-data.hscan'):
    require(re.fullmatch(r'[a-f0-9]{32}', token))
    require(1 <= len(filename) <= 180 and not re.search(r'[\\/:*?"<>|\x00-\x1f]', filename)
            and filename.lower().endswith('.hscan'), '올바른 자료 파일 이름을 입력하세요.')
    path = transfer.root() / (token + '.hscan')
    require(path.is_file(), '내보낸 자료가 만료되었습니다. 다시 내보내세요.')
    return FileResponse(path, filename=filename, media_type='application/octet-stream')


@router.post('/preview')
async def preview(file: UploadFile):
    try:
        return await run_in_threadpool(transfer.stage, file.file)
    finally:
        await file.close()


@router.post('/commit')
def commit(body: dict):
    return transfer.commit(body.get('token'), body.get('jobs', []), body.get('templates', []), copy_duplicates=body.get('copy_duplicates') is True)


@router.post('/merge-preview')
def merge_preview(body: dict):
    return transfer.merge_preview(body.get('token'), body.get('index'), body.get('target'))


@router.post('/merge')
def merge(body: dict):
    return transfer.merge(body.get('token'), body.get('index'), body.get('target'), body.get('revision'), body.get('choices'))


@router.post('/jobs/{job_id}/pages')
def pages(job_id: str):
    return transfer.details(job_id)


@router.get('/jobs/{job_id}/input/{page}')
def input_page(job_id: str, page: int):
    require(transfer.valid_name(job_id))
    require(jobs.status(job_id) is not None)
    images = jobs.input_images(job_id)
    require(0 <= page < len(images))
    # 선택 팝업용으로 이미지 크기를 제한한다.
    import io
    from PIL import Image
    from fastapi.responses import Response
    with Image.open(images[page]) as img:
        img = img.convert('RGB'); img.thumbnail((600, 800))
        buffer = io.BytesIO(); img.save(buffer, 'PNG')
    return Response(buffer.getvalue(), media_type='image/png')


@router.post('/jobs/{job_id}/release')
def release(job_id: str):
    return transfer.release_assignment(job_id)


def check_resume_model(job_id, accept_current=False):
    context = job_context.read(job_id)
    if not context or not context.get('imported'):
        return
    current = models.current()['id']
    require(context['model'] == current or accept_current, f"이 작업의 모델은 {context['model']}입니다. 해당 모델을 선택하거나 현재 모델({current})로 이어가기를 선택하세요.")
    if context['model'] != current:
        context['model'] = current; job_context.write(job_id, context)
    return current

/* 오류는 화면에 남기고, 기술 상세는 사용자가 펼칠 때 보여 준다. */
const noticeTimes = new Map();
function notify(message, options = {}) {
  const key = message + (options.action || '');
  if (Date.now() - (noticeTimes.get(key) || 0) < 15000) return;
  noticeTimes.set(key, Date.now());
  let host = document.getElementById('notifications');
  if (!host) {
    host = document.createElement('aside'); host.id = 'notifications';
    host.setAttribute('aria-live', 'polite'); document.body.append(host);
  }
  const card = document.createElement('div'); card.className = 'notice';
  const close = document.createElement('button'); close.className = 'secondary';
  close.textContent = '닫기'; close.onclick = () => card.remove(); card.append(close);
  const text = document.createElement('p'); text.textContent = message; card.append(text);
  if (options.action) { const p = document.createElement('p'); p.textContent = options.action; card.append(p); }
  if (options.technical) {
    const details = document.createElement('details'), summary = document.createElement('summary'), pre = document.createElement('pre');
    summary.textContent = '기술 상세 (복사해 전달할 수 있습니다)';
    pre.textContent = options.technical; details.append(summary, pre); card.append(details);
  }
  host.prepend(card);
  if (options.code || options.technical || options.reportable) {
    const report = document.createElement('button'); report.className = 'secondary';
    report.textContent = '이 오류 보고하기';
    report.onclick = () => window.openDiagnosticReport?.(options.code || 'unexpected');
    card.append(report);
  }
  while (host.children.length > 4) host.lastElementChild.remove();
}

async function apiFetch(url, options) {
  let response;
  try { response = await fetch(url, options); }
  catch (cause) {
    const error = new Error('프로그램과 연결할 수 없습니다. 프로그램 실행 상태와 네트워크를 확인하세요.');
    error.reported = true; if (!window.updateRestarting) notify(error.message, {code: 'app_connection'}); throw error;
  }
  if (!response.ok) {
    let body = {};
    try { body = await response.clone().json(); } catch {}
    const info = body.error_info || {};
    if (response.status === 405 && String(url).includes('/api/')) {
      info.message = '실행 중인 서버가 이 기능을 지원하지 않습니다. 화면과 서버 버전이 다를 수 있습니다.';
      info.action = '브라우저뿐 아니라 실행 중인 handwrite-scanner 프로그램도 종료한 뒤 새 버전 EXE를 실행하세요. 서버 PC가 따로 있으면 해당 PC를 확인하세요.';
      info.technical = `HTTP 405: ${url}\n실행 버전 확인: /api/health`;
    }
    const message = info.message || (typeof body.detail === 'string' ? body.detail : `요청을 처리하지 못했습니다 (${response.status}).`);
    const error = new Error(message); error.reported = true; error.info = info;
    notify(message, {...info, code: info.code || `http_${response.status}`, reportable: true}); throw error;
  }
  return response;
}

async function loadImage(url) {
  const response = await apiFetch(url);
  const local = URL.createObjectURL(await response.blob());
  try {
    const img = new Image();
    await new Promise((resolve, reject) => {
      img.onload = resolve;
      img.onerror = () => reject(new Error('이미지를 표시할 수 없습니다. 원본 또는 기준 이미지 파일을 확인하세요.'));
      img.src = local;
    });
    return img;
  } finally { URL.revokeObjectURL(local); }
}

window.addEventListener('unhandledrejection', event => {
  if (!event.reason?.reported) notify('요청을 완료하지 못했습니다. 다시 시도해 주세요.', {technical: String(event.reason)});
  event.preventDefault();
});

window.addEventListener('error', event => {
  if (event.error) notify('화면을 처리하는 중 오류가 발생했습니다. 오류 보고로 발생 상황을 알려 주세요.',
    {code: 'browser_error', technical: String(event.error)});
});

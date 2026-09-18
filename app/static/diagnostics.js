/* Explicit opt-in only. Never pass raw notification text, paths or technical logs. */
(() => {
  let dialog, snapshot, token, code, busy = false, canSend = false, sent = false;
  const el = id => document.getElementById(id);
  function sync() {
    el('diagnosticSend').disabled = busy || sent || !token || !canSend || !el('diagnosticConsent').checked;
    el('diagnosticSave').disabled = busy || !snapshot;
    el('diagnosticPrepare').disabled = busy;
    el('diagnosticContact').disabled = busy;
    el('diagnosticDescription').disabled = busy;
    el('diagnosticKind').disabled = busy;
    el('diagnosticCategory').disabled = busy;
  }
  function invalidate() {
    snapshot = null; token = null; sent = false;
    el('diagnosticConsent').checked = false;
    el('diagnosticPreview').textContent = '미리보기를 눌러 전송할 내용을 확인하세요.';
    el('diagnosticStatus').textContent = ''; sync();
  }
  async function post(path, body) {
    const r = await fetch('/api/diagnostics/' + path, {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body),
      signal: AbortSignal.timeout(25000)
    });
    const data = await r.json();
    if (!r.ok) throw new Error(typeof data.detail === 'string' ? data.detail : '처리하지 못했습니다.');
    return data;
  }
  function ensure() {
    if (dialog) return;
    dialog = document.createElement('dialog'); dialog.id = 'diagnosticDialog';
    dialog.className = 'transfer-dialog'; dialog.setAttribute('aria-labelledby', 'diagnosticTitle');
    dialog.innerHTML = `<h2 id="diagnosticTitle">오류 보고</h2>
      <label>보낼 내용 <select id="diagnosticKind"><option value="error">오류 보고</option><option value="feedback">의견 보내기</option></select></label>
      <label id="diagnosticCategoryRow" hidden>의견 종류 <select id="diagnosticCategory"><option value="suggestion">개선 제안</option><option value="usability">사용 불편</option><option value="other">기타 의견</option></select></label>
      <p id="diagnosticErrorInfo">앱 개발자에게 오류 코드·발생 위치·기기 사양·작업 상태와 최근 진단 기록을 보냅니다.
      원본 문서, 인식 내용, 파일 경로, PC 사용자 이름, 엔진 로그 원문은 자동 수집하지 않습니다.</p>
      <p id="diagnosticFeedbackInfo" hidden>앱 버전·현재 화면과 직접 입력한 의견·연락처만 보냅니다. 기기 사양·진단 기록·문서 내용은 첨부하지 않습니다.</p>
      <p class="hint">Cloudflare를 통해 전송·보관하며 보고서는 30일 후 삭제 대상이 됩니다.
      접속 IP는 서버의 전송 제한에 사용되지만 보고서에는 저장하지 않습니다.
      아래 입력란에 환자 정보나 비밀번호를 적지 마세요.</p>
      <label>연락처 (선택)<input id="diagnosticContact" maxlength="200" autocomplete="off" placeholder="답변받을 이메일 등"></label>
      <label><span id="diagnosticDescriptionLabel">어떤 작업 중 발생했나요? (선택)</span><textarea id="diagnosticDescription" maxlength="4000" rows="3"></textarea></label>
      <p class="hint">내용 최대 4,000자 · 연락처 최대 200자. 오류·의견 합산 IP당 1분 5회, 전체 하루 1,000건까지 접수합니다.</p>
      <button id="diagnosticPrepare" class="secondary">전송 내용 미리보기</button>
      <pre id="diagnosticPreview" tabindex="0"></pre>
      <label><input type="checkbox" id="diagnosticConsent"> 위 내용을 확인했으며 개발자에게 전송하는 데 동의합니다.</label>
      <p id="diagnosticStatus" role="status"></p>
      <div class="diagnostic-actions"><button id="diagnosticSend">동의하고 전송</button>
      <button id="diagnosticSave" class="secondary">보고서 파일 저장</button>
      <button id="diagnosticClose" class="secondary">닫기</button></div>`;
    document.body.append(dialog);
    el('diagnosticKind').onchange = () => { updateKind(); invalidate(); };
    el('diagnosticCategory').onchange = invalidate;
    for (const id of ['diagnosticContact', 'diagnosticDescription']) el(id).oninput = invalidate;
    el('diagnosticConsent').onchange = sync;
    el('diagnosticClose').onclick = () => { if (!busy) dialog.close(); };
    dialog.addEventListener('cancel', e => { if (busy) e.preventDefault(); });
    el('diagnosticPrepare').onclick = async () => {
      if (el('diagnosticKind').value === 'feedback' && !el('diagnosticDescription').value.trim()) {
        el('diagnosticStatus').textContent = '보낼 의견을 입력해 주세요.';
        el('diagnosticDescription').focus(); return;
      }
      busy = true; sync();
      const data = {code, kind: el('diagnosticKind').value, category: el('diagnosticCategory').value,
        screen: location.pathname.split('/').pop().replace('.html', '') || 'index',
        contact: el('diagnosticContact').value, description: el('diagnosticDescription').value};
      try {
        const result = await post('preview', data);
        if (data.kind === 'feedback' && result.report?.kind !== 'feedback') {
          throw new Error('실행 중인 프로그램이 의견 보내기를 지원하지 않습니다. 프로그램을 업데이트한 뒤 다시 실행해 주세요.');
        }
        snapshot = result.report; token = result.token; canSend = result.can_send;
        el('diagnosticStatus').textContent = canSend ? '아래 내용을 확인한 뒤 전송해 주세요.' : '온라인 접수가 설정되지 않았습니다. 파일로 저장해 전달할 수 있습니다.';
      } catch (e) {
        snapshot = {schema: 1, created_at: new Date().toISOString(), ...data, collection: 'browser-only'};
        token = null; canSend = false;
        el('diagnosticStatus').textContent = '진단 정보를 가져오지 못해 기본 보고서만 준비했습니다. 파일로 저장할 수 있습니다. ' + e.message;
      } finally {
        sent = false; el('diagnosticConsent').checked = false;
        el('diagnosticPreview').textContent = JSON.stringify(snapshot, null, 2);
        busy = false; sync();
      }
    };
    el('diagnosticSend').onclick = async () => {
      busy = true; sync(); el('diagnosticStatus').textContent = '전송 중…';
      try {
        const result = await post('submit', {token, consent: el('diagnosticConsent').checked});
        sent = true; el('diagnosticStatus').textContent = '접수 완료 · 접수 번호: ' + result.receipt;
      } catch (e) { el('diagnosticStatus').textContent = e.message + ' 보고서 파일 저장을 이용할 수 있습니다.'; }
      finally { busy = false; sync(); }
    };
    el('diagnosticSave').onclick = () => {
      const url = URL.createObjectURL(new Blob([JSON.stringify(snapshot, null, 2)], {type: 'application/json'}));
      const a = document.createElement('a'); a.href = url;
      a.download = (snapshot.kind === 'feedback' ? 'handwrite-feedback-' : 'handwrite-error-report-') + new Date().toISOString().slice(0, 10) + '.json';
      a.click(); setTimeout(() => URL.revokeObjectURL(url), 10000);
    };
  }
  function updateKind() {
    const feedback = el('diagnosticKind').value === 'feedback';
    el('diagnosticTitle').textContent = feedback ? '의견 보내기' : '오류 보고';
    el('diagnosticCategoryRow').hidden = !feedback;
    el('diagnosticFeedbackInfo').hidden = !feedback;
    el('diagnosticErrorInfo').hidden = feedback;
    el('diagnosticDescriptionLabel').textContent = feedback ? '의견 내용 (필수)' : '어떤 작업 중 발생했나요? (선택)';
  }
  window.openDiagnosticReport = (errorCode = 'unexpected', kind = 'error') => {
    ensure(); if (busy) return;
    el('diagnosticKind').value = kind; updateKind();
    code = /^[A-Za-z0-9_.-]{1,80}$/.test(errorCode) ? errorCode : 'unexpected';
    invalidate(); if (!dialog.open) dialog.showModal();
  };
  document.addEventListener('DOMContentLoaded', () => {
    const button = document.createElement('button'); button.textContent = '오류 보고'; button.className = 'secondary';
    button.title = '전송할 진단 내용을 먼저 확인하거나 파일로 저장합니다.';
    button.onclick = () => window.openDiagnosticReport();
    (document.querySelector('header') || document.body).append(button);
    const feedback = document.createElement('button'); feedback.textContent = '의견 보내기'; feedback.className = 'secondary';
    feedback.title = '개선 제안이나 사용 중 불편한 점을 보냅니다. 진단 정보는 첨부하지 않습니다.';
    feedback.onclick = () => window.openDiagnosticReport('unexpected', 'feedback');
    button.after(feedback);
  });
})();

// 업로드 원본은 서버에서 보관하고, 미리보기 선택만 작업 시작 요청으로 전달한다.
let inputDraft = null, inputSelections = [], inputPreparing = false, inputStored = true;
let availableTemplates = [], inputTemplates = null;
const savedTemplates = viewState.read('inputTemplates');
if (Array.isArray(savedTemplates)) inputTemplates = new Set(savedTemplates.filter(n => typeof n === 'string'));

function saveInput() {
  inputStored = inputTemplates === null || viewState.write('inputTemplates', [...inputTemplates]);
  if (inputDraft) inputStored = viewState.write('input', {token: inputDraft.token, pages: inputSelections.map(s => [...s])}) && inputStored;
}

async function restoreInput() {
  const saved = viewState.read('input');
  if (!saved?.token || !Array.isArray(saved.pages)) return;
  const file = document.querySelector('#up input[type=file]'), button = document.getElementById('submitJob');
  file.disabled = true; button.disabled = true;
  try {
    const draft = await j('/api/intake/' + encodeURIComponent(saved.token));
    if (draft.job_id) {
      viewState.remove('input');
      document.getElementById('uploadStatus').textContent = `접수된 작업이 있습니다: ${draft.job_id}`;
      return;
    }
    if (!Array.isArray(draft.files) || saved.pages.length !== draft.files.length) {
      viewState.remove('input'); return;
    }
    inputDraft = draft;
    inputSelections = draft.files.map((f, i) => new Set((Array.isArray(saved.pages[i]) ? saved.pages[i] : [])
      .filter(n => Number.isInteger(n) && n >= 1 && n <= f.pages)));
    file.required = false; renderPageSelection();
    document.getElementById('uploadStatus').textContent = '이전에 선택한 입력을 복원했습니다. 양식과 페이지를 확인한 뒤 인식 시작을 누르세요.';
  } catch (error) {
    if (error.info?.code === 'input_missing') viewState.remove('input');
  } finally { file.disabled = false; button.disabled = false; }
}

async function prepareInput() {
  if (inputPreparing) return null;
  const fileInput = document.querySelector('#up input[type=file]');
  inputDraft = null; inputSelections = [];
  viewState.remove('input'); fileInput.required = true;
  document.getElementById('pageSelection').replaceChildren();
  if (!fileInput.files.length) return null;
  const status = document.getElementById('uploadStatus'), button = document.getElementById('submitJob');
  inputPreparing = true; pendingUpload = true; renderJobs();
  fileInput.disabled = true; button.disabled = true; button.textContent = '입력 준비 중…';
  status.textContent = '파일을 전달하고 있습니다. 페이지 수를 확인하면 검사할 페이지를 선택할 수 있습니다.';
  try {
    const body = new FormData();
    for (const file of fileInput.files) body.append('files', file);
    inputDraft = await j('/api/intake', {method: 'POST', body});
    inputSelections = inputDraft.files.map(f => new Set(Array.from({length: f.pages}, (_, i) => i + 1)));
    fileInput.required = false; saveInput();
    renderPageSelection();
    status.textContent = '입력 준비 완료 · 양식과 페이지를 선택한 뒤 인식 시작을 누르세요.';
    return inputDraft;
  } catch (error) {
    status.textContent = `입력 준비 실패: ${error.message} 파일을 확인하고 인식 시작을 눌러 다시 시도하세요.`;
    return null;
  } finally {
    inputPreparing = false; pendingUpload = false; renderJobs();
    fileInput.disabled = false; button.disabled = false; button.textContent = '인식 시작';
    if (inputDraft) openPagePicker();
  }
}

function renderPageSelection() {
  const container = document.getElementById('pageSelection');
  container.replaceChildren();
  if (!inputDraft) return;
  const total = inputDraft.files.reduce((sum, f) => sum + f.pages, 0);
  const selected = inputSelections.reduce((sum, pages) => sum + pages.size, 0);
  const summary = document.createElement('span');
  summary.textContent = `${inputDraft.files.length}개 파일 · ${total}페이지 중 ${selected}페이지 선택 · 양식 ${inputTemplates?.size || 0}개`;
  summary.title = inputDraft.files.map(f => f.name).join('\n');
  const button = document.createElement('button'); button.type = 'button'; button.className = 'secondary';
  button.textContent = '양식·페이지 선택'; button.onclick = openPagePicker;
  container.append(summary, button);
}

async function openPagePicker() {
  if (!inputDraft || inputPreparing || pendingUpload) return;
  try { await loadTpl(); } catch { return; }
  if (!inputDraft || inputPreparing || pendingUpload) return;
  pagePicker.open(inputDraft, inputSelections, availableTemplates, inputTemplates, (selection, templates) => {
    inputSelections = selection; inputTemplates = templates; saveInput(); renderPageSelection();
  });
}

function selectedInput() {
  const templates = [...(inputTemplates || [])];
  const pages = inputSelections.map(s => [...s].sort((a, b) => a - b));
  if (!templates.length) { notify('검사할 양식을 하나 이상 선택하세요.'); return null; }
  if (!pages.some(p => p.length)) { notify('검사할 페이지를 하나 이상 선택하세요.'); return null; }
  return {templates, pages};
}

window.addEventListener('beforeunload', e => {
  if (inputPreparing || pendingUpload || (inputDraft && !inputStored)) { e.preventDefault(); e.returnValue = ''; }
});

// 업로드 원본은 서버에서 보관하고, 미리보기 선택만 작업 시작 요청으로 전달한다.
let inputDraft = null, inputSelections = [], inputPreparing = false;
let availableTemplates = [], inputTemplates = null;

async function prepareInput() {
  if (inputPreparing) return null;
  const fileInput = document.querySelector('#up input[type=file]');
  inputDraft = null; inputSelections = [];
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
    inputSelections = selection; inputTemplates = templates; renderPageSelection();
  });
}

function selectedInput() {
  const templates = [...(inputTemplates || [])];
  const pages = inputSelections.map(s => [...s].sort((a, b) => a - b));
  if (!templates.length) { notify('검사할 양식을 하나 이상 선택하세요.'); return null; }
  if (!pages.some(p => p.length)) { notify('검사할 페이지를 하나 이상 선택하세요.'); return null; }
  return {templates, pages};
}

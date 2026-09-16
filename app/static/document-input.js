// 업로드 원본은 서버에서 보관하고, 미리보기 선택만 작업 시작 요청으로 전달한다.
let inputDraft = null, inputSelections = [], inputPreparing = false;

async function prepareInput() {
  if (inputPreparing) return null;
  const fileInput = document.querySelector('#up input[type=file]');
  if (!fileInput.files.length) return null;
  inputDraft = null; inputSelections = [];
  document.getElementById('pageSelection').replaceChildren();
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
  }
}

function renderPageSelection() {
  const container = document.getElementById('pageSelection');
  container.replaceChildren();
  for (const file of inputDraft.files) {
    const section = document.createElement('section');
    section.className = 'input-file';
    const title = document.createElement('h4');
    title.textContent = `${file.name} · ${file.pages}페이지`;
    section.append(title);
    const actions = document.createElement('div'); actions.className = 'input-actions';
    const selected = inputSelections[file.index];
    const summary = document.createElement('span'); summary.className = 'hint';
    const grid = document.createElement('div'); grid.className = 'page-grid';
    const pager = document.createElement('div'); pager.className = 'input-actions';
    let offset = 0;
    const button = (text, fn, parent = actions) => {
      const b = document.createElement('button'); b.type = 'button'; b.className = 'secondary';
      b.textContent = text; b.onclick = fn; parent.append(b); return b;
    };
    const updateCount = () => { summary.textContent = `${file.pages}페이지 중 ${selected.size}페이지 선택`; };
    const draw = () => {
      grid.replaceChildren(); updateCount();
      for (let n = offset + 1; n <= Math.min(offset + 20, file.pages); n++) {
        const card = document.createElement('div'); card.className = 'page-choice';
        const label = document.createElement('label');
        const check = document.createElement('input'); check.type = 'checkbox'; check.checked = selected.has(n);
        check.onchange = () => { check.checked ? selected.add(n) : selected.delete(n); updateCount(); };
        label.append(check, ` ${n}페이지`); card.append(label);
        const link = document.createElement('a'); link.target = '_blank'; link.rel = 'noopener';
        link.href = `/api/intake/${inputDraft.token}/files/${file.index}/pages/${n}`;
        link.title = `${n}페이지 크게 보기`;
        const img = document.createElement('img'); img.loading = 'lazy'; img.alt = `${n}페이지 미리보기`;
        img.src = link.href;
        img.onerror = () => { link.textContent = '미리보기를 열어 확인'; };
        link.append(img); card.append(link); grid.append(card);
      }
      pager.replaceChildren();
      const prev = button('이전 20페이지', () => { offset -= 20; draw(); }, pager); prev.disabled = offset === 0;
      const info = document.createElement('span'); info.textContent = `${offset + 1}–${Math.min(offset + 20, file.pages)} / ${file.pages}`; pager.append(info);
      const next = button('다음 20페이지', () => { offset += 20; draw(); }, pager); next.disabled = offset + 20 >= file.pages;
      pager.hidden = file.pages <= 20;
    };
    button('전체 선택', () => { for (let n = 1; n <= file.pages; n++) selected.add(n); draw(); });
    button('전체 해제', () => { selected.clear(); draw(); });
    const range = document.createElement('input'); range.type = 'text'; range.placeholder = '예: 1-5, 8, 12';
    range.setAttribute('aria-label', '페이지 범위'); actions.append(range);
    button('범위 적용', () => {
      const numbers = new Set();
      for (const part of range.value.split(',')) {
        const match = part.trim().match(/^(\d+)(?:\s*-\s*(\d+))?$/);
        const first = match ? Number(match[1]) : 0, last = match ? Number(match[2] || match[1]) : 0;
        if (first < 1 || last < first || last > file.pages) {
          notify(`1~${file.pages} 안에서 페이지 범위를 입력하세요.`, {action: '예: 1-5, 8, 12'}); return;
        }
        for (let n = first; n <= last; n++) numbers.add(n);
      }
      selected.clear(); numbers.forEach(n => selected.add(n)); draw();
    });
    actions.append(summary); section.append(actions, grid, pager); container.append(section); draw();
  }
}

function selectedInput() {
  const templates = [...document.querySelectorAll('#templateChoices input:checked')].map(el => el.value);
  const pages = inputSelections.map(s => [...s].sort((a, b) => a - b));
  if (!templates.length) { notify('검사할 양식을 하나 이상 선택하세요.'); return null; }
  if (!pages.some(p => p.length)) { notify('검사할 페이지를 하나 이상 선택하세요.'); return null; }
  return {templates, pages};
}

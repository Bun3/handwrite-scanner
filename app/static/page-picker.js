/* 표시 영역과 인접 행만 유지한다. 미리보기 요청은 최대 4개씩 처리한다. */
class PagePicker {
  constructor() {
    this.dialog = document.createElement('dialog');
    this.dialog.id = 'pagePicker';
    this.dialog.setAttribute('aria-labelledby', 'pagePickerTitle');
    this.dialog.innerHTML = `<div class="picker-shell">
      <div class="picker-heading"><div><h3 id="pagePickerTitle">검사할 페이지 선택</h3>
        <p class="hint">검사할 양식과 페이지를 고른 뒤 ‘선택 적용’을 누르세요.</p></div>
        <button type="button" class="secondary" id="pickerClose" aria-label="페이지 선택 닫기">✕</button></div>
      <fieldset class="picker-templates"><legend>검사할 양식 (여러 개 선택 가능)</legend>
        <div id="templateChoices"></div>
        <p class="hint">선택한 양식과 맞지 않는 문서는 건너뜁니다.</p>
      </fieldset>
      <div class="picker-tools">
        <label class="picker-file-label">입력 파일 <select id="pickerFile"></select></label>
        <label>미리보기 크기 <select id="pickerSize"><option value="3">3열</option>
          <option value="5">5열</option><option value="8">8열</option></select></label>
        <span class="hint" id="pickerDensity"></span>
      </div>
      <div class="picker-tools">
        <button type="button" class="secondary" id="pickerAll">전체 선택</button>
        <button type="button" class="secondary" id="pickerNone">전체 해제</button>
        <span class="hint" id="pickerFileCount" role="status"></span>
      </div>
      <div id="pagePickerScroll" tabindex="0" role="region" aria-label="페이지 미리보기 스크롤">
        <div id="pickerSpacer"><div id="pickerGrid"></div></div>
      </div>
      <div class="picker-footer"><span id="pickerTotal" role="status"></span><div>
        <button type="button" class="secondary" id="pickerCancel">취소</button>
        <button type="button" id="pickerApply">선택 적용</button></div></div>
    </div>`;
    document.body.append(this.dialog);
    this.el = id => this.dialog.querySelector('#' + id);
    this.scroll = this.el('pagePickerScroll'); this.grid = this.el('pickerGrid'); this.spacer = this.el('pickerSpacer');
    this.cards = new Map(); this.requests = new Map(); this.frame = 0;
    this.el('pickerClose').onclick = this.el('pickerCancel').onclick = () => this.dialog.close();
    this.dialog.addEventListener('close', () => this.cleanup());
    this.el('pickerApply').onclick = () => {
      this.onApply(this.selection.map(s => new Set(s)), new Set(this.templates));
      this.dialog.close();
    };
    this.el('pickerFile').onchange = () => {
      this.positions.set(this.fileIndex, this.position());
      this.fileIndex = Number(this.el('pickerFile').value);
      this.clearCards(); this.layout(this.positions.get(this.fileIndex) || {anchor: 0}); this.counts();
    };
    this.el('pickerSize').onchange = () => {
      const position = this.position();
      try { localStorage.setItem('pagePickerColumns', this.el('pickerSize').value); } catch {}
      this.layout(position);
    };
    this.el('pickerAll').onclick = () => { for (let n = 1; n <= this.file.pages; n++) if (!this.file.disabled?.includes(n)) this.current.add(n); this.syncChecks(); };
    this.el('pickerNone').onclick = () => { this.current.clear(); this.syncChecks(); };
    this.scroll.onscroll = () => {
      if (!this.frame) this.frame = requestAnimationFrame(() => { this.frame = 0; this.draw(); });
    };
    this.observer = new ResizeObserver(() => { if (this.dialog.open) this.layout(this.position()); });
    this.observer.observe(this.scroll);
  }

  get file() { return this.draft.files[this.fileIndex]; }
  get current() { return this.selection[this.fileIndex]; }

  open(draft, selection, catalog, templates, onApply) {
    if (this.dialog.open) return;
    this.draft = draft; this.selection = selection.map(s => new Set(s)); this.onApply = onApply;
    this.dialog.querySelector('.picker-templates').hidden = !!draft.job;
    this.el('pagePickerTitle').textContent = draft.job ? '다른 PC에 맡길 페이지 선택' : '검사할 페이지 선택';
    this.templates = new Set(templates);
    this.el('templateChoices').replaceChildren(...catalog.map(t => {
      const label = document.createElement('label'), check = document.createElement('input');
      check.type = 'checkbox'; check.value = t.name; check.checked = this.templates.has(t.name);
      check.onchange = () => { check.checked ? this.templates.add(t.name) : this.templates.delete(t.name); };
      label.append(check, ' ' + t.name); return label;
    }));
    if (!catalog.length) this.el('templateChoices').textContent = '등록된 양식이 없습니다. 양식 등록 후 다시 열어주세요.';
    this.fileIndex = 0; this.positions = new Map(); this.metrics = null;
    let size = '5';
    try { size = localStorage.getItem('pagePickerColumns') || size; } catch {}
    this.el('pickerSize').value = ['3', '5', '8'].includes(size) ? size : '5';
    this.el('pickerFile').replaceChildren(...draft.files.map((f, i) => new Option(`${f.name} · ${f.pages}페이지`, String(i))));
    this.previousOverflow = document.body.style.overflow; document.body.style.overflow = 'hidden';
    this.dialog.showModal(); this.layout({anchor: 0}); this.counts();
  }

  position() {
    if (!this.metrics) return {anchor: 0};
    return {anchor: Math.floor(this.scroll.scrollTop / this.metrics.row) * this.metrics.columns,
      bottom: this.scroll.scrollTop > 0 && this.scroll.scrollTop + this.scroll.clientHeight >= this.spacer.offsetHeight - 2};
  }

  layout(position) {
    const width = this.spacer.clientWidth;
    if (!width) return;
    const preferred = Number(this.el('pickerSize').value);
    const columns = Math.min(preferred, Math.max(1, Math.floor(width / 120)));
    const row = Math.round(((width - (columns - 1) * 12) / columns) * 1.32) + 44;
    this.metrics = {columns, row};
    this.spacer.style.height = Math.ceil(this.file.pages / columns) * row + 'px';
    this.grid.style.gridTemplateColumns = `repeat(${columns}, minmax(0, 1fr))`;
    this.grid.style.gridAutoRows = row - 12 + 'px';
    this.el('pickerDensity').textContent = columns < preferred ? `창 너비에 맞춰 ${columns}열로 표시` : '';
    this.scroll.scrollTop = position.bottom ? this.spacer.offsetHeight : Math.floor(position.anchor / columns) * row;
    this.draw();
  }

  draw() {
    if (!this.dialog.open || !this.metrics) return;
    const {columns, row} = this.metrics;
    const firstRow = Math.max(0, Math.floor(this.scroll.scrollTop / row) - 1);
    const lastRow = Math.ceil((this.scroll.scrollTop + this.scroll.clientHeight) / row) + 1;
    const first = firstRow * columns + 1, last = Math.min(this.file.pages, lastRow * columns);
    for (const [n, card] of this.cards) {
      if (n < first || n > last) { this.dispose(card); this.cards.delete(n); }
    }
    for (let n = first; n <= last; n++) {
      if (!this.cards.has(n)) this.cards.set(n, this.makeCard(n));
    }
    this.grid.style.transform = `translateY(${firstRow * row}px)`;
    // 같은 노드는 옮기지 않아 포커스와 디코딩된 이미지를 유지한다.
    const ordered = [...this.cards].sort((a, b) => a[0] - b[0]).map(([, c]) => c.node);
    ordered.forEach((node, i) => { if (this.grid.children[i] !== node) this.grid.insertBefore(node, this.grid.children[i] || null); });
    this.pump();
  }

  makeCard(n) {
    const node = document.createElement('div'); node.className = 'page-choice';
    const label = document.createElement('label'), check = document.createElement('input');
    check.type = 'checkbox'; check.checked = this.current.has(n);
    check.disabled = this.file.disabled?.includes(n) || false;
    check.onchange = () => { check.checked ? this.current.add(n) : this.current.delete(n); this.counts(); };
    label.append(check, ` ${n}페이지`);
    if (this.file.labels) label.title = this.file.labels[n - 1];
    const link = document.createElement('a'); link.target = '_blank'; link.rel = 'noopener';
    link.href = this.draft.job ? `/api/transfer/jobs/${encodeURIComponent(this.draft.job)}/input/${n - 1}` : `/api/intake/${this.draft.token}/files/${this.file.index}/pages/${n}`;
    link.title = `${n}페이지 크게 보기`;
    const placeholder = document.createElement('span'); placeholder.className = 'preview-placeholder'; placeholder.textContent = '미리보기 준비 중';
    link.append(placeholder); node.append(label, link);
    return {node, check, link, n, requested: false, objectUrl: null};
  }

  pump() {
    if (!this.dialog.open) return;
    for (const card of this.cards.values()) {
      if (this.requests.size >= 4) break;
      const key = card.link.href;
      if (card.requested || this.requests.has(key)) continue;
      card.requested = true;
      const controller = new AbortController(); this.requests.set(key, controller);
      fetch(key, {signal: controller.signal}).then(async response => {
        if (!response.ok) throw new Error('preview');
        const blob = await response.blob();
        if (!this.dialog.open || this.cards.get(card.n) !== card) return;
        const img = new Image(); img.alt = `${card.n}페이지 미리보기`;
        card.objectUrl = URL.createObjectURL(blob); img.src = card.objectUrl; card.link.replaceChildren(img);
        img.onerror = () => { card.link.textContent = '미리보기를 열어 확인'; };
      }).catch(error => {
        if (error.name !== 'AbortError' && this.cards.get(card.n) === card) card.link.textContent = '미리보기를 열어 확인';
      }).finally(() => { if (this.requests.get(key) === controller) this.requests.delete(key); this.pump(); });
    }
  }

  syncChecks() {
    for (const [n, card] of this.cards) card.check.checked = this.current.has(n);
    this.counts();
  }

  counts() {
    this.el('pickerFileCount').textContent = `현재 파일 ${this.file.pages}페이지 중 ${this.current.size}페이지 선택`;
    this.el('pickerTotal').textContent = `전체 ${this.draft.files.length}개 파일 · ${this.selection.reduce((s, pages) => s + pages.size, 0)}페이지 선택`;
  }

  dispose(card) { if (card.objectUrl) URL.revokeObjectURL(card.objectUrl); card.node.remove(); }
  clearCards() { for (const card of this.cards.values()) this.dispose(card); this.cards.clear(); }
  cleanup() {
    cancelAnimationFrame(this.frame); this.frame = 0;
    this.clearCards(); for (const controller of this.requests.values()) controller.abort();
    document.body.style.overflow = this.previousOverflow;
    document.querySelector('#pageSelection button')?.focus();
  }
}

const pagePicker = new PagePicker();

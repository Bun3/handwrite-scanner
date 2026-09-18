const reviewStateKey = 'review:' + new URLSearchParams(location.search).get('id');
let reviewReady = false, reviewTouched = false;

function saveReviewState() {
  if (!reviewReady) return;
  viewState.write(reviewStateKey, {
    field: filterValue(), page: pageFilter(), sort: sortKeys(),
    format: document.getElementById('expFmt').value,
    only: document.getElementById('expOnly').checked, scroll: window.scrollY
  });
}

function restoreReviewState() {
  if (reviewTouched) { reviewReady = true; saveReviewState(); return; }
  const saved = viewState.read(reviewStateKey, {});
  const select = (id, value) => {
    const el = document.getElementById(id);
    if ([...el.options].some(o => o.value === value)) el.value = value;
  };
  select('fieldFilter', saved.field); select('pageField', saved.page?.field);
  document.getElementById('pageValue').value = typeof saved.page?.value === 'string' ? saved.page.value : '';
  select('expFmt', saved.format);
  document.getElementById('expOnly').checked = saved.only === true;
  if (Array.isArray(saved.sort) && saved.sort.length) {
    document.getElementById('sortKeys').replaceChildren();
    for (const key of saved.sort) {
      if (![...document.getElementById('fieldFilter').options].some(o => o.value === key.fld)) continue;
      addSortKey();
      const row = document.getElementById('sortKeys').lastElementChild;
      row.querySelector('select').value = key.fld;
      const dir = row.querySelector('button');
      dir.dataset.asc = key.asc ? '1' : ''; dir.textContent = key.asc ? '↑' : '↓';
    }
    if (!document.getElementById('sortKeys').children.length) addSortKey();
  }
  const targetNumber = new URLSearchParams(location.search).get('page');
  const target = targetNumber !== null && /^\d+$/.test(targetNumber)
    ? document.querySelector(`.page[data-page="${Number(targetNumber)}"] h4`) : null;
  if (target) {
    document.getElementById('fieldFilter').value = '';
    document.getElementById('pageField').value = '';
    document.getElementById('pageValue').value = '';
  }
  applyFilter(); sortPages(); reviewReady = true;
  requestAnimationFrame(() => {
    if (target) { target.tabIndex = -1; target.focus({preventScroll: true}); target.scrollIntoView({block: 'start'}); }
    else if (Number.isFinite(saved.scroll)) window.scrollTo(0, saved.scroll);
  });
}

function reviewChanged() {
  if (!reviewReady) reviewTouched = true;
  saveReviewState();
}
document.querySelector('main').addEventListener('input', reviewChanged);
document.querySelector('main').addEventListener('change', reviewChanged);
document.getElementById('sortKeys').addEventListener('click', reviewChanged);
window.addEventListener('pagehide', saveReviewState);

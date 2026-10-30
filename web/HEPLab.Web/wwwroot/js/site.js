(() => {
  const dialog = document.querySelector('#search-dialog');
  const input = document.querySelector('#search-input');
  const results = document.querySelector('#search-results');
  const status = document.querySelector('#search-status');
  const themeControls = [...document.querySelectorAll('#theme-select, #mobile-theme-select')];
  let indexPromise;
  let searchSequence = 0;
  const loadIndex = () => indexPromise ||= fetch('/search-index.json').then(response => {
    if (!response.ok) throw new Error('Search index unavailable');
    return response.json();
  }).catch(error => { indexPromise = null; throw error; });
  const showSearch = () => { if (!dialog.open) dialog.showModal(); input.focus(); };
  document.querySelector('#search-open')?.addEventListener('click', showSearch);
  dialog?.querySelector('.search-close').addEventListener('click', () => dialog.close());
  dialog?.addEventListener('click', event => { if (event.target === dialog) { const bounds = dialog.getBoundingClientRect(); if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) dialog.close(); } });
  input?.addEventListener('input', async () => {
    const sequence = ++searchSequence;
    const query = input.value.trim().toLocaleLowerCase();
    results.replaceChildren();
    if (query.length < 2) { status.textContent = 'Type at least two characters to search the guide.'; return; }
    status.textContent = 'Searching…';
    try {
      const docs = await loadIndex();
      if (sequence !== searchSequence) return;
      const words = query.split(/\s+/);
      const matches = docs.map(doc => {
        const title = doc.title.toLocaleLowerCase();
        const text = `${doc.title} ${doc.description} ${doc.text}`.toLocaleLowerCase();
        return { doc, score: words.every(word => text.includes(word)) ? words.reduce((sum, word) => sum + (title.includes(word) ? 4 : 1), 0) : 0 };
      }).filter(item => item.score > 0).sort((a, b) => b.score - a.score).slice(0, 12);
      status.textContent = matches.length ? `${matches.length} results for “${query}”` : 'No results. Try a model, workflow, or reference name.';
      for (const { doc } of matches) {
        const link = document.createElement('a');
        link.href = doc.url;
        const title = document.createElement('strong');
        title.textContent = doc.title;
        const detail = document.createElement('span');
        detail.textContent = doc.description;
        link.append(title, detail);
        results.append(link);
      }
    } catch { if (sequence === searchSequence) status.textContent = 'Search could not load. Please try again.'; }
  });
  dialog?.addEventListener('keydown', event => {
    if (!['ArrowDown', 'ArrowUp'].includes(event.key)) return;
    const links = [...results.querySelectorAll('a')];
    if (!links.length) return;
    event.preventDefault();
    const current = links.indexOf(document.activeElement);
    if (event.key === 'ArrowUp' && current <= 0) input.focus();
    else links[(current + (event.key === 'ArrowDown' ? 1 : -1) + links.length) % links.length].focus();
  });
  document.addEventListener('keydown', event => { if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); showSearch(); } });

  const applyTheme = value => {
    if (!['dark', 'light', 'auto'].includes(value)) value = 'dark';
    const resolved = value === 'auto' ? (matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark') : value;
    document.documentElement.dataset.theme = resolved;
    document.documentElement.dataset.bsTheme = resolved;
    themeControls.forEach(control => { control.value = value; });
    document.dispatchEvent(new CustomEvent('heplab:theme', { detail: resolved }));
  };
  let selectedTheme = 'dark';
  try { selectedTheme = localStorage.getItem('heplab-theme') || selectedTheme; } catch { /* Optional storage. */ }
  applyTheme(selectedTheme);
  themeControls.forEach(control => control.addEventListener('change', () => {
    selectedTheme = control.value;
    try { localStorage.setItem('heplab-theme', selectedTheme); } catch { /* Theme works without persistence. */ }
    applyTheme(selectedTheme);
  }));
  matchMedia('(prefers-color-scheme: light)').addEventListener('change', () => { if (selectedTheme === 'auto') applyTheme('auto'); });

  const drawer = document.querySelector('#site-sidebar');
  const drawerToggle = document.querySelector('#menu-toggle');
  drawer?.addEventListener('shown.bs.offcanvas', () => drawerToggle.setAttribute('aria-expanded', 'true'));
  drawer?.addEventListener('hidden.bs.offcanvas', () => drawerToggle.setAttribute('aria-expanded', 'false'));
  drawerToggle?.setAttribute('aria-expanded', 'false');
  matchMedia('(min-width: 992px)').addEventListener('change', event => { if (event.matches) bootstrap.Offcanvas.getInstance(drawer)?.hide(); });

  const announce = message => { document.querySelector('#site-status').textContent = message; };
  const copy = async (text, button, success) => {
    const original = button.textContent;
    try { await navigator.clipboard.writeText(text); button.textContent = success; announce(success); }
    catch { button.textContent = 'Copy unavailable'; announce('Clipboard access is unavailable. Select and copy the text manually.'); }
    setTimeout(() => { button.textContent = original; }, 2000);
  };
  document.querySelectorAll('pre > code').forEach(code => {
    const pre = code.parentElement;
    const language = [...code.classList].find(value => value.startsWith('language-'))?.slice(9) || 'code';
    const label = document.createElement('span'); label.className = 'code-language'; label.textContent = language;
    const button = document.createElement('button'); button.type = 'button'; button.className = 'copy-code'; button.textContent = 'Copy'; button.setAttribute('aria-label', `Copy ${language} code`);
    button.addEventListener('click', () => copy(code.textContent, button, 'Copied'));
    pre.append(label, button);
  });
  document.querySelector('[data-copy-page]')?.addEventListener('click', event => { const button = event.currentTarget; copy(location.href, button.querySelector('span'), 'Link copied'); });
  document.querySelectorAll('.markdown-body table').forEach(table => {
    const container = document.createElement('div'); container.className = 'table-container'; container.tabIndex = 0; container.setAttribute('role', 'region'); container.setAttribute('aria-label', 'Scrollable reference table');
    table.before(container); container.append(table);
  });
  const tocLinks = [...document.querySelectorAll('.toc nav a')];
  if (tocLinks.length && 'IntersectionObserver' in window) {
    const observer = new IntersectionObserver(entries => {
      const visible = entries.find(entry => entry.isIntersecting);
      if (!visible) return;
      tocLinks.forEach(link => { const active = link.hash === `#${visible.target.id}`; link.classList.toggle('active', active); if (active) link.setAttribute('aria-current', 'location'); else link.removeAttribute('aria-current'); });
    }, { rootMargin: '-15% 0px -65% 0px' });
    tocLinks.forEach(link => { const target = document.getElementById(decodeURIComponent(link.hash.slice(1))); if (target) observer.observe(target); });
  }
})();

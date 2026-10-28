/* Pin each window to one local workspace, including every API request and route. */
(() => {
  const query = new URLSearchParams(location.search);
  const workspace = query.get('workspace') === 'home' ? 'home' : 'work';
  window.tetherWorkspace = workspace;
  window.tetherWorkspaceURL = href => { const url=new URL(href,location.href);url.searchParams.set('workspace',workspace);return url.href; };
  const originalFetch = window.fetch.bind(window);
  window.fetch = (input, init = {}) => {
    const url = new URL(typeof input === 'string' ? input : input.url, location.href);
    if (url.origin === location.origin && /\/api(?:\/|$)/.test(url.pathname)) {
      const headers = new Headers(init.headers || (input instanceof Request ? input.headers : undefined));
      headers.set('X-Tether-Workspace', workspace);
      init = {...init, headers};
    }
    return originalFetch(input, init);
  };
  const decorate = href => {
    const url = new URL(href, location.href);
    if (/^https?:$/.test(url.protocol) && url.origin === location.origin) url.searchParams.set('workspace', workspace);
    return url.href;
  };
  document.addEventListener('click', event => {
    const link = event.target.closest?.('a[href]');
    if (link) link.href = decorate(link.href);
  }, true);
  document.addEventListener('DOMContentLoaded', () => {
    const header = document.querySelector('header');
    if (header) {
      if (!header.querySelector('[data-display-nav]')) {
        const tasks = [...header.querySelectorAll('a')].find(a => a.textContent.trim() === 'Tasks');
        const display = document.createElement('a'); display.textContent = 'Display'; display.dataset.displayNav = '';
        display.href = decorate('/display');
        if (/\/display(?:\.html)?$/.test(location.pathname)) display.className = 'active';
        tasks?.after(display);
      }
      const select = document.createElement('select');
      select.className = 'workspace-picker'; select.setAttribute('aria-label', 'Work or Home');
      for (const value of ['work', 'home']) { const option = new Option(value === 'work' ? 'Work' : 'Home', value); select.add(option); }
      select.value = workspace;
      select.addEventListener('change', () => {
        const mode = select.value;
        // Navigation, rather than replacing a live runtime, keeps queued jobs and drafts scoped.
        const shell = window.TETHER_CONFIG && window.top !== window ? window.top : window;
        const url = new URL(shell.location.href); url.searchParams.set('workspace', mode);
        url.hash = ''; url.searchParams.delete('discuss');
        if(shell.tetherSwitchWorkspace)shell.tetherSwitchWorkspace(mode);else shell.location.assign(url.href);
      });
      const spacer=header.querySelector('.grow');if(spacer)spacer.before(select);else header.append(select);
    }
    for (const frame of document.querySelectorAll('iframe[src]')) frame.src = decorate(frame.src);
    if (workspace === 'home') {
      const prompt = document.querySelector('#actionPrompt');
      if (prompt) prompt.placeholder = 'What should happen when this personal task is due?';
      const form = document.querySelector('#storageForm');
      if (form) { form.hidden = true; const note = document.createElement('p'); note.textContent = 'Home has its own local database beside Work. Database relocation is managed from Work.'; form.after(note); }
    }
  });
})();

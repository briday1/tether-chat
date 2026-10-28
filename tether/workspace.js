/* Pin each window to one local workspace, including every API request and route. */
(() => {
  // Installed application is always Work; the server independently enforces it.
  const workspace = 'work';
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
    }
    for (const frame of document.querySelectorAll('iframe[src]')) { const url=decorate(frame.src);if(url!==frame.src)frame.contentWindow.location.replace(url); }
  });
})();

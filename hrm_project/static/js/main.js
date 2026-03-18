/* ── Flash Message Auto-dismiss ─────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  const flashes = document.querySelectorAll('.flash');
  flashes.forEach(el => {
    // Auto-dismiss after 4 seconds
    setTimeout(() => dismissFlash(el), 4000);
    // Click to dismiss
    el.addEventListener('click', () => dismissFlash(el));
  });
});

function dismissFlash(el) {
  el.style.transition = 'all 0.3s ease';
  el.style.opacity = '0';
  el.style.transform = 'translateX(120%)';
  setTimeout(() => el.remove(), 300);
}

/* ── Delete Confirm Dialog ──────────────────────────── */
let pendingForm = null;

function confirmDelete(formId, name) {
  pendingForm = document.getElementById(formId);
  const overlay  = document.getElementById('confirmOverlay');
  const itemName = document.getElementById('confirmItemName');
  if (itemName) itemName.textContent = name || 'this item';
  overlay.classList.add('active');
}

function cancelDelete() {
  pendingForm = null;
  document.getElementById('confirmOverlay').classList.remove('active');
}

function proceedDelete() {
  if (pendingForm) {
    pendingForm.submit();
  }
  cancelDelete();
}

// Close on overlay click
document.addEventListener('DOMContentLoaded', () => {
  const overlay = document.getElementById('confirmOverlay');
  if (overlay) {
    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) cancelDelete();
    });
  }
});

// Keep browser URL fixed at "/" while preserving form targets for each page.
document.addEventListener('DOMContentLoaded', () => {
  const currentPath = window.location.pathname;
  const currentSearch = window.location.search;
  const currentUrl = `${currentPath}${currentSearch}`;

  if (currentPath === '/') {
    return;
  }

  document.querySelectorAll('form:not([action])').forEach((form) => {
    form.setAttribute('action', currentUrl);
  });

  window.history.replaceState(
    { ...(window.history.state || {}), maskedPath: currentPath },
    '',
    '/'
  );
});

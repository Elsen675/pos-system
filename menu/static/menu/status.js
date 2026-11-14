// Müştərinin sifariş statusu: 5 saniyədən bir yenilənir.
(function () {
  const page = document.getElementById('status-page');
  const statusEl = document.getElementById('order-status');
  const url = page.dataset.jsonUrl;
  const FINAL = ['served', 'cancelled'];

  async function poll() {
    try {
      const res = await fetch(url, { cache: 'no-store' });
      if (res.ok) {
        const data = await res.json();
        statusEl.textContent = data.status_display;
        statusEl.className = 'status--' + data.status;
        if (FINAL.includes(data.status)) return; // bitmiş sifarişi daha yoxlamırıq
      }
    } catch (e) { /* şəbəkə xətası: növbəti dəfə yenə cəhd edirik */ }
    setTimeout(poll, 5000);
  }
  setTimeout(poll, 5000);
})();

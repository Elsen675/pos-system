// Müştərinin sifariş statusu: 5 saniyədən bir yenilənir.
(function () {
  const page = document.getElementById('status-page');
  const statusEl = document.getElementById('order-status');
  const payEl = document.getElementById('pay-status');
  const url = page.dataset.jsonUrl;
  const FINAL = ['served', 'cancelled'];

  async function poll() {
    try {
      const res = await fetch(url, { cache: 'no-store' });
      if (res.ok) {
        const data = await res.json();
        statusEl.textContent = data.status_display;
        statusEl.className = 'status--' + data.status;
        payEl.textContent = data.pay_status_display;
        payEl.className = 'pay-status--' + data.pay_status;
        // Sifariş bitib VƏ ödəniş məsələsi bağlanıbsa daha yoxlamırıq.
        if (FINAL.includes(data.status) && (data.status === 'cancelled' || data.pay_status === 'paid')) return;
      }
    } catch (e) { /* şəbəkə xətası: növbəti dəfə yenə cəhd edirik */ }
    setTimeout(poll, 5000);
  }
  setTimeout(poll, 5000);
})();

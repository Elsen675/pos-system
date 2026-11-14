// Müştəri səbəti. Qiymətlər burada yalnız GÖSTƏRİŞ üçündür: server sifarişin
// məbləğini bazadakı qiymətlərdən özü hesablayır, buradan qiymət göndərilmir.
(function () {
  const ctx = JSON.parse(document.getElementById('order-context').textContent);
  const cart = new Map(); // id -> {qty, price}
  const cartBox = document.getElementById('cart');
  const totalEl = document.getElementById('cart-total');
  const errorEl = document.getElementById('cart-error');
  const submitBtn = document.getElementById('cart-submit');
  const noteEl = document.getElementById('cart-note');
  const MAX_QTY = 20;

  function render() {
    let total = 0;
    let count = 0;
    cart.forEach((line) => {
      total += line.qty * line.price;
      count += line.qty;
    });
    totalEl.textContent = total.toFixed(2);
    cartBox.hidden = count === 0;
  }

  function showError(msg) {
    errorEl.textContent = msg;
    errorEl.hidden = !msg;
  }

  document.querySelectorAll('.qty').forEach((box) => {
    const id = parseInt(box.dataset.id, 10);
    const price = parseFloat(box.dataset.price);
    const valEl = box.querySelector('.qty__val');
    box.addEventListener('click', (e) => {
      const btn = e.target.closest('.qty__btn');
      if (!btn) return;
      const current = cart.has(id) ? cart.get(id).qty : 0;
      const next = Math.max(0, Math.min(MAX_QTY, current + parseInt(btn.dataset.delta, 10)));
      if (next === 0) cart.delete(id);
      else cart.set(id, { qty: next, price: price });
      valEl.textContent = String(next);
      showError('');
      render();
    });
  });

  submitBtn.addEventListener('click', async () => {
    if (cart.size === 0) return;
    submitBtn.disabled = true;
    showError('');
    const items = [];
    cart.forEach((line, id) => items.push({ id: id, qty: line.qty }));
    try {
      const res = await fetch(ctx.orderUrl, {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCookie('csrftoken') || '',
        },
        body: JSON.stringify({ table: ctx.table, token: ctx.token, items: items, note: noteEl.value }),
      });
      const data = await res.json().catch(() => ({}));
      if (res.ok && data.status_url) {
        window.location.href = data.status_url;
        return;
      }
      showError(data.error || 'Sifariş göndərilmədi. Yenidən cəhd edin.');
    } catch (err) {
      showError('İnternet bağlantısı yoxdur. Sifariş üçün internet lazımdır.');
    }
    submitBtn.disabled = false;
  });

  render();
})();

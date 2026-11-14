// Restoran paneli: 5 saniyədən bir sifarişləri yükləyir, yeni sifarişdə səs çalır.
(function () {
  const FEED_URL = '/panel/orders/feed/';
  const statusUrl = (id) => '/panel/orders/' + encodeURIComponent(id) + '/status/';
  const statusChoices = JSON.parse(document.getElementById('status-choices').textContent);
  const ordersEl = document.getElementById('orders');
  const emptyEl = document.getElementById('orders-empty');
  const lastUpdateEl = document.getElementById('last-update');
  const connErrorEl = document.getElementById('conn-error');
  const template = document.getElementById('order-template');
  const soundBtn = document.getElementById('sound-toggle');

  let knownNewIds = null; // ilk yükləmədə səs çalmamaq üçün null
  let audioCtx = null;

  // Brauzerlər istifadəçi toxunmadan səs çalmağa icazə vermir,
  // ona görə işçi bir dəfə "Səsi aktiv et" düyməsini basmalıdır.
  soundBtn.addEventListener('click', () => {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) return;
    audioCtx = audioCtx || new Ctx();
    audioCtx.resume();
    beep();
    soundBtn.textContent = '🔔 Səs aktivdir';
  });

  function beep() {
    if (!audioCtx) return;
    const t = audioCtx.currentTime;
    [0, 0.25, 0.5].forEach((offset) => {
      const osc = audioCtx.createOscillator();
      const gain = audioCtx.createGain();
      osc.frequency.value = 880;
      gain.gain.setValueAtTime(0.3, t + offset);
      gain.gain.exponentialRampToValueAtTime(0.001, t + offset + 0.2);
      osc.connect(gain).connect(audioCtx.destination);
      osc.start(t + offset);
      osc.stop(t + offset + 0.2);
    });
  }

  async function changeStatus(id, status, button) {
    button.disabled = true;
    try {
      const res = await fetch(statusUrl(id), {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') || '' },
        body: JSON.stringify({ status: status }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        alert(data.error || 'Status dəyişmədi.');
      }
    } catch (e) {
      alert('Bağlantı xətası.');
    }
    load();
  }

  function renderOrder(order) {
    const node = template.content.firstElementChild.cloneNode(true);
    node.classList.add('order--' + order.status);
    node.querySelector('.order__table').textContent = 'Masa ' + order.table;
    node.querySelector('.order__time').textContent = order.created_at + ' · #' + order.short_id;
    node.querySelector('.order__status').textContent = order.status_display;

    const list = node.querySelector('.order__items');
    order.items.forEach((item) => list.appendChild(el('li', null, item.qty + ' × ' + item.name)));

    const noteEl = node.querySelector('.order__note');
    if (order.note) noteEl.textContent = 'Qeyd: ' + order.note;
    else noteEl.remove();

    node.querySelector('.order__total').textContent =
      'Cəmi: ' + order.total + ' ₼ · ' + order.pay_status_display;

    const actions = node.querySelector('.order__actions');
    statusChoices.forEach(([value, label]) => {
      if (value === order.status) return;
      const btn = el('button', 'btn btn--small btn--' + value, label);
      btn.type = 'button';
      btn.addEventListener('click', () => changeStatus(order.id, value, btn));
      actions.appendChild(btn);
    });
    return node;
  }

  async function load() {
    try {
      const res = await fetch(FEED_URL, { credentials: 'same-origin', cache: 'no-store' });
      if (res.status === 401 || res.status === 403 || res.redirected) {
        window.location.reload(); // sessiya bitib -> giriş səhifəsi
        return;
      }
      if (!res.ok) throw new Error('feed ' + res.status);
      const data = await res.json();

      const newIds = new Set(data.orders.filter((o) => o.status === 'new').map((o) => o.id));
      if (knownNewIds !== null) {
        for (const id of newIds) {
          if (!knownNewIds.has(id)) { beep(); break; }
        }
      }
      knownNewIds = newIds;

      ordersEl.replaceChildren(...data.orders.map(renderOrder));
      emptyEl.hidden = data.orders.length > 0;
      lastUpdateEl.textContent = data.server_time;
      connErrorEl.hidden = true;
    } catch (e) {
      connErrorEl.hidden = false;
    }
  }

  load();
  setInterval(load, 5000);
})();

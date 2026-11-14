// Restoran paneli: 5 saniyədən bir sifarişləri yükləyir, yeni sifarişdə səs çalır.
(function () {
  const FEED_URL = '/panel/orders/feed/';
  const statusUrl = (id) => '/panel/orders/' + encodeURIComponent(id) + '/status/';
  const config = JSON.parse(document.getElementById('panel-config').textContent);
  const statusChoices = config.statusChoices;
  const orderUrl = (id, action) => '/panel/orders/' + encodeURIComponent(id) + '/' + action + '/';
  const ordersEl = document.getElementById('orders');
  const emptyEl = document.getElementById('orders-empty');
  const lastUpdateEl = document.getElementById('last-update');
  const connErrorEl = document.getElementById('conn-error');
  const template = document.getElementById('order-template');
  const soundBtn = document.getElementById('sound-toggle');

  const callsEl = document.getElementById('calls');
  const baseTitle = document.title;

  let knownNewIds = null; // ilk yükləmədə səs çalmamaq üçün null
  let knownCallIds = null;
  let audioCtx = null;
  let wakeLock = null;

  // Brauzerlər istifadəçi toxunmadan səs çalmağa icazə vermir,
  // ona görə işçi bir dəfə "Səsi aktiv et" düyməsini basmalıdır.
  // Eyni düymə brauzer bildirişinə icazə istəyir və ekranın sönməsinin
  // qarşısını alır (piştaxtadakı planşet üçün).
  soundBtn.addEventListener('click', async () => {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (Ctx) {
      audioCtx = audioCtx || new Ctx();
      audioCtx.resume();
      beep();
    }
    if ('Notification' in window && Notification.permission === 'default') {
      try { await Notification.requestPermission(); } catch (e) { /* köhnə brauzer */ }
    }
    await keepScreenOn();
    soundBtn.textContent = '🔔 Səs aktivdir';
  });

  async function keepScreenOn() {
    if (!('wakeLock' in navigator)) return;
    try { wakeLock = await navigator.wakeLock.request('screen'); } catch (e) { wakeLock = null; }
  }
  // Tab gizlənəndə brauzer kilidi buraxır; geri qayıdanda yenidən alırıq.
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible' && audioCtx && !wakeLock) keepScreenOn();
    if (document.visibilityState === 'hidden') wakeLock = null;
  });

  // Tab arxa plandadırsa (işçi başqa tabdadır) sistem bildirişi göstəririk.
  // Bu, brauzer açıq olduqca işləyir; brauzer tam bağlıdırsa işləmir.
  function notify(title, body) {
    if (!('Notification' in window) || Notification.permission !== 'granted') return;
    if (document.visibilityState === 'visible') return;
    try { new Notification(title, { body: body, tag: title + body }); } catch (e) { /* mobil Chrome */ }
  }

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

  async function postAction(url, body, button, fallbackError) {
    button.disabled = true;
    try {
      const res = await fetch(url, {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') || '' },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        alert(data.error || fallbackError);
      }
    } catch (e) {
      alert('Bağlantı xətası.');
    }
    load();
  }

  function changeStatus(id, status, button) {
    postAction(statusUrl(id), { status: status }, button, 'Status dəyişmədi.');
  }

  function renderPayment(order, box) {
    if (order.pay_status === 'paid') {
      const parts = ['✔ Ödənilib'];
      if (order.paid_via_display) parts.push(order.paid_via_display);
      if (order.paid_at) parts.push(order.paid_at);
      if (order.paid_by) parts.push(order.paid_by);
      box.appendChild(el('span', 'paid-info', parts.join(' · ')));
      if (config.isManager && order.pay_method === 'table') {
        const undo = el('button', 'btn btn--small', 'Geri al');
        undo.type = 'button';
        undo.addEventListener('click', () => {
          if (confirm('Ödəniş qeydini geri almaq istəyirsiniz?')) {
            postAction(orderUrl(order.id, 'unpay'), {}, undo, 'Ödəniş geri alınmadı.');
          }
        });
        box.appendChild(undo);
      }
      return;
    }
    if (order.pay_method !== 'table' || order.status === 'cancelled') return;
    config.paidViaChoices.forEach(([value, label]) => {
      const btn = el('button', 'btn btn--small btn--pay', '💰 ' + label + ' ödənildi');
      btn.type = 'button';
      btn.addEventListener('click', () => {
        if (confirm('Masa ' + order.table + ': ' + order.total + ' ₼ — ' + label + ' ödənildi?')) {
          postAction(orderUrl(order.id, 'pay'), { via: value }, btn, 'Ödəniş qeyd edilmədi.');
        }
      });
      box.appendChild(btn);
    });
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

    renderPayment(order, node.querySelector('.order__pay'));
    if (order.pay_status === 'paid') node.classList.add('order--paid');

    const actions = node.querySelector('.order__actions');
    // Yalnız server icazə verən keçidlərin düymələri (yoxlama yenə serverdədir).
    statusChoices.forEach(([value, label]) => {
      if (!order.allowed_next.includes(value)) return;
      const btn = el('button', 'btn btn--small btn--' + value, label);
      btn.type = 'button';
      btn.addEventListener('click', () => changeStatus(order.id, value, btn));
      actions.appendChild(btn);
    });
    return node;
  }

  function renderCall(call) {
    const node = el('div', 'call call--' + call.kind);
    let text = 'Masa ' + call.table + ' — ' + call.kind_display;
    if (call.pay_hint_display) text += ' (' + call.pay_hint_display + ')';
    node.appendChild(el('strong', null, text));
    node.appendChild(el('span', 'call__time', call.created_at));
    const btn = el('button', 'btn btn--small btn--pay', '✓ Həll edildi');
    btn.type = 'button';
    btn.addEventListener('click', () => {
      postAction('/panel/calls/' + encodeURIComponent(call.id) + '/resolve/', {}, btn, 'Alınmadı.');
    });
    node.appendChild(btn);
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

      const newOrders = data.orders.filter((o) => o.status === 'new');
      const newIds = new Set(newOrders.map((o) => o.id));
      const callIds = new Set(data.calls.map((c) => c.id));
      let alerted = false;
      if (knownNewIds !== null) {
        const fresh = newOrders.filter((o) => !knownNewIds.has(o.id));
        if (fresh.length) {
          alerted = true;
          notify('Yeni sifariş', fresh.map((o) => 'Masa ' + o.table).join(', '));
        }
      }
      if (knownCallIds !== null) {
        const freshCalls = data.calls.filter((c) => !knownCallIds.has(c.id));
        if (freshCalls.length) {
          alerted = true;
          freshCalls.forEach((c) => notify('Masa ' + c.table, c.kind_display));
        }
      }
      if (alerted) beep();
      knownNewIds = newIds;
      knownCallIds = callIds;

      callsEl.replaceChildren(...data.calls.map(renderCall));
      callsEl.hidden = data.calls.length === 0;
      document.title = (data.calls.length || newOrders.length ? '(' + (data.calls.length + newOrders.length) + ') ' : '') + baseTitle;

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

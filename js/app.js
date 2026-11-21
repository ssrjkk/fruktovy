/* Логика витрины «Фруктовый дворец». Данных здесь нет — каталог лежит в js/data.js,
   палитра до первой отрисовки ставится в js/app-head.js.

   Деньги намеренно отсутствуют: цену на завоз дня называет продавец, поэтому в пакет,
   в текст заявки и в разметку не попадает ни одна сумма. Заявка уходит одним сообщением
   в Telegram; своего бэкенда у сайта нет, а значит и хранить нечего — всё живёт
   в localStorage под ключами KEYS.

   Тесты пакета (tools/test_cart.py) вырезают тело этой IIFE и гоняют его в quickjs,
   поэтому форма «() => { … })();» здесь обязательна. */

(() => {
  'use strict';

  function readJSON(key, fallback) {
    try {
      const raw = localStorage.getItem(key);
      return raw ? JSON.parse(raw) : fallback;
    } catch (err) {
      return fallback;
    }
  }

  function writeJSON(key, val) {
    try {
      localStorage.setItem(key, JSON.stringify(val));
    } catch (err) {}
  }
  const byId = id => PRODUCTS.find(p => p.id === id);
  const inSeason = (p, m = CURRENT_MONTH) => p.season.includes(m);
  const formatKg = kg => `~${kg.toFixed(1).replace('.', ',')} кг`;
  const formatRub = n => `${Math.round(n).toLocaleString('ru-RU')} ₽`;
  const state = {
    theme: document.documentElement.dataset.theme || 'market',
    cardMode: document.documentElement.dataset.cards || '3d',
    cat: 'all',
    search: '',
    sort: 'default',
    seasonOnly: false,
    viewMode: 'aisles',
    cart: readJSON(KEYS.cart, {}),
    lastOrder: readJSON(KEYS.last, null),
    orders: readJSON(KEYS.orders, []),
    favs: new Set(readJSON(KEYS.favs, [])),
    recent: readJSON(KEYS.recent, []),
    delivery: 'pickup',
    promoCode: null,
    wishes: new Set(),
    selectedMonth: CURRENT_MONTH,
    guideTab: 'fruits',
    cratePreset: 'week',
    crateSize: 5,
    crateSeed: 0,
    crateItems: [],
    peekId: null,
    peekQty: 1,
    peekPhotoIdx: 0,
    lbIndex: 0
  };

  function showToast(text, undoFn) {
    const host = document.getElementById('toastHost');
    const el = document.createElement('div');
    el.className = 'toast';
    el.innerHTML = `<span>${text}</span>${undoFn ? '<button type="button" class="toast-undo">Отменить</button>' : ''}`;
    host.appendChild(el);
    if (undoFn) {
      el.querySelector('.toast-undo').addEventListener('click', () => {
        undoFn();
        el.remove();
      });
    }
    setTimeout(() => el.remove(), 3400);
  }

  function applyTheme(name, announce = false) {
    if (!THEME_LABELS[name]) return;
    state.theme = name;
    document.documentElement.dataset.theme = name;
    try {
      localStorage.setItem(KEYS.theme, name);
    } catch (err) {}
    document.querySelectorAll('[data-set-theme]').forEach(btn => {
      btn.setAttribute('aria-pressed', String(btn.dataset.setTheme === name));
    });
    if (announce) showToast(`Палитра: «${THEME_LABELS[name]}»`);
  }

  function applyCardMode(mode, announce = false) {
    if (mode !== '2d' && mode !== '3d') return;
    state.cardMode = mode;
    document.documentElement.dataset.cards = mode;
    try {
      localStorage.setItem(KEYS.cardMode, mode);
    } catch (err) {}
    document.querySelectorAll('[data-card-mode]').forEach(btn => {
      btn.setAttribute('aria-pressed', String(btn.dataset.cardMode === mode));
    });
    if (mode === '2d') {
      document.querySelectorAll('.product-card.is-tilting').forEach(c => {
        c.classList.remove('is-tilting');
        c.style.removeProperty('--rx');
        c.style.removeProperty('--ry');
        c.style.willChange = 'auto';
      });
    }
    if (announce) showToast(mode === '3d' ? 'Включены объёмные 3D-карточки' : 'Включены лёгкие 2D-карточки');
  }

  function updateStatus() {
    try {
      const now = new Date();
      const mskHour = Number(new Intl.DateTimeFormat('ru-RU', {
        timeZone: 'Europe/Moscow',
        hour: 'numeric',
        hour12: false
      }).format(now));
      const isOpen = mskHour >= 8 && mskHour < 21;
      const dot = document.getElementById('statusDot');
      const txt = document.getElementById('statusText');
      if (dot) dot.classList.toggle('is-closed', !isOpen);
      if (txt) txt.textContent = isOpen ? 'Открыто сегодня до 21:00 · Сытнинская, 12' : 'Откроемся завтра в 08:00 · Заявка в Telegram круглосуточно';
    } catch (err) {}
  }

  function cartStats() {
    const entries = Object.entries(state.cart).filter(([id, q]) => q > 0 && byId(id));
    let kg = 0;
    entries.forEach(([id, q]) => {
      const p = byId(id);
      if (p) kg += (p.weightKg || 0.2) * q;
    });
    const promo = state.promoCode ? PROMOS[state.promoCode] : null;
    return {
      entries,
      count: entries.length,
      kg,
      promo
    };
  }

  function flyToBag(sourceEl) {
    if (!sourceEl || (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches)) return;
    const bag = document.getElementById('openCartBtn');
    if (!bag) return;
    const a = sourceEl.getBoundingClientRect();
    const b = bag.getBoundingClientRect();
    const dot = document.createElement('div');
    dot.className = 'fly-dot';
    dot.style.left = `${a.left + a.width / 2 - 11}px`;
    dot.style.top = `${a.top + a.height / 2 - 11}px`;
    document.body.appendChild(dot);
    requestAnimationFrame(() => {
      dot.style.transform = `translate(${b.left + b.width / 2 - a.left - a.width / 2}px, ${b.top + b.height / 2 - a.top - a.height / 2}px) scale(0.45)`;
      dot.style.opacity = '0.2';
    });
    setTimeout(() => dot.remove(), 540);
  }

  function renderCardActionHTML(id) {
    const p = byId(id);
    const qty = state.cart[id] || 0;
    if (qty > 0) {
      return `
            <div class="qty-stepper">
              <button type="button" data-dec="${id}" aria-label="Уменьшить количество">−</button>
              <span class="tnum">${qty} ${p ? p.unit : ''}</span>
              <button type="button" data-inc="${id}" aria-label="Увеличить количество">+</button>
            </div>
          `;
    }
    return `<button type="button" class="card-add-btn" data-add="${id}">+ В пакет</button>`;
  }

  function syncBagBadges() {
    const {
      count,
      kg
    } = cartStats();
    document.getElementById('hdrBagCount').textContent = String(count);
    document.getElementById('hdrBagWeight').textContent = count > 0 ? formatKg(kg) : '';
    const ordEl = document.getElementById('hdrOrdersCount');
    if (ordEl) ordEl.textContent = `(${state.orders.length})`;
  }

  function setCartQty(id, nextQty, sourceEl) {
    const prev = state.cart[id] || 0;
    const clamped = Math.max(0, Math.min(30, nextQty));
    if (clamped === 0) delete state.cart[id];
    else state.cart[id] = clamped;
    writeJSON(KEYS.cart, state.cart);
    syncBagBadges();
    document.querySelectorAll(`[data-action-slot="${id}"]`).forEach(slot => {
      slot.innerHTML = renderCardActionHTML(id);
    });
    if (clamped > prev && sourceEl) flyToBag(sourceEl);
    if (document.getElementById('cartDialog').open) renderCartDrawer();
  }

  function hydrateCartFromHash() {
    const m = location.hash.match(/^#cart=([a-z0-9:,-]+)$/i);
    if (!m) return;
    const pairs = m[1].split(',');
    let loaded = 0;
    pairs.forEach(pair => {
      const [id, q] = pair.split(':');
      const qty = Number(q);
      if (byId(id) && qty > 0 && qty <= 30) {
        state.cart[id] = qty;
        loaded++;
      }
    });
    if (loaded > 0) {
      writeJSON(KEYS.cart, state.cart);
      showToast(`Загружен пакет по ссылке (${loaded} поз.)`);
    }
  }

  function copyCartShareLink() {
    const {
      entries
    } = cartStats();
    if (!entries.length) {
      showToast('Сначала добавьте товары в пакет');
      return;
    }
    const hash = '#cart=' + entries.map(([id, q]) => `${id}:${q}`).join(',');
    const url = `${location.origin}${location.pathname}${hash}`;
    try {
      const ta = document.createElement('textarea');
      ta.value = url;
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      ta.remove();
      showToast('Ссылка на пакет скопирована');
    } catch (err) {
      showToast('Не удалось скопировать ссылку');
    }
  }

  function renderChalkHits() {
    document.getElementById('chalkHits').innerHTML = DAILY_HITS.map(id => {
      const p = byId(id);
      if (!p) return '';
      return `
            <article class="chalk-hit">
              <div class="chalk-hit-top">
                <img src="${photoSrc(p.photo, 200, 200)}" alt="${p.name}" width="64" height="64" loading="lazy" decoding="async" data-fb-color="${p.color}" data-fb-label="${p.name}">
                <div>
                  <h3>${p.name}</h3>
                  <p>${p.tag} · цена по запросу</p>
                </div>
              </div>
              <button type="button" class="chalk-hit-btn" data-add="${p.id}">+ В пакет</button>
            </article>
          `;
    }).join('');
  }

  function renderCategoryTabs() {
    const favCount = state.favs.size;
    const tabs = [{
      id: 'all',
      label: 'Весь прилавок',
      count: PRODUCTS.length
    }, ...AISLES.map(a => ({
      id: a.id,
      label: a.label,
      count: PRODUCTS.filter(p => p.cat === a.id).length
    })), {
      id: 'favs',
      label: 'Избранное',
      count: favCount
    }];
    document.getElementById('catTabs').innerHTML = tabs.map(t => `
          <button type="button" class="cat-tab" data-cat="${t.id}" aria-pressed="${state.cat === t.id}">
            <span>${t.label}</span>
            <span class="cat-tab-count">${t.count}</span>
          </button>
        `).join('');
  }

  function renderRecent() {
    const bar = document.getElementById('recentBar');
    const items = state.recent.map(byId).filter(Boolean);
    if (!items.length) {
      bar.classList.remove('is-visible');
      bar.innerHTML = '';
      return;
    }
    bar.classList.add('is-visible');
    bar.innerHTML = `<span style="font-weight:700;color:var(--ink-muted);">Недавно смотрели:</span>` +
      items.map(p => `<button type="button" class="wish-chip" data-peek="${p.id}">${p.name}</button>`).join('');
  }

  function renderProductCard(p) {
    const seasonal = inSeason(p);
    const fav = state.favs.has(p.id);
    return `
          <article class="product-card" data-tilt-card>
            <div class="card-sheen" aria-hidden="true"></div>
            <div class="card-media">
              <div class="card-media-clip">
                <img src="${photoSrc(p.photo, 640, 480)}" alt="${p.name}" width="640" height="480" loading="lazy" decoding="async" data-fb-color="${p.color}" data-fb-label="${p.name}">
              </div>
              <div class="card-badges">
                ${seasonal ? '<span class="badge badge-season">В сезоне</span>' : ''}
                <span class="badge badge-tag">${p.tag}</span>
              </div>
              <button type="button" class="fav-btn" data-fav="${p.id}" aria-pressed="${fav}" aria-label="${fav ? 'Убрать из избранного' : 'В избранное'}">
                <svg class="icon"><use href="#ic-heart"/></svg>
              </button>
              <button type="button" class="peek-trigger" data-peek="${p.id}">Подробнее</button>
            </div>
            <div class="card-body">
              <div>
                <h3 class="card-title" data-peek="${p.id}">${p.name}</h3>
                <div class="card-price-row">
                  <span class="unit-pill tnum">за ${p.unit}</span>
                  <span class="card-price-val is-ask">цена по запросу</span>
                </div>
              </div>
              <div class="card-action-slot" data-action-slot="${p.id}">
                ${renderCardActionHTML(p.id)}
              </div>
            </div>
          </article>
        `;
  }

  function renderCatalog() {
    const q = state.search.trim().toLowerCase();
    let list = PRODUCTS.filter(p => {
      if (state.cat === 'favs' && !state.favs.has(p.id)) return false;
      if (state.cat !== 'all' && state.cat !== 'favs' && p.cat !== state.cat) return false;
      if (state.seasonOnly && !inSeason(p)) return false;
      if (q && !(p.name.toLowerCase().includes(q) || p.tag.toLowerCase().includes(q) || p.note.toLowerCase().includes(q))) return false;
      return true;
    });
    if (state.sort === 'season') {
      list = [...list].sort((a, b) => Number(inSeason(b)) - Number(inSeason(a)));
    } else if (state.sort === 'az') {
      list = [...list].sort((a, b) => a.name.localeCompare(b.name, 'ru'));
    }
    document.getElementById('catalogCount').textContent = `Показано: ${list.length} из ${PRODUCTS.length}`;
    const mount = document.getElementById('catalogMount');
    if (!list.length) {
      mount.innerHTML = `
            <div style="text-align:center;padding:42px 20px;background:var(--surface);border:1.5px dashed var(--border-strong);border-radius:22px;">
              <p class="serif" style="font-size:28px;margin:0 0 8px;">На этом прилавке пока пусто</p>
              <p style="color:var(--ink-muted);margin:0 0 16px;">Попробуйте сбросить поиск или переключить фильтр сезонности.</p>
              <button type="button" id="resetFiltersBtn" class="btn btn-brand">Показать весь прилавок</button>
            </div>
          `;
      return;
    }
    if (state.viewMode === 'aisles' && state.cat === 'all' && !q && state.sort === 'default') {
      mount.innerHTML = AISLES.map(a => {
        const items = list.filter(p => p.cat === a.id);
        if (!items.length) return '';
        return `
              <div class="aisle-block">
                <div class="aisle-header">
                  <h3 class="aisle-title">${a.label}</h3>
                  <span class="aisle-sub">${a.sub} · ${items.length} поз.</span>
                </div>
                <div class="catalog-grid">${items.map(renderProductCard).join('')}</div>
              </div>
            `;
      }).join('');
    } else {
      mount.innerHTML = `<div class="catalog-grid">${list.map(renderProductCard).join('')}</div>`;
    }
  }
  const peekDialog = document.getElementById('peekDialog');
  const PEEK_ANGLES = [{
    label: 'Прилавок',
    transform: 'scale(1)',
    filter: 'none'
  }, {
    label: 'Крупный план',
    transform: 'scale(1.22)',
    filter: 'contrast(1.04) saturate(1.08)'
  }, {
    label: 'Тёплый свет',
    transform: 'scale(1.1) translateX(-3%)',
    filter: 'saturate(1.15) brightness(1.03)'
  }];

  function switchProductGalleryPhoto(index) {
    const idx = Math.max(0, Math.min(PEEK_ANGLES.length - 1, Number(index) || 0));
    state.peekPhotoIdx = idx;
    const angle = PEEK_ANGLES[idx];
    const img = document.getElementById('product-main-img');
    if (img) {
      img.style.transform = angle.transform;
      img.style.filter = angle.filter;
    }
    document.querySelectorAll('#peekThumbs .peek-thumb-btn').forEach((btn, i) => {
      btn.setAttribute('aria-pressed', String(i === idx));
    });
  }
  window.switchProductGalleryPhoto = switchProductGalleryPhoto;

  function openPeek(id) {
    const p = byId(id);
    if (!p) return;
    state.peekId = id;
    state.peekQty = Math.max(1, state.cart[id] || 1);
    state.recent = [id, ...state.recent.filter(x => x !== id)].slice(0, 6);
    writeJSON(KEYS.recent, state.recent);
    renderRecent();
    const row = AISLES.find(r => r.id === p.cat);
    const img = document.getElementById('product-main-img');
    delete img.dataset.fbApplied;
    img.src = photoSrc(p.photo, 900, 675);
    img.alt = p.name;
    img.onerror = () => window.__fdImgFallback(img, p.color, p.name);
    document.getElementById('peekThumbs').innerHTML = PEEK_ANGLES.map((a, i) => `
          <button type="button" class="peek-thumb-btn" data-peek-angle="${i}" aria-pressed="${i === 0}">
            <img src="${photoSrc(p.photo, 240, 180)}" alt="${p.name} — ${a.label}" style="transform:${a.transform};filter:${a.filter};" data-fb-color="${p.color}" data-fb-label="${p.name}">
            <span class="peek-thumb-lbl">${a.label}</span>
          </button>
        `).join('');
    switchProductGalleryPhoto(0);
    document.getElementById('peekBadges').innerHTML = `
          ${inSeason(p) ? '<span class="badge badge-season">В сезоне сейчас</span>' : ''}
          <span class="badge badge-tag">${p.tag}</span>
        `;
    document.getElementById('peekRow').textContent = row ? row.label : '';
    document.getElementById('peekTitle').textContent = p.name;
    document.getElementById('peekUnit').textContent = `за ${p.unit} — цена по запросу`;
    document.getElementById('peekNote').textContent = p.note;
    document.getElementById('peekQty').textContent = String(state.peekQty);
    document.getElementById('peekSeasonBar').innerHTML = MONTHS.map(m => {
      const peak = p.season.includes(m.num);
      const now = m.num === CURRENT_MONTH;
      return `<span class="s-month-cell ${peak ? 'is-peak' : ''} ${now ? 'is-now' : ''}" title="${m.short}">${m.short[0]}</span>`;
    }).join('');
    const pairIds = (p.together || []).map(byId).filter(Boolean);
    document.getElementById('peekTogether').innerHTML = pairIds.map(t => `
          <button type="button" class="wish-chip" data-peek="${t.id}">${t.name}</button>
        `).join('');
    if (!peekDialog.open) peekDialog.showModal();
  }
  const CRATE_PRESETS = {
    week: {
      title: 'К чаю и семье',
      ids: ['apple', 'banana', 'mandarin', 'apricot', 'walnut', 'pear', 'dates', 'herbs']
    },
    gift: {
      title: 'На стол гостям',
      ids: ['grape', 'tomato', 'cucumber', 'mandarin', 'churchkhela', 'walnut', 'sweets', 'pear']
    },
    tea: {
      title: 'Витаминный запас',
      ids: ['orange', 'mandarin', 'lemon', 'apple', 'almond', 'apricot', 'herbs', 'carrot']
    },
    salad: {
      title: 'В подарок с лентой',
      ids: ['mandarin', 'dates', 'churchkhela', 'walnut', 'sweets', 'grape', 'apricot', 'hazelnut']
    }
  };

  function buildCrate() {
    const onlySeason = document.getElementById('chkCrateSeason').checked;
    const preset = CRATE_PRESETS[state.cratePreset] || CRATE_PRESETS.week;
    let pool = preset.ids.map(byId).filter(Boolean);
    if (onlySeason) pool = pool.filter(p => inSeason(p));
    if (pool.length < state.crateSize) {
      const extra = PRODUCTS.filter(p => !pool.includes(p) && (!onlySeason || inSeason(p)));
      pool = [...pool, ...extra];
    }
    if (pool.length < state.crateSize) pool = [...PRODUCTS];
    const shift = (state.crateSeed * 2) % Math.max(1, pool.length);
    const rotated = [...pool.slice(shift), ...pool.slice(0, shift)];
    state.crateItems = rotated.slice(0, state.crateSize).map(p => ({
      p,
      qty: p.unit === '100 г' ? 2 : 1
    }));
    const estKg = state.crateItems.reduce((s, x) => s + (x.p.weightKg || 0.1) * x.qty, 0);
    document.getElementById('builderTitle').textContent = preset.title;
    document.getElementById('builderMeta').textContent = `${state.crateItems.length} поз. · ${formatKg(estKg)}`;
    const tokensEl = document.getElementById('crateTokens');
    if (tokensEl) {
      tokensEl.innerHTML = state.crateItems.map(({
        p
      }, idx) => {
        const tz = 8 + (idx % 3) * 8;
        const rot = ((idx % 2 === 0 ? -1 : 1) * (4 + (idx % 3) * 3));
        return `
              <button type="button" class="crate-token" data-peek="${p.id}" title="${p.name}" style="--tz:${tz}px;--rot:${rot}deg;">
                <img src="${photoSrc(p.photo, 140, 140)}" alt="${p.name}" width="50" height="50" loading="lazy" decoding="async" data-fb-color="${p.color}" data-fb-label="${p.name}">
              </button>
            `;
      }).join('');
    }
    document.getElementById('builderList').innerHTML = state.crateItems.map(({
      p,
      qty
    }) => `
          <div class="builder-row">
            <div style="display:flex;align-items:center;gap:11px;min-width:0;">
              <img src="${photoSrc(p.photo, 140, 140)}" alt="" width="40" height="40" class="builder-row-thumb" loading="lazy" decoding="async" data-fb-color="${p.color}" data-fb-label="${p.name}">
              <div style="min-width:0;">
                <button type="button" data-peek="${p.id}" style="font-weight:800;font-size:14px;text-align:left;display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:100%;">${p.name}</button>
                <span style="font-size:12px;color:var(--ink-muted);">${p.tag}${inSeason(p) ? ' · в сезоне' : ''}</span>
              </div>
            </div>
            <span class="unit-pill tnum" style="flex-shrink:0;">${qty} × ${p.unit}</span>
          </div>
        `).join('');
  }
  const cartDialog = document.getElementById('cartDialog');
  const checkoutDialog = document.getElementById('checkoutDialog');
  const ordersDialog = document.getElementById('ordersDialog');

  function renderCartDrawer() {
    const {
      entries,
      count,
      kg,
      promo
    } = cartStats();
    document.getElementById('cartSub').textContent = count ? `${count} поз. · ${formatKg(kg)}` : 'Пока пусто';
    document.getElementById('meterKg').textContent = formatKg(kg);
    document.getElementById('meterFill').style.width = `${Math.min(100, Math.round((count / 6) * 100))}%`;
    document.getElementById('meterLabel').textContent = state.delivery === 'courier' ? `Курьер ${DELIVERY_ZONE} ${formatRub(COURIER_FEE)}, бесплатно от ${formatRub(FREE_DELIVERY_FROM)}` : 'Самовывоз со Сытнинской, 12 — бесплатно';
    document.getElementById('sumItems').textContent = String(count);
    document.getElementById('sumWeight').textContent = count ? formatKg(kg) : '—';
    const promoRow = document.getElementById('sumPromoRow');
    promoRow.style.display = promo ? 'flex' : 'none';
    document.getElementById('sumPromo').textContent = state.promoCode || '—';
    document.getElementById('sumGrand').textContent = count ? 'по запросу' : '—';
    const body = document.getElementById('cartItems');
    if (!entries.length) {
      body.innerHTML = `
            <div style="text-align:center;padding:34px 12px;color:var(--ink-muted);">
              <p class="serif" style="font-size:26px;color:var(--ink);margin:0 0 8px;">Пакет пока пуст</p>
              <p style="margin:0 0 16px;font-size:14px;">Добавляйте плоды прямо с прилавка или повторите прошлый заказ.</p>
              ${state.lastOrder ? '<button type="button" id="repeatLastBtn" class="btn btn-brand">Повторить прошлый заказ</button>' : ''}
            </div>
          `;
      return;
    }
    body.innerHTML = entries.map(([id, qty]) => {
      const p = byId(id);
      if (!p) return '';
      return `
            <div class="cart-item">
              <img src="${photoSrc(p.photo, 140, 140)}" alt="${p.name}" width="52" height="52" data-fb-color="${p.color}" data-fb-label="${p.name}">
              <div style="flex:1;min-width:0;">
                <div style="font-weight:800;font-size:14.5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${p.name}</div>
                <div style="font-size:12px;color:var(--ink-muted);">${p.tag} · цена по запросу</div>
              </div>
              <div class="qty-stepper" style="width:116px;height:36px;flex-shrink:0;">
                <button type="button" data-dec="${p.id}" style="height:36px;">−</button>
                <span class="tnum">${qty}</span>
                <button type="button" data-inc="${p.id}" style="height:36px;">+</button>
              </div>
            </div>
          `;
    }).join('');
  }

  function buildOrderText(ref, contact) {
    const {
      entries,
      count,
      kg
    } = cartStats();
    const lines = entries.map(([id, q], i) => {
      const p = byId(id);
      return `${i + 1}. ${p ? p.name : id} — ${q} ${p ? p.unit : ''}`;
    });
    const wishes = [...state.wishes].join(', ');
    const note = document.getElementById('cartNote').value.trim();
    return [ref ? `Заявка ${ref} с сайта «Фруктовый дворец»:` : 'Здравствуйте! Заявка с сайта «Фруктовый дворец»:', '', ...lines, '', `Позиций: ${count}, примерно ${formatKg(kg)}. Пришлите, пожалуйста, цены сегодняшнего завоза и итог.`, state.delivery === 'courier' ? `Курьером: ${contact ? contact.address : 'адрес уточню'} · время: ${contact ? contact.slot : 'любое'}` : 'Заберу сам: Сытнинская, 12', state.promoCode ? `Промокод: ${state.promoCode}` : '', wishes ? `Пожелания: ${wishes}` : '', note ? `Комментарий: ${note}` : '', contact ? `Отвечать на: ${contact.phone} (${contact.name})` : ''].filter(Boolean).join('\n');
  }

  function copyToClipboard(text) {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.cssText = 'position:fixed;top:0;left:0;opacity:0;';
    document.body.appendChild(ta);
    ta.select();
    let ok = false;
    try { ok = document.execCommand('copy'); } catch (err) { ok = false; }
    ta.remove();
    return ok;
  }

  function sendChatOrder() {
    const {
      entries
    } = cartStats();
    if (!entries.length) {
      showToast('Добавьте хотя бы одну позицию в пакет');
      return;
    }
    state.lastOrder = {
      ...state.cart
    };
    writeJSON(KEYS.last, state.lastOrder);
    const copied = copyToClipboard(buildOrderText());
    window.open(chatUrl(), '_blank', 'noopener,noreferrer');
    showToast(copied ? 'Список скопирован — вставьте его в чат Telegram' : 'Открываем Telegram: список пакета ниже в заявке');
  }

  function openCheckout() {
    const stats = cartStats();
    if (!stats.entries.length) {
      showToast('Сначала добавьте позиции в пакет');
      return;
    }
    if (cartDialog.open) cartDialog.close();
    document.getElementById('checkoutFormView').style.display = 'flex';
    document.getElementById('checkoutSuccessView').style.display = 'none';
    document.getElementById('chkAddressBlock').style.display = state.delivery === 'courier' ? 'grid' : 'none';
    document.getElementById('chkSummaryMeta').textContent = `Позиций: ${stats.count}`;
    document.getElementById('chkSummarySub').textContent = formatKg(stats.kg);
    document.getElementById('chkSummaryExtra').textContent = state.delivery === 'courier' ? `курьер ${DELIVERY_ZONE} — ${formatRub(COURIER_FEE)}, бесплатно от ${formatRub(FREE_DELIVERY_FROM)}` : 'самовывоз, бесплатно';
    document.getElementById('chkSummaryTotal').textContent = 'по запросу';
    if (!checkoutDialog.open) checkoutDialog.showModal();
  }

  function submitRequest() {
    const name = document.getElementById('chkName').value.trim();
    const phone = document.getElementById('chkPhone').value.trim();
    const address = document.getElementById('chkAddress').value.trim();
    if (!name || !phone) {
      showToast('Укажите имя и номер, куда ответить');
      return;
    }
    if (state.delivery === 'courier' && !address) {
      showToast('Укажите адрес доставки');
      return;
    }
    const stats = cartStats();
    const ref = 'З-' + (1000 + Math.floor(Math.random() * 8999));
    const contact = {
      name,
      phone,
      address,
      slot: document.getElementById('chkSlot').value
    };
    const orderText = buildOrderText(ref, contact);
    const items = stats.entries.map(([id, qty]) => {
      const p = byId(id);
      return {
        id,
        name: p ? p.name : id,
        qty,
        unit: p ? p.unit : ''
      };
    });
    state.orders.unshift({
      num: ref,
      date: new Date().toLocaleString('ru-RU', {
        day: '2-digit',
        month: '2-digit',
        hour: '2-digit',
        minute: '2-digit'
      }),
      status: 'Отправлена · ждём расчёт',
      delivery: state.delivery === 'courier' ? `Курьер: ${address} (${contact.slot})` : 'Самовывоз: Сытнинская, 12',
      promo: state.promoCode,
      items,
      rawCart: {
        ...state.cart
      }
    });
    state.orders = state.orders.slice(0, 15);
    writeJSON(KEYS.orders, state.orders);
    state.lastOrder = {
      ...state.cart
    };
    writeJSON(KEYS.last, state.lastOrder);
    copyToClipboard(orderText);
    window.open(chatUrl(), '_blank', 'noopener,noreferrer');
    document.getElementById('successChatLink').href = chatUrl();
    document.getElementById('successOrderNum').textContent = `Заявка ${ref} отправлена`;
    document.getElementById('successOrderMeta').textContent = `${contact.name}, отвечаем на ${contact.phone} — там же цены и итог этого завоза.`;
    document.getElementById('successReceipt').innerHTML = `
          <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;">
            <span class="order-status-badge">${state.delivery === 'courier' ? `Курьер ${DELIVERY_ZONE}` : 'Самовывоз'}</span>
            <strong class="tnum">${stats.count} поз. · ${formatKg(stats.kg)}</strong>
          </div>
          <div style="font-size:13px;color:var(--ink-muted);">${items.map(i => `${i.name}× ${i.qty}${i.unit}`).join(', ')}</div>
          ${state.promoCode ? `<div style="font-size:13px;color:var(--ink-muted);">Промокод в заявке:<strong>${state.promoCode}</strong></div>` : ''}
        `;
    state.cart = {};
    state.promoCode = null;
    writeJSON(KEYS.cart, state.cart);
    syncBagBadges();
    renderCatalog();
    document.getElementById('checkoutFormView').style.display = 'none';
    document.getElementById('checkoutSuccessView').style.display = 'flex';
    showToast(`Заявка ${ref} — открываем Telegram, список скопирован`);
  }

  function renderOrdersModal() {
    const list = document.getElementById('ordersList');
    if (!state.orders.length) {
      list.innerHTML = `
            <div style="text-align:center;padding:30px 12px;color:var(--ink-muted);">
              <p class="serif" style="font-size:26px;color:var(--ink);margin:0 0 8px;">Заявок пока нет</p>
              <p style="margin:0;font-size:14px;">Соберите пакет и отправьте заявку — здесь останется её копия, чтобы повторить тем же составом.</p>
            </div>
          `;
      return;
    }
    list.innerHTML = state.orders.map((o, idx) => {
      const kg = Object.entries(o.rawCart || {}).reduce((s, [id, q]) => {
        const p = byId(id);
        return s + ((p && p.weightKg) || 0.2) * q;
      }, 0);
      return `
          <article class="order-card">
            <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;">
              <strong>${o.num} · ${o.date}</strong>
              <span class="order-status-badge">${o.status}</span>
            </div>
            <div style="font-size:13px;color:var(--ink-muted);">${o.delivery}</div>
            <div style="font-size:13.5px;">${o.items.map(i => `${i.name}(${i.qty}${i.unit})`).join(', ')}</div>
            ${o.promo ? `<div style="font-size:13px;color:var(--ink-muted);">Промокод:<strong>${o.promo}</strong></div>` : ''}
            <div style="display:flex;justify-content:space-between;align-items:center;padding-top:6px;border-top:1px dashed var(--border);">
              <strong class="tnum" style="font-size:15px;">${o.items.length} поз. · ${formatKg(kg)}</strong>
              <button type="button" class="btn btn-outline" data-repeat-order="${idx}" style="height:34px;padding:0 12px;font-size:12.5px;">Повторить в пакет</button>
            </div>
          </article>`;
    }).join('');
  }
  const chatMessagesEl = document.getElementById('chatMessages');

  function appendChatMsg(text, who = 'bot', handoff = false) {
    const b = document.createElement('div');
    b.className = `chat-bubble is-${who}`;
    b.textContent = text;
    if (handoff) {
      const a = document.createElement('a');
      a.href = chatUrl();
      a.target = '_blank';
      a.rel = 'noopener noreferrer';
      a.style.cssText = 'display:inline-block;margin-top:6px;font-weight:800;text-decoration:underline;';
      a.textContent = 'Написать в Telegram →';
      b.appendChild(document.createElement('br'));
      b.appendChild(a);
    }
    chatMessagesEl.appendChild(b);
    chatMessagesEl.scrollTop = chatMessagesEl.scrollHeight;
  }

  function replyToChat(userText) {
    const q = userText.toLowerCase();
    let reply = 'Я автоматический: отвечаю по тому, что лежит на витрине. Точный ответ и фото сегодняшнего завоза — в Telegram.';
    let handoff = true;
    if (q.includes('сладк') || q.includes('вкусн') || q.includes('хит')) {
      reply = 'Сейчас на прилавке: тонкокорые мандарины с веточкой, мясистые бакинские томаты и мягкая чурчхела на гранатовом соке. Цену назовём при подтверждении — завоз утренний.';
      handoff = false;
    } else if (q.includes('промо') || q.includes('скидк')) {
      reply = 'Промокоды РЫНОК10 и ПРИВЕТ укажите прямо в заявке — продавец посчитает их вместе с ценами сегодняшнего завоза.';
      handoff = false;
    } else if (q.includes('доставк') || q.includes('самовывоз')) {
      reply = `Самовывоз со Сытнинской, 12 бесплатный. Курьер ${DELIVERY_ZONE} — ${formatRub(COURIER_FEE)}, а при заказе от ${formatRub(FREE_DELIVERY_FROM)} привезём бесплатно.`;
      handoff = false;
    } else if (q.includes('оплат') || q.includes('карт') || q.includes('сбп')) {
      reply = 'Онлайн-оплаты на сайте нет: цену и итог называем в подтверждении, платите при получении — в лавке или курьеру.';
      handoff = false;
    }
    setTimeout(() => appendChatMsg(reply, 'bot', handoff), 450);
  }

  function initStoreChat() {
    appendChatMsg('Здравствуйте! Это подсказки прилавка «Фруктовый дворец» на Сытнинской, 12. Отвечу про спелость, сорт, промокод и доставку — а цены этого завоза и живое фото пришлёт продавец в Telegram.', 'bot', true);
  }

  function init3DInteractions() {
    const reduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const coarse = window.matchMedia && window.matchMedia('(pointer: coarse)').matches;
    const mount = document.getElementById('catalogMount');
    if (mount && !reduced && !coarse) {
      let activeCard = null;
      let rafId = 0;
      let pendingX = 0;
      let pendingY = 0;
      const resetCard = card => {
        if (!card) return;
        card.classList.remove('is-tilting');
        card.style.setProperty('--rx', '0deg');
        card.style.setProperty('--ry', '0deg');
        card.style.willChange = 'auto';
      };
      mount.addEventListener('pointermove', e => {
        if (state.cardMode !== '3d') return;
        const card = e.target.closest('[data-tilt-card]');
        if (card !== activeCard) {
          resetCard(activeCard);
          activeCard = card;
          if (activeCard) {
            activeCard.style.willChange = 'transform';
            activeCard.classList.add('is-tilting');
          }
        }
        if (!activeCard) return;
        pendingX = e.clientX;
        pendingY = e.clientY;
        if (!rafId) {
          rafId = requestAnimationFrame(() => {
            rafId = 0;
            if (!activeCard || state.cardMode !== '3d') return;
            const rect = activeCard.getBoundingClientRect();
            if (!rect.width || !rect.height) return;
            const px = Math.max(0, Math.min(1, (pendingX - rect.left) / rect.width));
            const py = Math.max(0, Math.min(1, (pendingY - rect.top) / rect.height));
            const rx = ((0.5 - py) * 11).toFixed(2);
            const ry = ((px - 0.5) * 13).toFixed(2);
            activeCard.style.setProperty('--rx', `${rx}deg`);
            activeCard.style.setProperty('--ry', `${ry}deg`);
            activeCard.style.setProperty('--mx', `${(px * 100).toFixed(1)}%`);
            activeCard.style.setProperty('--my', `${(py * 100).toFixed(1)}%`);
          });
        }
      });
      mount.addEventListener('pointerleave', () => {
        if (rafId) {
          cancelAnimationFrame(rafId);
          rafId = 0;
        }
        resetCard(activeCard);
        activeCard = null;
      });
    }
    const stage = document.getElementById('crateStage');
    const crate = document.getElementById('isoCrate');
    if (stage && crate && !reduced) {
      let dragging = false;
      let crateRaf = 0;
      let targetRx = 18;
      let targetRy = -12;
      const applyCrate = () => {
        crateRaf = 0;
        crate.style.setProperty('--crx', `${targetRx.toFixed(1)}deg`);
        crate.style.setProperty('--cry', `${targetRy.toFixed(1)}deg`);
      };
      const updateFromPoint = (clientX, clientY) => {
        const rect = stage.getBoundingClientRect();
        const nx = Math.max(-1, Math.min(1, ((clientX - rect.left) / rect.width) * 2 - 1));
        const ny = Math.max(-1, Math.min(1, ((clientY - rect.top) / rect.height) * 2 - 1));
        targetRx = 18 - ny * 14;
        targetRy = nx * 24;
        if (!crateRaf) crateRaf = requestAnimationFrame(applyCrate);
      };
      stage.addEventListener('pointerdown', e => {
        dragging = true;
        stage.classList.add('is-dragging');
        updateFromPoint(e.clientX, e.clientY);
      });
      stage.addEventListener('pointermove', e => {
        if (!dragging && coarse) return;
        updateFromPoint(e.clientX, e.clientY);
      });
      const endCrate = () => {
        dragging = false;
        stage.classList.remove('is-dragging');
        targetRx = 18;
        targetRy = -12;
        if (!crateRaf) crateRaf = requestAnimationFrame(applyCrate);
      };
      stage.addEventListener('pointerup', endCrate);
      stage.addEventListener('pointerleave', endCrate);
      stage.addEventListener('pointercancel', endCrate);
    }
  }

  function renderSeasons() {
    document.getElementById('monthsRow').innerHTML = MONTHS.map(m => `
          <button type="button" class="month-btn" data-month="${m.num}" aria-pressed="${m.num === state.selectedMonth}">${m.short}</button>
        `).join('');
    const items = PRODUCTS.filter(p => inSeason(p, state.selectedMonth));
    document.getElementById('seasonChips').innerHTML = items.map(p => `
          <button type="button" class="season-chip" data-peek="${p.id}">
            <img src="${photoSrc(p.photo, 120, 120)}" alt="" width="30" height="30" loading="lazy" decoding="async" data-fb-color="${p.color}" data-fb-label="${p.name}">
            <span>${p.name}</span>
          </button>
        `).join('');
  }

  function renderGuide() {
    document.querySelectorAll('[data-guide]').forEach(b => {
      b.setAttribute('aria-pressed', String(b.dataset.guide === state.guideTab));
    });
    const list = GUIDE_DATA[state.guideTab] || GUIDE_DATA.fruits;
    document.getElementById('guideGrid').innerHTML = list.map(g => `
          <article class="guide-card">
            <h3>${g.title}</h3>
            <p>${g.text}</p>
          </article>
        `).join('');
  }

  function renderGallery() {
    document.getElementById('galleryGrid').innerHTML = GALLERY_ITEMS.map((g, i) => `
          <button type="button" class="gallery-tile" data-lb="${i}">
            <img src="${photoSrc(g.photo, 640, 480)}" alt="${g.caption}" width="640" height="480" loading="lazy" decoding="async" data-fb-color="${g.color}" data-fb-label="${g.caption}">
            <span class="gallery-cap">${g.caption}</span>
          </button>
        `).join('');
  }
  const lbDialog = document.getElementById('lbDialog');

  function openLightbox(idx) {
    state.lbIndex = (idx + GALLERY_ITEMS.length) % GALLERY_ITEMS.length;
    const item = GALLERY_ITEMS[state.lbIndex];
    const img = document.getElementById('lbImg');
    img.classList.remove('is-zoomed');
    delete img.dataset.fbApplied;
    img.src = photoSrc(item.photo, 1200, 900);
    img.alt = item.caption;
    img.onerror = () => window.__fdImgFallback(img, item.color, item.caption);
    document.getElementById('lbCaption').textContent = item.caption;
    if (!lbDialog.open) lbDialog.showModal();
  }

  function bindEvents() {
    document.addEventListener('click', e => {
      const tBtn = e.target.closest('[data-set-theme]');
      if (tBtn) {
        applyTheme(tBtn.dataset.setTheme, true);
        return;
      }
      const cmBtn = e.target.closest('[data-card-mode]');
      if (cmBtn) {
        applyCardMode(cmBtn.dataset.cardMode, true);
        return;
      }
      const vBtn = e.target.closest('[data-view]');
      if (vBtn) {
        state.viewMode = vBtn.dataset.view;
        document.querySelectorAll('[data-view]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.view === state.viewMode)));
        renderCatalog();
        return;
      }
      const catBtn = e.target.closest('[data-cat]');
      if (catBtn) {
        state.cat = catBtn.dataset.cat;
        renderCategoryTabs();
        renderCatalog();
        return;
      }
      const addBtn = e.target.closest('[data-add]');
      if (addBtn) {
        setCartQty(addBtn.dataset.add, (state.cart[addBtn.dataset.add] || 0) + 1, addBtn);
        return;
      }
      const incBtn = e.target.closest('[data-inc]');
      if (incBtn) {
        setCartQty(incBtn.dataset.inc, (state.cart[incBtn.dataset.inc] || 0) + 1);
        return;
      }
      const decBtn = e.target.closest('[data-dec]');
      if (decBtn) {
        const id = decBtn.dataset.dec;
        const prev = state.cart[id] || 0;
        setCartQty(id, prev - 1);
        if (prev === 1) {
          const p = byId(id);
          showToast(`Убрали «${p ? p.name : id}»`, () => setCartQty(id, 1));
        }
        return;
      }
      const favBtn = e.target.closest('[data-fav]');
      if (favBtn) {
        const id = favBtn.dataset.fav;
        if (state.favs.has(id)) state.favs.delete(id);
        else state.favs.add(id);
        writeJSON(KEYS.favs, [...state.favs]);
        favBtn.setAttribute('aria-pressed', String(state.favs.has(id)));
        renderCategoryTabs();
        if (state.cat === 'favs') renderCatalog();
        return;
      }
      const peekBtn = e.target.closest('[data-peek]');
      if (peekBtn) {
        openPeek(peekBtn.dataset.peek);
        return;
      }
      const angleBtn = e.target.closest('[data-peek-angle]');
      if (angleBtn) {
        switchProductGalleryPhoto(Number(angleBtn.dataset.peekAngle));
        return;
      }
      const presetBtn = e.target.closest('[data-preset]');
      if (presetBtn) {
        state.cratePreset = presetBtn.dataset.preset;
        document.querySelectorAll('[data-preset]').forEach(b => b.classList.toggle('is-active', b.dataset.preset === state.cratePreset));
        buildCrate();
        return;
      }
      const sizeBtn = e.target.closest('[data-crate-size]');
      if (sizeBtn) {
        state.crateSize = Number(sizeBtn.dataset.crateSize);
        document.querySelectorAll('[data-crate-size]').forEach(b => b.setAttribute('aria-pressed', String(Number(b.dataset.crateSize) === state.crateSize)));
        buildCrate();
        return;
      }
      const monthBtn = e.target.closest('[data-month]');
      if (monthBtn) {
        state.selectedMonth = Number(monthBtn.dataset.month);
        renderSeasons();
        return;
      }
      const guideBtn = e.target.closest('[data-guide]');
      if (guideBtn) {
        state.guideTab = guideBtn.dataset.guide;
        renderGuide();
        return;
      }
      const lbBtn = e.target.closest('[data-lb]');
      if (lbBtn) {
        openLightbox(Number(lbBtn.dataset.lb));
        return;
      }
      const delBtn = e.target.closest('[data-delivery]');
      if (delBtn) {
        state.delivery = delBtn.dataset.delivery;
        document.querySelectorAll('[data-delivery]').forEach(b => b.classList.toggle('is-active', b.dataset.delivery === state.delivery));
        syncBagBadges();
        renderCartDrawer();
        return;
      }
      const repOrdBtn = e.target.closest('[data-repeat-order]');
      if (repOrdBtn) {
        const ord = state.orders[Number(repOrdBtn.dataset.repeatOrder)];
        if (ord && ord.rawCart) {
          state.cart = {
            ...ord.rawCart
          };
          writeJSON(KEYS.cart, state.cart);
          syncBagBadges();
          renderCatalog();
          ordersDialog.close();
          renderCartDrawer();
          cartDialog.showModal();
          showToast(`Заказ #${ord.num} добавлен в пакет`);
        }
        return;
      }
      const chatQBtn = e.target.closest('[data-chat-q]');
      if (chatQBtn) {
        const txt = chatQBtn.dataset.chatQ;
        appendChatMsg(txt, 'user');
        replyToChat(txt);
        return;
      }
      const wishBtn = e.target.closest('[data-wish]');
      if (wishBtn) {
        const w = wishBtn.dataset.wish;
        if (state.wishes.has(w)) state.wishes.delete(w);
        else state.wishes.add(w);
        wishBtn.classList.toggle('is-active', state.wishes.has(w));
        return;
      }
      if (e.target.closest('#resetFiltersBtn')) {
        state.cat = 'all';
        state.search = '';
        state.seasonOnly = false;
        state.sort = 'default';
        document.getElementById('searchInput').value = '';
        document.getElementById('clearSearchBtn').classList.remove('is-visible');
        document.getElementById('sortSelect').value = 'default';
        document.getElementById('seasonOnlyBtn').setAttribute('aria-pressed', 'false');
        renderCategoryTabs();
        renderCatalog();
        return;
      }
      if (e.target.closest('#repeatLastBtn') && state.lastOrder) {
        state.cart = {
          ...state.lastOrder
        };
        writeJSON(KEYS.cart, state.cart);
        syncBagBadges();
        renderCatalog();
        renderCartDrawer();
        showToast('Прошлый заказ снова в пакете');
        return;
      }
      if (e.target.closest('[data-close-menu]')) {
        document.getElementById('mobileMenu').classList.remove('is-open');
        document.getElementById('burgerBtn').setAttribute('aria-expanded', 'false');
      }
    });
    const searchInput = document.getElementById('searchInput');
    const clearSearchBtn = document.getElementById('clearSearchBtn');
    searchInput.addEventListener('input', () => {
      state.search = searchInput.value;
      clearSearchBtn.classList.toggle('is-visible', Boolean(state.search));
      renderCatalog();
    });
    clearSearchBtn.addEventListener('click', () => {
      searchInput.value = '';
      state.search = '';
      clearSearchBtn.classList.remove('is-visible');
      renderCatalog();
    });
    document.getElementById('sortSelect').addEventListener('change', e => {
      state.sort = e.target.value;
      renderCatalog();
    });
    document.getElementById('seasonOnlyBtn').addEventListener('click', e => {
      state.seasonOnly = !state.seasonOnly;
      e.currentTarget.setAttribute('aria-pressed', String(state.seasonOnly));
      renderCatalog();
    });
    document.getElementById('chkCrateSeason').addEventListener('change', buildCrate);
    document.getElementById('rerollBuilderBtn').addEventListener('click', () => {
      state.crateSeed++;
      buildCrate();
    });
    document.getElementById('addBuilderBtn').addEventListener('click', e => {
      state.crateItems.forEach(({
        p,
        qty
      }) => {
        state.cart[p.id] = (state.cart[p.id] || 0) + qty;
      });
      writeJSON(KEYS.cart, state.cart);
      syncBagBadges();
      renderCatalog();
      flyToBag(e.currentTarget);
      showToast(`Ящик добавлен в пакет (${state.crateItems.length} поз.)`);
    });
    document.getElementById('burgerBtn').addEventListener('click', e => {
      const open = document.getElementById('mobileMenu').classList.toggle('is-open');
      e.currentTarget.setAttribute('aria-expanded', String(open));
    });
    document.getElementById('closePeekBtn').addEventListener('click', () => peekDialog.close());
    peekDialog.addEventListener('click', e => {
      if (e.target === peekDialog) peekDialog.close();
    });
    document.getElementById('peekDecBtn').addEventListener('click', () => {
      state.peekQty = Math.max(1, state.peekQty - 1);
      document.getElementById('peekQty').textContent = String(state.peekQty);
    });
    document.getElementById('peekIncBtn').addEventListener('click', () => {
      state.peekQty = Math.min(30, state.peekQty + 1);
      document.getElementById('peekQty').textContent = String(state.peekQty);
    });
    document.getElementById('peekAddBtn').addEventListener('click', () => {
      if (!state.peekId) return;
      setCartQty(state.peekId, state.peekQty);
      const p = byId(state.peekId);
      peekDialog.close();
      showToast(`В пакете: ${p ? p.name : ''} × ${state.peekQty}`);
    });
    document.getElementById('openCartBtn').addEventListener('click', () => {
      renderCartDrawer();
      if (!cartDialog.open) cartDialog.showModal();
    });
    document.getElementById('closeCartBtn').addEventListener('click', () => cartDialog.close());
    cartDialog.addEventListener('click', e => {
      if (e.target === cartDialog) cartDialog.close();
    });
    document.getElementById('shareCartBtn').addEventListener('click', copyCartShareLink);
    document.getElementById('sendChatOrderBtn').addEventListener('click', sendChatOrder);
    document.getElementById('openCheckoutBtn').addEventListener('click', openCheckout);
    document.getElementById('clearCartBtn').addEventListener('click', () => {
      if (!Object.keys(state.cart).length) return;
      const prevCart = {
        ...state.cart
      };
      state.cart = {};
      state.promoCode = null;
      writeJSON(KEYS.cart, state.cart);
      syncBagBadges();
      renderCatalog();
      renderCartDrawer();
      showToast('Пакет очищен', () => {
        state.cart = prevCart;
        writeJSON(KEYS.cart, state.cart);
        syncBagBadges();
        renderCatalog();
        if (cartDialog.open) renderCartDrawer();
      });
    });
    document.getElementById('applyPromoBtn').addEventListener('click', () => {
      const code = document.getElementById('promoInput').value.trim().toUpperCase();
      if (PROMOS[code]) {
        state.promoCode = code;
        document.getElementById('promoInput').value = code;
        syncBagBadges();
        renderCartDrawer();
        showToast(PROMOS[code].label);
      } else {
        showToast('Промокод не найден. Попробуйте РЫНОК10 или ПРИВЕТ');
      }
    });
    document.getElementById('closeCheckoutBtn').addEventListener('click', () => checkoutDialog.close());
    document.getElementById('doneCheckoutBtn').addEventListener('click', () => checkoutDialog.close());
    checkoutDialog.addEventListener('click', e => {
      if (e.target === checkoutDialog) checkoutDialog.close();
    });
    document.getElementById('submitRequestBtn').addEventListener('click', submitRequest);
    const openOrders = () => {
      renderOrdersModal();
      if (!ordersDialog.open) ordersDialog.showModal();
    };
    document.getElementById('openOrdersBtn').addEventListener('click', openOrders);
    document.getElementById('mobileOrdersBtn').addEventListener('click', openOrders);
    document.getElementById('closeOrdersBtn').addEventListener('click', () => ordersDialog.close());
    ordersDialog.addEventListener('click', e => {
      if (e.target === ordersDialog) ordersDialog.close();
    });
    const chatWidget = document.getElementById('storeChatWidget');
    const toggleChatBtn = document.getElementById('toggleChatBtn');
    const setChatOpen = open => {
      chatWidget.classList.toggle('is-open', open);
      toggleChatBtn.setAttribute('aria-expanded', String(open));
    };
    toggleChatBtn.addEventListener('click', () => setChatOpen(!chatWidget.classList.contains('is-open')));
    document.getElementById('closeChatBtn').addEventListener('click', () => setChatOpen(false));
    document.getElementById('openChatFromVisit').addEventListener('click', () => setChatOpen(true));
    document.getElementById('chatForm').addEventListener('submit', e => {
      e.preventDefault();
      const input = document.getElementById('chatInput');
      const txt = input.value.trim();
      if (!txt) return;
      input.value = '';
      appendChatMsg(txt, 'user');
      replyToChat(txt);
    });
    document.getElementById('closeLbBtn').addEventListener('click', () => lbDialog.close());
    lbDialog.addEventListener('click', e => {
      if (e.target === lbDialog) lbDialog.close();
    });
    document.getElementById('lbPrevBtn').addEventListener('click', () => openLightbox(state.lbIndex - 1));
    document.getElementById('lbNextBtn').addEventListener('click', () => openLightbox(state.lbIndex + 1));
    document.getElementById('lbImg').addEventListener('click', e => e.currentTarget.classList.toggle('is-zoomed'));
    document.getElementById('loadMapBtn').addEventListener('click', () => {
      document.getElementById('mapBox').innerHTML = '<iframe title="Яндекс Карта — Сытнинская, 12" src="https://yandex.ru/map-widget/v1/?text=%D0%A1%D0%B0%D0%BD%D0%BA%D1%82-%D0%9F%D0%B5%D1%82%D0%B5%D1%80%D0%B1%D1%83%D1%80%D0%B3%2C%20%D0%A1%D1%8B%D1%82%D0%BD%D0%B8%D0%BD%D1%81%D0%BA%D0%B0%D1%8F%20%D1%83%D0%BB%D0%B8%D1%86%D0%B0%2C%2012&z=16" loading="lazy"></iframe>';
    });
    document.addEventListener('keydown', e => {
      if (e.key === '/' && document.activeElement.tagName !== 'INPUT' && document.activeElement.tagName !== 'TEXTAREA') {
        e.preventDefault();
        searchInput.focus();
      }
    });
  }

  function init() {
    applyTheme(state.theme, false);
    applyCardMode(state.cardMode, false);
    hydrateCartFromHash();
    updateStatus();
    setInterval(updateStatus, 60000);
    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.register('sw.js').catch(() => {});
    }
    syncBagBadges();
    renderChalkHits();
    renderCategoryTabs();
    renderRecent();
    renderCatalog();
    buildCrate();
    renderSeasons();
    renderGuide();
    renderGallery();
    initStoreChat();
    bindEvents();
    init3DInteractions();
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
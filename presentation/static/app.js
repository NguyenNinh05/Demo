/* SnapShop front-end (Presentation layer, browser side).
   Talks only to the WebSearchUI HTTP API: /api/search, /api/products, /api/samples ... */
(() => {
  "use strict";

  const CONFIG = JSON.parse(document.getElementById("site-config").textContent);
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const vnd = (v) => new Intl.NumberFormat("vi-VN").format(Math.round(v)) + "₫";
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const PAGE = 24;

  const ICON = {
    camera: '<svg viewBox="0 0 24 24"><path d="M4 8.5A2.5 2.5 0 0 1 6.5 6h1.2l1.3-2h6l1.3 2h1.2A2.5 2.5 0 0 1 20 8.5v9A2.5 2.5 0 0 1 17.5 20h-11A2.5 2.5 0 0 1 4 17.5z"/><circle cx="12" cy="12.5" r="3.6"/></svg>',
    mic: '<svg viewBox="0 0 24 24"><rect x="9" y="3" width="6" height="11.5" rx="3"/><path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21M8.5 21h7"/></svg>',
    bag: '<svg viewBox="0 0 24 24"><path d="M5 8h14l-1 12H6z"/><path d="M9 8V6.5a3 3 0 0 1 6 0V8"/></svg>',
    truck: '<svg viewBox="0 0 24 24"><path d="M3 6h11v10H3zM14 9.5h4l3 3.5v3h-7"/><circle cx="7" cy="17.5" r="1.8"/><circle cx="17.5" cy="17.5" r="1.8"/></svg>',
    check: '<svg viewBox="0 0 24 24"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>',
    sparkle: '<svg viewBox="0 0 24 24"><path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8zM19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8z"/></svg>',
    info: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 7.6v.2"/></svg>',
    alert: '<svg viewBox="0 0 24 24"><path d="M12 4l9 16H3z"/><path d="M12 10v4M12 17v.2"/></svg>',
    similar: '<svg viewBox="0 0 24 24"><rect x="3" y="3" width="8" height="10" rx="2"/><rect x="13" y="11" width="8" height="10" rx="2"/><path d="M15 3h4a2 2 0 0 1 2 2v3M3 16v3a2 2 0 0 0 2 2h3"/></svg>',
    stop: '<svg viewBox="0 0 24 24"><rect x="7" y="7" width="10" height="10" rx="2" fill="currentColor"/></svg>',
    ext: '<svg viewBox="0 0 24 24"><path d="M14 4h6v6M20 4l-9 9M18 14v5H5V6h5"/></svg>',
  };

  const COLOR_HEX = {
    "đen": "#1f1f1f", "trắng": "#f8f8f6", "be": "#d8c5a3", "xám": "#9c9c9a",
    "xanh dương": "#3d5f94", "xanh lá": "#55895c", "xanh rêu": "#6f6c3f", "xanh ngọc": "#3ea6a0",
    "đỏ": "#b5332f", "hồng": "#e6a4b4", "nâu": "#7b5236", "vàng": "#e1bf45", "cam": "#df7b3a",
    "tím": "#8c6cb3", "bạc": "#c2c2c2",
    "nhiều màu": "conic-gradient(#b5332f,#e1bf45,#55895c,#3d5f94,#8c6cb3,#b5332f)",
  };
  const KIND_DOT = {
    category: "#1c1b19", price: "#b0704a", color: null, gender: "#3f5f8a", material: "#8a7a5c",
    pattern: "#8a7a5c", feature: "#6d6a63", occasion: "#7c5aa6", sort: "#3f7d58",
    in_stock: "#3f7d58", order: "#1c1b19", unsupported: "#b34a3c", prefer: "#8a7a5c",
  };
  const MODE_LABEL = { text: "Chữ", voice: "Giọng nói", image: "Hình ảnh",
    multimodal: "Chữ + ảnh", similar: "Sản phẩm tương tự" };

  const state = {
    view: "home", browse: { category: null, gender: null, sort: "popular", page: 1, total: 0 },
    items: [], shown: PAGE, response: null, image: null, imageUrl: null, sample: null,
    cart: loadCart(), lastText: "",
  };

  // ============================================================ helpers
  function toast(msg, ms = 2600) {
    const t = $("#toast");
    t.textContent = msg;
    t.hidden = false;
    clearTimeout(toast.timer);
    toast.timer = setTimeout(() => (t.hidden = true), ms);
  }

  async function api(url, opts) {
    const res = await fetch(url, opts);
    let data = null;
    try { data = await res.json(); } catch (_) { /* not json */ }
    if (!res.ok) throw new Error((data && data.detail) || `Lỗi ${res.status}`);
    return data;
  }

  function loadCart() {
    try { return JSON.parse(localStorage.getItem("snapshop-cart") || "[]"); } catch (_) { return []; }
  }
  function saveCart() {
    try { localStorage.setItem("snapshop-cart", JSON.stringify(state.cart)); } catch (_) { /* private mode */ }
    const n = state.cart.reduce((s, i) => s + i.qty, 0);
    $("#cartCount").textContent = n;
    $("#cartCount").classList.toggle("on", n > 0);
  }

  function llmLabel(name) {
    return "AI";                                // the provider / model is not shown to customers
  }

  function swatch(color) {
    const bg = COLOR_HEX[color] || "#ccc";
    return `<span class="swatch"><i style="background:${bg}"></i>${esc(color || "")}</span>`;
  }

  function imgFade(root) {
    $$("img[data-fade]", root).forEach((img) => {
      if (img.complete) img.classList.add("loaded");
      else img.addEventListener("load", () => img.classList.add("loaded"), { once: true });
    });
  }

  function openLayer(el) {
    el.hidden = false;
    if (el.classList.contains("drawer")) $("#scrim").hidden = false;
    document.body.style.overflow = "hidden";
  }
  function closeLayers() {
    $$(".drawer, .modal").forEach((el) => (el.hidden = true));
    $("#scrim").hidden = true;
    document.body.style.overflow = "";
    if (voice.active) voice.cancel();
  }

  // ============================================================ init
  function init() {
    $("#cameraBtn").innerHTML = ICON.camera;
    $("#micBtn").innerHTML = ICON.mic;
    $("#ordersBtn").insertAdjacentHTML("afterbegin", ICON.truck);
    $("#cartBtn").insertAdjacentHTML("afterbegin", ICON.bag);
    saveCart();

    $("#examples").innerHTML = CONFIG.examples
      .map((e) => `<button type="button" class="chip" data-example="${esc(e)}">${esc(e)}</button>`).join("");
    $("#examples").addEventListener("click", (e) => {
      const b = e.target.closest("[data-example]");
      if (!b) return;
      $("#q").value = b.dataset.example;
      search();
    });
    rotatePlaceholder();
    bindEvents();
    loadHome();
  }

  function rotatePlaceholder() {
    const input = $("#q");
    const list = ["Tìm áo, quần…", ...CONFIG.examples.map((e) => `Thử: “${e}”`)];
    let i = 0;
    setInterval(() => {
      if (document.activeElement === input || input.value) return;
      i = (i + 1) % list.length;
      input.placeholder = list[i];
    }, 3200);
  }

  async function loadHome() {
    state.view = "home";
    $(".results__tools").hidden = false;
    document.body.className = "mode-home";
    $("#understood").hidden = true;
    $("#notices").innerHTML = "";
    $("#resultsTitle").textContent = "Bán chạy tuần này";
    $("#sortSelect").value = "popular";
    $$(".nav button").forEach((b) => b.classList.remove("active"));
    state.browse = { category: null, gender: null, sort: "popular", page: 1, total: 0 };
    loadBrowse(true);
    if (!$("#heroCollage").children.length) {
      try {
        const data = await api("/api/products?sort=popular&size=40");
        const picks = [];
        const seen = new Set();
        for (const p of data.products) {
          const group = p.category_id.split("_")[0] + (picks.length === 1 ? "x" : "");
          if (!seen.has(p.category_id) && !seen.has(group)) {
            picks.push(p); seen.add(p.category_id); seen.add(group);
          }
          if (picks.length === 3) break;
        }
        $("#heroCollage").innerHTML = picks.map((p) =>
          `<figure><img src="${p.image_url}" alt="${esc(p.name)}"></figure>`).join("");
      } catch (_) { /* decorative only */ }
      loadTiles();
    }
  }

  async function loadTiles() {
    const tiles = ["ao_phong", "ao_so_mi", "ao_khoac", "ao_len", "quan_jeans", "quan_short"];
    const names = Object.fromEntries(CONFIG.categories.map((c) => [c.category_id, c.name]));
    const results = await Promise.all(tiles.map((c) =>
      api(`/api/products?category=${c}&size=1&sort=popular`).catch(() => null)));
    $("#categoryTiles").innerHTML = tiles.map((c, i) => {
      const p = results[i] && results[i].products[0];
      return p ? `<button class="tile" data-tile="${c}"><img src="${p.image_url}" alt=""><span>${esc(names[c])}</span></button>` : "";
    }).join("");
  }

  // ============================================================ browse
  async function loadBrowse(reset) {
    const b = state.browse;
    if (reset) { b.page = 1; state.items = []; skeleton(); }
    const qs = new URLSearchParams({ sort: b.sort, page: b.page, size: PAGE });
    if (b.category) qs.set("category", b.category);
    if (b.gender) qs.set("gender", b.gender);
    try {
      const data = await api(`/api/products?${qs}`);
      b.total = data.total;
      state.items = reset ? data.products : state.items.concat(data.products);
      state.shown = state.items.length;
      $("#orders").hidden = true;
      renderGrid();
      $("#resultsMeta").textContent = `${b.total} sản phẩm`;
      $("#moreBtn").hidden = state.items.length >= b.total;
    } catch (e) { toast(e.message); }
  }

  function browseBy({ category = null, gender = null, sort = "popular", title }) {
    state.view = "browse";
    $(".results__tools").hidden = false;
    document.body.className = "mode-results";
    $("#understood").hidden = true;
    $("#notices").innerHTML = "";
    state.browse = { category, gender, sort, page: 1, total: 0 };
    $("#resultsTitle").textContent = title;
    $("#sortSelect").value = sort;
    window.scrollTo({ top: 0, behavior: "smooth" });
    loadBrowse(true);
  }

  // ============================================================ search
  async function search(extra = {}) {
    const text = $("#q").value.trim();
    const hasImage = !!(state.image || state.sample);
    let mode = extra.mode || (hasImage ? (text ? "multimodal" : "image") : "text");
    if (mode === "text" && !text) { $("#q").focus(); return; }
    const fd = new FormData();
    fd.set("mode", mode);
    if (text && mode !== "image" && mode !== "similar") fd.set("text", text);
    if (extra.text) fd.set("text", extra.text);
    if (extra.engine) fd.set("engine", extra.engine);
    if (extra.audio) fd.set("audio", extra.audio, "voice.wav");
    if (extra.product_id) fd.set("product_id", extra.product_id);
    if (mode === "image" || mode === "multimodal") {
      if (state.image) fd.set("image", state.image, state.image.name || "photo.jpg");
      else if (state.sample) fd.set("sample", state.sample);
    }
    state.view = "search";
    document.body.className = "mode-results";
    $("#cameraPop").hidden = true;
    skeleton();
    window.scrollTo({ top: 0, behavior: "smooth" });
    try {
      const data = await api("/api/search", { method: "POST", body: fd });
      renderResponse(data, extra);
      return data;
    } catch (e) {
      $("#grid").innerHTML = `<div class="empty"><h3>Có lỗi xảy ra</h3><p>${esc(e.message)}</p></div>`;
      toast(e.message);
      throw e;
    }
  }

  function skeleton() {
    $("#orders").hidden = true;
    $("#grid").hidden = false;
    $("#moreBtn").hidden = true;
    $("#grid").innerHTML = Array.from({ length: 8 }, () =>
      `<div class="card skeleton"><div class="card__photo"></div><div class="line"></div><div class="line short"></div></div>`).join("");
  }

  function renderResponse(data, extra = {}) {
    state.response = data;
    const q = data.query || {};
    renderUnderstood(data, extra);
    renderNotices(data);
    let title;
    if (data.mode === "image") title = "Giống ảnh của bạn";
    else if (data.mode === "similar") title = `Mẫu tương tự`;
    else if (data.mode === "voice") title = `“${data.input.normalized || data.input.text}”`;
    else if (data.mode === "multimodal") title = `Giống ảnh · “${q.query || ""}”`;
    else title = `“${q.query || ""}”`;
    if (data.orders) title = data.orders.length > 1 ? "Đơn hàng của bạn" : "Theo dõi đơn hàng";
    $("#resultsTitle").textContent = title;

    $(".results__tools").hidden = !!data.orders;
    if (data.orders) {
      $("#grid").hidden = true;
      renderOrders(data.orders);
      $("#resultsMeta").textContent = `${data.orders.length} đơn · ${data.total_ms} ms`;
      return;
    }
    $("#grid").hidden = false;
    state.items = data.results || [];
    state.shown = PAGE;
    const sortSel = $("#sortSelect");
    sortSel.value = q.sort && [...sortSel.options].some((o) => o.value === q.sort) ? q.sort : "relevance";
    renderGrid();
    const parts = [`${state.items.length} sản phẩm`];
    if (data.candidates != null) parts.push(`${data.candidates} ứng viên`);
    parts.push(`${data.total_ms} ms`);
    $("#resultsMeta").textContent = parts.join(" · ");
  }

  function chipRemovable(u) {
    if (!u.text || u.source === "llm" || state.response?.mode === "voice") return false;
    return spanRegex(u.text).test($("#q").value);
  }
  function spanRegex(span) {
    const parts = span.split(/\s+/).map((p) => p.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
    return new RegExp(parts.join("\\s*"), "i");
  }

  function renderUnderstood(data) {
    const q = data.query || {};
    const box = $("#understood");
    const chips = [];
    if (data.mode === "voice") {
      const d = data.input.dialect ? ` · giọng ${data.input.dialect}` : "";
      chips.push(`<span class="ichip ichip--note ichip--plain">${ICON.mic.replace("<svg", '<svg style="width:15px;height:15px"')} “${esc(data.input.transcript)}”${d}</span>`);
    }
    if (data.input && data.input.image && state.imageUrl && data.mode !== "similar") {
      chips.push(`<span class="ichip ichip--plain"><img src="${state.imageUrl}" style="width:22px;height:22px;border-radius:6px;object-fit:cover"> Ảnh của bạn</span>`);
    }
    if (data.image_category) {
      const c = data.image_category;
      chips.push(`<span class="ichip ichip--plain"><i></i>Ảnh trông giống: ${esc(c.name)} · ${Math.round(c.confidence * 100)}%</span>`);
    }
    (q.understood || []).forEach((u, idx) => {
      if (!u.label) return;
      const note = u.kind === "dialect" || u.kind === "typo";
      const cls = u.source === "llm" ? "ichip ichip--gemini" : note || u.source === "image" ? "ichip ichip--note" : "ichip";
      let dot = KIND_DOT[u.kind] ?? "#1c1b19";
      if (u.kind === "color") dot = COLOR_HEX[u.value] || "#999";
      const removable = !note && chipRemovable(u);
      const label = note ? (u.kind === "dialect" ? "Từ địa phương: " : "Sửa lỗi gõ: ") + u.label : u.label;
      chips.push(`<span class="${cls}${removable ? "" : " ichip--plain"}" style="animation-delay:${idx * 40}ms">
        ${note ? "" : `<i style="background:${dot}"></i>`}${esc(label)}
        ${removable ? `<button title="Bỏ điều kiện này" data-remove="${esc(u.text)}">×</button>` : ""}</span>`);
    });
    if (!chips.length && data.mode === "text") chips.push(`<span class="ichip ichip--plain">Tìm theo từ khóa</span>`);
    let parser = "";
    if (q.llm_name) parser = `<span class="pill pill--gemini">${ICON.sparkle.replace("<svg", '<svg style="width:13px;height:13px"')} Rule parser + AI · ${q.llm_ms ?? "?"} ms</span>`;
    else if (q.parser === "rule") parser = `<span class="pill">Rule parser · ${q.parse_ms} ms</span>`;
    else if (q.parser === "clip") parser = `<span class="pill">So khớp hình ảnh</span>`;
    box.innerHTML = `<span class="understood__label">SnapShop hiểu</span>${chips.join("")}${parser}
      <button class="link why" id="whyBtn">Vì sao có kết quả này?</button>`;
    box.hidden = false;
  }

  function renderNotices(data) {
    const q = data.query || {};
    const out = [];
    if (data.message) out.push(`<div class="notice">${ICON.info}<div>${esc(data.message)}</div></div>`);
    if (q.explanation) out.push(`<div class="notice notice--info">${ICON.sparkle}<div><b>AI hiểu là:</b> ${esc(q.explanation)}</div></div>`);
    if (q.llm_error) out.push(`<div class="notice notice--info">${ICON.info}<div>${esc(q.llm_error)}</div></div>`);
    if (q.llm_skipped && (data.results || []).length === 0) out.push(`<div class="notice notice--info">${ICON.info}<div>${esc(q.llm_skipped)}</div></div>`);
    $("#notices").innerHTML = out.join("");
  }

  // ============================================================ grid
  function sortedItems() {
    const s = $("#sortSelect").value;
    const items = [...state.items];
    const key = {
      price_asc: (a, b) => a.price - b.price, price_desc: (a, b) => b.price - a.price,
      popular: (a, b) => b.popularity - a.popularity, newest: null,
      relevance: (a, b) => (a.rank ?? 0) - (b.rank ?? 0),
    }[s];
    if (state.view === "search" && key) items.sort(key);
    return items;
  }

  function cardHTML(p, i) {
    const isSearch = p.score != null;
    const out = p.stock <= 0;
    let scores = "";
    if (isSearch) {
      const pt = p.parts || {};
      const w = (v) => `${Math.min(100, 100 * (v || 0))}%`;
      scores = `<div class="scorebar" title="Chữ ${pt.text?.toFixed(3)} · Ảnh ${pt.image?.toFixed(3)} · Business ${pt.business?.toFixed(3)}">
          <span class="t" style="width:${w(pt.text)}"></span><span class="i" style="width:${w(pt.image)}"></span><span class="b" style="width:${w(pt.business)}"></span></div>
        <div class="score-label"><span>Độ phù hợp</span><span>${(p.score * 100).toFixed(0)}%</span></div>`;
    }
    return `<article class="card" data-id="${p.id}" style="animation-delay:${Math.min(i, 12) * 35}ms">
      <div class="card__photo">
        <img data-fade src="${p.image_url}" alt="${esc(p.name)}" loading="lazy">
        ${isSearch ? `<span class="card__rank">#${p.rank}</span>` : ""}
        ${out ? `<span class="card__badge card__badge--soft">Tạm hết</span>` : p.popularity > 0.75 ? `<span class="card__badge">Bán chạy</span>` : ""}
        <button class="card__add" data-add="${p.id}" ${out ? "disabled" : ""}>${ICON.bag} ${out ? "Tạm hết hàng" : "Thêm vào giỏ"}</button>
      </div>
      <div class="card__body">
        <div class="card__brand">${esc(p.brand)} · ${p.gender === "nam" ? "Nam" : "Nữ"}</div>
        <h3 class="card__name">${esc(p.name)}</h3>
        <div class="card__row"><span class="card__price">${vnd(p.price)}</span>${swatch(p.color)}</div>
        ${scores}
      </div>
    </article>`;
  }

  function renderGrid() {
    const items = sortedItems();
    const grid = $("#grid");
    if (!items.length) {
      grid.innerHTML = `<div class="empty"><h3>Không tìm thấy sản phẩm phù hợp</h3><p>Bạn thử bỏ bớt điều kiện hoặc mô tả khác đi nhé.</p></div>`;
      $("#moreBtn").hidden = true;
      return;
    }
    const shown = state.view === "search" ? items.slice(0, state.shown) : items;
    grid.innerHTML = shown.map(cardHTML).join("");
    imgFade(grid);
    if (state.view === "search") $("#moreBtn").hidden = state.shown >= items.length;
  }

  // ============================================================ orders
  const STEPS = ["Chờ xác nhận", "Đang chuẩn bị hàng", "Đang giao", "Đã giao"];
  function renderOrders(orders) {
    const box = $("#orders");
    box.hidden = false;
    if (!orders.length) {
      box.innerHTML = `<div class="empty"><h3>Không tìm thấy đơn hàng</h3><p>Bạn kiểm tra lại mã đơn (ví dụ DH010) nhé.</p></div>`;
      return;
    }
    box.innerHTML = orders.map((o, k) => {
      const cancelled = o.status === "Đã hủy";
      const at = STEPS.indexOf(o.status);
      const cls = cancelled ? "status status--cancel" : at < 2 ? "status status--wait" : "status";
      const pay = o.payments[0];
      return `<div class="order" style="animation-delay:${k * 60}ms">
        <div class="order__head"><div><div class="order__id">${esc(o.order_id)}</div>
          <div class="order__meta">Đặt lúc ${esc(o.date)} · ${esc(o.address || "")}</div></div>
          <span class="${cls}">${esc(o.status)}</span></div>
        ${cancelled ? "" : `<div class="timeline">${STEPS.map((s, i) => `<div class="timeline__step ${i <= at ? "done" : ""}"><div class="timeline__dot">${i <= at ? ICON.check : ""}</div>${s}</div>`).join("")}</div>`}
        <div class="order__items" ${cancelled ? 'style="margin-top:18px"' : ""}>${o.items.map((it) => `
          <div class="order__item"><img src="${it.image_url}" alt=""><div>${esc(it.name)}<small>Màu ${esc(it.color)} · SL ${it.quantity}</small></div><b>${vnd(it.unit_price * it.quantity)}</b></div>`).join("")}</div>
        <div class="order__foot"><span>${pay ? `${esc(pay.method)} · ${esc(pay.status)}` : ""}${o.mine ? "" : " · (đơn của khách khác)"}</span><span>Tổng cộng (gồm phí ship) <strong>${vnd(o.total)}</strong></span></div>
      </div>`;
    }).join("");
  }

  // ============================================================ product modal
  function findItem(id) { return state.items.find((p) => p.id === id); }

  async function openProduct(id) {
    let p = findItem(id);
    if (!p) p = await api(`/api/products/${id}`);
    const out = p.stock <= 0;
    $("#productBody").innerHTML = `<button class="icon-btn modal__close" data-close aria-label="Đóng">×</button>
      <div class="pd"><div class="pd__photo"><img src="${p.image_url}" alt="${esc(p.name)}"></div>
      <div class="pd__info">
        <div class="pd__brand">${esc(p.brand)} · ${esc(p.category_name)}</div>
        <h2 class="pd__name">${esc(p.name)}</h2>
        <div class="pd__model">Mẫu ${esc(p.model)}</div>
        <div class="pd__price">${vnd(p.price)}</div>
        <div class="${out ? "stock stock--out" : "stock"}">${out ? "Tạm hết hàng" : `Còn ${p.stock} sản phẩm`}</div>
        <dl class="pd__facts">
          <div><dt>Màu</dt><dd>${swatch(p.color)}</dd></div>
          <div><dt>Chất liệu</dt><dd>${esc(p.material)}</dd></div>
          <div><dt>Họa tiết</dt><dd>${esc(p.pattern)}</dd></div>
          <div><dt>Dành cho</dt><dd>${p.gender === "nam" ? "Nam" : "Nữ"}</dd></div>
        </dl>
        <p class="pd__desc">${esc(p.description)}</p>
        <details class="pd__en"><summary>Mô tả gốc (H&amp;M)</summary><p>${esc(p.description_en)}</p>
          ${p.source_url ? `<a class="link" href="${esc(p.source_url)}" target="_blank" rel="noopener">Trang sản phẩm gốc</a>` : ""}</details>
        <div class="pd__actions">
          <button class="btn btn--dark" data-add="${p.id}" ${out ? "disabled" : ""}>${ICON.bag} Thêm vào giỏ</button>
          <button class="btn" data-similar="${p.id}">${ICON.similar} Tìm mẫu tương tự</button>
        </div>
      </div></div>`;
    $("#productBody").dataset.product = JSON.stringify(p);
    openLayer($("#productModal"));
  }

  async function similar(id) {
    closeLayers();
    const p = findItem(id) || JSON.parse($("#productBody").dataset.product || "{}");
    clearImage();
    $("#q").value = "";
    state.imageUrl = p.image_url;
    await search({ mode: "similar", product_id: id });
    $("#resultsTitle").textContent = `Tương tự “${p.name}”`;
  }

  // ============================================================ cart
  function addToCart(id) {
    const p = findItem(id) || JSON.parse($("#productBody").dataset.product || "null");
    if (!p) return;
    const line = state.cart.find((l) => l.id === id);
    if (line) line.qty += 1;
    else state.cart.push({ id: p.id, name: p.name, price: p.price, color: p.color, image_url: p.image_url, qty: 1 });
    saveCart();
    toast(`Đã thêm “${p.name}” vào giỏ`);
  }

  function renderCart() {
    const body = $("#cartBody");
    if (!state.cart.length) {
      body.innerHTML = `<div class="empty" style="padding:60px 0"><h3>Giỏ hàng trống</h3><p>Tìm vài món bạn thích nhé.</p></div>`;
      return;
    }
    const total = state.cart.reduce((s, l) => s + l.price * l.qty, 0);
    body.innerHTML = state.cart.map((l) => `<div class="cart-item"><img src="${l.image_url}" alt="">
      <div>${esc(l.name)}<small>Màu ${esc(l.color)}</small><div class="qty"><button data-qty="${l.id}" data-d="-1">−</button><span>${l.qty}</span><button data-qty="${l.id}" data-d="1">+</button></div></div>
      <b>${vnd(l.price * l.qty)}</b></div>`).join("") +
      `<div class="cart-total"><span>Tạm tính</span><strong>${vnd(total)}</strong></div>
       <button class="btn btn--dark btn--block" disabled>Thanh toán (ngoài phạm vi demo)</button>`;
  }

  // ============================================================ explain drawer
  function renderExplain() {
    const d = state.response;
    if (!d) return;
    const q = d.query || {};
    const input = d.mode === "voice"
      ? `<q>${esc(d.input.transcript)}</q><small>Chuẩn hóa: “${esc(d.input.normalized)}”${d.input.dialect ? " · giọng " + esc(d.input.dialect) : ""}</small>`
      : d.mode === "image" || d.mode === "similar"
        ? `${state.imageUrl ? `<img src="${state.imageUrl}" style="width:72px;border-radius:10px">` : ""}<small>${esc(d.input.image || q.image || "")}</small>`
        : `<q>${esc(q.query)}</q>${state.imageUrl && d.mode === "multimodal" ? `<small>+ ảnh ${esc(d.input.image)}</small>` : ""}`;
    const chips = (q.understood || []).filter((u) => u.label)
      .map((u) => `<span class="ichip ichip--plain ${u.source === "llm" ? "ichip--gemini" : ""}">${esc(u.label)}</span>`).join("") || "<span class='pill'>—</span>";
    const conf = q.confidence != null ? `<div class="meter"><span style="width:${q.confidence * 100}%"></span></div>
      <small style="color:var(--muted)">Độ tin cậy của rule parser: ${(q.confidence * 100).toFixed(0)}% ${q.llm_name ? "→ đã hỏi thêm " + llmLabel(q.llm_name) : q.confidence < 0.6 ? "(thấp)" : ""}</small>` : "";
    const steps = [{ component: "SearchUI (web)", layer: "Presentation", detail: `mode = ${d.mode}`, ms: "" }, ...d.trace]
      .map((s) => `<li><span class="ms">${s.ms !== "" ? s.ms + " ms" : ""}</span><strong>${esc(s.component)}</strong><span class="layer ${esc(s.layer)}">${esc(s.layer)}</span><small>${esc(s.detail)}</small></li>`).join("");
    const w = d.weights;
    const formula = w ? `<div class="formula">S = ${w.text.toFixed(2)}·S<sub>text</sub> + ${w.image.toFixed(2)}·S<sub>image</sub> + ${w.business.toFixed(2)}·S<sub>business</sub></div>
      <div class="legend"><span><i style="background:var(--s-text)"></i>Chữ (từ khóa + ngữ nghĩa)</span><span><i style="background:var(--s-image)"></i>Ảnh (độ giống hình ảnh)</span><span><i style="background:var(--s-business)"></i>Phổ biến + còn hàng</span></div>` : "";
    const top = (d.results || []).slice(0, 5).map((p) => `<div class="xtop__row"><img src="${p.image_url}" alt="">
      <div><div style="font-weight:500">${esc(p.name)}</div><div class="scorebar"><span class="t" style="width:${p.parts.text * 100}%"></span><span class="i" style="width:${p.parts.image * 100}%"></span><span class="b" style="width:${p.parts.business * 100}%"></span></div>
      <small style="color:var(--muted)">text ${p.s_text} · image ${p.s_image} · business ${p.s_business}</small></div><b>${p.score.toFixed(3)}</b></div>`).join("");
    $("#explainBody").innerHTML = `
      <div class="xsec"><h4>1 · Đầu vào (${MODE_LABEL[d.mode] || d.mode})</h4><div class="xinput">${input}</div></div>
      ${q.understood ? `<div class="xsec"><h4>2 · Biểu diễn truy vấn chung</h4><div class="xchips">${chips}</div>${conf}
        ${q.keywords ? `<p style="font-size:13px;color:var(--muted);margin:10px 0 0">Từ khóa BM25: ${esc(q.keywords.join(", "))}</p>` : ""}
        ${q.semantic_text ? `<p style="font-size:13px;color:var(--muted);margin:4px 0 0">Câu dùng để tìm theo ngữ nghĩa: “${esc(q.semantic_text)}”</p>` : ""}</div>` : ""}
      <div class="xsec"><h4>3 · Các component đã chạy</h4><ul class="steps">${steps}</ul>
        <small style="color:var(--muted)">Tổng: ${d.total_ms} ms</small></div>
      ${formula ? `<div class="xsec"><h4>4 · Xếp hạng (RankingService)</h4>${formula}</div>` : ""}
      ${top ? `<div class="xsec"><h4>5 · Top 5 và điểm thành phần</h4><div class="xtop">${top}</div></div>` : ""}`;
    openLayer($("#explainDrawer"));
  }

  // ============================================================ image input
  function setImage(file) {
    if (!file || !file.type.startsWith("image/")) { toast("Bạn chọn một file ảnh nhé"); return; }
    if (state.view === "search" && !state.image && !state.sample) $("#q").value = "";   // a new photo starts a new search
    state.image = file;
    state.sample = null;
    if (state.imageUrl && state.imageUrl.startsWith("blob:")) URL.revokeObjectURL(state.imageUrl);
    state.imageUrl = URL.createObjectURL(file);
    showThumb(state.imageUrl);
  }
  function setSample(name, url) {
    if (state.view === "search" && !state.image && !state.sample) $("#q").value = "";
    state.image = null;
    state.sample = name;
    state.imageUrl = url;
    showThumb(url);
  }
  function showThumb(url) {
    $("#thumbImg").src = url;
    $("#thumb").hidden = false;
    $("#cameraPop").hidden = true;
    $("#q").placeholder = "Thêm mô tả, vd: “màu đen”, “dưới 500k” (không bắt buộc)";
  }
  function clearImage() {
    state.image = null;
    state.sample = null;
    state.imageUrl = null;
    $("#thumb").hidden = true;
    $("#q").placeholder = "Tìm áo, quần…";
  }

  async function openCamera() {
    const pop = $("#cameraPop");
    pop.hidden = !pop.hidden;
    if (!pop.hidden && !$("#samples").children.length) {
      try {
        const list = await api("/api/samples");
        $("#samples").innerHTML = list.map((s) =>
          `<button type="button" data-sample="${esc(s.name)}" data-url="${s.url}"><img src="${s.url}" alt="" loading="lazy"></button>`).join("");
      } catch (_) { $("#samples").innerHTML = "<small>Không tải được ảnh mẫu</small>"; }
    }
  }

  // ============================================================ voice
  const voice = {
    active: false, stream: null, ctx: null, chunks: [], recognition: null, raf: 0, timer: 0,

    open() {
      this.active = true;
      const gemini = CONFIG.gemini_stt;
      const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
      const engine = CONFIG.stt_streaming ? "Chữ hiện ngay khi bạn nói" : gemini ? "Hiểu giọng 3 miền"
        : SR ? "Nhận dạng của trình duyệt (vi-VN)" : "Nhập tay";
      $("#voiceBody").className = "modal__card voice";
      $("#voiceBody").innerHTML = `<button class="icon-btn modal__close" data-close aria-label="Đóng">×</button>
        <h3 id="vTitle">Bạn cần tìm gì?</h3><p id="vSub">Nhấn vào micro và nói tự nhiên, giọng miền nào cũng được.</p>
        <div class="voice__orb"><button id="vOrb" aria-label="Bắt đầu / dừng ghi âm">${ICON.mic}</button></div>
        <canvas id="vWave" width="440" height="56"></canvas>
        <div class="voice__timer" id="vTimer"></div>
        <div class="voice__transcript" id="vText"></div>
        <div class="voice__caption" id="vCaption"></div>
        ${!CONFIG.stt_streaming && !gemini && !SR ? `<form id="vTyped" style="display:flex;gap:8px;margin-top:10px"><input class="btn btn--ghost" style="flex:1;text-align:left;cursor:text" placeholder="Gõ câu bạn muốn nói…" id="vTypedInput"><button class="btn btn--dark">Tìm</button></form>` : ""}
        <div class="voice__hint">Thử nói: “cho tui coi mấy cái áo thun hông quá trăm rưỡi” · “có quần jean nam mô dưới năm trăm nghìn không” · “đơn hàng gần nhất của tôi đâu”</div>
        <div class="voice__engine"><span class="pill ${gemini || CONFIG.stt_streaming ? "pill--gemini" : ""}">${esc(engine)}</span></div>`;
      openLayer($("#voiceModal"));
      if (CONFIG.stt_streaming) this.prefetchSession();     // ready before the microphone is tapped
      $("#vOrb").addEventListener("click", () => (this.recording ? this.stop() : this.start()));
      const typed = $("#vTyped");
      if (typed) typed.addEventListener("submit", (e) => {
        e.preventDefault();
        const t = $("#vTypedInput").value.trim();
        if (t) this.finishText(t, "typed");
      });
    },

    async start() {
      if (CONFIG.stt_streaming) return this.startSoniox();
      if (CONFIG.gemini_stt) return this.startRecorder();
      const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
      if (SR) return this.startBrowser(SR);
      toast("Trình duyệt không hỗ trợ ghi âm, bạn gõ câu vào ô bên dưới nhé");
    },

    setRecordingUI(on) {
      this.recording = on;
      $("#voiceBody").classList.toggle("recording", on);
      $("#vOrb").innerHTML = on ? ICON.stop : ICON.mic;
      $("#vTitle").textContent = on ? "Đang nghe…" : "Bạn cần tìm gì?";
    },

    // --- Soniox path: the microphone is streamed (16 kHz PCM) straight to Soniox with a
    // temporary key from the server; final words are shown dark, provisional words grey.
    prefetchSession() {
      const p = api("/api/stt/session", { method: "POST" });
      p.catch(() => {});                        // the error is reported when it is used
      this.session = { promise: p, at: Date.now() };
    },

    async startSoniox() {
      // the temporary key lives 60 s and is single-use: reuse the prefetched one if fresh
      if (!this.session || Date.now() - this.session.at > 45000) this.prefetchSession();
      const sessionPromise = this.session.promise;
      this.session = null;
      const micPromise = navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true } });
      micPromise.catch(() => {});
      let session;
      try {
        session = await sessionPromise;
      } catch (e) {
        micPromise.then((s) => s.getTracks().forEach((t) => t.stop())).catch(() => {});
        toast(e.message);
        return CONFIG.gemini_stt ? this.startRecorder() : null;
      }
      try {
        this.stream = await micPromise;
      } catch (_) { toast("Bạn cần cho phép dùng micro"); return; }
      const ws = (this.ws = new WebSocket(session.url));
      ws.binaryType = "arraybuffer";
      this.finalText = "";
      this.partial = "";
      this.wsError = null;
      this.wsDone = new Promise((resolve) => (this.wsResolve = resolve));
      const queue = [];                         // audio captured before the socket is open
      ws.onopen = () => {
        ws.send(JSON.stringify({ ...session.config, api_key: session.api_key }));
        queue.splice(0).forEach((chunk) => ws.send(chunk));
      };
      ws.onmessage = (e) => {
        const m = JSON.parse(e.data);
        if (m.error_code) {
          this.wsError = "Dịch vụ nhận dạng giọng nói gặp lỗi, bạn thử lại nhé.";
          this.wsResolve();
          return;
        }
        let partial = "", endpoint = false;
        for (const t of m.tokens || []) {
          if (t.text === "<end>") { endpoint = true; continue; }
          if (t.text.startsWith("<")) continue;    // other control tokens
          if (t.is_final) this.finalText += t.text; else partial += t.text;
        }
        this.partial = partial;
        this.renderSoniox();
        if (m.finished) this.wsResolve();
        if (endpoint && this.recording && this.finalText.trim()) this.stop();   // the customer stopped talking
      };
      ws.onerror = () => { this.wsError = this.wsError || "Mất kết nối tới dịch vụ nhận dạng giọng nói"; this.wsResolve(); };
      ws.onclose = () => this.wsResolve();

      const ctx = (this.ctx = new (window.AudioContext || window.webkitAudioContext)());
      const src = ctx.createMediaStreamSource(this.stream);
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 1024;
      const proc = ctx.createScriptProcessor(4096, 1, 1);
      const t0 = performance.now();
      let spoke = false, lastLoud = t0;
      this.chunks = [];                         // kept for Gemini in case Soniox fails mid-way
      proc.onaudioprocess = (e) => {
        const data = e.inputBuffer.getChannelData(0);
        this.chunks.push(new Float32Array(data));
        const pcm = toPCM16(downsample(data, ctx.sampleRate, 16000));
        if (ws.readyState === WebSocket.OPEN) ws.send(pcm);
        else if (ws.readyState === WebSocket.CONNECTING) queue.push(pcm);
        let rms = 0;
        for (let i = 0; i < data.length; i += 4) rms += data[i] * data[i];
        rms = Math.sqrt(rms / (data.length / 4));
        const now = performance.now();
        if (rms > 0.025) { spoke = true; lastLoud = now; }
        if ((spoke && now - lastLoud > 2500) || now - t0 > 15000) this.stop();   // backup for endpoint detection
      };
      src.connect(analyser);
      src.connect(proc);
      proc.connect(ctx.destination);
      this.setRecordingUI(true);
      this.renderSoniox();
      this.captionStatus("");
      this.draw(analyser);
      this.timer = setInterval(() => {
        $("#vTimer").textContent = `0:${String(Math.floor((performance.now() - t0) / 1000)).padStart(2, "0")}`;
      }, 250);
    },

    renderSoniox() {
      $("#vText").innerHTML = `<span>${esc(this.finalText)}</span><span class="voice__live">${esc(this.partial)}</span>`;
    },

    async stopSoniox() {
      this.setRecordingUI(false);
      clearInterval(this.timer);
      cancelAnimationFrame(this.raf);
      const rate = this.ctx ? this.ctx.sampleRate : 48000;
      this.cleanupAudio();
      const ws = this.ws;
      $("#vTitle").textContent = "Đang chốt câu…";
      try { if (ws.readyState === WebSocket.OPEN) ws.send(""); } catch (_) { /* closed */ }   // end of audio
      await Promise.race([this.wsDone, new Promise((r) => setTimeout(r, 2500))]);
      try { ws.close(); } catch (_) { /* closed */ }
      this.ws = null;
      const text = (this.finalText + this.partial).trim();
      if (text) return this.finishText(text, "soniox");
      const merged = mergeChunks(this.chunks);
      if (this.wsError && CONFIG.gemini_stt && merged.length > rate * 0.4) {
        // Soniox failed: send the same recording to Gemini (fallback only, no double check)
        toast("Đang thử nhận dạng lại…");
        $("#vTitle").textContent = "Đang nhận dạng…";
        $("#vText").innerHTML = '<div class="spinner"></div>';
        try {
          const data = await search({ mode: "voice", audio: encodeWav(downsample(merged, rate, 16000), 16000) });
          $("#vText").textContent = `“${data.input.transcript}”`;
          setTimeout(closeLayers, 700);
          return;
        } catch (e) { this.wsError = e.message; }
      }
      $("#vText").textContent = "";
      $("#vTitle").textContent = "Chưa nghe rõ";
      $("#vSub").textContent = this.wsError || "Bạn nói lại giúp mình nhé.";
    },

    // --- Gemini path: record WAV (16 kHz mono) and send it to the server
    async startRecorder() {
      try {
        this.stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true } });
      } catch (_) { toast("Bạn cần cho phép dùng micro"); return; }
      const ctx = (this.ctx = new (window.AudioContext || window.webkitAudioContext)());
      const src = ctx.createMediaStreamSource(this.stream);
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 1024;
      const proc = ctx.createScriptProcessor(4096, 1, 1);
      this.chunks = [];
      let spoke = false, lastLoud = performance.now();
      const t0 = performance.now();
      proc.onaudioprocess = (e) => {
        const data = e.inputBuffer.getChannelData(0);
        this.chunks.push(new Float32Array(data));
        let rms = 0;
        for (let i = 0; i < data.length; i += 4) rms += data[i] * data[i];
        rms = Math.sqrt(rms / (data.length / 4));
        const now = performance.now();
        if (rms > 0.025) { spoke = true; lastLoud = now; }
        if ((spoke && now - lastLoud > 1600) || now - t0 > 12000) this.stop();   // silence / max length
      };
      src.connect(analyser);
      src.connect(proc);
      proc.connect(ctx.destination);
      this.setRecordingUI(true);
      this.startLiveCaptions();
      this.draw(analyser);
      this.timer = setInterval(() => {
        $("#vTimer").textContent = `0:${String(Math.floor((performance.now() - t0) / 1000)).padStart(2, "0")}`;
      }, 250);
    },

    // Live captions while recording for Gemini. 1) the browser recogniser (Chrome / Edge)
    // shows the words as they are spoken; 2) if the browser has none or it fails (Safari,
    // Firefox, Brave, Arc...), the audio recorded so far is sent to Gemini every ~1.5 s.
    // Gemini's sentence for the whole recording replaces the captions at the end.
    startLiveCaptions() {
      this.live = "";
      this.liveFrom = null;
      const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
      if (!SR) return this.startGeminiCaptions("trình duyệt này không có nhận dạng giọng nói");
      try {
        const rec = (this.liveRec = new SR());
        rec.lang = "vi-VN";
        rec.interimResults = true;
        rec.continuous = true;
        rec.onstart = () => this.captionStatus("");
        rec.onresult = (e) => {
          let text = "";
          for (const r of e.results) text += r[0].transcript;
          this.showLive(text, "browser");
        };
        rec.onerror = (e) => {
          const why = {
            network: "trình duyệt chặn dịch vụ nhận dạng của Google (hay gặp ở Brave, Arc, Cốc Cốc)",
            "not-allowed": "trình duyệt không cho dùng micro cho nhận dạng",
            "service-not-allowed": "trình duyệt không cho dùng dịch vụ nhận dạng",
            "audio-capture": "micro đang bận",
            "language-not-supported": "trình duyệt không hỗ trợ tiếng Việt",
          }[e.error];
          if (why) { this.liveRec = null; this.startGeminiCaptions(why); }
        };
        rec.onend = () => {                       // Chrome stops after a pause: start again
          if (this.recording && this.liveRec === rec) { try { rec.start(); } catch (_) { /* ignore */ } }
        };
        rec.start();
      } catch (_) {
        this.liveRec = null;
        this.startGeminiCaptions("không khởi động được nhận dạng của trình duyệt");
      }
    },

    startGeminiCaptions(reason) {
      if (this.geminiTimer || !this.recording) return;
      this.captionStatus(`Chữ tạm hiện chậm khoảng 2 giây — vì ${reason}`);
      let busy = false, sentSamples = 0;
      this.geminiTimer = setInterval(async () => {
        if (busy || !this.recording || !this.ctx) return;
        const merged = mergeChunks(this.chunks);
        const rate = this.ctx.sampleRate;
        if (merged.length - sentSamples < rate * 0.8 || merged.length < rate * 0.8) return;
        busy = true;
        sentSamples = merged.length;
        try {
          const fd = new FormData();
          fd.set("audio", encodeWav(downsample(merged, rate, 16000), 16000), "partial.wav");
          const r = await api("/api/transcribe", { method: "POST", body: fd });
          if (this.recording) this.showLive(r.transcript, "gemini");
        } catch (_) { /* a missing partial caption is fine */ }
        busy = false;
      }, 1500);
    },

    showLive(text, from) {
      text = (text || "").trim();
      if (!text || (from === "gemini" && this.liveFrom === "browser")) return;
      this.live = text;
      this.liveFrom = from;
      $("#vText").innerHTML = `<span class="voice__live">${esc(text)}</span>`;
    },

    captionStatus(msg) {
      const el = $("#vCaption");
      if (el) el.textContent = msg;
    },

    stopLiveCaptions() {
      const rec = this.liveRec;
      this.liveRec = null;
      if (rec) { try { rec.stop(); } catch (_) { /* already stopped */ } }
      clearInterval(this.geminiTimer);
      this.geminiTimer = null;
    },

    draw(analyser) {
      const canvas = $("#vWave");
      if (!canvas) return;
      const g = canvas.getContext("2d");
      const buf = new Uint8Array(analyser.frequencyBinCount);
      const loop = () => {
        analyser.getByteTimeDomainData(buf);
        g.clearRect(0, 0, canvas.width, canvas.height);
        const bars = 48, step = Math.floor(buf.length / bars);
        for (let i = 0; i < bars; i++) {
          let peak = 0;
          for (let j = 0; j < step; j++) peak = Math.max(peak, Math.abs(buf[i * step + j] - 128));
          const h = Math.max(3, (peak / 128) * canvas.height * 1.6);
          g.fillStyle = "#1c1b19";
          g.globalAlpha = 0.25 + 0.75 * Math.min(1, peak / 40);
          g.beginPath();
          g.roundRect(i * (canvas.width / bars) + 2, (canvas.height - h) / 2, canvas.width / bars - 4, h, 3);
          g.fill();
        }
        this.raf = requestAnimationFrame(loop);
      };
      loop();
    },

    async stop() {
      if (!this.recording) return;
      if (this.ws) return this.stopSoniox();
      this.setRecordingUI(false);
      clearInterval(this.timer);
      cancelAnimationFrame(this.raf);
      if (this.recognition) { this.recognition.stop(); return; }
      const rate = this.ctx.sampleRate;
      this.stopLiveCaptions();
      this.cleanupAudio();
      const merged = mergeChunks(this.chunks);
      if (merged.length < rate * 0.4) { toast("Bản ghi quá ngắn, bạn nói lại nhé"); return; }
      const wav = encodeWav(downsample(merged, rate, 16000), 16000);
      $("#vTitle").textContent = "Đang nhận dạng…";
      $("#vSub").textContent = "Đang chép lời và chuẩn hóa từ địa phương";
      const live = this.live;
      $("#vText").innerHTML = (live ? `<span class="voice__live">${esc(live)}</span>` : "") +
        '<div class="spinner"></div>';
      try {
        const data = await search({ mode: "voice", audio: wav });
        $("#vText").textContent = `“${data.input.transcript}”`;
        setTimeout(closeLayers, 700);
      } catch (e) {
        if (live) {                             // Gemini failed: keep the browser's words
          toast("Chưa nhận dạng được, dùng chữ của trình duyệt");
          return this.finishText(live, "browser");
        }
        $("#vText").textContent = "";
        $("#vTitle").textContent = "Chưa nghe rõ";
        $("#vSub").textContent = e.message;
      }
    },

    // --- browser path (no Gemini key): Web Speech API, vi-VN
    startBrowser(SR) {
      const rec = (this.recognition = new SR());
      rec.lang = "vi-VN";
      rec.interimResults = true;
      rec.continuous = false;
      let finalText = "";
      rec.onresult = (e) => {
        let interim = "";
        for (const r of e.results) (r.isFinal ? (finalText = r[0].transcript) : (interim += r[0].transcript));
        $("#vText").textContent = finalText || interim;
      };
      rec.onerror = (e) => { toast(e.error === "not-allowed" ? "Bạn cần cho phép dùng micro" : "Không nhận dạng được, thử lại nhé"); };
      rec.onend = () => {
        this.recognition = null;
        this.setRecordingUI(false);
        const text = finalText || $("#vText").textContent;
        if (text) this.finishText(text, "browser");
      };
      rec.start();
      this.setRecordingUI(true);
    },

    async finishText(text, engine) {
      $("#vText").textContent = `“${text}”`;
      try {
        await search({ mode: "voice", text, engine });
        setTimeout(closeLayers, 600);
      } catch (_) { /* toast shown */ }
    },

    cleanupAudio() {
      if (this.stream) this.stream.getTracks().forEach((t) => t.stop());
      if (this.ctx) this.ctx.close();
      this.stream = this.ctx = null;
    },

    cancel() {
      this.active = false;
      clearInterval(this.timer);
      cancelAnimationFrame(this.raf);
      if (this.recognition) { this.recognition.onend = null; this.recognition.abort(); this.recognition = null; }
      this.stopLiveCaptions();
      if (this.ws) { try { this.ws.close(); } catch (_) { /* closed */ } this.ws = null; }
      this.recording = false;
      this.cleanupAudio();
    },
  };

  function toPCM16(samples) {
    const out = new Int16Array(samples.length);
    for (let i = 0; i < samples.length; i++) {
      const x = Math.max(-1, Math.min(1, samples[i]));
      out[i] = x < 0 ? x * 0x8000 : x * 0x7fff;
    }
    return out.buffer;
  }

  function mergeChunks(chunks) {
    const out = new Float32Array(chunks.reduce((n, c) => n + c.length, 0));
    let o = 0;
    for (const c of chunks) { out.set(c, o); o += c.length; }
    return out;
  }
  function downsample(buf, inRate, outRate) {
    if (outRate >= inRate) return buf;
    const ratio = inRate / outRate, out = new Float32Array(Math.floor(buf.length / ratio));
    for (let i = 0; i < out.length; i++) {
      const a = Math.floor(i * ratio), b = Math.min(buf.length, Math.floor((i + 1) * ratio));
      let s = 0;
      for (let j = a; j < b; j++) s += buf[j];
      out[i] = s / Math.max(1, b - a);
    }
    return out;
  }
  function encodeWav(samples, rate) {
    const view = new DataView(new ArrayBuffer(44 + samples.length * 2));
    const str = (o, s) => [...s].forEach((c, i) => view.setUint8(o + i, c.charCodeAt(0)));
    str(0, "RIFF"); view.setUint32(4, 36 + samples.length * 2, true); str(8, "WAVE"); str(12, "fmt ");
    view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true);
    view.setUint32(24, rate, true); view.setUint32(28, rate * 2, true); view.setUint16(32, 2, true);
    view.setUint16(34, 16, true); str(36, "data"); view.setUint32(40, samples.length * 2, true);
    let o = 44;
    for (const s of samples) {
      const x = Math.max(-1, Math.min(1, s));
      view.setInt16(o, x < 0 ? x * 0x8000 : x * 0x7fff, true);
      o += 2;
    }
    return new Blob([view], { type: "audio/wav" });
  }

  // ============================================================ evaluation
  async function openEvaluation() {
    $("#evalBody").innerHTML = `<button class="icon-btn modal__close" data-close aria-label="Đóng">×</button>
      <div class="eval"><h3>Đánh giá hệ thống</h3><p style="color:var(--muted)">Đang chạy bộ test (chữ, giọng nói, ảnh, chữ + ảnh)…</p><div class="spinner"></div></div>`;
    openLayer($("#evalModal"));
    try {
      const r = await api("/api/evaluation");
      const cards = [`<div class="eval__card"><b>${(100 * r.success / r.total).toFixed(1)}%</b><span>Tổng · ${r.success}/${r.total} truy vấn đạt</span></div>`]
        .concat(r.modes.map((m) => `<div class="eval__card"><b>${m.total ? (100 * m.success / m.total).toFixed(0) : 0}%</b><span>${esc(m.mode)} · ${m.success}/${m.total}</span></div>`));
      const metrics = (r.metrics || []).map((m) => `<div class="eval__card"><b>${esc(m.value)}</b><span>${esc(m.name)}</span></div>`).join("");
      $("#evalBody .eval").innerHTML = `<h3>Đánh giá hệ thống</h3>
        <p style="color:var(--muted);margin:0">Một truy vấn “đạt” khi kết quả #1 thỏa mọi điều kiện người dùng đưa ra (loại, giá, màu, giới tính…) hoặc là đúng sản phẩm / đúng đơn hàng.</p>
        <div class="eval__cards">${cards.join("")}</div>
        ${metrics ? `<h4 style="margin:0 0 8px;font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:var(--muted)">Chỉ số chi tiết</h4><div class="eval__cards" style="margin-top:0">${metrics}</div>` : ""}
        <table><thead><tr><th>#</th><th>Truy vấn</th><th>Kiểu</th><th>Kết quả #1</th><th>P@5</th><th></th></tr></thead><tbody>
        ${r.rows.map((x, i) => `<tr><td>${i + 1}</td><td>${esc(x.query)}</td><td>${esc(x.mode)}</td><td>${esc(x.top1)}</td><td>${esc(x.p5 ?? "")}</td><td class="${x.ok ? "ok" : "no"}">${x.ok ? "Đạt" : "Chưa"}</td></tr>`).join("")}
        </tbody></table>`;
    } catch (e) {
      $("#evalBody .eval").innerHTML = `<h3>Đánh giá hệ thống</h3><p>${esc(e.message)}</p>`;
    }
  }

  // ============================================================ events
  function bindEvents() {
    $("#searchForm").addEventListener("submit", (e) => { e.preventDefault(); search(); });
    $("#cameraBtn").addEventListener("click", openCamera);
    $("#uploadBtn").addEventListener("click", () => $("#fileInput").click());
    $("#fileInput").addEventListener("change", (e) => {
      if (e.target.files[0]) { setImage(e.target.files[0]); search(); }
      e.target.value = "";
    });
    $("#samples").addEventListener("click", (e) => {
      const b = e.target.closest("[data-sample]");
      if (b) { setSample(b.dataset.sample, b.dataset.url); search(); }
    });
    $("#thumbClear").addEventListener("click", () => { clearImage(); $("#q").focus(); });
    $("#micBtn").addEventListener("click", () => voice.open());
    $("#ordersBtn").addEventListener("click", () => { clearImage(); $("#q").value = "các đơn hàng của tôi"; search(); });
    $("#cartBtn").addEventListener("click", () => { renderCart(); openLayer($("#cartDrawer")); });
    $("#evalBtn").addEventListener("click", openEvaluation);
    $("#moreBtn").addEventListener("click", () => {
      if (state.view === "search") { state.shown += PAGE; renderGrid(); }
      else { state.browse.page += 1; loadBrowse(false); }
    });
    $("#sortSelect").addEventListener("change", (e) => {
      if (state.view === "search") renderGrid();
      else { state.browse.sort = e.target.value === "relevance" ? "popular" : e.target.value; loadBrowse(true); }
    });
    $("#nav").addEventListener("click", (e) => {
      const b = e.target.closest("button");
      if (!b) return;
      $$(".nav button").forEach((x) => x.classList.toggle("active", x === b));
      const cat = b.dataset.browseCategory, gender = b.dataset.browseGender, sort = b.dataset.browseSort;
      browseBy({ category: cat || null, gender: gender || null, sort: sort || "popular", title: b.textContent === "Mới về" ? "Hàng mới về" : `Thời trang ${b.textContent.toLowerCase()}` });
    });
    $("[data-action=home]").addEventListener("click", (e) => { e.preventDefault(); clearImage(); $("#q").value = ""; loadHome(); window.scrollTo({ top: 0, behavior: "smooth" }); });
    $("#categoryTiles").addEventListener("click", (e) => {
      const t = e.target.closest("[data-tile]");
      if (t) browseBy({ category: t.dataset.tile, title: t.textContent.trim() });
    });

    document.addEventListener("click", (e) => {
      const add = e.target.closest("[data-add]");
      if (add) { e.stopPropagation(); addToCart(Number(add.dataset.add)); return; }
      const sim = e.target.closest("[data-similar]");
      if (sim) { similar(Number(sim.dataset.similar)); return; }
      const rm = e.target.closest("[data-remove]");
      if (rm) {
        $("#q").value = $("#q").value.replace(spanRegex(rm.dataset.remove), " ").replace(/\s+/g, " ").trim();
        if ($("#q").value || state.image || state.sample) search(); else loadHome();
        return;
      }
      if (e.target.closest("#whyBtn")) { renderExplain(); return; }
      const card = e.target.closest(".card[data-id]");
      if (card) { openProduct(Number(card.dataset.id)); return; }
      const qty = e.target.closest("[data-qty]");
      if (qty) {
        const line = state.cart.find((l) => l.id === Number(qty.dataset.qty));
        line.qty += Number(qty.dataset.d);
        if (line.qty <= 0) state.cart = state.cart.filter((l) => l !== line);
        saveCart(); renderCart(); return;
      }
      if (e.target.closest("[data-close]") || e.target === $("#scrim") || e.target.classList.contains("modal")) closeLayers();
      if (!e.target.closest("#cameraPop") && !e.target.closest("#cameraBtn")) $("#cameraPop").hidden = true;
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") { closeLayers(); $("#cameraPop").hidden = true; }
      if (e.key === "/" && document.activeElement !== $("#q")) { e.preventDefault(); $("#q").focus(); }
    });
    window.addEventListener("scroll", () => document.body.classList.toggle("scrolled", window.scrollY > 10), { passive: true });

    // drag & drop and paste a photo anywhere
    let depth = 0;
    window.addEventListener("dragenter", (e) => {
      if ([...e.dataTransfer.types].includes("Files")) { depth++; $("#dropzone").hidden = false; }
    });
    window.addEventListener("dragleave", () => { if (--depth <= 0) { depth = 0; $("#dropzone").hidden = true; } });
    window.addEventListener("dragover", (e) => e.preventDefault());
    window.addEventListener("drop", (e) => {
      e.preventDefault(); depth = 0; $("#dropzone").hidden = true;
      const f = e.dataTransfer.files[0];
      if (f) { setImage(f); search(); }
    });
    window.addEventListener("paste", (e) => {
      const item = [...(e.clipboardData?.items || [])].find((i) => i.type.startsWith("image/"));
      if (item) { e.preventDefault(); setImage(item.getAsFile()); search(); }
    });
  }

  init();
})();

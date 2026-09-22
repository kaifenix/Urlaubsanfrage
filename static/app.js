"use strict";

// ---------------------------------------------------------------- Helpers ----
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
const esc = (s) =>
  String(s ?? "").replace(/[&<>"]/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])
  );

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `Fehler ${res.status}`);
  return data;
}

function toast(msg, isErr = false) {
  const t = $("#toast");
  t.textContent = msg;
  t.className = "toast show" + (isErr ? " err" : "");
  setTimeout(() => (t.className = "toast"), 3200);
}

// State
let HOTELS = [];
let FACETS = { regions: [], tags: [] };
let PARSED_OFFERS = []; // aktuell ausgelesene, noch nicht gespeicherte Angebote

// ------------------------------------------------------------------ Tabs ----
$$(".tab").forEach((btn) => {
  btn.addEventListener("click", () => {
    $$(".tab").forEach((b) => b.classList.remove("active"));
    $$(".panel").forEach((p) => p.classList.remove("active"));
    btn.classList.add("active");
    $("#" + btn.dataset.tab).classList.add("active");
    if (btn.dataset.tab === "anfrage") renderAnfrageHotels();
    if (btn.dataset.tab === "vergleich") { fillOfferHotelSelect(); loadOffers(); }
  });
});

// ============================================================== HOTELS =====
async function loadHotels() {
  HOTELS = await api("/api/hotels");
  FACETS = await api("/api/hotels/facets");
  fillFacetSelect("#filter-region", FACETS.regions);
  fillFacetSelect("#filter-tag", FACETS.tags);
  fillFacetSelect("#af-filter-region", FACETS.regions);
  fillFacetSelect("#af-filter-tag", FACETS.tags);
  renderHotelList();
}

function fillFacetSelect(sel, values) {
  const el = $(sel);
  if (!el) return;
  const cur = el.value;
  el.innerHTML = '<option value="">Alle</option>' +
    values.map((v) => `<option>${esc(v)}</option>`).join("");
  el.value = cur;
}

function filteredHotels(region, tag) {
  return HOTELS.filter(
    (h) =>
      (!region || (h.region || "").toLowerCase() === region.toLowerCase()) &&
      (!tag || (h.features || []).some((f) => f.toLowerCase() === tag.toLowerCase()))
  );
}

function renderHotelList() {
  const region = $("#filter-region").value;
  const tag = $("#filter-tag").value;
  const list = filteredHotels(region, tag);
  $("#hotel-count").textContent = `${list.length} von ${HOTELS.length} Hotels`;
  const el = $("#hotel-list");
  if (!list.length) {
    el.innerHTML = '<p class="muted">Noch keine Hotels. Oben eine URL auslesen oder leeres Hotel anlegen.</p>';
    return;
  }
  el.innerHTML = list.map(hotelCard).join("");
}

function hotelCard(h) {
  const chips = (h.features || []).map((f) => `<span class="chip">${esc(f)}</span>`).join("");
  return `
  <div class="hotel-item" data-id="${h.id}">
    <div class="hotel-head">
      <div>
        <strong>${esc(h.name) || "(ohne Namen)"}</strong>
        <div class="muted">${esc(h.ort)}${h.ort && h.region ? " · " : ""}${esc(h.region)}</div>
        <div class="chips">${chips}</div>
      </div>
      <div>
        <button class="small" onclick="editHotel(${h.id})">Bearbeiten</button>
        <button class="small danger" onclick="deleteHotel(${h.id})">Löschen</button>
      </div>
    </div>
  </div>`;
}

$("#filter-region").addEventListener("change", renderHotelList);
$("#filter-tag").addEventListener("change", renderHotelList);

// ---- URL auslesen ----
$("#btn-extract").addEventListener("click", async () => {
  const url = $("#hotel-url").value.trim();
  if (!url) return toast("Bitte eine URL eingeben.", true);
  const status = $("#extract-status");
  status.className = "status";
  status.textContent = "Seite wird geladen und ausgelesen …";
  $("#btn-extract").disabled = true;
  try {
    const data = await api("/api/hotels/extract", {
      method: "POST",
      body: JSON.stringify({ url }),
    });
    if (data.warning) {
      status.className = "status warn";
      status.textContent = "Hinweis: " + data.warning + " – bitte manuell ausfüllen.";
    } else {
      status.className = "status ok";
      status.textContent = "Ausgelesen. Bitte prüfen, ergänzen und speichern.";
    }
    openHotelEditor(data);
    $("#hotel-url").value = "";
  } catch (e) {
    status.className = "status err";
    status.textContent = e.message;
  } finally {
    $("#btn-extract").disabled = false;
  }
});

$("#btn-new-hotel").addEventListener("click", () =>
  openHotelEditor({ name: "", url: "", ort: "", region: "", email: "", features: [] })
);

// ---- Hotel-Editor (Formular für neu/bearbeiten) ----
function openHotelEditor(h) {
  const isEdit = !!h.id;
  const editorId = "hotel-editor";
  document.getElementById(editorId)?.remove();
  const div = document.createElement("div");
  div.id = editorId;
  div.className = "card";
  div.innerHTML = `
    <h3>${isEdit ? "Hotel bearbeiten" : "Neues Hotel prüfen & speichern"}</h3>
    <div class="grid2">
      <label>Name <input id="he-name" value="${esc(h.name)}" /></label>
      <label>Kontakt-E-Mail <input id="he-email" value="${esc(h.email)}" placeholder="leer lassen wenn unsicher" /></label>
      <label>Ort <input id="he-ort" value="${esc(h.ort)}" /></label>
      <label>Region <input id="he-region" value="${esc(h.region)}" list="region-datalist" /></label>
    </div>
    <datalist id="region-datalist">${FACETS.regions.map((r) => `<option>${esc(r)}</option>`).join("")}</datalist>
    <label>Webseite <input id="he-url" value="${esc(h.url)}" /></label>
    <label>Merkmale / Tags (Enter zum Hinzufügen)</label>
    <div class="tags-input" id="he-tags"></div>
    <label>Notizen <textarea id="he-notes" rows="2">${esc(h.notes)}</textarea></label>
    <div class="row">
      <button class="primary" id="he-save">${isEdit ? "Änderungen speichern" : "Hotel speichern"}</button>
      <button id="he-cancel">Abbrechen</button>
    </div>`;
  const anchor = $("#hotels .card:nth-child(2)");
  anchor.parentNode.insertBefore(div, anchor);

  const tags = [...(h.features || [])];
  renderTagsInput($("#he-tags"), tags);

  $("#he-cancel").addEventListener("click", () => div.remove());
  $("#he-save").addEventListener("click", async () => {
    const payload = {
      name: $("#he-name").value,
      email: $("#he-email").value,
      ort: $("#he-ort").value,
      region: $("#he-region").value,
      url: $("#he-url").value,
      notes: $("#he-notes").value,
      features: tags,
    };
    try {
      if (isEdit) {
        await api(`/api/hotels/${h.id}`, { method: "PUT", body: JSON.stringify(payload) });
        toast("Hotel aktualisiert.");
      } else {
        await api("/api/hotels", { method: "POST", body: JSON.stringify(payload) });
        toast("Hotel gespeichert.");
      }
      div.remove();
      await loadHotels();
    } catch (e) {
      toast(e.message, true);
    }
  });
  div.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function renderTagsInput(container, tags) {
  function draw() {
    container.innerHTML =
      tags.map((t, i) => `<span class="chip">${esc(t)}<button data-i="${i}">×</button></span>`).join("") +
      '<input type="text" placeholder="Merkmal eingeben …" />';
    const input = container.querySelector("input");
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        const v = input.value.trim();
        if (v && !tags.includes(v)) tags.push(v);
        draw();
        container.querySelector("input").focus();
      }
    });
    $$("button", container).forEach((b) =>
      b.addEventListener("click", () => { tags.splice(+b.dataset.i, 1); draw(); })
    );
  }
  draw();
}

window.editHotel = (id) => {
  const h = HOTELS.find((x) => x.id === id);
  if (h) openHotelEditor(h);
};
window.deleteHotel = async (id) => {
  if (!confirm("Dieses Hotel wirklich löschen?")) return;
  await api(`/api/hotels/${id}`, { method: "DELETE" });
  toast("Hotel gelöscht.");
  await loadHotels();
};

// ============================================================== ANFRAGE ====
function renderAnfrageHotels() {
  fillFacetSelect("#af-filter-region", FACETS.regions);
  fillFacetSelect("#af-filter-tag", FACETS.tags);
  const region = $("#af-filter-region").value;
  const tag = $("#af-filter-tag").value;
  const list = filteredHotels(region, tag);
  $("#anfrage-count").textContent = `${list.length} Hotels`;
  const el = $("#anfrage-hotel-list");
  if (!list.length) {
    el.innerHTML = '<p class="muted">Keine Hotels für diesen Filter.</p>';
    return;
  }
  el.innerHTML = list.map((h) => {
    const noMail = h.email ? "" : ' <span class="to-warn">(keine E-Mail hinterlegt)</span>';
    return `<label class="selectable">
      <input type="checkbox" class="af-check" value="${h.id}" ${h.email ? "" : ""}/>
      <span><strong>${esc(h.name) || "(ohne Namen)"}</strong> – ${esc(h.region)}${noMail}
      <div class="chips">${(h.features || []).map((f) => `<span class="chip">${esc(f)}</span>`).join("")}</div>
      </span></label>`;
  }).join("");
}

$("#af-filter-region").addEventListener("change", renderAnfrageHotels);
$("#af-filter-tag").addEventListener("change", renderAnfrageHotels);
$("#btn-select-all").addEventListener("click", () =>
  $$(".af-check").forEach((c) => (c.checked = true))
);

$("#btn-preview").addEventListener("click", async () => {
  const ids = $$(".af-check").filter((c) => c.checked).map((c) => +c.value);
  if (!ids.length) return toast("Bitte mindestens ein Hotel auswählen.", true);
  const body = {
    hotel_ids: ids,
    von: $("#req-von").value,
    bis: $("#req-bis").value,
    personen: +$("#req-personen").value || 2,
    kinder: $("#req-kinder").value,
    extra: $("#req-extra").value,
  };
  try {
    const data = await api("/api/requests/preview", {
      method: "POST",
      body: JSON.stringify(body),
    });
    renderPreviews(data.request, data.previews);
  } catch (e) {
    toast(e.message, true);
  }
});

function renderPreviews(req, previews) {
  const area = $("#preview-area");
  area.innerHTML = `
    <div class="card">
      <h3>Vorschau (${previews.length} E-Mails) – bitte prüfen und bestätigen</h3>
      <p class="hint">Betreff, Empfänger und Text sind hier noch editierbar. Erst mit
        „Alle senden“ werden die Mails tatsächlich verschickt.</p>
      <div id="preview-list"></div>
      <div class="row">
        <button class="primary" id="btn-send-all">Alle ${previews.length} senden</button>
        <span id="send-status" class="status"></span>
      </div>
    </div>`;
  $("#preview-list").innerHTML = previews.map((p, i) => {
    const warn = p.to_email ? "" : '<div class="to-warn">Keine E-Mail-Adresse – wird übersprungen. Bitte im Hotel nachtragen.</div>';
    return `<div class="preview-mail" data-i="${i}">
      <label>An <input class="pv-to" value="${esc(p.to_email)}" /></label>${warn}
      <label>Betreff <input class="pv-subject" value="${esc(p.subject)}" /></label>
      <label>Text <textarea class="pv-body" rows="10">${esc(p.body)}</textarea></label>
      <div class="muted">Hotel: ${esc(p.hotel_name)}</div>
    </div>`;
  }).join("");

  area.__req = req;
  area.__previews = previews;

  $("#btn-send-all").addEventListener("click", sendAll);
  area.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

async function sendAll() {
  const area = $("#preview-area");
  const mails = $$(".preview-mail", area).map((div, i) => ({
    hotel_id: area.__previews[i].hotel_id,
    hotel_name: area.__previews[i].hotel_name,
    to_email: $(".pv-to", div).value.trim(),
    subject: $(".pv-subject", div).value,
    body: $(".pv-body", div).value,
  }));
  const withMail = mails.filter((m) => m.to_email);
  if (!withMail.length) return toast("Keine Empfänger-Adressen vorhanden.", true);
  if (!confirm(`${withMail.length} E-Mail(s) jetzt wirklich versenden?`)) return;

  const status = $("#send-status");
  status.className = "status";
  status.textContent = "Versand läuft …";
  $("#btn-send-all").disabled = true;
  try {
    const data = await api("/api/requests/send", {
      method: "POST",
      body: JSON.stringify({ request: area.__req, emails: withMail }),
    });
    const ok = data.results.filter((r) => r.status === "gesendet").length;
    const fail = data.results.filter((r) => r.status !== "gesendet");
    status.className = "status " + (fail.length ? "warn" : "ok");
    status.innerHTML = `${ok} gesendet.` +
      (fail.length ? " Fehler bei: " + fail.map((f) => esc(f.hotel_name) + " (" + esc(f.error) + ")").join("; ") : "");
    toast(`${ok} E-Mail(s) gesendet.`);
  } catch (e) {
    status.className = "status err";
    status.textContent = e.message;
  } finally {
    $("#btn-send-all").disabled = false;
  }
}

// ============================================================== VERGLEICH ==
function fillOfferHotelSelect() {
  const sel = $("#offer-hotel");
  sel.innerHTML = '<option value="">– kein Hotel –</option>' +
    HOTELS.map((h) => `<option value="${h.id}">${esc(h.name) || "(ohne Namen)"} – ${esc(h.region)}</option>`).join("");
}

$("#btn-parse-offer").addEventListener("click", async () => {
  const text = $("#offer-text").value.trim();
  if (!text) return toast("Bitte den Mail-Text einfügen.", true);
  const status = $("#offer-parse-status");
  status.className = "status";
  status.textContent = "Angebote werden per KI ausgelesen …";
  $("#btn-parse-offer").disabled = true;
  try {
    const data = await api("/api/offers/parse", {
      method: "POST",
      body: JSON.stringify({ text, follow_links: $("#offer-follow-links").checked }),
    });
    PARSED_OFFERS = data.offers;
    status.className = "status ok";
    status.textContent = `${data.offers.length} Angebot(e) erkannt` +
      (data.links_followed.length ? `, Links ausgewertet: ${data.links_followed.length}` : "") +
      ". Bitte prüfen und speichern.";
    renderOfferDrafts();
  } catch (e) {
    status.className = "status err";
    status.textContent = e.message;
  } finally {
    $("#btn-parse-offer").disabled = false;
  }
});

function renderOfferDrafts() {
  const area = $("#offer-draft-area");
  if (!PARSED_OFFERS.length) { area.innerHTML = ""; return; }
  area.innerHTML =
    PARSED_OFFERS.map((o, i) => `
      <div class="offer-draft" data-i="${i}">
        <div class="grid2">
          <label>Preis (gesamt) <input class="od-price" type="number" value="${o.price ?? ""}" /></label>
          <label>Währung <input class="od-currency" value="${esc(o.currency || "EUR")}" /></label>
          <label>Von <input class="od-von" value="${esc(o.von)}" placeholder="YYYY-MM-DD" /></label>
          <label>Bis <input class="od-bis" value="${esc(o.bis)}" placeholder="YYYY-MM-DD" /></label>
          <label>Nächte <input class="od-naechte" type="number" value="${o.naechte ?? ""}" /></label>
          <label>Personen <input class="od-personen" type="number" value="${o.personen ?? ""}" /></label>
          <label>Zimmer <input class="od-zimmer" value="${esc(o.zimmer)}" /></label>
          <label>Verpflegung <input class="od-verpflegung" value="${esc(o.verpflegung)}" /></label>
        </div>
        <label>Leistungen <input class="od-leistungen" value="${esc(o.leistungen)}" /></label>
        <label>Storno <input class="od-storno" value="${esc(o.storno)}" /></label>
        <label>Notizen <input class="od-notes" value="${esc(o.notes)}" /></label>
      </div>`).join("") +
    `<div class="row"><button class="primary" id="btn-save-offers">${PARSED_OFFERS.length} Angebot(e) speichern</button></div>`;

  $("#btn-save-offers").addEventListener("click", saveOffers);
}

async function saveOffers() {
  const area = $("#offer-draft-area");
  const offers = $$(".offer-draft", area).map((div) => ({
    price: parseFloat($(".od-price", div).value) || null,
    currency: $(".od-currency", div).value || "EUR",
    von: $(".od-von", div).value,
    bis: $(".od-bis", div).value,
    naechte: parseInt($(".od-naechte", div).value) || null,
    personen: parseInt($(".od-personen", div).value) || null,
    zimmer: $(".od-zimmer", div).value,
    verpflegung: $(".od-verpflegung", div).value,
    leistungen: $(".od-leistungen", div).value,
    storno: $(".od-storno", div).value,
    notes: $(".od-notes", div).value,
  }));
  try {
    await api("/api/offers", {
      method: "POST",
      body: JSON.stringify({
        hotel_id: $("#offer-hotel").value || null,
        offers,
      }),
    });
    toast(`${offers.length} Angebot(e) gespeichert.`);
    PARSED_OFFERS = [];
    $("#offer-draft-area").innerHTML = "";
    $("#offer-text").value = "";
    $("#offer-parse-status").textContent = "";
    loadOffers();
  } catch (e) {
    toast(e.message, true);
  }
}

async function loadOffers() {
  const offers = await api("/api/offers");
  renderCompareTable(offers);
}

function renderCompareTable(offers) {
  const el = $("#compare-table");
  if (!offers.length) {
    el.innerHTML = '<p class="muted">Noch keine gespeicherten Angebote.</p>';
    return;
  }
  const priced = offers.filter((o) => o.price != null);
  const minPrice = priced.length ? Math.min(...priced.map((o) => o.price)) : null;

  const rows = offers.map((o) => {
    const cheapest = o.price != null && o.price === minPrice ? "cheapest" : "";
    const price = o.price != null ? `${o.price.toLocaleString("de-DE")} ${esc(o.currency)}` : "–";
    const ppn = o.price_per_night != null ? `${o.price_per_night.toLocaleString("de-DE")} ${esc(o.currency)}` : "–";
    const zeit = (o.von || o.bis) ? `${esc(o.von || "?")} – ${esc(o.bis || "?")}` : "–";
    return `<tr class="${cheapest}">
      <td>${esc(o.hotel_name) || "(kein Hotel)"}<div class="muted">${esc(o.hotel_region || "")}</div></td>
      <td><strong>${price}</strong></td>
      <td>${ppn}</td>
      <td>${zeit}${o.naechte ? `<div class="muted">${o.naechte} Nächte</div>` : ""}</td>
      <td>${esc(o.zimmer) || "–"}</td>
      <td>${esc(o.verpflegung) || "–"}</td>
      <td>${esc(o.leistungen) || "–"}</td>
      <td>${esc(o.storno) || "–"}${o.notes ? `<div class="muted">${esc(o.notes)}</div>` : ""}</td>
      <td><button class="small danger" onclick="deleteOffer(${o.id})">×</button></td>
    </tr>`;
  }).join("");

  el.innerHTML = `<div class="table-wrap"><table>
    <thead><tr>
      <th>Hotel</th><th>Preis</th><th>Preis/Nacht</th><th>Zeitraum</th>
      <th>Zimmer</th><th>Verpflegung</th><th>Leistungen</th><th>Storno / Notizen</th><th></th>
    </tr></thead>
    <tbody>${rows}</tbody>
  </table></div>`;
}

window.deleteOffer = async (id) => {
  if (!confirm("Angebot löschen?")) return;
  await api(`/api/offers/${id}`, { method: "DELETE" });
  toast("Angebot gelöscht.");
  loadOffers();
};

$("#btn-refresh-offers").addEventListener("click", loadOffers);
$("#btn-summary-mail").addEventListener("click", async () => {
  if (!confirm("Zusammenfassung aller Angebote an deine eigene Adresse senden?")) return;
  try {
    await api("/api/offers/summary-email", { method: "POST" });
    toast("Zusammenfassung gesendet.");
  } catch (e) {
    toast(e.message, true);
  }
});

// ============================================================== SETTINGS ===
async function loadSettings() {
  const cfg = await api("/api/settings");
  $("#set-model").value = cfg.model || "claude-haiku-4-5";
  $("#set-sender-name").value = cfg.sender_name || "";
  $("#set-sender-contact").value = cfg.sender_contact || "";
  $("#set-self-email").value = cfg.self_email || "";
  const smtp = cfg.smtp || {};
  $("#set-smtp-host").value = smtp.host || "";
  $("#set-smtp-port").value = smtp.port || 587;
  $("#set-smtp-user").value = smtp.user || "";
  $("#set-smtp-from").value = smtp.from_email || "";
  $("#set-smtp-tls").checked = smtp.use_tls !== false;
  $("#apikey-status").textContent = cfg.anthropic_api_key_set
    ? "✓ API-Key ist hinterlegt (Eingabe leer lassen = unverändert)."
    : "⚠ Noch kein API-Key hinterlegt – KI-Funktionen sind bis dahin deaktiviert.";
  $("#smtp-status").textContent = smtp.password_set
    ? "✓ SMTP-Passwort ist hinterlegt."
    : "Kein SMTP-Passwort hinterlegt.";
}

$("#btn-save-settings").addEventListener("click", async () => {
  const payload = {
    model: $("#set-model").value,
    sender_name: $("#set-sender-name").value,
    sender_contact: $("#set-sender-contact").value,
    self_email: $("#set-self-email").value,
    smtp: {
      host: $("#set-smtp-host").value,
      port: +$("#set-smtp-port").value || 587,
      user: $("#set-smtp-user").value,
      from_email: $("#set-smtp-from").value,
      use_tls: $("#set-smtp-tls").checked,
    },
  };
  if ($("#set-apikey").value.trim()) payload.anthropic_api_key = $("#set-apikey").value.trim();
  if ($("#set-smtp-pass").value.trim()) payload.smtp.password = $("#set-smtp-pass").value.trim();
  try {
    await api("/api/settings", { method: "POST", body: JSON.stringify(payload) });
    $("#set-apikey").value = "";
    $("#set-smtp-pass").value = "";
    toast("Einstellungen gespeichert.");
    loadSettings();
  } catch (e) {
    toast(e.message, true);
  }
});

// ------------------------------------------------------------------ Init ----
loadHotels();
loadSettings();

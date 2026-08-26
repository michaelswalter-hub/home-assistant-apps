const grid = document.getElementById("libraryGrid");
const seriesGrid = document.getElementById("seriesGrid");
const emptyState = document.getElementById("emptyState");
const bookCount = document.getElementById("bookCount");
const searchInput = document.getElementById("searchInput");
const seriesFilter = document.getElementById("seriesFilter");
const fileInput = document.getElementById("fileInput");
const uploadButton = document.getElementById("uploadButton");
const emptyUploadButton = document.getElementById("emptyUploadButton");
const uploadStatus = document.getElementById("uploadStatus");
const dialog = document.getElementById("detailDialog");
const detailContent = document.getElementById("detailContent");
const closeDialog = document.getElementById("closeDialog");
const template = document.getElementById("bookTemplate");

const booksViewButton = document.getElementById("booksViewButton");
const seriesViewButton = document.getElementById("seriesViewButton");
const settingsButton = document.getElementById("settingsButton");
const settingsDialog = document.getElementById("settingsDialog");
const closeSettingsDialog = document.getElementById("closeSettingsDialog");
const seriesForm = document.getElementById("seriesForm");
const seriesName = document.getElementById("seriesName");
const seriesList = document.getElementById("seriesList");

let books = [];
let series = [];
let currentView = "books";

function api(path) {
  return `api/${path}`;
}

function formatBytes(bytes) {
  if (!Number.isFinite(bytes)) return "–";
  const units = ["B", "KB", "MB", "GB"];
  let value = bytes;
  let i = 0;
  while (value >= 1024 && i < units.length - 1) {
    value /= 1024;
    i++;
  }
  return `${value.toFixed(i ? 1 : 0)} ${units[i]}`;
}

function formatSeriesIndex(value) {
  if (value == null) return "";
  return Number.isInteger(Number(value)) ? String(Number(value)) : String(value);
}

function esc(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

async function loadData() {
  const [bookResponse, seriesResponse] = await Promise.all([
    fetch(api("books")),
    fetch(api("series"))
  ]);
  books = await bookResponse.json();
  series = await seriesResponse.json();
  updateSeriesFilter();
  render();
}

function updateSeriesFilter() {
  const current = seriesFilter.value;
  seriesFilter.innerHTML = `<option value="">Alle Serien</option>` +
    series.map(item =>
      `<option value="${esc(item.id)}">${esc(item.name)} (${item.book_count})</option>`
    ).join("");
  if ([...seriesFilter.options].some(o => o.value === current)) {
    seriesFilter.value = current;
  }
}

function setView(view) {
  currentView = view;
  booksViewButton.classList.toggle("active", view === "books");
  seriesViewButton.classList.toggle("active", view === "series");
  seriesFilter.classList.toggle("hidden", view === "series");
  render();
}

function filteredBooks() {
  const query = searchInput.value.trim().toLocaleLowerCase();
  const selectedSeries = seriesFilter.value;
  return books.filter(book =>
    (!query ||
      (book.title || "").toLocaleLowerCase().includes(query) ||
      (book.author || "").toLocaleLowerCase().includes(query) ||
      (book.series_name || "").toLocaleLowerCase().includes(query)) &&
    (!selectedSeries || book.series_id === selectedSeries)
  );
}

function render() {
  const visibleBooks = filteredBooks();

  if (currentView === "series") {
    renderSeriesView();
    return;
  }

  grid.classList.remove("hidden");
  seriesGrid.classList.add("hidden");
  emptyState.classList.toggle("hidden", books.length !== 0);

  visibleBooks.sort((a, b) => {
    if (seriesFilter.value) {
      const ai = a.series_index ?? Number.MAX_SAFE_INTEGER;
      const bi = b.series_index ?? Number.MAX_SAFE_INTEGER;
      if (ai !== bi) return ai - bi;
    }
    return (a.title || "").localeCompare(b.title || "", "de", {sensitivity: "base"});
  });

  grid.innerHTML = "";
  bookCount.textContent = `${visibleBooks.length} ${visibleBooks.length === 1 ? "Buch" : "Bücher"}`;

  for (const book of visibleBooks) {
    const node = template.content.cloneNode(true);
    const card = node.querySelector(".book-card");
    const image = node.querySelector(".cover");
    const fallback = node.querySelector(".cover-fallback");
    image.alt = `Cover von ${book.title}`;
    image.src = api(`books/${book.id}/cover`);
    image.addEventListener("load", () => fallback.classList.add("hidden"));
    image.addEventListener("error", () => image.classList.add("hidden"));
    node.querySelector(".format-badge").textContent = book.format;
    node.querySelector(".book-title").textContent = book.title;
    node.querySelector(".book-author").textContent = book.author || "Autor unbekannt";
    const seriesLine = node.querySelector(".book-series");
    if (book.series_name) {
      seriesLine.textContent = book.series_index
        ? `${book.series_name} · Band ${formatSeriesIndex(book.series_index)}`
        : book.series_name;
    } else {
      seriesLine.classList.add("hidden");
    }
    card.addEventListener("click", () => showBook(book.id));
    card.addEventListener("keydown", event => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        showBook(book.id);
      }
    });
    grid.appendChild(node);
  }
}

function renderSeriesView() {
  grid.classList.add("hidden");
  seriesGrid.classList.remove("hidden");
  emptyState.classList.toggle("hidden", series.length !== 0 || books.length !== 0);

  const query = searchInput.value.trim().toLocaleLowerCase();
  const visibleSeries = series.filter(item =>
    !query ||
    item.name.toLocaleLowerCase().includes(query) ||
    books.some(book =>
      book.series_id === item.id &&
      ((book.title || "").toLocaleLowerCase().includes(query) ||
       (book.author || "").toLocaleLowerCase().includes(query))
    )
  );

  seriesGrid.innerHTML = "";
  bookCount.textContent = `${visibleSeries.length} ${visibleSeries.length === 1 ? "Serie" : "Serien"}`;

  for (const item of visibleSeries) {
    const members = books
      .filter(book => book.series_id === item.id)
      .sort((a, b) => (a.series_index ?? 999999) - (b.series_index ?? 999999));

    const card = document.createElement("article");
    card.className = "series-card";
    card.tabIndex = 0;
    const covers = members.slice(0, 3).map(book =>
      `<img src="${api(`books/${book.id}/cover`)}" alt="" onerror="this.outerHTML='<div class=&quot;series-cover-placeholder&quot;>Kein Cover</div>'">`
    ).join("");
    const placeholders = Array.from(
      {length: Math.max(0, 3 - Math.min(3, members.length))},
      () => `<div class="series-cover-placeholder">Kein Cover</div>`
    ).join("");

    card.innerHTML = `
      <div class="series-covers">${covers}${placeholders}</div>
      <div class="series-card-body">
        <h2>${esc(item.name)}</h2>
        <p>${item.book_count} ${item.book_count === 1 ? "Buch" : "Bücher"}</p>
      </div>
    `;
    card.addEventListener("click", () => showSeries(item.id));
    card.addEventListener("keydown", event => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        showSeries(item.id);
      }
    });
    seriesGrid.appendChild(card);
  }
}

function seriesOptions(selected) {
  return `<option value="">Keine Serie</option>` + series.map(item =>
    `<option value="${esc(item.id)}" ${item.id === selected ? "selected" : ""}>${esc(item.name)}</option>`
  ).join("");
}

async function showBook(id) {
  const response = await fetch(api(`books/${id}`));
  const book = await response.json();
  const cover = api(`books/${book.id}/cover`);
  detailContent.innerHTML = `
    <div class="detail">
      <img class="detail-cover" src="${cover}" alt="Cover von ${esc(book.title)}"
           onerror="this.style.visibility='hidden'">
      <div>
        <h2>${esc(book.title)}</h2>
        ${book.subtitle ? `<p class="subtitle">${esc(book.subtitle)}</p>` : ""}
        <p class="detail-author">${esc(book.author || "Autor unbekannt")}</p>

        <div class="detail-top-actions">
          <button class="secondary" id="editBook">Bearbeiten</button>
          <button class="secondary" id="refreshMetadata">Metadaten erneut suchen</button>
        </div>

        <p class="description">${esc(book.description || "Noch keine Zusammenfassung vorhanden.")}</p>

        <dl class="meta">
          ${book.series_name ? `<dt>Serie</dt><dd>${esc(book.series_name)}${book.series_index ? ` · Band ${esc(formatSeriesIndex(book.series_index))}` : ""}</dd>` : ""}
          <dt>ISBN</dt><dd>${esc(book.isbn || "–")}</dd>
          <dt>Verlag</dt><dd>${esc(book.publisher || "–")}</dd>
          <dt>Erschienen</dt><dd>${esc(book.published_date || "–")}</dd>
          <dt>Sprache</dt><dd>${esc(book.language || "–")}</dd>
          <dt>Format</dt><dd>${esc(book.format)}</dd>
          <dt>Dateigröße</dt><dd>${esc(formatBytes(book.file_size))}</dd>
          <dt>Metadaten</dt><dd>${esc(book.metadata_source || "–")}</dd>
        </dl>
        <div class="actions">
          <button class="primary" id="shareBook">Teilen / In Dateien sichern</button>
          <a class="secondary" href="${api(`books/${book.id}/download`)}" target="_blank" rel="noopener">Direkter Download</a>
        </div>
        <p class="share-note">Auf iPhone/iPad öffnet „Teilen / In Dateien sichern“ nach Möglichkeit das iOS-Teilen-Menü.</p>
      </div>
    </div>
  `;
  if (!dialog.open) dialog.showModal();

  document.getElementById("editBook").addEventListener("click", () => showEditBook(book));

  document.getElementById("shareBook").addEventListener("click", async event => {
    const button = event.currentTarget;
    button.disabled = true;
    button.textContent = "Datei wird vorbereitet …";
    try {
      const fileResponse = await fetch(api(`books/${book.id}/download`));
      if (!fileResponse.ok) throw new Error("Datei konnte nicht geladen werden.");
      const blob = await fileResponse.blob();
      const mime = book.format === "PDF" ? "application/pdf" : "application/epub+zip";
      const file = new File([blob], book.file_name, {type: mime});

      if (navigator.share && (!navigator.canShare || navigator.canShare({files: [file]}))) {
        await navigator.share({files: [file], title: book.title});
      } else {
        const objectUrl = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = objectUrl;
        link.download = book.file_name;
        link.target = "_blank";
        document.body.appendChild(link);
        link.click();
        link.remove();
        setTimeout(() => URL.revokeObjectURL(objectUrl), 60000);
      }
    } catch (error) {
      if (error.name !== "AbortError") {
        window.open(api(`books/${book.id}/open`), "_blank");
      }
    } finally {
      button.disabled = false;
      button.textContent = "Teilen / In Dateien sichern";
    }
  });

  document.getElementById("refreshMetadata").addEventListener("click", async event => {
    event.currentTarget.disabled = true;
    event.currentTarget.textContent = "Suche läuft …";
    try {
      const refresh = await fetch(api(`books/${book.id}/refresh-metadata`), {method: "POST"});
      if (!refresh.ok) throw new Error("Metadatensuche fehlgeschlagen");
      await loadData();
      await showBook(book.id);
    } catch (error) {
      event.currentTarget.disabled = false;
      event.currentTarget.textContent = "Metadaten erneut suchen";
      alert(error.message);
    }
  });
}

function showEditBook(book) {
  detailContent.innerHTML = `
    <div class="detail">
      <img class="detail-cover" src="${api(`books/${book.id}/cover`)}" alt="Cover von ${esc(book.title)}"
           onerror="this.style.visibility='hidden'">
      <div>
        <h2>Buch bearbeiten</h2>
        <form id="editBookForm" class="edit-form">
          <label>Titel
            <input name="title" required value="${esc(book.title || "")}">
          </label>

          <label>Untertitel
            <input name="subtitle" value="${esc(book.subtitle || "")}">
          </label>

          <label>Autor
            <input name="author" value="${esc(book.author || "")}">
          </label>

          <label>Zusammenfassung
            <textarea name="description">${esc(book.description || "")}</textarea>
          </label>

          <div class="edit-grid">
            <label>ISBN
              <input name="isbn" value="${esc(book.isbn || "")}">
            </label>
            <label>Verlag
              <input name="publisher" value="${esc(book.publisher || "")}">
            </label>
            <label>Erscheinungsdatum
              <input name="published_date" value="${esc(book.published_date || "")}">
            </label>
            <label>Sprache
              <input name="language" value="${esc(book.language || "")}">
            </label>
          </div>

          <div class="edit-grid">
            <label>Serie
              <select name="series_id">${seriesOptions(book.series_id)}</select>
            </label>
            <label>Band
              <input name="series_index" type="number" min="0.1" step="0.1"
                     value="${book.series_index == null ? "" : esc(formatSeriesIndex(book.series_index))}">
            </label>
          </div>

          <div class="edit-actions">
            <button class="primary" type="submit">Änderungen speichern</button>
            <button class="secondary" type="button" id="cancelEdit">Abbrechen</button>
          </div>
        </form>
      </div>
    </div>
  `;

  document.getElementById("cancelEdit").addEventListener("click", () => showBook(book.id));
  document.getElementById("editBookForm").addEventListener("submit", async event => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const payload = Object.fromEntries(form.entries());

    const response = await fetch(api(`books/${book.id}`), {
      method: "PATCH",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payload)
    });
    const result = await response.json();
    if (!response.ok) {
      alert(result.error || "Änderungen konnten nicht gespeichert werden.");
      return;
    }

    await loadData();
    await showBook(book.id);
  });
}

function showSeries(seriesId) {
  const item = series.find(entry => entry.id === seriesId);
  if (!item) return;

  const members = books
    .filter(book => book.series_id === seriesId)
    .sort((a, b) => {
      const ai = a.series_index ?? 999999;
      const bi = b.series_index ?? 999999;
      if (ai !== bi) return ai - bi;
      return (a.title || "").localeCompare(b.title || "", "de");
    });

  detailContent.innerHTML = `
    <div class="detail">
      <div></div>
      <div>
        <div class="series-detail-header">
          <p class="eyebrow">SERIE</p>
          <h2>${esc(item.name)}</h2>
          <p class="subtitle">${members.length} ${members.length === 1 ? "Buch" : "Bücher"}</p>
        </div>
        <div class="series-detail-list">
          ${members.length ? members.map(book => `
            <div class="series-detail-book" data-book-id="${esc(book.id)}">
              <img src="${api(`books/${book.id}/cover`)}" alt="">
              <div>
                <h4>${book.series_index ? `Band ${esc(formatSeriesIndex(book.series_index))}: ` : ""}${esc(book.title)}</h4>
                <p>${esc(book.author || "Autor unbekannt")}</p>
              </div>
            </div>
          `).join("") : "<p>Dieser Serie sind noch keine Bücher zugeordnet.</p>"}
        </div>
      </div>
    </div>
  `;

  if (!dialog.open) dialog.showModal();
  detailContent.querySelectorAll(".series-detail-book").forEach(row => {
    row.addEventListener("click", () => showBook(row.dataset.bookId));
  });
}

function renderSeriesManager() {
  seriesList.innerHTML = series.length ? "" : "<p>Noch keine Serien angelegt.</p>";
  for (const item of series) {
    const row = document.createElement("div");
    row.className = "series-item";
    row.innerHTML = `
      <input class="series-edit-name" value="${esc(item.name)}" maxlength="160">
      <small>${item.book_count} ${item.book_count === 1 ? "Buch" : "Bücher"}</small>
      <div>
        <button class="secondary save-series">Speichern</button>
        <button class="danger delete-series">Löschen</button>
      </div>
    `;
    row.querySelector(".save-series").addEventListener("click", async () => {
      const name = row.querySelector(".series-edit-name").value.trim();
      const response = await fetch(api(`series/${item.id}`), {
        method: "PATCH",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({name})
      });
      const result = response.status === 204 ? {} : await response.json();
      if (!response.ok) return alert(result.error || "Serie konnte nicht geändert werden.");
      await loadData();
      renderSeriesManager();
    });
    row.querySelector(".delete-series").addEventListener("click", async () => {
      if (!confirm(`Serie „${item.name}“ löschen? Die Bücher bleiben erhalten und werden nur aus der Serie entfernt.`)) return;
      const response = await fetch(api(`series/${item.id}`), {method: "DELETE"});
      if (!response.ok) return alert("Serie konnte nicht gelöscht werden.");
      await loadData();
      renderSeriesManager();
    });
    seriesList.appendChild(row);
  }
}

async function uploadFiles(files) {
  if (!files.length) return;
  uploadStatus.classList.remove("hidden", "error");

  for (let i = 0; i < files.length; i++) {
    const file = files[i];
    uploadStatus.textContent = `${i + 1}/${files.length}: ${file.name} wird verarbeitet …`;
    const form = new FormData();
    form.append("file", file);

    try {
      const response = await fetch(api("books"), {method: "POST", body: form});
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "Upload fehlgeschlagen");
    } catch (error) {
      uploadStatus.classList.add("error");
      uploadStatus.textContent = `${file.name}: ${error.message}`;
      await loadData();
      return;
    }
  }

  uploadStatus.textContent = `${files.length} ${files.length === 1 ? "Buch wurde" : "Bücher wurden"} hinzugefügt.`;
  fileInput.value = "";
  await loadData();
  window.setTimeout(() => uploadStatus.classList.add("hidden"), 3500);
}

uploadButton.addEventListener("click", () => fileInput.click());
emptyUploadButton.addEventListener("click", () => fileInput.click());
fileInput.addEventListener("change", () => uploadFiles([...fileInput.files]));
searchInput.addEventListener("input", render);
seriesFilter.addEventListener("change", render);
booksViewButton.addEventListener("click", () => setView("books"));
seriesViewButton.addEventListener("click", () => setView("series"));

closeDialog.addEventListener("click", () => dialog.close());
dialog.addEventListener("click", event => {
  if (event.target === dialog) dialog.close();
});

settingsButton.addEventListener("click", () => {
  renderSeriesManager();
  settingsDialog.showModal();
});
closeSettingsDialog.addEventListener("click", () => settingsDialog.close());
settingsDialog.addEventListener("click", event => {
  if (event.target === settingsDialog) settingsDialog.close();
});
seriesForm.addEventListener("submit", async event => {
  event.preventDefault();
  const name = seriesName.value.trim();
  if (!name) return;
  const response = await fetch(api("series"), {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({name})
  });
  const result = await response.json();
  if (!response.ok) return alert(result.error || "Serie konnte nicht angelegt werden.");
  seriesName.value = "";
  await loadData();
  renderSeriesManager();
});

loadData().catch(error => {
  uploadStatus.classList.remove("hidden");
  uploadStatus.classList.add("error");
  uploadStatus.textContent = `Bibliothek konnte nicht geladen werden: ${error.message}`;
});

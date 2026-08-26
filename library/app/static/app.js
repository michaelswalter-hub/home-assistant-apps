const grid = document.getElementById("libraryGrid");
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

const seriesDialog = document.getElementById("seriesDialog");
const manageSeriesButton = document.getElementById("manageSeriesButton");
const closeSeriesDialog = document.getElementById("closeSeriesDialog");
const seriesForm = document.getElementById("seriesForm");
const seriesName = document.getElementById("seriesName");
const seriesList = document.getElementById("seriesList");

let books = [];
let series = [];

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

function render() {
  const query = searchInput.value.trim().toLocaleLowerCase();
  const selectedSeries = seriesFilter.value;
  const filtered = books.filter(book =>
    (!query ||
      (book.title || "").toLocaleLowerCase().includes(query) ||
      (book.author || "").toLocaleLowerCase().includes(query) ||
      (book.series_name || "").toLocaleLowerCase().includes(query)) &&
    (!selectedSeries || book.series_id === selectedSeries)
  );

  filtered.sort((a, b) => {
    if (selectedSeries) {
      const ai = a.series_index ?? Number.MAX_SAFE_INTEGER;
      const bi = b.series_index ?? Number.MAX_SAFE_INTEGER;
      if (ai !== bi) return ai - bi;
    }
    return (a.title || "").localeCompare(b.title || "", "de", {sensitivity: "base"});
  });

  grid.innerHTML = "";
  bookCount.textContent = `${filtered.length} ${filtered.length === 1 ? "Buch" : "Bücher"}`;
  emptyState.classList.toggle("hidden", books.length !== 0);

  for (const book of filtered) {
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
        <p class="description">${esc(book.description || "Noch keine Zusammenfassung vorhanden.")}</p>

        <div class="series-assignment">
          <h3>Serie</h3>
          <div class="series-row">
            <select id="bookSeries" class="select">${seriesOptions(book.series_id)}</select>
            <input id="bookSeriesIndex" class="series-index-input" type="number"
                   min="0.1" step="0.1" placeholder="Band"
                   value="${book.series_index == null ? "" : esc(formatSeriesIndex(book.series_index))}">
            <button id="saveBookSeries" class="secondary">Speichern</button>
          </div>
        </div>

        <dl class="meta">
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
          <button class="secondary" id="refreshMetadata">Metadaten erneut suchen</button>
        </div>
        <p class="share-note">Auf iPhone/iPad öffnet „Teilen / In Dateien sichern“ nach Möglichkeit das iOS-Teilen-Menü. Dort kannst du „In Dateien sichern“ wählen.</p>
      </div>
    </div>
  `;
  if (!dialog.open) dialog.showModal();

  document.getElementById("saveBookSeries").addEventListener("click", async event => {
    event.currentTarget.disabled = true;
    const selected = document.getElementById("bookSeries").value || null;
    const index = document.getElementById("bookSeriesIndex").value || null;
    const response = await fetch(api(`books/${book.id}/series`), {
      method: "PATCH",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({series_id: selected, series_index: index})
    });
    const result = await response.json();
    if (!response.ok) {
      alert(result.error || "Serie konnte nicht gespeichert werden.");
      event.currentTarget.disabled = false;
      return;
    }
    await loadData();
    await showBook(book.id);
  });

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
        await navigator.share({
          files: [file],
          title: book.title
        });
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
        // Last fallback: inline/open response. PDFs can be handled by iOS Quick Look/Safari.
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
closeDialog.addEventListener("click", () => dialog.close());
dialog.addEventListener("click", event => {
  if (event.target === dialog) dialog.close();
});

manageSeriesButton.addEventListener("click", () => {
  renderSeriesManager();
  seriesDialog.showModal();
});
closeSeriesDialog.addEventListener("click", () => seriesDialog.close());
seriesDialog.addEventListener("click", event => {
  if (event.target === seriesDialog) seriesDialog.close();
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

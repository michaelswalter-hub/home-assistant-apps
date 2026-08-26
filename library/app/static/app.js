const grid = document.getElementById("libraryGrid");
const emptyState = document.getElementById("emptyState");
const bookCount = document.getElementById("bookCount");
const searchInput = document.getElementById("searchInput");
const fileInput = document.getElementById("fileInput");
const uploadButton = document.getElementById("uploadButton");
const emptyUploadButton = document.getElementById("emptyUploadButton");
const uploadStatus = document.getElementById("uploadStatus");
const dialog = document.getElementById("detailDialog");
const detailContent = document.getElementById("detailContent");
const closeDialog = document.getElementById("closeDialog");
const template = document.getElementById("bookTemplate");

let books = [];

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

function esc(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

async function loadBooks() {
  const response = await fetch(api("books"));
  books = await response.json();
  render();
}

function render() {
  const query = searchInput.value.trim().toLocaleLowerCase();
  const filtered = books.filter(book =>
    !query ||
    (book.title || "").toLocaleLowerCase().includes(query) ||
    (book.author || "").toLocaleLowerCase().includes(query)
  );

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
          <a class="primary" href="${api(`books/${book.id}/download`)}">Herunterladen</a>
          <button class="secondary" id="refreshMetadata">Metadaten erneut suchen</button>
        </div>
      </div>
    </div>
  `;
  dialog.showModal();
  document.getElementById("refreshMetadata").addEventListener("click", async event => {
    event.currentTarget.disabled = true;
    event.currentTarget.textContent = "Suche läuft …";
    try {
      const refresh = await fetch(api(`books/${book.id}/refresh-metadata`), {method: "POST"});
      if (!refresh.ok) throw new Error("Metadatensuche fehlgeschlagen");
      await loadBooks();
      await showBook(book.id);
    } catch (error) {
      event.currentTarget.disabled = false;
      event.currentTarget.textContent = "Metadaten erneut suchen";
      alert(error.message);
    }
  });
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
      await loadBooks();
      return;
    }
  }

  uploadStatus.textContent = `${files.length} ${files.length === 1 ? "Buch wurde" : "Bücher wurden"} hinzugefügt.`;
  fileInput.value = "";
  await loadBooks();
  window.setTimeout(() => uploadStatus.classList.add("hidden"), 3500);
}

uploadButton.addEventListener("click", () => fileInput.click());
emptyUploadButton.addEventListener("click", () => fileInput.click());
fileInput.addEventListener("change", () => uploadFiles([...fileInput.files]));
searchInput.addEventListener("input", render);
closeDialog.addEventListener("click", () => dialog.close());
dialog.addEventListener("click", event => {
  if (event.target === dialog) dialog.close();
});

loadBooks().catch(error => {
  uploadStatus.classList.remove("hidden");
  uploadStatus.classList.add("error");
  uploadStatus.textContent = `Bibliothek konnte nicht geladen werden: ${error.message}`;
});

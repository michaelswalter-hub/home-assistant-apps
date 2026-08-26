const grid = document.getElementById("libraryGrid");
const seriesGrid = document.getElementById("seriesGrid");
const emptyState = document.getElementById("emptyState");
const bookCount = document.getElementById("bookCount");
const searchInput = document.getElementById("searchInput");
const ratingFilter = document.getElementById("ratingFilter");
const personFilter = document.getElementById("personFilter");
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
const metadataDialog = document.getElementById("metadataDialog");
const metadataCandidates = document.getElementById("metadataCandidates");
const closeMetadata = document.getElementById("closeMetadata");
const readerDialog = document.getElementById("readerDialog");
const readerTitle = document.getElementById("readerTitle");
const readerContent = document.getElementById("readerContent");
const closeReader = document.getElementById("closeReader");
const readerFontDown = document.getElementById("readerFontDown");
const readerFontUp = document.getElementById("readerFontUp");
const closeSettingsDialog = document.getElementById("closeSettingsDialog");
const seriesForm = document.getElementById("seriesForm");
const seriesName = document.getElementById("seriesName");
const seriesList = document.getElementById("seriesList");
const genreForm = document.getElementById("genreForm");
const genreName = document.getElementById("genreName");
const genreList = document.getElementById("genreList");
const aiSettingsForm = document.getElementById("aiSettingsForm");
const aiEnabled = document.getElementById("aiEnabled");
const aiMode = document.getElementById("aiMode");
const aiModel = document.getElementById("aiModel");
const openaiApiKey = document.getElementById("openaiApiKey");
const apiKeyStatus = document.getElementById("apiKeyStatus");
const clearApiKey = document.getElementById("clearApiKey");
const googleBooksSettingsForm = document.getElementById("googleBooksSettingsForm");
const googleBooksApiKey = document.getElementById("googleBooksApiKey");
const googleBooksKeyStatus = document.getElementById("googleBooksKeyStatus");
const clearGoogleBooksApiKey = document.getElementById("clearGoogleBooksApiKey");

let books = [];
let series = [];
let genres = [];
let currentView = "books";
let selectedRating = 0;
let selectedPerson = "";
let appSettings = {ai_enabled: false, ai_mode: "fallback", ai_model: "gpt-5.4-mini", openai_api_key_configured: false, google_books_api_key_configured: false};

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
  const [bookResponse, seriesResponse, genreResponse, settingsResponse] = await Promise.all([
    fetch(api("books")),
    fetch(api("series")),
    fetch(api("genres")),
    fetch(api("settings"))
  ]);

  if (!bookResponse.ok) throw new Error("Bücher konnten nicht geladen werden.");
  if (!seriesResponse.ok) throw new Error("Serien konnten nicht geladen werden.");
  if (!genreResponse.ok) throw new Error("Genres konnten nicht geladen werden.");

  const loadedBooks = await bookResponse.json();
  const loadedSeries = await seriesResponse.json();
  const loadedGenres = await genreResponse.json();

  books = Array.isArray(loadedBooks) ? loadedBooks : [];
  series = Array.isArray(loadedSeries) ? loadedSeries : [];
  genres = Array.isArray(loadedGenres) ? loadedGenres : [];

  if (settingsResponse.ok) {
    appSettings = await settingsResponse.json();
  }
  render();
}

function bookIsHidden(book) {
  return (book.genres || []).some(genre => Boolean(genre.hidden));
}

function visibleBookGenres(book) {
  return (book.genres || []).filter(genre => !genre.hidden);
}

function setView(view) {
  currentView = view;
  booksViewButton.classList.toggle("active", view === "books");
  seriesViewButton.classList.toggle("active", view === "series");
  render();
}


function ratingStarsHtml(book, className = "book-rating-star") {
  const rating = Number(book.rating || 0);
  return Array.from({length: 5}, (_, index) => {
    const value = index + 1;
    return `<button type="button" class="${className}${value <= rating ? " active" : ""}" data-value="${value}" aria-label="${value} Sterne">★</button>`;
  }).join("");
}


function setRatingVisual(container, rating) {
  if (!container) return;
  const numericRating = Number(rating || 0);
  container.querySelectorAll(".book-rating-star").forEach(star => {
    const value = Number(star.dataset.value);
    star.classList.toggle("active", value <= numericRating);
  });
}

async function setBookRating(bookId, rating) {
  const response = await fetch(api(`books/${bookId}/rating`), {
    method: "PATCH",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({rating})
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "Bewertung konnte nicht gespeichert werden.");

  const index = books.findIndex(book => book.id === bookId);
  if (index >= 0) books[index] = result;

  // Re-render the overview after persistence so filters and sort state stay correct.
  render();
  return result;
}

function bindRatingButtons(container, book) {
  setRatingVisual(container, book.rating || 0);

  container.querySelectorAll(".book-rating-star").forEach(button => {
    button.addEventListener("click", async event => {
      event.preventDefault();
      event.stopPropagation();

      const value = Number(button.dataset.value);
      const previous = Number(book.rating || 0);
      const next = previous === value ? 0 : value;

      // Update all five stars immediately, so e.g. selecting 2 lights 1 + 2.
      book.rating = next;
      setRatingVisual(container, next);

      try {
        const updated = await setBookRating(book.id, next);
        book.rating = updated.rating;
      } catch (error) {
        book.rating = previous;
        setRatingVisual(container, previous);
        alert(error.message);
      }
    });
  });
}


function genreSearchMatch(query, genreName) {
  const q = String(query || "").trim().toLocaleLowerCase();
  const genre = String(genreName || "").trim().toLocaleLowerCase();
  if (!q || !genre) return false;

  // A genre should only trigger once the user has typed most of its name.
  // Example: "Fan" should not already reveal "Fantasy", while "Fantas" should.
  const minimumLength = Math.max(3, Math.ceil(genre.length * 0.7));
  return q.length >= minimumLength && genre.includes(q);
}

function filteredBooks() {
  const query = searchInput.value.trim().toLocaleLowerCase();

  return books.filter(book => {
    // Bücher mit Serienzuordnung werden ausschließlich in der Serienansicht gezeigt.
    if (book.series_id) return false;

    const genreMatch = Boolean(query) && (book.genres || []).some(
      genre => genreSearchMatch(query, genre.name)
    );

    // Hidden genres hide books during normal browsing. A sufficiently complete
    // genre search deliberately reveals them again.
    if (bookIsHidden(book) && !genreMatch) return false;
    if (selectedRating && Number(book.rating || 0) !== selectedRating) return false;
    if (selectedPerson && book.person !== selectedPerson) return false;

    return (
      !query ||
      (book.title || "").toLocaleLowerCase().includes(query) ||
      (book.author || "").toLocaleLowerCase().includes(query) ||
      genreMatch
    );
  });
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

  visibleBooks.sort((a, b) =>
    (a.title || "").localeCompare(b.title || "", "de", {sensitivity: "base"})
  );

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

    if (book.genres && book.genres.length) {
      const genreWrap = document.createElement("div");
      genreWrap.className = "book-card-genres";
      for (const genre of book.genres.slice(0, 3)) {
        const chip = document.createElement("span");
        chip.className = `book-card-genre${genre.hidden ? " hidden-genre" : ""}`;
        chip.textContent = genre.name;
        genreWrap.appendChild(chip);
      }
      card.appendChild(genreWrap);
    }

    if (book.person) {
      const personLine = document.createElement("p");
      personLine.className = "book-person";
      personLine.textContent = book.person;
      card.appendChild(personLine);
    }

    const ratingWrap = document.createElement("div");
    ratingWrap.className = "book-rating";
    ratingWrap.innerHTML = ratingStarsHtml(book);
    card.appendChild(ratingWrap);
    bindRatingButtons(ratingWrap, book);

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
      !bookIsHidden(book) &&
      (!selectedPerson || book.person === selectedPerson) &&
      ((book.title || "").toLocaleLowerCase().includes(query) ||
       (book.author || "").toLocaleLowerCase().includes(query))
    )
  );

  seriesGrid.innerHTML = "";
  bookCount.textContent = `${visibleSeries.length} ${visibleSeries.length === 1 ? "Serie" : "Serien"}`;

  for (const item of visibleSeries) {
    const members = books
      .filter(book =>
        book.series_id === item.id &&
        !bookIsHidden(book) &&
        (!selectedPerson || book.person === selectedPerson)
      )
      .sort((a, b) => (a.series_index ?? 999999) - (b.series_index ?? 999999));

    if (!members.length) continue;

    const card = document.createElement("article");
    card.className = "series-card";
    card.tabIndex = 0;

    const firstBook = members[0] || null;
    const coverHtml = firstBook
      ? `<img src="${api(`books/${firstBook.id}/cover`)}" alt="Cover von ${esc(firstBook.title)}"
           onerror="this.outerHTML='<div class=&quot;series-cover-placeholder&quot;>Kein Cover</div>'">`
      : `<div class="series-cover-placeholder">Kein Cover</div>`;

    card.innerHTML = `
      <div class="series-covers single-cover">${coverHtml}</div>
      <div class="series-card-body">
        <h2>${esc(item.name)}</h2>
        <p>${members.length} ${members.length === 1 ? "Buch" : "Bücher"}</p>
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
  const cover = `${api(`books/${book.id}/cover`)}?v=${encodeURIComponent(book.updated_at || "")}`;
  detailContent.innerHTML = `
    <div class="detail">
      <img class="detail-cover" src="${cover}" alt="Cover von ${esc(book.title)}"
           onerror="this.style.visibility='hidden'">
      <div>
        <h2>${esc(book.title)}</h2>
        ${book.subtitle ? `<p class="subtitle">${esc(book.subtitle)}</p>` : ""}
        <p class="detail-author">${esc(book.author || "Autor unbekannt")}</p>
        <div id="detailRating" class="book-rating detail-rating">${ratingStarsHtml(book)}</div>
        ${(book.genres || []).length ? `<div class="genre-chips">${(book.genres || []).map(g => `<span class="genre-chip${g.hidden ? " hidden-genre" : ""}">${esc(g.name)}${g.hidden ? " · ausgeblendet" : ""}</span>`).join("")}</div>` : ""}

        <div class="detail-top-actions">
          <button class="secondary" id="editBook">Bearbeiten</button>
          <button class="secondary" id="refreshMetadata">Metadaten erneut suchen</button>
        </div>

        <p class="description">${esc(book.description || "Noch keine Zusammenfassung vorhanden.")}</p>

        <dl class="meta">
          ${book.person ? `<dt>Person</dt><dd>${esc(book.person)}</dd>` : ""}
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
          <button class="primary" id="readBook">Lesen</button>
          <button class="secondary" id="shareBook">Teilen / In Dateien sichern</button>
          <a class="secondary" href="${api(`books/${book.id}/download`)}" target="_blank" rel="noopener">Direkter Download</a>
          <button class="danger-filled" id="deleteBook">Buch löschen</button>
        </div>
        <p class="share-note">Auf iPhone/iPad öffnet „Teilen / In Dateien sichern“ nach Möglichkeit das iOS-Teilen-Menü.</p>
      </div>
    </div>
  `;
  if (!dialog.open) dialog.showModal();

  const detailRating = document.getElementById("detailRating");
  if (detailRating) bindRatingButtons(detailRating, book);

  document.getElementById("editBook").addEventListener("click", () => showEditBook(book));

  document.getElementById("readBook").addEventListener("click", () => openReader(book));

  document.getElementById("deleteBook").addEventListener("click", async () => {
    const confirmed = confirm(`„${book.title}“ wirklich löschen? Die gespeicherte Buchdatei wird ebenfalls entfernt.`);
    if (!confirmed) return;

    const response = await fetch(api(`books/${book.id}`), {method: "DELETE"});
    if (!response.ok) {
      const result = await response.json().catch(() => ({}));
      alert(result.error || "Buch konnte nicht gelöscht werden.");
      return;
    }

    dialog.close();
    await loadData();
  });

  document.getElementById("shareBook").addEventListener("click", async event => {
    const button = event.currentTarget;
    button.disabled = true;
    button.textContent = "Datei wird vorbereitet …";
    try {
      const fileResponse = await fetch(api(`books/${book.id}/download`));
      if (!fileResponse.ok) throw new Error("Datei konnte nicht geladen werden.");
      const blob = await fileResponse.blob();
      const mime = {
        PDF: "application/pdf",
        EPUB: "application/epub+zip",
        MOBI: "application/x-mobipocket-ebook"
      }[book.format] || "application/octet-stream";
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
      await showMetadataCandidates(book);
    } catch (error) {
      alert(error.message);
    } finally {
      event.currentTarget.disabled = false;
      event.currentTarget.textContent = "Metadaten erneut suchen";
    }
  });
}


async function loadCoverGallery(book) {
  const gallery = document.getElementById("coverGallery");
  if (!gallery) return;

  try {
    const response = await fetch(api(`books/${book.id}/covers`));
    if (!response.ok) throw new Error("Cover konnten nicht geladen werden.");
    const covers = await response.json();

    if (!Array.isArray(covers) || !covers.length) {
      gallery.innerHTML = "<p>Für dieses Buch ist noch kein Cover gespeichert.</p>";
      return;
    }

    gallery.innerHTML = "";

    for (const cover of covers) {
      const card = document.createElement("div");
      card.className = `cover-choice${cover.active ? " active" : ""}`;
      card.innerHTML = `
        <button type="button" class="cover-select" title="Als Hauptcover verwenden">
          <img src="${cover.url}?v=${Date.now()}" alt="Gespeichertes Cover">
          ${cover.active ? `<span class="cover-active-badge">Aktiv</span>` : ""}
        </button>
        <button type="button" class="cover-delete" title="Cover löschen">Löschen</button>
      `;

      card.querySelector(".cover-select").addEventListener("click", async () => {
        if (cover.active) return;

        const response = await fetch(
          api(`books/${book.id}/covers/${encodeURIComponent(cover.id)}/active`),
          {method: "PATCH"}
        );
        const result = await response.json();
        if (!response.ok) {
          alert(result.error || "Cover konnte nicht ausgewählt werden.");
          return;
        }

        const bookIndex = books.findIndex(item => item.id === book.id);
        if (bookIndex >= 0) books[bookIndex] = result;

        book.updated_at = result.updated_at;
        book.has_cover = result.has_cover;
        await loadCoverGallery(book);

        const preview = document.querySelector("#detailContent .detail-cover");
        if (preview) {
          preview.style.visibility = "visible";
          preview.src = `${api(`books/${book.id}/cover`)}?v=${encodeURIComponent(result.updated_at || Date.now())}`;
        }
      });

      card.querySelector(".cover-delete").addEventListener("click", async event => {
        event.stopPropagation();

        const confirmed = confirm(
          cover.active
            ? "Dieses Cover ist aktuell ausgewählt. Wirklich löschen? Falls weitere Cover vorhanden sind, wird eines davon automatisch gewählt."
            : "Dieses Cover wirklich löschen?"
        );
        if (!confirmed) return;

        const response = await fetch(
          api(`books/${book.id}/covers/${encodeURIComponent(cover.id)}`),
          {method: "DELETE"}
        );
        const result = await response.json();
        if (!response.ok) {
          alert(result.error || "Cover konnte nicht gelöscht werden.");
          return;
        }

        const bookIndex = books.findIndex(item => item.id === book.id);
        if (bookIndex >= 0) books[bookIndex] = result;

        book.updated_at = result.updated_at;
        book.has_cover = result.has_cover;
        await loadCoverGallery(book);

        const preview = document.querySelector("#detailContent .detail-cover");
        if (preview) {
          if (result.has_cover) {
            preview.style.visibility = "visible";
            preview.src = `${api(`books/${book.id}/cover`)}?v=${encodeURIComponent(result.updated_at || Date.now())}`;
          } else {
            preview.style.visibility = "hidden";
          }
        }
      });

      gallery.appendChild(card);
    }
  } catch (error) {
    gallery.innerHTML = `<p>${esc(error.message)}</p>`;
  }
}

function showEditBook(book) {
  detailContent.innerHTML = `
    <div class="detail">
      <div>
        <img class="detail-cover" src="${api(`books/${book.id}/cover`)}?v=${encodeURIComponent(book.updated_at || "")}" alt="Cover von ${esc(book.title)}"
             onerror="this.style.visibility='hidden'">
      </div>
      <div>
        <h2>Buch bearbeiten</h2>

        <section class="cover-manager">
          <div class="cover-manager-head">
            <h3>Cover auswählen</h3>
            <span class="settings-help">Antippen = als Hauptcover verwenden</span>
          </div>
          <div id="coverGallery" class="cover-gallery">
            <p>Cover werden geladen …</p>
          </div>
        </section>

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

          <fieldset class="genre-picker">
            <legend>Genres</legend>
            <div class="genre-picker-list">
              ${genres.length ? genres.map(genre => `
                <label class="genre-pick">
                  <input type="checkbox" name="genre_ids" value="${esc(genre.id)}"
                    ${(book.genres || []).some(bg => bg.id === genre.id) ? "checked" : ""}>
                  <span>${esc(genre.name)}${genre.hidden ? " (ausgeblendet)" : ""}</span>
                </label>
              `).join("") : `<p>Noch keine Genres angelegt. Du kannst sie über das Zahnrad in den Einstellungen erstellen.</p>`}
            </div>
          </fieldset>

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

          <div class="person-edit-row">
            <label>Person
              <select name="person">
                <option value="" ${!book.person ? "selected" : ""}>Nicht zugeordnet</option>
                <option value="Hase" ${book.person === "Hase" ? "selected" : ""}>Hase</option>
                <option value="HoBi" ${book.person === "HoBi" ? "selected" : ""}>HoBi</option>
              </select>
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

  loadCoverGallery(book);
  document.getElementById("cancelEdit").addEventListener("click", () => showBook(book.id));
  document.getElementById("editBookForm").addEventListener("submit", async event => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const payload = Object.fromEntries(form.entries());
    payload.genre_ids = form.getAll("genre_ids");

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




function populateGoogleBooksSettings() {
  if (!googleBooksSettingsForm) return;
  googleBooksApiKey.value = "";
  googleBooksKeyStatus.textContent = appSettings.google_books_api_key_configured
    ? "Google Books API-Key ist hinterlegt."
    : "Kein Google Books API-Key hinterlegt – öffentliche API wird verwendet.";
}

function populateAiSettings() {
  if (!aiSettingsForm) return;
  aiEnabled.checked = Boolean(appSettings.ai_enabled);
  aiMode.value = appSettings.ai_mode || "fallback";
  aiModel.value = appSettings.ai_model || "gpt-5.4-mini";
  openaiApiKey.value = "";
  apiKeyStatus.textContent = appSettings.openai_api_key_configured
    ? "API-Key ist hinterlegt. Er wird aus Sicherheitsgründen nicht angezeigt."
    : "Noch kein API-Key hinterlegt.";
}

function renderGenreManager() {
  const container = document.getElementById("genreList");
  container.innerHTML = genres.length ? "" : "<p>Noch keine Genres angelegt.</p>";

  for (const genre of genres) {
    const row = document.createElement("div");
    row.className = "series-item genre-manager-item";
    row.innerHTML = `
      <input class="series-edit-name genre-edit-name" value="${esc(genre.name)}" maxlength="100">
      <label class="genre-hide-toggle" title="Bücher dieses Genres in der Übersicht ausblenden">
        <input type="checkbox" class="genre-hidden" ${genre.hidden ? "checked" : ""}>
        <span>Ausblenden</span>
      </label>
      <small>${genre.book_count} ${genre.book_count === 1 ? "Buch" : "Bücher"}</small>
      <div>
        <button class="secondary save-genre">Speichern</button>
        <button class="danger delete-genre">Löschen</button>
      </div>
    `;

    row.querySelector(".save-genre").addEventListener("click", async () => {
      const name = row.querySelector(".genre-edit-name").value.trim();
      const hidden = row.querySelector(".genre-hidden").checked;
      const response = await fetch(api(`genres/${genre.id}`), {
        method: "PATCH",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({name, hidden})
      });
      const result = await response.json();
      if (!response.ok) return alert(result.error || "Genre konnte nicht gespeichert werden.");
      await loadData();
      renderGenreManager();
    });

    row.querySelector(".genre-hidden").addEventListener("change", async event => {
      const response = await fetch(api(`genres/${genre.id}`), {
        method: "PATCH",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({hidden: event.target.checked})
      });
      const result = await response.json();
      if (!response.ok) {
        event.target.checked = !event.target.checked;
        return alert(result.error || "Einstellung konnte nicht gespeichert werden.");
      }
      await loadData();
      renderGenreManager();
    });

    row.querySelector(".delete-genre").addEventListener("click", async () => {
      if (!confirm(`Genre „${genre.name}“ löschen? Die Bücher bleiben erhalten.`)) return;
      const response = await fetch(api(`genres/${genre.id}`), {method: "DELETE"});
      if (!response.ok) return alert("Genre konnte nicht gelöscht werden.");
      await loadData();
      renderGenreManager();
    });

    container.appendChild(row);
  }
}



let readerFontSize = 18;

function applyReaderFontSize() {
  if (!readerContent || readerContent.classList.contains("pdf-mode")) return;
  readerContent.style.fontSize = `${readerFontSize}px`;
}

async function openReader(book) {
  if (!readerDialog || !readerContent) {
    alert("Reader ist nicht verfügbar.");
    return;
  }

  readerTitle.textContent = book.title || "Buch lesen";
  readerContent.classList.remove("pdf-mode");
  readerContent.style.fontSize = "";
  readerContent.textContent = "Buch wird vorbereitet …";
  readerDialog.showModal();

  try {
    const response = await fetch(api(`books/${book.id}/reader-content`));
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Buch konnte nicht geöffnet werden.");

    if (result.format === "PDF") {
      readerContent.classList.add("pdf-mode");
      readerContent.innerHTML = `<iframe src="${result.url}" title="${esc(book.title)}"></iframe>`;
    } else {
      readerContent.classList.remove("pdf-mode");
      readerContent.textContent = result.content || "";
      applyReaderFontSize();
    }
  } catch (error) {
    readerContent.classList.remove("pdf-mode");
    readerContent.textContent = error.message;
  }
}

function amazonSearchUrl(candidate) {
  const query = candidate.isbn || [candidate.title, candidate.author].filter(Boolean).join(" ");
  return `https://www.amazon.de/s?k=${encodeURIComponent(query)}`;
}


function renderAiCandidate(book, candidate) {
  const card = document.createElement("article");
  card.className = "metadata-candidate ai-candidate";
  const sources = Array.isArray(candidate.sources) ? candidate.sources : [];

  card.innerHTML = `
    <div>${candidate.cover_url ? `<img src="${esc(candidate.cover_url)}" alt="">` : `<div class="metadata-cover-placeholder"></div>`}</div>
    <div>
      <h3>${esc(candidate.title || book.title || "Ohne Titel")}</h3>
      <p>${esc(candidate.author || book.author || "Autor unbekannt")}</p>
      <p><strong>ISBN:</strong> ${esc(candidate.isbn || "–")}</p>
      <p><strong>Ausgabe:</strong> ${esc(candidate.published_date || "–")}${candidate.publisher ? ` · ${esc(candidate.publisher)}` : ""}</p>
      <p><strong>Quelle:</strong> <span class="metadata-source-badge">KI-Websuche</span></p>
      ${candidate.confidence ? `<p><strong>Sicherheit:</strong> ${esc(candidate.confidence)}</p>` : ""}
      ${candidate.notes ? `<p class="metadata-summary-preview">${esc(candidate.notes)}</p>` : ""}
      <p class="metadata-summary-preview">${esc(candidate.description || "Keine Zusammenfassung gefunden.")}</p>
      ${sources.length ? `<div class="ai-sources"><strong>Quellen:</strong>${sources.slice(0, 5).map(url => `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(url)}</a>`).join("")}</div>` : ""}
      <div class="metadata-candidate-actions">
        <button class="primary choose-ai-metadata" type="button">KI-Treffer übernehmen</button>
        <a class="secondary amazon-search" target="_blank" rel="noopener noreferrer">Auf Amazon suchen</a>
      </div>
    </div>
  `;

  card.querySelector(".amazon-search").href = amazonSearchUrl(candidate);
  card.querySelector(".choose-ai-metadata").addEventListener("click", async () => {
    const button = card.querySelector(".choose-ai-metadata");
    button.disabled = true;
    button.textContent = "Übernehme …";
    try {
      const apply = await fetch(api(`books/${book.id}/metadata-candidates/apply`), {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({candidate})
      });
      const result = await apply.json();
      if (!apply.ok) throw new Error(result.error || "Metadaten konnten nicht übernommen werden.");
      metadataDialog.close();
      await loadData();
      await showBook(book.id);
    } catch (error) {
      alert(error.message);
      button.disabled = false;
      button.textContent = "KI-Treffer übernehmen";
    }
  });

  return card;
}

async function runAiMetadataSearch(book, button) {
  if (button) {
    button.disabled = true;
    button.textContent = "KI recherchiert im Web …";
  }
  try {
    const response = await fetch(api(`books/${book.id}/metadata-ai`), {method: "POST"});
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "KI-Suche fehlgeschlagen.");
    metadataCandidates.appendChild(renderAiCandidate(book, result));
    if (button) button.remove();
  } finally {
    if (button && button.isConnected) {
      button.disabled = false;
      button.textContent = "Mit KI im Internet suchen";
    }
  }
}

async function showMetadataCandidates(book) {
  if (!metadataDialog || !metadataCandidates) {
    throw new Error("Die Metadaten-Auswahl konnte nicht geöffnet werden. Bitte die App aktualisieren und neu laden.");
  }

  metadataCandidates.innerHTML = "<p>Metadaten werden gesucht …</p>";
  metadataDialog.showModal();

  const [response, statusResponse] = await Promise.all([
    fetch(api(`books/${book.id}/metadata-candidates`)),
    fetch(api(`books/${book.id}/metadata-provider-status`))
  ]);

  if (!response.ok) throw new Error("Metadatensuche fehlgeschlagen.");
  const candidates = await response.json();

  let providerStatus = null;
  if (statusResponse.ok) {
    providerStatus = await statusResponse.json();
  }

  metadataCandidates.innerHTML = "";

  if (providerStatus && providerStatus.google_books) {
    const info = document.createElement("div");
    info.className = "metadata-provider-status";
    const google = providerStatus.google_books;
    if (google.ok) {
      info.textContent = `Google Books: HTTP ${google.status || 200} · ${google.count} angezeigte Treffer · ${google.total_items ?? 0} insgesamt${google.api_key_configured ? " · API-Key aktiv" : ""}`;
    } else {
      info.textContent = `Google Books Fehler${google.status ? ` HTTP ${google.status}` : ""}: ${google.error || "unbekannter Fehler"}${google.api_key_configured ? " · API-Key aktiv" : " · ohne API-Key"}`;
      info.classList.add("error");
    }
    metadataCandidates.appendChild(info);
  }

  if (!candidates.length) {
    const empty = document.createElement("p");
    empty.textContent = "Keine passenden Treffer gefunden.";
    metadataCandidates.appendChild(empty);
    return;
  }
  for (const candidate of candidates) {
    if (candidate.metadata_source === "KI-Websuche") {
      metadataCandidates.appendChild(renderAiCandidate(book, candidate));
      continue;
    }

    const card = document.createElement("article");
    card.className = "metadata-candidate";
    card.innerHTML = `
      <div>${candidate.cover_url ? `<img src="${esc(candidate.cover_url)}" alt="">` : `<div class="metadata-cover-placeholder"></div>`}</div>
      <div>
        <h3>${esc(candidate.title || "Ohne Titel")}</h3>
        <p>${esc(candidate.author || "Autor unbekannt")}</p>
        <p><strong>ISBN:</strong> ${esc(candidate.isbn || "–")}</p>
        <p><strong>Ausgabe:</strong> ${esc(candidate.published_date || "–")}${candidate.publisher ? ` · ${esc(candidate.publisher)}` : ""}</p>
        <p><strong>Quelle:</strong> <span class="metadata-source-badge">${esc(candidate.metadata_source || "Online")}</span></p>
        ${candidate.description_source ? `<p><strong>Zusammenfassung:</strong> ${esc(candidate.description_source)}</p>` : ""}
        <p class="metadata-summary-preview">${esc(candidate.description || "Keine Zusammenfassung in diesem Treffer.")}</p>
        <div class="metadata-candidate-actions">
          <button class="primary choose-metadata" type="button">Diesen Treffer übernehmen</button>
          <a class="secondary amazon-search" target="_blank" rel="noopener noreferrer">Auf Amazon suchen</a>
        </div>
      </div>`;
    card.querySelector(".amazon-search").href = amazonSearchUrl(candidate);
    card.querySelector(".choose-metadata").addEventListener("click", async () => {
      const button=card.querySelector(".choose-metadata"); button.disabled=true; button.textContent="Übernehme …";
      try {
        const apply=await fetch(api(`books/${book.id}/metadata-candidates/apply`),{
          method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({candidate})
        });
        const result=await apply.json();
        if(!apply.ok) throw new Error(result.error || "Metadaten konnten nicht übernommen werden.");
        metadataDialog.close(); await loadData(); await showBook(book.id);
      } catch(error) { alert(error.message); button.disabled=false; button.textContent="Diesen Treffer übernehmen"; }
    });
    metadataCandidates.appendChild(card);
  }

  if (appSettings.ai_enabled && appSettings.openai_api_key_configured) {
    const aiButton = document.createElement("button");
    aiButton.type = "button";
    aiButton.className = "secondary ai-search-button";
    aiButton.textContent = "Mit KI im Internet suchen";
    aiButton.addEventListener("click", async () => {
      try {
        await runAiMetadataSearch(book, aiButton);
      } catch (error) {
        alert(error.message);
      }
    });
    metadataCandidates.appendChild(aiButton);
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

if (ratingFilter) {
  const filterStars = [...ratingFilter.querySelectorAll(".rating-filter-star")];

  function paintRatingFilter() {
    filterStars.forEach(star => {
      const starValue = Number(star.dataset.rating);
      star.classList.toggle(
        "active",
        selectedRating > 0 && starValue <= selectedRating
      );
    });
  }

  filterStars.forEach(button => {
    button.addEventListener("click", () => {
      const value = Number(button.dataset.rating);

      // Clicking the active rating a second time switches the filter completely off.
      selectedRating = selectedRating === value ? 0 : value;
      paintRatingFilter();
      render();
    });
  });

  paintRatingFilter();
}

if (personFilter) {
  const personButtons = [...personFilter.querySelectorAll(".person-filter-button")];
  personButtons.forEach(button => {
    button.addEventListener("click", () => {
      selectedPerson = button.dataset.person || "";
      personButtons.forEach(item => {
        item.classList.toggle("active", (item.dataset.person || "") === selectedPerson);
      });
      render();
    });
  });
}

booksViewButton.addEventListener("click", () => setView("books"));
seriesViewButton.addEventListener("click", () => setView("series"));

closeDialog.addEventListener("click", () => dialog.close());
dialog.addEventListener("click", event => {
  if (event.target === dialog) dialog.close();
});


if (closeReader && readerDialog) {
  closeReader.addEventListener("click", () => readerDialog.close());
}
if (readerFontDown) {
  readerFontDown.addEventListener("click", () => {
    readerFontSize = Math.max(12, readerFontSize - 2);
    applyReaderFontSize();
  });
}
if (readerFontUp) {
  readerFontUp.addEventListener("click", () => {
    readerFontSize = Math.min(34, readerFontSize + 2);
    applyReaderFontSize();
  });
}

if (closeMetadata && metadataDialog) {
  
if (closeReader && readerDialog) {
  closeReader.addEventListener("click", () => readerDialog.close());
}
if (readerFontDown) {
  readerFontDown.addEventListener("click", () => {
    readerFontSize = Math.max(12, readerFontSize - 2);
    applyReaderFontSize();
  });
}
if (readerFontUp) {
  readerFontUp.addEventListener("click", () => {
    readerFontSize = Math.min(34, readerFontSize + 2);
    applyReaderFontSize();
  });
}

if (closeMetadata && metadataDialog) {
  closeMetadata.addEventListener("click", () => metadataDialog.close());
}
}

settingsButton.addEventListener("click", () => {
  renderSeriesManager();
  renderGenreManager();
  populateGoogleBooksSettings();
  populateAiSettings();
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


genreForm.addEventListener("submit", async event => {
  event.preventDefault();
  const name = genreName.value.trim();
  if (!name) return;
  const response = await fetch(api("genres"), {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({name})
  });
  const result = await response.json();
  if (!response.ok) return alert(result.error || "Genre konnte nicht angelegt werden.");
  genreName.value = "";
  await loadData();
  renderGenreManager();
});



if (googleBooksSettingsForm) {
  googleBooksSettingsForm.addEventListener("submit", async event => {
    event.preventDefault();
    const payload = {};
    if (googleBooksApiKey.value.trim()) {
      payload.google_books_api_key = googleBooksApiKey.value.trim();
    }
    const response = await fetch(api("settings"), {
      method: "PATCH",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payload)
    });
    const result = await response.json();
    if (!response.ok) {
      alert(result.error || "Google-Books-Einstellungen konnten nicht gespeichert werden.");
      return;
    }
    appSettings = result;
    populateGoogleBooksSettings();
    alert("Google-Books-Einstellungen gespeichert.");
  });

  clearGoogleBooksApiKey.addEventListener("click", async () => {
    if (!confirm("Google Books API-Key wirklich entfernen?")) return;
    const response = await fetch(api("settings"), {
      method: "PATCH",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({clear_google_books_api_key: true})
    });
    const result = await response.json();
    if (!response.ok) {
      alert(result.error || "Google Books API-Key konnte nicht entfernt werden.");
      return;
    }
    appSettings = result;
    populateGoogleBooksSettings();
  });
}

if (aiSettingsForm) {
  aiSettingsForm.addEventListener("submit", async event => {
    event.preventDefault();
    const payload = {
      ai_enabled: aiEnabled.checked,
      ai_mode: aiMode.value,
      ai_model: aiModel.value.trim() || "gpt-5.4-mini"
    };
    if (openaiApiKey.value.trim()) {
      payload.openai_api_key = openaiApiKey.value.trim();
    }

    const response = await fetch(api("settings"), {
      method: "PATCH",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payload)
    });
    const result = await response.json();
    if (!response.ok) {
      alert(result.error || "KI-Einstellungen konnten nicht gespeichert werden.");
      return;
    }
    appSettings = result;
    populateAiSettings();
    alert("KI-Einstellungen gespeichert.");
  });

  clearApiKey.addEventListener("click", async () => {
    if (!confirm("OpenAI API-Key wirklich entfernen?")) return;
    const response = await fetch(api("settings"), {
      method: "PATCH",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({clear_openai_api_key: true})
    });
    const result = await response.json();
    if (!response.ok) {
      alert(result.error || "API-Key konnte nicht entfernt werden.");
      return;
    }
    appSettings = result;
    populateAiSettings();
  });
}

loadData().catch(error => {
  uploadStatus.classList.remove("hidden");
  uploadStatus.classList.add("error");
  uploadStatus.textContent = `Bibliothek konnte nicht geladen werden: ${error.message}`;
});

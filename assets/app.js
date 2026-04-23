const DATASETS = [
  {
    key: "irs-current",
    label: "IRS current",
    path: "data/irs/current/forms.json",
  },
  {
    key: "irs-prior",
    label: "IRS prior",
    path: "data/irs/prior/forms.json",
  },
  {
    key: "states",
    label: "States",
    path: "data/states/forms.json",
  },
];

const MAX_RENDERED_RESULTS = 160;

const elements = {
  clearSearch: document.querySelector("#clearSearch"),
  emptyState: document.querySelector("#emptyState"),
  federalCount: document.querySelector("#federalCount"),
  fileFilter: document.querySelector("#fileFilter"),
  jurisdictionFilter: document.querySelector("#jurisdictionFilter"),
  loadStatus: document.querySelector("#loadStatus"),
  resultsList: document.querySelector("#resultsList"),
  searchInput: document.querySelector("#searchInput"),
  shownCount: document.querySelector("#shownCount"),
  stateCount: document.querySelector("#stateCount"),
  totalCount: document.querySelector("#totalCount"),
  typeFilter: document.querySelector("#typeFilter"),
  yearFilter: document.querySelector("#yearFilter"),
};

const state = {
  dataset: "all",
  records: [],
};

init();

async function init() {
  wireEvents();

  try {
    const payloads = await Promise.all(DATASETS.map(loadDataset));
    state.records = payloads.flatMap(({ config, payload }) =>
      payload.records.map((record) => normalizeRecord(config, record)),
    );
    populateFilters();
    updateTotals();
    applyFilters();
    elements.loadStatus.textContent = "Catalogs loaded";
  } catch (error) {
    elements.loadStatus.textContent = "Catalog data could not be loaded";
    elements.resultsList.innerHTML = "";
    elements.emptyState.hidden = false;
    console.error(error);
  }
}

function wireEvents() {
  document.querySelectorAll("[data-dataset]").forEach((button) => {
    button.addEventListener("click", () => {
      state.dataset = button.dataset.dataset;
      document
        .querySelectorAll("[data-dataset]")
        .forEach((item) => item.classList.toggle("is-active", item === button));
      applyFilters();
    });
  });

  elements.searchInput.addEventListener("input", debounce(applyFilters, 90));
  elements.clearSearch.addEventListener("click", () => {
    elements.searchInput.value = "";
    elements.searchInput.focus();
    applyFilters();
  });

  [
    elements.jurisdictionFilter,
    elements.typeFilter,
    elements.yearFilter,
    elements.fileFilter,
  ].forEach((element) => element.addEventListener("change", applyFilters));
}

async function loadDataset(config) {
  const response = await fetch(config.path);
  if (!response.ok) {
    throw new Error(`Could not load ${config.path}: ${response.status}`);
  }
  return { config, payload: await response.json() };
}

function normalizeRecord(config, record) {
  const isState = config.key === "states";
  const normalized = {
    category: isState ? record.tax_category || record.record_type || "" : record.kind || "",
    datasetKey: config.key,
    datasetLabel: config.label,
    documentUrl: isState ? record.document_url || "" : record.pdf_url || "",
    fileType: isState ? record.file_type || "" : "pdf",
    formNumber: isState ? record.form_number || "" : record.product_number || "",
    jurisdictionCode: isState ? record.jurisdiction_code : "IRS",
    jurisdictionName: isState ? record.jurisdiction_name : "Internal Revenue Service",
    recordType: isState ? record.record_type : "document",
    revisionDate: record.revision_date || "",
    sourcePageUrl: record.source_page_url || "",
    status: isState ? record.retrieval_status : "ok",
    title: record.title || "(untitled)",
    year: isState ? record.tax_year || "" : record.revision_year || "",
  };

  normalized.searchText = [
    normalized.title,
    normalized.formNumber,
    normalized.jurisdictionCode,
    normalized.jurisdictionName,
    normalized.category,
    normalized.year,
    normalized.datasetLabel,
    normalized.fileType,
  ]
    .join(" ")
    .toLowerCase();

  return normalized;
}

function populateFilters() {
  const jurisdictions = uniqueOptions(
    state.records.map((record) => [
      record.jurisdictionCode,
      record.jurisdictionCode === "IRS"
        ? "IRS"
        : `${record.jurisdictionName} (${record.jurisdictionCode})`,
    ]),
  );
  const types = uniqueOptions(
    state.records
      .filter((record) => record.category)
      .map((record) => [record.category, labelize(record.category)]),
  );
  const years = uniqueOptions(
    state.records
      .filter((record) => record.year)
      .map((record) => [record.year, record.year]),
  ).sort((a, b) => Number(b.value) - Number(a.value));
  const fileTypes = uniqueOptions(
    state.records
      .filter((record) => record.fileType)
      .map((record) => [record.fileType, record.fileType.toUpperCase()]),
  );

  fillSelect(elements.jurisdictionFilter, "All jurisdictions", jurisdictions);
  fillSelect(elements.typeFilter, "All types", types);
  fillSelect(elements.yearFilter, "All years", years);
  fillSelect(elements.fileFilter, "All files", fileTypes);
}

function uniqueOptions(entries) {
  const map = new Map();
  entries.forEach(([value, label]) => {
    if (value && !map.has(value)) {
      map.set(value, label);
    }
  });
  return [...map.entries()]
    .map(([value, label]) => ({ value, label }))
    .sort((a, b) => a.label.localeCompare(b.label, undefined, { numeric: true }));
}

function fillSelect(select, allLabel, options) {
  select.replaceChildren();
  select.append(new Option(allLabel, ""));
  options.forEach((option) => select.append(new Option(option.label, option.value)));
}

function updateTotals() {
  const total = state.records.length;
  const federal = state.records.filter((record) => record.jurisdictionCode === "IRS").length;
  const states = total - federal;

  elements.totalCount.textContent = formatNumber(total);
  elements.federalCount.textContent = formatNumber(federal);
  elements.stateCount.textContent = formatNumber(states);
}

function applyFilters() {
  const query = elements.searchInput.value.trim().toLowerCase();
  const terms = query.split(/\s+/).filter(Boolean);
  const jurisdiction = elements.jurisdictionFilter.value;
  const category = elements.typeFilter.value;
  const year = elements.yearFilter.value;
  const fileType = elements.fileFilter.value;

  const filtered = state.records
    .filter((record) => {
      if (state.dataset !== "all" && record.datasetKey !== state.dataset) return false;
      if (jurisdiction && record.jurisdictionCode !== jurisdiction) return false;
      if (category && record.category !== category) return false;
      if (year && record.year !== year) return false;
      if (fileType && record.fileType !== fileType) return false;
      return terms.every((term) => record.searchText.includes(term));
    })
    .map((record) => ({ record, score: scoreRecord(record, terms) }))
    .sort(compareScoredRecords)
    .map((entry) => entry.record);

  elements.shownCount.textContent = formatNumber(filtered.length);
  elements.loadStatus.textContent = `${formatNumber(filtered.length)} matching records`;
  renderResults(filtered);
}

function scoreRecord(record, terms) {
  if (!terms.length) return 0;
  const fields = [
    [record.formNumber.toLowerCase(), 8],
    [record.title.toLowerCase(), 5],
    [record.jurisdictionCode.toLowerCase(), 4],
    [record.jurisdictionName.toLowerCase(), 3],
    [record.category.toLowerCase(), 2],
  ];
  return terms.reduce((score, term) => {
    const fieldScore = fields.reduce(
      (best, [value, weight]) => Math.max(best, value.includes(term) ? weight : 0),
      0,
    );
    return score + fieldScore;
  }, 0);
}

function compareScoredRecords(left, right) {
  if (right.score !== left.score) return right.score - left.score;
  const yearDifference = Number(right.record.year || 0) - Number(left.record.year || 0);
  if (yearDifference) return yearDifference;
  return left.record.title.localeCompare(right.record.title, undefined, { numeric: true });
}

function renderResults(records) {
  elements.resultsList.replaceChildren();
  elements.emptyState.hidden = records.length > 0;

  const fragment = document.createDocumentFragment();
  records.slice(0, MAX_RENDERED_RESULTS).forEach((record) => {
    fragment.append(renderRecord(record));
  });

  if (records.length > MAX_RENDERED_RESULTS) {
    const overflow = document.createElement("li");
    overflow.className = "result-card";
    overflow.textContent = `${formatNumber(records.length - MAX_RENDERED_RESULTS)} more matches hidden by the result limit.`;
    fragment.append(overflow);
  }

  elements.resultsList.append(fragment);
}

function renderRecord(record) {
  const item = document.createElement("li");
  item.className = "result-card";

  const titleUrl = record.documentUrl || record.sourcePageUrl;
  const metadata = [
    record.formNumber,
    record.year,
    record.category && labelize(record.category),
    record.datasetLabel,
    record.fileType && record.fileType.toUpperCase(),
    record.recordType && labelize(record.recordType),
  ].filter(Boolean);

  item.innerHTML = `
    <div class="result-card__top">
      <h3 class="result-title">
        <a href="${escapeAttribute(titleUrl)}" target="_blank" rel="noopener noreferrer">
          ${escapeHtml(record.title)}
        </a>
      </h3>
      <span class="jurisdiction-badge">${escapeHtml(record.jurisdictionCode)}</span>
    </div>
    <ul class="meta-list">
      ${metadata.map((value) => `<li>${escapeHtml(value)}</li>`).join("")}
      ${
        record.status !== "ok"
          ? `<li class="warning">${escapeHtml(labelize(record.status))}</li>`
          : ""
      }
    </ul>
    <div class="result-actions">
      ${actionLink(titleUrl, record.recordType === "source_page" ? "Open source" : "Open document")}
      ${record.sourcePageUrl ? actionLink(record.sourcePageUrl, "Source page") : ""}
    </div>
  `;

  return item;
}

function actionLink(url, label) {
  if (!url) return "";
  return `
    <a href="${escapeAttribute(url)}" target="_blank" rel="noopener noreferrer">
      ${escapeHtml(label)}
      <svg aria-hidden="true" viewBox="0 0 24 24">
        <path d="M14 3h7v7h-2V6.4l-8.3 8.3-1.4-1.4L17.6 5H14z"></path>
        <path d="M5 5h6v2H7v10h10v-4h2v6H5z"></path>
      </svg>
    </a>
  `;
}

function labelize(value) {
  return String(value)
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatNumber(value) {
  return new Intl.NumberFormat("en-US").format(value);
}

function debounce(callback, delay) {
  let timeout;
  return (...args) => {
    window.clearTimeout(timeout);
    timeout = window.setTimeout(() => callback(...args), delay);
  };
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function escapeAttribute(value) {
  return escapeHtml(value);
}

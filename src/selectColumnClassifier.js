const CLASSIFICATION_OPTIONS = [
  { value: "categorical", label: "Categorical" },
  { value: "quantitative", label: "Quantitative" },
  { value: "no_defined", label: "No Defined" },
];

const sortColumns = (columns = []) =>
  [...columns]
    .map((column) => String(column ?? "").trim())
    .filter(Boolean)
    .sort((left, right) => left.localeCompare(right, undefined, { sensitivity: "base", numeric: true }));

const formatProfileCopy = (profile = {}) => {
  const sampleValues = Array.isArray(profile.sample_values) ? profile.sample_values.filter(Boolean) : [];
  const parts = [
    `${Number(profile.non_empty_count ?? 0)} values`,
    `${Number(profile.unique_count ?? 0)} unique`,
  ];
  if (typeof profile.numeric_ratio === "number") {
    parts.push(`${Math.round(profile.numeric_ratio * 100)}% numeric`);
  }
  if (sampleValues.length) {
    parts.push(`Examples: ${sampleValues.join(", ")}`);
  }
  return parts.join(" · ");
};

export const renderSelectColumnClassifier = ({
  mountNode,
  columns = [],
  assignments = {},
  enabledColumns = [],
  profiles = {},
  scrollTop = 0,
  disabled = true,
  disabledMessage = "Confirm Germplams Identifiers to classify the remaining columns.",
  emptyMessage = "No columns are available for classification.",
  onAssignmentChange = () => {},
  onEnabledChange = () => {},
  onScroll = () => {},
  onApplySelection = () => {},
} = {}) => {
  if (!mountNode) {
    return;
  }

  mountNode.innerHTML = "";

  const panel = document.createElement("section");
  panel.className = `select-columns-classifier${disabled ? " is-disabled" : ""}`;

  const sortedColumns = sortColumns(columns);
  if (!sortedColumns.length) {
    const empty = document.createElement("div");
    empty.className = "select-columns-empty";
    empty.textContent = disabled ? disabledMessage : emptyMessage;
    panel.append(empty);
    mountNode.append(panel);
    return;
  }

  const header = document.createElement("div");
  header.className = "select-columns-classifier-head";

  const counter = document.createElement("span");
  counter.className = "selection-pill selection-pill-quiet";
  counter.textContent = `${sortedColumns.length} rows`;

  header.append(counter);
  panel.append(header);

  const list = document.createElement("div");
  list.className = "select-columns-classifier-list";
  const normalizedScrollTop = Number(scrollTop ?? 0);

  const enabledSet = new Set(enabledColumns.map((column) => String(column ?? "").trim()).filter(Boolean));

  sortedColumns.forEach((column) => {
    const profile = profiles[column] ?? {};
    const recommendedValue = String(profile.recommended_classification ?? "no_defined").trim() || "no_defined";
    const selectedValue = String(assignments[column] ?? recommendedValue).trim() || "no_defined";
    const isEnabled = enabledSet.has(column);

    const row = document.createElement("div");
    row.className = `select-columns-classifier-row${isEnabled ? "" : " is-disabled-row"}`;

    const toggle = document.createElement("label");
    toggle.className = "select-columns-classifier-toggle";

    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.className = "select-columns-classifier-checkbox";
    checkbox.checked = isEnabled;
    checkbox.disabled = disabled;

    toggle.append(checkbox);

    const copy = document.createElement("div");
    copy.className = "select-columns-classifier-row-copy";

    const rowTitle = document.createElement("strong");
    rowTitle.className = "select-columns-classifier-row-title";
    rowTitle.textContent = column;

    const rowMeta = document.createElement("span");
    rowMeta.className = "select-columns-classifier-row-meta";
    rowMeta.textContent = formatProfileCopy(profile);

    const recommendation = document.createElement("span");
    recommendation.className = "select-columns-classifier-recommendation";
    recommendation.textContent = `Suggested: ${CLASSIFICATION_OPTIONS.find((option) => option.value === recommendedValue)?.label ?? "No Defined"}`;

    copy.append(rowTitle, rowMeta, recommendation);

    const select = document.createElement("select");
    select.className = "select-columns-classifier-select";
    select.disabled = disabled || !isEnabled;

    CLASSIFICATION_OPTIONS.forEach((option) => {
      const element = document.createElement("option");
      element.value = option.value;
      element.textContent = option.label;
      element.selected = option.value === selectedValue;
      select.append(element);
    });

    checkbox.addEventListener("change", () => {
      row.classList.toggle("is-disabled-row", !checkbox.checked);
      select.disabled = disabled || !checkbox.checked;
      onEnabledChange(column, checkbox.checked, list.scrollTop);
    });

    select.addEventListener("change", () => {
      onAssignmentChange(column, select.value, list.scrollTop);
    });

    row.append(toggle, copy, select);
    list.append(row);
  });

  list.addEventListener("scroll", () => {
    onScroll(list.scrollTop);
  });

  panel.append(list);

  requestAnimationFrame(() => {
    if (normalizedScrollTop > 0) {
      list.scrollTop = normalizedScrollTop;
    }
  });

  const footer = document.createElement("div");
  footer.className = "select-columns-classifier-footer";

  const confirmButton = document.createElement("button");
  confirmButton.type = "button";
  confirmButton.className = "selection-step-cta";
  confirmButton.disabled = disabled || !sortedColumns.length || !enabledSet.size;
  confirmButton.setAttribute("aria-label", "Confirm column classifications");
  confirmButton.title = "Confirm column classifications";
  confirmButton.innerHTML = '<span class="selection-step-cta-arrow" aria-hidden="true">✓</span>';
  confirmButton.addEventListener("click", () => onApplySelection());

  footer.append(confirmButton);
  panel.append(footer);
  mountNode.append(panel);
};

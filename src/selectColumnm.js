const sortColumns = (columns = [], priorityColumns = []) => {
  const normalizedPriority = priorityColumns
    .map((column) => String(column ?? "").trim())
    .filter(Boolean);
  const priorityIndex = new Map(normalizedPriority.map((column, index) => [column, index]));
  return [...columns]
    .map((column) => String(column ?? "").trim())
    .filter(Boolean)
    .sort((left, right) => {
      const leftPriority = priorityIndex.get(left);
      const rightPriority = priorityIndex.get(right);
      if (leftPriority !== undefined || rightPriority !== undefined) {
        if (leftPriority === undefined) {
          return 1;
        }
        if (rightPriority === undefined) {
          return -1;
        }
        return leftPriority - rightPriority;
      }
      return left.localeCompare(right, undefined, { sensitivity: "base", numeric: true });
    });
};

const createActionButton = ({ icon, label, disabled = false, onClick }) => {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "select-columns-action";
  button.setAttribute("aria-label", label);
  button.title = label;
  button.innerHTML = `<span aria-hidden="true">${icon}</span>`;
  button.disabled = disabled;
  button.addEventListener("click", onClick);
  return button;
};

const createEmptyState = (message) => {
  const empty = document.createElement("div");
  empty.className = "select-columns-empty";
  empty.textContent = message;
  return empty;
};

export const renderSelectColumnm = ({
  mountNode,
  title = "select Germplams Identifiers",
  helperText = "Select one or more columns that identify germplasm records. The list shows 10 elements at a time and supports scroll through the remaining columns.",
  columns = [],
  selectedColumns = [],
  highlightedColumn = "",
  scrollTop = 0,
  disabled = true,
  disabledMessage = "Complete the target variable, longitude column, and latitude column selections to enable Select Columns",
  emptyMessage = "No columns are currently available for this step.",
  priorityColumns = [],
  lockedColumns = [],
  showHeader = true,
  showCounter = true,
  onSelectionChange = () => {},
  onApplySelection = () => {},
  onReviewSelection = () => {},
  onClearSelection = () => {},
} = {}) => {
  if (!mountNode) {
    return;
  }

  mountNode.innerHTML = "";

  const panel = document.createElement("section");
  panel.className = `select-columns-panel${disabled ? " is-disabled" : ""}`;

  let header = null;
  if (showHeader) {
    header = document.createElement("div");
    header.className = "select-columns-header";

    const headerCopy = document.createElement("div");

    const heading = document.createElement("h4");
    heading.className = "select-columns-title";
    heading.textContent = title;

    const helper = document.createElement("p");
    helper.className = "select-columns-copy";
    helper.textContent = disabled ? disabledMessage : helperText;

    headerCopy.append(heading, helper);
    header.append(headerCopy);

    if (showCounter) {
      const counter = document.createElement("span");
      counter.className = "selection-pill selection-pill-quiet";
      counter.textContent = `${selectedColumns.length} selected`;
      header.append(counter);
    }
  }

  const sortedColumns = sortColumns(columns, priorityColumns);
  if (!sortedColumns.length) {
    if (header) {
      panel.append(header);
    }
    panel.append(createEmptyState(disabled ? disabledMessage : emptyMessage));
    mountNode.append(panel);
    return;
  }

  const selectedSet = new Set(sortColumns(selectedColumns));
  const lockedSet = new Set(sortColumns(lockedColumns));
  let activeColumn = String(highlightedColumn ?? "").trim() || selectedColumns[0] || sortedColumns[0] || "";

  const body = document.createElement("div");
  body.className = "select-columns-body";

  const listWrap = document.createElement("div");
  listWrap.className = "select-columns-list-wrap";

  const list = document.createElement("div");
  list.className = "select-columns-list";
  list.setAttribute("role", "listbox");
  list.setAttribute("aria-multiselectable", "true");
  list.setAttribute("aria-label", title);

  const emitSelection = () => {
    const selectedValues = sortColumns([...selectedSet]);
    const normalizedActive = selectedValues.includes(activeColumn) || sortedColumns.includes(activeColumn)
      ? activeColumn
      : selectedValues[0] || sortedColumns[0] || "";
    activeColumn = normalizedActive;
    onSelectionChange(selectedValues, activeColumn, list.scrollTop);
  };

  sortedColumns.forEach((column) => {
    const isLocked = lockedSet.has(column);
    const row = document.createElement("div");
    row.className = `select-columns-item${selectedSet.has(column) ? " is-selected" : ""}${activeColumn === column ? " is-active" : ""}`;
    row.setAttribute("role", "option");
    row.setAttribute("aria-selected", selectedSet.has(column) ? "true" : "false");

    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.className = "select-columns-checkbox";
    checkbox.value = column;
    checkbox.checked = selectedSet.has(column);
    checkbox.disabled = disabled || isLocked;

    const text = document.createElement("span");
    text.className = "select-columns-item-text";
    text.textContent = column;

    const indicator = document.createElement("span");
    indicator.className = "select-columns-item-indicator";
    indicator.setAttribute("aria-hidden", "true");
    indicator.textContent = isLocked ? "Required" : selectedSet.has(column) ? "Selected" : "Available";

    const applyCheckboxState = () => {
      if (isLocked) {
        checkbox.checked = true;
        selectedSet.add(column);
        activeColumn = column;
        emitSelection();
        return;
      }
      if (checkbox.checked) {
        selectedSet.add(column);
      } else {
        selectedSet.delete(column);
      }
      activeColumn = column;
      emitSelection();
    };

    checkbox.addEventListener("click", (event) => {
      event.stopPropagation();
    });

    checkbox.addEventListener("change", applyCheckboxState);

    row.addEventListener("click", () => {
      if (disabled || isLocked) {
        return;
      }
      checkbox.checked = !checkbox.checked;
      applyCheckboxState();
    });

    row.append(checkbox, text, indicator);
    list.append(row);
  });

  const normalizedScrollTop = Number(scrollTop ?? 0);

  listWrap.append(list);

  const toolbar = document.createElement("div");
  toolbar.className = "select-columns-toolbar";

  const applyButton = createActionButton({
    icon: "✓",
    label: selectedColumns.length ? "Confirm selected germplasm identifiers" : "Select at least one germplasm identifier",
    disabled: disabled || selectedColumns.length < 1,
    onClick: () => onApplySelection(selectedColumns),
  });

  const reviewTarget = highlightedColumn || selectedColumns[0] || activeColumn || "";
  const reviewButton = createActionButton({
    icon: "✎",
    label: reviewTarget ? `Review ${reviewTarget}` : "Review selected germplasm identifier",
    disabled: disabled || !reviewTarget,
    onClick: () => onReviewSelection(reviewTarget),
  });

  const clearButton = createActionButton({
    icon: "⌫",
    label: selectedColumns.length ? "Clear selected rows" : "No selected rows to clear",
    disabled: disabled || selectedColumns.length < 1,
    onClick: () => onClearSelection([], "", list.scrollTop),
  });

  toolbar.append(applyButton, reviewButton, clearButton);
  body.append(listWrap, toolbar);
  if (header) {
    panel.append(header);
  }
  panel.append(body);
  mountNode.append(panel);

  requestAnimationFrame(() => {
    if (normalizedScrollTop > 0) {
      list.scrollTop = normalizedScrollTop;
      return;
    }
    const activeItem = list.querySelector('.select-columns-item.is-active');
    if (activeItem) {
      activeItem.scrollIntoView({ block: "nearest" });
    }
  });
};

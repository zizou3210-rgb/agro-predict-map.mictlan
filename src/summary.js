const formatList = (values = []) =>
  values
    .map((value) => String(value ?? "").trim())
    .filter(Boolean)
    .sort((left, right) => left.localeCompare(right, undefined, { sensitivity: "base", numeric: true }));

const createSummarySection = (title, values = []) => {
  const card = document.createElement("article");
  card.className = "selection-summary-section";

  const heading = document.createElement("h4");
  heading.textContent = title;
  card.append(heading);

  const list = document.createElement("div");
  list.className = "selection-summary-list";

  const normalizedValues = formatList(values);
  if (!normalizedValues.length) {
    const empty = document.createElement("p");
    empty.className = "selection-summary-empty";
    empty.textContent = "No columns selected";
    list.append(empty);
  } else {
    normalizedValues.forEach((value) => {
      const item = document.createElement("span");
      item.className = "selection-summary-chip";
      item.textContent = value;
      list.append(item);
    });
  }

  card.append(list);
  return card;
};

const createOverviewCard = (label, value) => {
  const card = document.createElement("article");
  card.className = "selection-summary-overview-card";

  const heading = document.createElement("span");
  heading.className = "selection-summary-overview-label";
  heading.textContent = label;

  const content = document.createElement("strong");
  content.textContent = String(value ?? "Pending").trim() || "Pending";

  card.append(heading, content);
  return card;
};

export const renderSelectionSummary = ({
  mountNode,
  initialSettings = {},
  divisions = {},
  disabled = true,
  onPlay = () => {},
} = {}) => {
  if (!mountNode) {
    return;
  }

  mountNode.innerHTML = "";

  const panel = document.createElement("section");
  panel.className = `selection-summary-panel${disabled ? " is-disabled" : ""}`;

  const overview = document.createElement("div");
  overview.className = "selection-summary-overview";
  overview.append(
    createOverviewCard("Target", initialSettings.targetColumn ?? "Pending"),
    createOverviewCard("Longitude", initialSettings.longitudeColumn ?? "Pending"),
    createOverviewCard("Latitude", initialSettings.latitudeColumn ?? "Pending"),
    createOverviewCard("Date of Plating", initialSettings.plantingDateColumn ?? "Pending"),
    createOverviewCard("Date of Harvesting", initialSettings.harvestingDateColumn ?? "Pending"),
    createOverviewCard("Soil type/texture", initialSettings.soilTextureColumn ?? "Pending"),
    createOverviewCard("Soil Depth (cm)", initialSettings.soilDepthColumn ?? "Pending"),
  );

  const sections = document.createElement("div");
  sections.className = "selection-summary-sections";
  sections.append(
    createSummarySection("Germplams Identifiers", divisions.identifierColumns ?? []),
    createSummarySection("Categorical Data", divisions.categoricalColumns ?? []),
    createSummarySection("Quantitative Data", divisions.quantitativeColumns ?? []),
  );

  const actions = document.createElement("div");
  actions.className = "selection-summary-actions";

  const playButton = document.createElement("button");
  playButton.type = "button";
  playButton.className = "selection-summary-play";
  playButton.disabled = disabled;
  playButton.setAttribute("aria-label", "Execute Summary");
  playButton.innerHTML = '<span aria-hidden="true">▶</span>';
  playButton.addEventListener("click", () => onPlay());

  actions.append(playButton);
  panel.append(overview, sections, actions);
  mountNode.append(panel);
};

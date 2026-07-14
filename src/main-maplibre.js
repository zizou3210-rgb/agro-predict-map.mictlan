const attributesPerPage = 10;
const requiredColumns = [
  "_GPS coordinates_latitude",
  "_GPS coordinates_longitude",
];

const mapContainer = document.getElementById("map");
const tooltip = document.getElementById("tooltip");
const statsContainer = document.getElementById("stats");
const detailsTitle = document.getElementById("details-title");
const detailsSubtitle = document.getElementById("details-subtitle");
const detailsMeta = document.getElementById("details-meta");
const detailsList = document.getElementById("details-list");
const pageIndicator = document.getElementById("page-indicator");
const prevPageButton = document.getElementById("prev-page");
const nextPageButton = document.getElementById("next-page");
const tabGeoButton = document.getElementById("tab-geo");
const tabAttributesButton = document.getElementById("tab-attributes");
const panelGeo = document.getElementById("panel-geo");
const panelAttributes = document.getElementById("panel-attributes");
const fileInput = document.getElementById("xlsx-file");
const loadingPanel = document.getElementById("loading-panel");
const loadingBarFill = document.getElementById("loading-bar-fill");
const loadingStage = document.getElementById("loading-stage");
const loadingPercent = document.getElementById("loading-percent");
const loadingMessage = document.getElementById("loading-message");

const parser = new DOMParser();
const markerSvg =
  '<svg viewBox="-12 -14 24 32" aria-hidden="true"><path class="marker-pin" d="M0,-11 C5,-11 9,-7 9,-2 C9,5 3,8 0,14 C-3,8 -9,5 -9,-2 C-9,-7 -5,-11 0,-11 Z"></path><circle class="marker-center" cx="0" cy="-2.5" r="2.6"></circle></svg>';

let map = null;
let selectedFeature = null;
let currentPage = 0;
let markerEntries = [];
let reverseGeocodeQueue = Promise.resolve();
const reverseGeocodeCache = new Map();

const sleepFrame = () => new Promise((resolve) => requestAnimationFrame(resolve));

const setLoadingState = async (percent, stage, message, visible = true) => {
  loadingPanel.hidden = !visible;
  loadingBarFill.style.width = `${percent}%`;
  loadingStage.textContent = stage;
  loadingPercent.textContent = `${percent}%`;
  loadingMessage.textContent = message;
  await sleepFrame();
};

const createStat = (label, value) => {
  const article = document.createElement("article");
  article.className = "stat";
  article.innerHTML = `
    <span class="stat-label">${label}</span>
    <span class="stat-value">${value}</span>
  `;
  return article;
};

const renderEmptyStats = () => {
  statsContainer.replaceChildren(
    createStat("Points", "--"),
    createStat("Attributes", "--"),
    createStat("Zoom", "--"),
    createStat("Min Latitude", "--"),
    createStat("Max Latitude", "--"),
    createStat("Min Longitude", "--"),
    createStat("Max Longitude", "--"),
  );
};

const formatAttributeValue = (value) => {
  if (value === null || value === undefined || value === "") {
    return "No data";
  }
  return typeof value === "number" ? new Intl.NumberFormat("en-US").format(value) : String(value);
};

const formatCoordinate = (value) =>
  new Intl.NumberFormat("en-US", {
    minimumFractionDigits: 0,
    maximumFractionDigits: 5,
  }).format(value);

const asFloat = (value) => {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  const numeric = Number(String(value).replace(",", "."));
  return Number.isFinite(numeric) ? numeric : null;
};

let activeTargetColumn = "Grain Yield (T/Ha)";

const resolveFeatureTargetColumn = (properties = {}) => {
  const metadataTarget = String(properties?.target_column ?? "").trim();
  if (metadataTarget && Object.prototype.hasOwnProperty.call(properties, metadataTarget)) {
    return metadataTarget;
  }
  if (Object.prototype.hasOwnProperty.call(properties, activeTargetColumn)) {
    return activeTargetColumn;
  }
  if (Object.prototype.hasOwnProperty.call(properties, "Grain Yield (T/Ha)")) {
    return "Grain Yield (T/Ha)";
  }
  const yieldLike = Object.keys(properties).find((key) => /yield/i.test(String(key)));
  return yieldLike || activeTargetColumn;
};

const getPagedAttributes = (feature) => {
  const entries = Object.entries(feature.properties).filter(
    ([key]) => !["row_number", "Country", resolveFeatureTargetColumn(feature.properties), "idPK"].includes(key),
  );
  entries.sort(([left], [right]) => left.localeCompare(right));
  return entries;
};

const geoInfoEntries = (feature) => {
  const [longitude, latitude] = feature.geometry.coordinates;
  const enrichment = feature.__geoEnrichment;
  const entries = [
    ["Geocoordinate ID", feature.properties.idPK ?? feature.properties.row_number],
    ["Country", feature.properties.Country ?? enrichment?.country ?? "No data"],
    [resolveFeatureTargetColumn(feature.properties), formatAttributeValue(feature.properties[resolveFeatureTargetColumn(feature.properties)])],
    ["Latitude", formatCoordinate(latitude)],
    ["Longitude", formatCoordinate(longitude)],
  ];

  if (enrichment?.state) entries.push(["State", enrichment.state]);
  if (enrichment?.county) entries.push(["County", enrichment.county]);
  if (enrichment?.locality) entries.push(["Locality", enrichment.locality]);
  if (enrichment?.road) entries.push(["Road", enrichment.road]);
  if (enrichment?.postcode) entries.push(["Postcode", enrichment.postcode]);
  if (enrichment?.displayName) entries.push(["Label", enrichment.displayName]);
  if (enrichment?.status === "loading") entries.push(["Geo Status", "Loading enrichment..."]);
  if (enrichment?.status === "error") entries.push(["Geo Status", "Geographic enrichment unavailable"]);

  return entries;
};

const showTooltip = (event, feature) => {
  const { properties } = feature;
  const [longitude, latitude] = feature.geometry.coordinates;
  tooltip.hidden = false;
  tooltip.innerHTML = `
    <strong>Record ${properties.idPK ?? properties.row_number}</strong>
    <p>${resolveFeatureTargetColumn(properties)}: ${formatAttributeValue(properties[resolveFeatureTargetColumn(properties)])}</p>
    <p>Latitude: ${formatCoordinate(latitude)}</p>
    <p>Longitude: ${formatCoordinate(longitude)}</p>
    ${properties.Country ? `<p>Country: ${properties.Country}</p>` : ""}
    ${properties.Rank ? `<p>Rank: ${properties.Rank}</p>` : ""}
  `;

  const bounds = mapContainer.getBoundingClientRect();
  tooltip.style.left = `${event.clientX - bounds.left}px`;
  tooltip.style.top = `${event.clientY - bounds.top}px`;
};

const hideTooltip = () => {
  tooltip.hidden = true;
};

const setActiveDetailsTab = (tab) => {
  tabGeoButton.classList.toggle("active", tab === "geo");
  tabAttributesButton.classList.toggle("active", tab === "attributes");
  panelGeo.hidden = tab !== "geo";
  panelAttributes.hidden = tab !== "attributes";
};

const cacheKeyForFeature = (feature) => {
  const [longitude, latitude] = feature.geometry.coordinates;
  return `${latitude.toFixed(5)},${longitude.toFixed(5)}`;
};

const fetchReverseGeocode = async (feature) => {
  const cacheKey = cacheKeyForFeature(feature);
  if (reverseGeocodeCache.has(cacheKey)) {
    return reverseGeocodeCache.get(cacheKey);
  }

  const [longitude, latitude] = feature.geometry.coordinates;
  const url = new URL("https://nominatim.openstreetmap.org/reverse");
  url.searchParams.set("format", "jsonv2");
  url.searchParams.set("lat", String(latitude));
  url.searchParams.set("lon", String(longitude));
  url.searchParams.set("addressdetails", "1");
  url.searchParams.set("zoom", "18");
  url.searchParams.set("accept-language", "en");

  const result = await fetch(url.toString(), {
    headers: {
      Accept: "application/json",
    },
  });

  if (!result.ok) {
    throw new Error(`Reverse geocoding failed with status ${result.status}`);
  }

  const payload = await result.json();
  const address = payload.address ?? {};
  const enrichment = {
    status: "ready",
    country: address.country ?? null,
    state: address.state ?? address.region ?? null,
    county: address.county ?? address.state_district ?? null,
    locality:
      address.city ??
      address.town ??
      address.village ??
      address.hamlet ??
      address.municipality ??
      address.suburb ??
      null,
    road: address.road ?? address.pedestrian ?? address.cycleway ?? null,
    postcode: address.postcode ?? null,
    displayName: payload.display_name ?? null,
  };

  reverseGeocodeCache.set(cacheKey, enrichment);
  return enrichment;
};

const queueReverseGeocode = (feature) => {
  const cacheKey = cacheKeyForFeature(feature);
  if (reverseGeocodeCache.has(cacheKey)) {
    feature.__geoEnrichment = reverseGeocodeCache.get(cacheKey);
    return Promise.resolve(reverseGeocodeCache.get(cacheKey));
  }

  if (feature.__geoEnrichment?.status === "loading") {
    return reverseGeocodeQueue;
  }

  feature.__geoEnrichment = { status: "loading" };
  reverseGeocodeQueue = reverseGeocodeQueue
    .catch(() => undefined)
    .then(() => fetchReverseGeocode(feature))
    .then(async (enrichment) => {
      feature.__geoEnrichment = enrichment;
      if (selectedFeature === feature) {
        renderDetails();
      }
      await new Promise((resolve) => setTimeout(resolve, 1000));
      return enrichment;
    })
    .catch(async () => {
      feature.__geoEnrichment = { status: "error" };
      if (selectedFeature === feature) {
        renderDetails();
      }
      await new Promise((resolve) => setTimeout(resolve, 1000));
      return null;
    });

  return reverseGeocodeQueue;
};

const resetDetails = () => {
  setActiveDetailsTab("geo");
  detailsMeta.innerHTML = "";
  detailsList.innerHTML = "";
  detailsTitle.textContent = "Select a Geocoordinate";
  detailsSubtitle.textContent =
    "Load an Excel file first. Then you can explore the details of each record.";
  pageIndicator.textContent = "0 / 0";
  prevPageButton.disabled = true;
  nextPageButton.disabled = true;
};

const renderDetails = () => {
  if (!selectedFeature) {
    resetDetails();
    return;
  }

  const attributes = getPagedAttributes(selectedFeature);
  const totalPages = Math.max(1, Math.ceil(attributes.length / attributesPerPage));
  currentPage = Math.min(currentPage, totalPages - 1);
  const currentSlice = attributes.slice(
    currentPage * attributesPerPage,
    currentPage * attributesPerPage + attributesPerPage,
  );
  const [longitude, latitude] = selectedFeature.geometry.coordinates;

  if (!selectedFeature.__geoEnrichment) {
    queueReverseGeocode(selectedFeature);
  }

  detailsTitle.textContent =
    selectedFeature.properties.idPK ?? `Row ${selectedFeature.properties.row_number}`;
  detailsSubtitle.textContent =
    selectedFeature.properties["Local check, Name of variety provided by farmer"] ??
    "Record loaded from the Excel file.";

  detailsMeta.innerHTML = "";
  geoInfoEntries(selectedFeature).forEach(([label, value]) => {
    const chip = document.createElement("div");
    chip.className = "meta-chip";
    chip.textContent = `${label}: ${value}`;
    detailsMeta.append(chip);
  });

  detailsList.innerHTML = "";
  currentSlice.forEach(([key, value]) => {
    const article = document.createElement("article");
    article.className = "attribute-card";
    article.innerHTML = `
      <span class="attribute-name">${key}</span>
      <span class="attribute-value">${formatAttributeValue(value)}</span>
    `;
    detailsList.append(article);
  });

  pageIndicator.textContent = `${currentPage + 1} / ${totalPages}`;
  prevPageButton.disabled = currentPage === 0;
  nextPageButton.disabled = currentPage >= totalPages - 1;
};

const columnLettersToIndex = (reference) => {
  const letters = reference.replace(/[^A-Z]/gi, "");
  let index = 0;
  for (const character of letters) {
    index = index * 26 + (character.toUpperCase().charCodeAt(0) - 64);
  }
  return index - 1;
};

const parseXml = (text) => parser.parseFromString(text, "application/xml");
const xmlText = (node, selector) => node.querySelector(selector)?.textContent ?? "";

const normalizeValue = (text) => {
  const trimmed = String(text).trim();
  if (trimmed === "") {
    return "";
  }
  if (/^-?\d+$/.test(trimmed)) {
    return Number(trimmed);
  }
  if (/^-?\d+\.\d+$/.test(trimmed)) {
    return Number(trimmed);
  }
  return trimmed;
};

const readCellValue = (cell, sharedStrings) => {
  const type = cell.getAttribute("t");
  if (type === "inlineStr") {
    return normalizeValue(
      Array.from(cell.querySelectorAll("is t"))
        .map((node) => node.textContent ?? "")
        .join(""),
    );
  }

  const value = xmlText(cell, "v");
  if (type === "s") {
    return sharedStrings[Number(value)] ?? "";
  }
  return normalizeValue(value);
};

const readWorkbookSheetPath = async (zip) => {
  const workbookXml = parseXml(await zip.file("xl/workbook.xml").async("string"));
  const relsXml = parseXml(await zip.file("xl/_rels/workbook.xml.rels").async("string"));
  const firstSheet = workbookXml.querySelector("sheet");
  const relationId =
    firstSheet?.getAttribute("r:id") ??
    firstSheet?.getAttribute("id") ??
    firstSheet?.getAttributeNS(
      "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
      "id",
    );
  const relation = Array.from(relsXml.querySelectorAll("Relationship")).find(
    (node) => node.getAttribute("Id") === relationId,
  );
  if (!relation) {
    return "xl/worksheets/sheet1.xml";
  }
  const target = relation.getAttribute("Target") ?? "worksheets/sheet1.xml";
  return target.startsWith("/") ? target.replace(/^\//, "") : `xl/${target}`.replace("xl/xl/", "xl/");
};

const readSharedStrings = async (zip) => {
  const sharedStringsFile = zip.file("xl/sharedStrings.xml");
  if (!sharedStringsFile) {
    return [];
  }
  const sharedXml = parseXml(await sharedStringsFile.async("string"));
  return Array.from(sharedXml.querySelectorAll("si")).map((item) =>
    Array.from(item.querySelectorAll("t"))
      .map((node) => node.textContent ?? "")
      .join(""),
  );
};

const extractRowsFromWorkbook = async (file) => {
  const zip = await JSZip.loadAsync(await file.arrayBuffer());
  const sharedStrings = await readSharedStrings(zip);
  const sheetPath = await readWorkbookSheetPath(zip);
  const sheetXml = parseXml(await zip.file(sheetPath).async("string"));
  const rows = Array.from(sheetXml.querySelectorAll("sheetData > row"));

  const parsedRows = rows.map((row) => {
    const values = [];
    row.querySelectorAll("c").forEach((cell) => {
      const ref = cell.getAttribute("r") ?? "";
      values[columnLettersToIndex(ref)] = readCellValue(cell, sharedStrings);
    });
    return values;
  });

  const headers = (parsedRows[0] ?? []).map((value) => String(value ?? ""));
  const dataRows = parsedRows.slice(1).map((row) =>
    headers.map((_, index) => (row[index] === undefined ? "" : row[index])),
  );

  return { headers, rows: dataRows };
};

const buildFeatureCollection = (headers, rows, sourceName) => {
  const headerIndex = Object.fromEntries(headers.map((header, index) => [header, index]));
  const missingColumns = requiredColumns.filter((column) => !(column in headerIndex));

  if (missingColumns.length) {
    throw new Error(`Missing required columns: ${missingColumns.join(", ")}`);
  }

  const latitudeIndex = headerIndex["_GPS coordinates_latitude"];
  const longitudeIndex = headerIndex["_GPS coordinates_longitude"];
  const features = [];

  rows.forEach((row, rowOffset) => {
    const latitude = asFloat(row[latitudeIndex]);
    const longitude = asFloat(row[longitudeIndex]);
    if (latitude === null || longitude === null) {
      return;
    }

    const properties = { row_number: rowOffset + 2 };
    headers.forEach((header, index) => {
      if (!header || requiredColumns.includes(header)) {
        return;
      }
      const value = row[index];
      if (value === "" || value === null || value === undefined) {
        return;
      }
      properties[header] = value;
    });

    features.push({
      type: "Feature",
      geometry: { type: "Point", coordinates: [longitude, latitude] },
      properties,
    });
  });

  if (!features.length) {
    throw new Error("No valid Geocoordinates were found with latitude and longitude.");
  }

  return {
    type: "FeatureCollection",
    metadata: {
      attribute_count: Math.max(headers.length - requiredColumns.length, 0),
      total_features: features.length,
      source_file_name: sourceName,
    },
    features,
  };
};

const createMarkerElement = () => {
  const element = document.createElement("button");
  element.type = "button";
  element.className = "custom-marker";
  element.innerHTML = markerSvg;
  return element;
};

const clearMarkers = () => {
  hideTooltip();
  selectedFeature = null;
  currentPage = 0;
  markerEntries.forEach(({ marker }) => marker.remove());
  markerEntries = [];
  resetDetails();
};

const updateActiveMarker = () => {
  markerEntries.forEach(({ feature, element }) => {
    element.classList.toggle("active", feature === selectedFeature);
  });
};

const fitMapToFeatures = (features) => {
  const bounds = new maplibregl.LngLatBounds();
  features.forEach((feature) => bounds.extend(feature.geometry.coordinates));
  map.fitBounds(bounds, {
    padding: { top: 70, right: 70, bottom: 70, left: 70 },
    maxZoom: 11.5,
    duration: 900,
  });
};

const applyFeatureCollection = async (geojson, sourceName) => {
  const points = geojson.features;
  if (Array.isArray(points) && points.length) {
    activeTargetColumn = resolveFeatureTargetColumn(points[0].properties ?? {});
  }
  const longitudes = points.map((feature) => feature.geometry.coordinates[0]);
  const latitudes = points.map((feature) => feature.geometry.coordinates[1]);

  clearMarkers();
  await setLoadingState(70, "Building Geocoordinates", "Drawing points and enabling interactions.");

  markerEntries = points.map((feature) => {
    const element = createMarkerElement();
    const marker = new maplibregl.Marker({ element, anchor: "bottom" })
      .setLngLat(feature.geometry.coordinates)
      .addTo(map);

    element.addEventListener("mouseenter", (event) => showTooltip(event, feature));
    element.addEventListener("mousemove", (event) => showTooltip(event, feature));
    element.addEventListener("mouseleave", hideTooltip);
    element.addEventListener("click", () => {
      selectedFeature = feature;
      currentPage = 0;
      updateActiveMarker();
      renderDetails();
      map.easeTo({ center: feature.geometry.coordinates, duration: 600 });
    });

    return { feature, marker, element };
  });

  await setLoadingState(85, "Updating view", "Calculating zoom and record detail.");
  fitMapToFeatures(points);

  selectedFeature = points[0];
  updateActiveMarker();
  renderDetails();

  statsContainer.replaceChildren(
    createStat("Points", geojson.metadata.total_features.toLocaleString("en-US")),
    createStat("Attributes", geojson.metadata.attribute_count.toLocaleString("en-US")),
    createStat("Zoom", "Countries, states, localities"),
    createStat("Min Latitude", formatCoordinate(Math.min(...latitudes))),
    createStat("Max Latitude", formatCoordinate(Math.max(...latitudes))),
    createStat("Min Longitude", formatCoordinate(Math.min(...longitudes))),
    createStat("Max Longitude", formatCoordinate(Math.max(...longitudes))),
  );

  await setLoadingState(100, "Upload complete", `File processed successfully: ${sourceName}.`);
};

const handleFileUpload = async (event) => {
  const [file] = event.target.files ?? [];
  if (!file) {
    return;
  }

  try {
    renderEmptyStats();
    clearMarkers();
    await setLoadingState(10, "Loading file", `Reading ${file.name} from the interface.`);
    const { headers, rows } = await extractRowsFromWorkbook(file);

    await setLoadingState(40, "Validating data", "Searching coordinate columns and checking Geocoordinates.");
    const geojson = buildFeatureCollection(headers, rows, file.name);

    await setLoadingState(60, "Validating Geocoordinates", `${geojson.features.length} Geocoordinates with coordinates were validated.`);
    await applyFeatureCollection(geojson, file.name);
  } catch (error) {
    console.error(error);
    clearMarkers();
    renderEmptyStats();
    await setLoadingState(
      100,
      "Upload error",
      error instanceof Error ? error.message : "The file could not be processed.",
    );
  }
};

const setupMap = async () => {
  map = new maplibregl.Map({
    container: "map",
    style: "https://demotiles.maplibre.org/style.json",
    center: [34.8, -1.2],
    zoom: 4.2,
    minZoom: 2,
    maxZoom: 17,
    attributionControl: true,
  });

  map.addControl(new maplibregl.NavigationControl({ visualizePitch: false }), "top-right");
  map.addControl(new maplibregl.ScaleControl({ maxWidth: 120, unit: "metric" }));

  await new Promise((resolve) => map.once("load", resolve));
};

prevPageButton.addEventListener("click", () => {
  if (!selectedFeature || currentPage === 0) {
    return;
  }
  currentPage -= 1;
  renderDetails();
});

nextPageButton.addEventListener("click", () => {
  if (!selectedFeature) {
    return;
  }
  currentPage += 1;
  renderDetails();
});

tabGeoButton.addEventListener("click", () => setActiveDetailsTab("geo"));
tabAttributesButton.addEventListener("click", () => setActiveDetailsTab("attributes"));
fileInput.addEventListener("change", handleFileUpload);

const init = async () => {
  renderEmptyStats();
  resetDetails();
  await setLoadingState(0, "Waiting for file", "Upload a file to start processing.", false);
  await setupMap();
};

init().catch((error) => {
  console.error(error);
  statsContainer.replaceChildren(createStat("Error", "The map could not be initialized"));
});

import {
  SELECCTION_PROPERTIES_FLOW_ID,
  buildAvailableSelectionColumns,
  buildSelectableColumnOptions,
  buildSelectionPropertiesSummary,
  classifySelectionPropertiesColumns,
  isDGColumn,
  selectionPropertiesSteps,
} from "../selecctionProperties/flow.js";
import { renderSelectColumnm } from "./selectColumnm.js";
import { renderSelectColumnClassifier } from "./selectColumnClassifier.js";
import { renderSelectionSummary } from "./summary.js";

const width = 1000;
const height = 680;
const minZoom = 2;
const maxZoom = 17;
const attributesPerPage = 10;
const tileSize = 256;
const tileUrlTemplate = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
const requiredColumns = [
  "_GPS coordinates_latitude",
  "_GPS coordinates_longitude",
];
const actualYieldKey = "Grain Yield (T/Ha)";
const predictedYieldKey = "Grain Yield predicted";
const predictionProfileKey = "Prediction Profile Key";
const predictionProfileLabelKey = "Prediction Profile";
const predictionProfileAboveMeanKey = "Prediction Profile Above Target Mean";
const geoInformationAttributeKeys = new Set([
  "Country",
  "GPS coordinates",
  "_GPS coordinates_altitude",
  "_GPS coordinates_precision",
  "_GPS coordinates_latitude",
  "_GPS coordinates_longitude",
]);
const germplasmAttributeKeys = [
  "Trial series name",
  "Rep",
  "Farm",
  "Site Number",
  "Plot",
  "EntryCode",
  "Name",
  "Local check, Name of variety provided by farmer",
];
const germplasmAttributeKeySet = new Set(germplasmAttributeKeys);

const countryPalette = [
  "#d9d2c3",
  "#c7d6cf",
  "#d8c8d8",
  "#e6d7bf",
  "#c5d1df",
  "#d5ddc6",
  "#dbc7bf",
  "#c7d7d3",
  "#d7d1c8",
  "#cad2c0",
];
const multiProfilePalette = [
  "#2e7d32",
  "#f39c12",
  "#8e44ad",
  "#00897b",
  "#c0392b",
  "#6d4c41",
  "#ff7043",
  "#7cb342",
  "#26a69a",
  "#5c6bc0",
];

const svg = d3.select("#map");
const mapFrame = document.getElementById("map-frame");
const tooltip = document.getElementById("tooltip");
const statsContainer = document.getElementById("stats");
const detailsTitle = document.getElementById("details-title");
const detailsSubtitle = document.getElementById("details-subtitle");
const detailsMeta = document.getElementById("details-meta");
const detailsList = document.getElementById("details-list");
const pageIndicator = document.getElementById("page-indicator");
const prevPageButton = document.getElementById("prev-page");
const nextPageButton = document.getElementById("next-page");
const summaryTabCountriesButton = document.getElementById("summary-tab-countries");
const summaryTabStatsButton = document.getElementById("summary-tab-stats");
const summaryTabLogButton = document.getElementById("summary-tab-log");
const summaryPanelCountries = document.getElementById("summary-panel-countries");
const summaryPanelStats = document.getElementById("summary-panel-stats");
const summaryPanelLog = document.getElementById("summary-panel-log");
const summaryLog = document.getElementById("summary-log");
const dataViewTabOriginalButton = document.getElementById("data-view-tab-original");
const dataViewTabTrainingButton = document.getElementById("data-view-tab-training");
const dataViewTabTopGermplasmButton = document.getElementById("data-view-tab-top-germplasm");
const dataViewTabPredictionButton = document.getElementById("data-view-tab-prediction");
const topGermplasmPanel = document.getElementById("top-germplasm-panel");
const topGermplasmDownload = document.getElementById("top-germplasm-download");
const topGermplasmPreview = document.getElementById("top-germplasm-preview");
const topGermplasmPreviewTable = document.getElementById("top-germplasm-preview-table");
const topGermplasmPreviewStatus = document.getElementById("top-germplasm-preview-status");
const topGermplasmPreviewSliderWrap = document.getElementById("top-germplasm-preview-slider-wrap");
const topGermplasmPreviewSlider = document.getElementById("top-germplasm-preview-slider");
const predictionControlsPanel = document.getElementById("prediction-controls-panel");
const predictionLoadingSlot = document.getElementById("prediction-loading-slot");
const selectionPropertiesPanel = document.getElementById("selection-properties-panel");
const selectionPropertiesStepper = document.getElementById("selection-properties-stepper");
const selectionPropertiesCollapsed = document.getElementById("selection-properties-collapsed");
const selectionPropertiesCollapsedCopy = document.getElementById("selection-properties-collapsed-copy");
const selectionPropertiesRestore = document.getElementById("selection-properties-restore");
const selectionPropertiesHide = document.getElementById("selection-properties-hide");
const selectionPropertiesBadge = document.getElementById("selection-properties-badge");
const selectionWorkspaceNameInput = document.getElementById("selection-workspace-name");
const selectionPropertiesFileName = document.getElementById("selection-properties-file-name");
const selectionPropertiesUploadTrigger = document.getElementById("selection-properties-upload-trigger");
const selectionPropertiesStatus = document.getElementById("selection-properties-status");
const selectionInitialSettingsCard = document.getElementById("selection-initial-settings-card");
const selectionStepNextButton = document.getElementById("selection-step-next-button");
const selectionTargetVariableSelect = document.getElementById("selection-target-variable");
const selectionLongitudeColumnSelect = document.getElementById("selection-longitude-column");
const selectionLatitudeColumnSelect = document.getElementById("selection-latitude-column");
const selectionPlantingDateColumnSelect = document.getElementById("selection-planting-date-column");
const selectionHarvestingDateColumnSelect = document.getElementById("selection-harvesting-date-column");
const selectionSoilTextureColumnSelect = document.getElementById("selection-soil-texture-column");
const selectionSoilDepthColumnSelect = document.getElementById("selection-soil-depth-column");
const selectionSelectColumnsCard = document.getElementById("selection-select-columns-card");
const selectionSelectColumnsRoot = document.getElementById("selection-select-columns-root");
const selectionCategoricalCard = document.getElementById("selection-categorical-card");
const selectionCategoricalRoot = document.getElementById("selection-categorical-root");
const selectionQuantitativeCard = document.getElementById("selection-quantitative-card");
const selectionQuantitativeRoot = document.getElementById("selection-quantitative-root");
const selectionSummaryCard = document.getElementById("selection-summary-card");
const selectionSummaryRoot = document.getElementById("selection-summary-root");
const selectionCategoricListbox = document.getElementById("selection-categoric-listbox");
const selectionQuantitativeListbox = document.getElementById("selection-cuantitative-listbox");
const selectionExcludedListbox = document.getElementById("selection-excluded-listbox");
const selectionCategoricSearch = document.getElementById("selection-categoric-search");
const selectionQuantitativeSearch = document.getElementById("selection-cuantitative-search");
const selectionExcludedSearch = document.getElementById("selection-excluded-search");
const selectionStepItems = [...document.querySelectorAll(".selection-step")];
const selectionSelectColumnsCount = document.getElementById("selection-select-columns-count");
const selectionSummaryNextButton = document.getElementById("selection-summary-next-button");
const selectionSummaryBadge = document.getElementById("selection-summary-badge");
const selectionOverviewTarget = document.getElementById("selection-overview-target");
const selectionOverviewLongitude = document.getElementById("selection-overview-longitude");
const selectionOverviewLatitude = document.getElementById("selection-overview-latitude");
const selectionOverviewColumns = document.getElementById("selection-overview-columns");
const selectionOverviewRows = document.getElementById("selection-overview-rows");
const selectionOverviewPoints = document.getElementById("selection-overview-points");
const newWorkspaceReloadFlagKey = "cimmyt_app_open_stepper_after_reload";
let forceOpenStepperAfterReload = false;
const selectionChoices = new Map();
const selectionChoiceConfigs = new Map();
const tabGeoButton = document.getElementById("tab-geo");
const tabAttributesButton = document.getElementById("tab-attributes");
const tabGermplasmButton = document.getElementById("tab-germplasm");
const panelGeo = document.getElementById("panel-geo");
const panelAttributes = document.getElementById("panel-attributes");
const panelGermplasm = document.getElementById("panel-germplasm");
const countrySummary = document.getElementById("country-summary");
const germplasmList = document.getElementById("germplasm-list");
const fileInput = document.getElementById("xlsx-file");
const fileUploadTriggers = [...document.querySelectorAll("label[for='xlsx-file']")];
const savedModelSelect = document.getElementById("saved-model-select");
const savedModelGroup = savedModelSelect?.closest(".model-select-group") ?? null;
const predictionControlsClearButton = document.getElementById("prediction-controls-clear");
const savedModelHelp = document.getElementById("saved-model-help");
const climateScopeGroup = document.getElementById("climate-scope-group");
const climateScopeSelect = document.getElementById("climate-scope-select");
const climateScopeHelp = document.getElementById("climate-scope-help");
const predictionPointUploadPanel = document.getElementById("prediction-point-upload-panel");
const predictionPointOriginalButton = document.getElementById("prediction-point-original-button");
const predictionPointUploadButton = document.getElementById("prediction-point-upload-button");
const predictionPointUploadCopy = document.getElementById("prediction-point-upload-copy");
const regionalCountryPanel = document.getElementById("regional-country-panel");
const regionalCountrySelect = document.getElementById("regional-country-select");
const regionalCountryPreview = document.getElementById("regional-country-preview");
const regionalManualPanel = document.getElementById("regional-manual-panel");
const regionalBoundsLatitudeMinInput = document.getElementById("regional-bounds-latitude-min");
const regionalBoundsLatitudeMaxInput = document.getElementById("regional-bounds-latitude-max");
const regionalBoundsLongitudeMinInput = document.getElementById("regional-bounds-longitude-min");
const regionalBoundsLongitudeMaxInput = document.getElementById("regional-bounds-longitude-max");
const regionalManualPreview = document.getElementById("regional-manual-preview");
const regionalBoundsDrawMapButton = document.getElementById("regional-bounds-draw-map");
const regionalBoundsClearMapButton = document.getElementById("regional-bounds-clear-map");
const regionalManualMapHelp = document.getElementById("regional-manual-map-help");
const forecastDatesPanel = document.getElementById("forecast-dates-panel");
const forecastPlantingDateInput = document.getElementById("forecast-planting-date");
const forecastHarvestingDateInput = document.getElementById("forecast-harvesting-date");
const germplasmSelectionPanel = document.getElementById("germplasm-selection-panel");
const germplasmSelectionTitle = document.getElementById("germplasm-selection-title");
const germplasmSelectionList = document.getElementById("germplasm-selection-list");
const germplasmSelectionCount = document.getElementById("germplasm-selection-count");
const germplasmSelectionHelp = document.getElementById("germplasm-selection-help");
const germplasmSelectAllButton = document.getElementById("germplasm-select-all");
const germplasmClearAllButton = document.getElementById("germplasm-clear-all");
const germplasmSelectionIdPicker = document.getElementById("germplasm-selection-id-picker");
const germplasmSelectionIdSelect = document.getElementById("germplasm-selection-id-select");
const executeGermplasmSelectionButton = document.getElementById("execute-germplasm-selection");
const preprocessValidationPanel = document.getElementById("preprocess-validation-panel");
const preprocessValidationMessage = document.getElementById("preprocess-validation-message");
const downloadPreprocessOutput = document.getElementById("download-preprocess-output");
const continueAfterPreprocessButton = document.getElementById("continue-after-preprocess");
const modelCount = document.getElementById("model-count");
const modelPanel = document.querySelector(".model-panel");
const modelEmpty = document.getElementById("model-empty");
const modelList = document.getElementById("model-list");
const modelScroller = document.getElementById("model-scroller");
const modelScrollPrev = document.getElementById("model-scroll-prev");
const modelScrollNext = document.getElementById("model-scroll-next");
const modelModal = document.getElementById("model-modal");
const modelModalBackdrop = document.getElementById("model-modal-backdrop");
const modelModalClose = document.getElementById("model-modal-close");
const modelModalCard = document.getElementById("model-modal-card");
const modelModalTitle = document.getElementById("model-modal-title");
const modelModalDescription = document.getElementById("model-modal-description");
const modelModalGrid = document.getElementById("model-modal-grid");
const modelModalMachines = document.getElementById("model-modal-machines");
const modelModalDownloads = document.getElementById("model-modal-downloads");
const modelDeleteButton = document.getElementById("model-delete-button");
const modelNameModal = document.getElementById("model-name-modal");
const modelNameModalBackdrop = document.getElementById("model-name-modal-backdrop");
const modelNameModalClose = document.getElementById("model-name-modal-close");
const modelNameModalCard = document.getElementById("model-name-modal-card");
const modelNameModalDescription = document.getElementById("model-name-modal-description");
const modelNameModalMeta = document.getElementById("model-name-modal-meta");
const modelNameInput = document.getElementById("model-name-input");
const modelNameModalLater = document.getElementById("model-name-modal-later");
const modelNameModalSave = document.getElementById("model-name-modal-save");
const loadingPanel = document.getElementById("loading-panel");
const loadingBarFill = document.getElementById("loading-bar-fill");
const loadingStage = document.getElementById("loading-stage");
const loadingPercent = document.getElementById("loading-percent");
const loadingMessage = document.getElementById("loading-message");
const loadingPanelHomeParent = loadingPanel?.parentElement ?? null;
const loadingPanelHomeNextSibling = loadingPanel?.nextElementSibling ?? null;
const tilesContainer = document.getElementById("tiles");
const buildBadge = document.getElementById("build-badge");
const heroBuildInline = document.getElementById("hero-build-inline");
const cancelAllButton = document.getElementById("cancel-all-button");
const newWorkspaceButton = document.getElementById("new-workspace-button");
const refreshAppButton = document.getElementById("refresh-app-button");
const settingsButton = document.getElementById("settings-button");
const settingsModal = document.getElementById("settings-modal");
const settingsModalBackdrop = document.getElementById("settings-modal-backdrop");
const settingsModalClose = document.getElementById("settings-modal-close");
const settingsModalCard = document.getElementById("settings-modal-card");
const settingsModalCancel = document.getElementById("settings-modal-cancel");
const settingsModalSave = document.getElementById("settings-modal-save");
const settingsModalStatus = document.getElementById("settings-modal-status");
const settingsFeatureheroGenerationInput = document.getElementById("settings-featurehero-generation");
const settingsFeatureheroPopulationInput = document.getElementById("settings-featurehero-population");
const settingsFeatureheroMachinesInput = document.getElementById("settings-featurehero-machines");
const settingsFeatureheroMetricInput = document.getElementById("settings-featurehero-metric");
const settingsNasaResolutionInput = document.getElementById("settings-nasa-resolution");
const predictionIdModal = document.getElementById("prediction-id-modal");
const predictionIdModalBackdrop = document.getElementById("prediction-id-modal-backdrop");
const predictionIdModalClose = document.getElementById("prediction-id-modal-close");
const predictionIdModalCard = document.getElementById("prediction-id-modal-card");
const predictionIdModalDescription = document.getElementById("prediction-id-modal-description");
const predictionIdColumnSelect = document.getElementById("prediction-id-column-select");
const predictionIdModalCancel = document.getElementById("prediction-id-modal-cancel");
const predictionIdModalAccept = document.getElementById("prediction-id-modal-accept");
selectionChoiceConfigs.set(selectionTargetVariableSelect, { searchEnabled: true, searchPlaceholderValue: "Search target variable", placeholderValue: "Select target variable" });
selectionChoiceConfigs.set(selectionLongitudeColumnSelect, { searchEnabled: true, searchPlaceholderValue: "Search longitude column", placeholderValue: "Select longitude column" });
selectionChoiceConfigs.set(selectionLatitudeColumnSelect, { searchEnabled: true, searchPlaceholderValue: "Search latitude column", placeholderValue: "Select latitude column" });
selectionChoiceConfigs.set(selectionPlantingDateColumnSelect, { searchEnabled: true, searchPlaceholderValue: "Search Date of Plating", placeholderValue: "Select Date of Plating" });
selectionChoiceConfigs.set(selectionHarvestingDateColumnSelect, { searchEnabled: true, searchPlaceholderValue: "Search Date of Harvesting", placeholderValue: "Select Date of Harvesting" });
selectionChoiceConfigs.set(selectionSoilTextureColumnSelect, { searchEnabled: true, searchPlaceholderValue: "Search Soil type/texture", placeholderValue: "Select Soil type/texture" });
selectionChoiceConfigs.set(selectionSoilDepthColumnSelect, { searchEnabled: true, searchPlaceholderValue: "Search Soil Depth (cm)", placeholderValue: "Select Soil Depth (cm)" });
selectionChoiceConfigs.set(germplasmSelectionIdSelect, { searchEnabled: true, searchPlaceholderValue: "Search id field", placeholderValue: "Select id field" });
selectionChoiceConfigs.set(predictionIdColumnSelect, { searchEnabled: true, searchPlaceholderValue: "Search id field", placeholderValue: "Select id field" });
const legendDot = document.getElementById("legend-dot");
const TOP_GERMPLASM_ENABLED = false;
const legendLabel = document.getElementById("legend-label");
const trainingMetric = document.getElementById("training-metric");
const trainingMetricValue = document.getElementById("training-metric-value");
const predictionMeanBanner = document.getElementById("prediction-mean-banner");
const predictionMeanBannerValue = document.getElementById("prediction-mean-banner-value");
const colorHelpPanel = document.getElementById("color-help-panel");
const colorHelpList = document.getElementById("color-help-list");
const ACTIVE_PIPELINE_JOB_STORAGE_KEY = "mictlan-active-pipeline-job";
const ACTIVE_PIPELINE_JOB_MAX_AGE_MS = 30 * 60 * 1000;
const PIPELINE_POLL_BASE_DELAY_MS = 700;
const PIPELINE_POLL_MAX_DELAY_MS = 8000;
const TRANSIENT_PIPELINE_STATUS_CODES = new Set([408, 425, 429, 500, 502, 503, 504, 520, 521, 522, 523, 524]);

const formatNumber = d3.format(",");
const formatCoordinate = d3.format(".5f");
const formatSignedNumber = d3.format("+,.3f");
const baseProjection = d3
  .geoMercator()
  .scale(256 / (2 * Math.PI))
  .translate([128, 128]);

const markerPath =
  "M0,-11 C5,-11 9,-7 9,-2 C9,5 3,8 0,14 C-3,8 -9,5 -9,-2 C-9,-7 -5,-11 0,-11 Z";
const OVERLAPPING_MARKER_BASE_RADIUS = 14;
const OVERLAPPING_MARKER_RING_STEP = 10;
const AUTOMATIC_FLOW_PROXIMITY_BUCKET_DEGREES = 0.0025;

let selectedFeature = null;
let currentPage = 0;
let activeDetailsTab = "germplasm";
let activeSummaryTab = "countries";
let currentTransform = d3.zoomIdentity;
let initialTransform = d3.zoomIdentity;
let zoomBehavior = null;
let mapContext = null;
let loadedFeatures = [];
let predictedYieldStats = null;
let trainingErrorQuartiles = null;
let activePredictionProfileHighlight = "";
let selectionSummaryPhaseTimerId = 0;
let selectionSummaryPhase3TimerId = 0;
let savedModelsCache = [];
let selectedSavedModelId = "";
let activeModalModelId = "";
let lastFocusedElement = null;
let workflowInteractive = false;
let pausedPreprocessPayload = null;
let selectedClimateScope = "";
let mapBoundingBoxSelectionMode = false;
let mapBoundingBoxDraft = null;
let mapBoundingBoxSelectionStart = null;
let regionalCountryBoundsCache = [];
let preprocessValidationEnabled = true;
let featureheroSettings = {
  number_generation: 10,
  number_population: 10,
  machines: ["extreme_gradient_boost_regression"],
  metric: "mean_absolute_error",
  nasa_power_resolution_km: 5,
};
const defaultFeatureheroMachine = "extreme_gradient_boost_regression";
const defaultFeatureheroMetric = "mean_absolute_error";
const supportedFeatureheroMachines = new Set([
  "extreme_gradient_boost_regression",
  "random_forest_regression",
  "lasso_regression",
  "support_vector_regression",
]);
const supportedFeatureheroMetrics = new Set([
  "mean_absolute_error",
  "root_mean_squared_error",
]);
const supportedNasaResolutionKm = new Set(Array.from({ length: 10 }, (_, index) => index + 1));
let pendingSavedModelFile = null;
let availableGermplasmNames = [];
let availableGermplasmProfilesByName = {};
let availablePredictionIdFields = [];
let selectedPredictionIdField = "";
let availablePredictionIdValuesByName = {};
const clearSelectionIdSentinel = "__clear_selection__";
let pendingPredictionIdModalPayload = null;
let selectedGermplasmNames = new Set();
let selectedGermplasmRunInProgress = false;
let regionalManualPreviewGridCellCount = null;
let regionalManualPreviewGrid = null;
let loadingPanelResetTimer = null;
let currentRenderedFlowMode = "automatic";
let activeDataViewTab = "original";
let selectedWorkflowMode = "training";
let predictionBridgeState = null;
let predictionGermplasmSourceMode = "uploaded";
let topGermplasmPreviewStart = 0;
let datasetStore = {
  original: null,
  training: null,
  top_germplasm: null,
  prediction: null,
};
let promptedModelNames = new Set();
let pendingModelNameRequest = null;
const selectionPropertiesFlowEnabled = true;
const legacyPipelineDisabled = false;
let selectionPropertiesState = {
  file: null,
  sourceName: "",
  workspaceName: "",
  headers: [],
  columnProfiles: {},
  columnAssignments: {},
  enabledClassifierColumns: [],
  classifierListScrollTop: 0,
  noDefinedColumns: [],
  rowCount: 0,
  attributeCount: 0,
  targetColumn: "",
  latitudeColumn: "",
  longitudeColumn: "",
  plantingDateColumn: "",
  harvestingDateColumn: "",
  soilTextureColumn: "",
  soilDepthColumn: "",
  identifierColumns: [],
  identifierConfirmed: false,
  categoricalColumns: [],
  categoricalConfirmed: false,
  quantitativeColumns: [],
  quantitativeConfirmed: false,
  columnClassificationConfirmed: false,
  excludedColumns: [],
  summaryReady: false,
  summaryExecuting: false,
  statusUnlocked: false,
  collapsed: false,
  latestSummaryRun: null,
  previewOriginalLoaded: false,
  workspaceReadonlyLoaded: false,
  activeStep: "initial",
  highlightedIdentifierColumn: "",
  highlightedCategoricalColumn: "",
  highlightedQuantitativeColumn: "",
  identifierListScrollTop: 0,
  categoricalListScrollTop: 0,
  quantitativeListScrollTop: 0,
  mappedFeatureCount: 0,
  search: {
    target: "",
    longitude: "",
    latitude: "",
    plantingDate: "",
    harvestingDate: "",
    soilTexture: "",
    soilDepth: "",
    identifiers: "",
    categoric: "",
    cuantitative: "",
    excluded: "",
  },
};

const sleepFrame = () => new Promise((resolve) => requestAnimationFrame(resolve));
const sleep = (ms) => new Promise((resolve) => window.setTimeout(resolve, ms));

const setSettingsStatus = (message = "") => {
  if (settingsModalStatus) {
    settingsModalStatus.textContent = message;
  }
};

const populateFeatureheroSettingsForm = (settings = featureheroSettings) => {
  const machines = Array.isArray(settings?.machines)
    ? settings.machines.map((item) => String(item).trim()).filter((item) => supportedFeatureheroMachines.has(item))
    : [];
  const metric = String(settings?.metric ?? defaultFeatureheroMetric).trim();
  const nasaResolution = Number(settings?.nasa_power_resolution_km ?? 5);
  featureheroSettings = {
    number_generation: Number(settings?.number_generation ?? 10),
    number_population: Number(settings?.number_population ?? 10),
    machines: machines.length ? machines : [defaultFeatureheroMachine],
    metric: supportedFeatureheroMetrics.has(metric) ? metric : defaultFeatureheroMetric,
    nasa_power_resolution_km: supportedNasaResolutionKm.has(nasaResolution) ? nasaResolution : 5,
  };
  if (settingsFeatureheroGenerationInput) {
    settingsFeatureheroGenerationInput.value = String(featureheroSettings.number_generation);
  }
  if (settingsFeatureheroPopulationInput) {
    settingsFeatureheroPopulationInput.value = String(featureheroSettings.number_population);
  }
  if (settingsFeatureheroMachinesInput) {
    settingsFeatureheroMachinesInput.value = featureheroSettings.machines[0] ?? defaultFeatureheroMachine;
  }
  if (settingsFeatureheroMetricInput) {
    settingsFeatureheroMetricInput.value = featureheroSettings.metric;
  }
  if (settingsNasaResolutionInput) {
    settingsNasaResolutionInput.value = String(featureheroSettings.nasa_power_resolution_km);
  }
};

const closeSettingsModal = () => {
  if (!settingsModal) {
    return;
  }
  settingsModal.hidden = true;
  settingsModal.setAttribute("inert", "");
  settingsModal.setAttribute("aria-hidden", "true");
  if (settingsModalCard) {
    settingsModalCard.removeAttribute("role");
    settingsModalCard.removeAttribute("aria-modal");
  }
  setSettingsStatus("");
};

const openSettingsModal = () => {
  if (!settingsModal) {
    return;
  }
  populateFeatureheroSettingsForm(featureheroSettings);
  settingsModal.hidden = false;
  settingsModal.removeAttribute("inert");
  settingsModal.setAttribute("aria-hidden", "false");
  if (settingsModalCard) {
    settingsModalCard.setAttribute("role", "dialog");
    settingsModalCard.setAttribute("aria-modal", "true");
  }
  setSettingsStatus("");
  settingsFeatureheroGenerationInput?.focus();
};

const parseFeatureheroSettingsForm = () => {
  const numberGeneration = Number(settingsFeatureheroGenerationInput?.value ?? 0);
  const numberPopulation = Number(settingsFeatureheroPopulationInput?.value ?? 0);
  const selectedMachine = String(settingsFeatureheroMachinesInput?.value ?? "").trim();
  const machines = supportedFeatureheroMachines.has(selectedMachine) ? [selectedMachine] : [];
  const metric = String(settingsFeatureheroMetricInput?.value ?? "").trim();
  const nasaResolutionKm = Number(settingsNasaResolutionInput?.value ?? 0);
  if (!machines.length) {
    throw new Error("Select at least one FeatureHero machine.");
  }
  if (!supportedFeatureheroMetrics.has(metric)) {
    throw new Error("Select a valid FeatureHero metric.");
  }
  if (!supportedNasaResolutionKm.has(nasaResolutionKm)) {
    throw new Error("Select a valid climate grid resolution.");
  }
  return {
    number_generation: numberGeneration,
    number_population: numberPopulation,
    machines,
    metric,
    nasa_power_resolution_km: nasaResolutionKm,
  };
};

const saveFeatureheroSettings = async () => {
  const payload = {
    featurehero_settings: parseFeatureheroSettingsForm(),
  };
  setSettingsStatus("Saving settings...");
  const response = await fetch("/api/cimmyt-app-config", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  const result = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(result.error ?? "The settings could not be saved.");
  }
  populateFeatureheroSettingsForm(result.featurehero_settings ?? payload.featurehero_settings);
  if (isRegionalManualMode()) {
    renderManualRegionalPreview().catch((error) => console.error(error));
  }
  setSettingsStatus("Settings saved successfully.");
  closeSettingsModal();
};

const cancelAllProcesses = async () => {
  await setLoadingState(12, "Cancelling processes", "Stopping running pipeline and FeatureHero jobs.");
  const response = await fetch("/api/process-xlsx/cancel-all", {
    method: "POST",
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.error ?? "The running processes could not be cancelled.");
  }
  clearActivePipelineJob();
  await setLoadingState(
    100,
    "Processes cancelled",
    `${payload.cancelled_total ?? 0} running process(es) were stopped. Refreshing the app.`,
  );
  window.setTimeout(() => {
    window.location.reload();
  }, 450);
};

const persistActivePipelineJob = (job) => {
  try {
    window.localStorage.setItem(
      ACTIVE_PIPELINE_JOB_STORAGE_KEY,
      JSON.stringify({
        ...job,
        savedAt: new Date().toISOString(),
      }),
    );
  } catch (error) {
    console.error(error);
  }
};

const readActivePipelineJob = () => {
  try {
    const raw = window.localStorage.getItem(ACTIVE_PIPELINE_JOB_STORAGE_KEY);
    if (!raw) {
      return null;
    }
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") {
      return null;
    }
    const savedAtValue = Date.parse(String(parsed.savedAt ?? ""));
    const jobAgeMs = Number.isFinite(savedAtValue) ? Date.now() - savedAtValue : 0;
    const lastPercent = Number(parsed.lastPercent ?? 0);
    const state = String(parsed.state ?? "").trim().toLowerCase();
    if ((Number.isFinite(lastPercent) && lastPercent >= 100) || state === "completed" || (jobAgeMs > ACTIVE_PIPELINE_JOB_MAX_AGE_MS)) {
      clearActivePipelineJob();
      return null;
    }
    return parsed;
  } catch (error) {
    console.error(error);
    return null;
  }
};

const clearActivePipelineJob = () => {
  try {
    window.localStorage.removeItem(ACTIVE_PIPELINE_JOB_STORAGE_KEY);
  } catch (error) {
    console.error(error);
  }
};

const triggerBrowserDownload = (downloadUrl) => {
  const normalizedUrl = String(downloadUrl ?? "").trim();
  if (!normalizedUrl) {
    return;
  }
  const anchor = document.createElement("a");
  anchor.href = normalizedUrl;
  anchor.style.display = "none";
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
};

const getInitialPipelineLoadingStep = (fileName = "uploaded workbook", workflowMode = "training") => {
  const normalizedFileName = String(fileName ?? "uploaded workbook").trim() || "uploaded workbook";
  if (workflowMode === "prediction") {
    return {
      percent: 12,
      stage: "Preparing ce prediction input",
      message: `Validating ${normalizedFileName} against the workspace model and preparing the phase02prediction input workbook.`,
    };
  }
  return {
    percent: 12,
    stage: "Loading uploaded workbook",
    message: `Validating ${normalizedFileName} and preparing the ce_pipeline training workspace.`,
  };
};

const getFallbackPipelineProgress = (workflowMode = "training") => {
  if (workflowMode === "prediction") {
    return {
      stage: "Executing High-Potential Sites pipeline",
      message: "The backend is running phase02prediction, phase03prediction, phase04prediction, and phase05 for the selected germplasm.",
    };
  }
  return {
    stage: "Executing ce_pipeline",
    message: "The backend is processing phase01 through phase05 for the current training run.",
  };
};

const setMapEnabled = (enabled) => {
  mapFrame.classList.toggle("map-frame-disabled", !enabled);
};

const shouldEnableMapForBoundingBoxSelection = () =>
  isPredictionWorkflowMode() && isRegionalManualMode();

const refreshMapAvailability = () => {
  setMapEnabled(workflowInteractive || shouldEnableMapForBoundingBoxSelection());
};

const setWorkflowInteractive = (enabled) => {
  workflowInteractive = enabled;
  refreshMapAvailability();
  summaryTabCountriesButton.disabled = !enabled;
  summaryTabStatsButton.disabled = !enabled;
  if (summaryTabLogButton) {
    summaryTabLogButton.disabled = !enabled;
  }
  tabAttributesButton.disabled = !enabled;
  tabGermplasmButton.disabled = !enabled;
  tabGeoButton.disabled = !enabled;
  prevPageButton.disabled = !enabled || currentPage === 0;
  nextPageButton.disabled = !enabled;
  if (!enabled) {
    return;
  }
};

const formatDateTime = (value) => {
  if (!value) {
    return "Unknown date";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString();
};

const truncateText = (value, maxLength = 78) => {
  const normalized = String(value ?? "").trim();
  if (normalized.length <= maxLength) {
    return normalized;
  }
  return `${normalized.slice(0, maxLength - 1)}...`;
};

const escapeHtml = (value) =>
  String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");

const buildModelOptionLabel = (model) => {
  const metricValue =
    typeof model?.metric_value === "number" ? model.metric_value.toFixed(4) : "N/A";
  const createdAt = formatDateTime(model?.created_at);
  const description = truncateText(model?.description ?? "No description available.");
  const displayName = String(model?.display_name ?? "").trim();
  const identity = displayName
    ? `${displayName} | ${model?.model_id ?? "Unnamed"}`
    : `${model?.model_id ?? "Unnamed"}`;
  return `${identity} | ${createdAt} | ${description} | ${model?.metric_name ?? "Metric"} ${metricValue}`;
};

const getSelectedSavedModel = () =>
  savedModelsCache.find((model) => model.model_id === selectedSavedModelId) ?? null;

const isPredictionWorkflowMode = () => selectedWorkflowMode === "prediction";
const isTrainingWorkflowMode = () => selectedWorkflowMode === "training";
const isSavedModelForecastMode = () => Boolean(selectedSavedModelId);
const isSavedModelRenderMode = () => currentRenderedFlowMode === "saved_model";
const isOriginalDataRenderMode = () => currentRenderedFlowMode === "original";
const getEffectiveClimateScope = () =>
  isPredictionWorkflowMode() && isSavedModelForecastMode() ? selectedClimateScope : "point";
const isHighPotentialSitesPredictionMode = () =>
  isPredictionWorkflowMode() && isRegionalManualMode();

const isMultiProfilePredictionResult = () =>
  activeDataViewTab === "prediction" && Boolean(datasetStore.prediction?.summary?.multi_profile_mode);

const getPredictionDistinctGermplasmNames = () => {
  const candidateFeatures = loadedFeatures.length
    ? loadedFeatures
    : Array.isArray(datasetStore.prediction?.geojson?.features)
      ? datasetStore.prediction.geojson.features
      : [];
  return Array.from(
    new Set(
      candidateFeatures
        .map((feature) => String(feature?.properties?.Name ?? "").trim())
        .filter(Boolean),
    ),
  );
};

const isMultiGermplasmPredictionResult = () =>
  activeDataViewTab === "prediction" &&
  currentRenderedFlowMode === "saved_model" &&
  getPredictionDistinctGermplasmNames().length > 1;

const isCategoricalPredictionColorMode = () =>
  isMultiGermplasmPredictionResult() || isMultiProfilePredictionResult();

const getPredictionProfileVaryingColumns = () =>
  Array.isArray(datasetStore.prediction?.summary?.varying_columns)
    ? datasetStore.prediction.summary.varying_columns
    : [];

const getPredictionProfileSingleVaryingHeader = () => {
  const varyingColumns = getPredictionProfileVaryingColumns();
  return varyingColumns.length === 1
    ? String(varyingColumns[0]?.header ?? "").trim()
    : "";
};

const getPredictionCategoryLabelForFeature = (feature) => {
  if (isMultiGermplasmPredictionResult()) {
    return String(feature?.properties?.Name ?? "").trim();
  }
  return String(feature?.properties?.[predictionProfileLabelKey] ?? "").trim();
};

const getPredictionProfileDisplayLabel = (label) => {
  const normalizedLabel = String(label ?? "").trim();
  if (!normalizedLabel) {
    return "Profile";
  }
  if (isMultiGermplasmPredictionResult()) {
    return normalizedLabel;
  }
  const singleHeader = getPredictionProfileSingleVaryingHeader();
  if (!singleHeader) {
    return normalizedLabel;
  }
  const prefix = `${singleHeader}:`;
  if (!normalizedLabel.startsWith(prefix)) {
    return normalizedLabel;
  }
  const compactValue = normalizedLabel.slice(prefix.length).trim();
  return compactValue || normalizedLabel;
};

const getPredictionProfileColorMap = () => {
  if (isMultiGermplasmPredictionResult()) {
    const labels = getPredictionDistinctGermplasmNames();
    return new Map(
      labels.map((label, index) => [label, multiProfilePalette[index % multiProfilePalette.length]]),
    );
  }
  const summaryProfiles = Array.isArray(datasetStore.prediction?.summary?.profile_summaries)
    ? datasetStore.prediction.summary.profile_summaries
    : [];
  const labels = summaryProfiles
    .map((item) => String(item?.label ?? "").trim())
    .filter(Boolean);
  if (!labels.length) {
    const featureLabels = (datasetStore.prediction?.geojson?.features ?? [])
      .map((feature) => String(feature?.properties?.[predictionProfileLabelKey] ?? "").trim())
      .filter(Boolean);
    featureLabels.forEach((label) => {
      if (!labels.includes(label)) {
        labels.push(label);
      }
    });
  }
  return new Map(
    labels.map((label, index) => [label, multiProfilePalette[index % multiProfilePalette.length]]),
  );
};

const getPredictionProfileColor = (label) => {
  const normalized = String(label ?? "").trim();
  if (!normalized) {
    return "#2e7d32";
  }
  return getPredictionProfileColorMap().get(normalized) ?? "#2e7d32";
};

const setLegendState = (renderFlowMode = currentRenderedFlowMode) => {
  if (!legendDot || !legendLabel) {
    return;
  }
  if (renderFlowMode === "original") {
    legendDot.style.background = "#e2b93b";
    legendDot.style.boxShadow = "0 0 0 3px rgba(226, 185, 59, 0.18)";
    legendLabel.textContent = "Original workbook records";
    return;
  }
  if (renderFlowMode === "saved_model") {
    if (isCategoricalPredictionColorMode()) {
      const firstColor = multiProfilePalette[0];
      legendDot.style.background = firstColor;
      legendDot.style.boxShadow = "0 0 0 3px rgba(46, 125, 50, 0.16)";
      legendLabel.textContent = isMultiGermplasmPredictionResult()
        ? "Selected germplasms"
        : "Prediction profiles";
      return;
    }
    legendDot.style.background = "#245c9f";
    legendDot.style.boxShadow = "0 0 0 3px rgba(36, 92, 159, 0.16)";
    legendLabel.textContent = `Predicted ${getObservedTargetColumnLabel()}`;
    return;
  }
  legendDot.style.background = "#2f9e44";
  legendDot.style.boxShadow = "0 0 0 3px rgba(47, 158, 68, 0.15)";
  legendLabel.textContent = "Training comparison";
};

const formatMetricValue = (value) => {
  const numeric = asFloat(value);
  return numeric === null ? "--" : numeric.toFixed(4);
};

const updateTrainingMetricVisibility = () => {
  if (!trainingMetric || !trainingMetricValue) {
    if (predictionMeanBanner && predictionMeanBannerValue) {
      predictionMeanBanner.hidden = true;
      predictionMeanBannerValue.textContent = "--";
    }
    return;
  }
  const trainingSummary = datasetStore.training?.summary ?? null;
  const metricValue = trainingSummary?.prediction_model_metric_value;
  const shouldShowTrainingMetric =
    activeDataViewTab === "training" &&
    trainingSummary &&
    trainingSummary.prediction_model_metric_name === "mean_absolute_error" &&
    asFloat(metricValue) !== null;
  trainingMetric.hidden = !shouldShowTrainingMetric;
  if (!shouldShowTrainingMetric) {
    trainingMetricValue.textContent = "--";
  } else {
    trainingMetricValue.textContent = formatMetricValue(metricValue);
  }
  const shouldShowPredictionMean =
    activeDataViewTab === "prediction" &&
    currentRenderedFlowMode === "saved_model" &&
    getPredictedMeanValue() !== null;
  if (predictionMeanBanner && predictionMeanBannerValue) {
    predictionMeanBanner.hidden = !shouldShowPredictionMean;
    predictionMeanBannerValue.textContent = shouldShowPredictionMean ? getPredictedMeanLabel() : "--";
  }
};

const renderTopGermplasmPreview = () => {
  if (!topGermplasmPreview || !topGermplasmPreviewTable || !topGermplasmPreviewStatus || !topGermplasmPreviewSliderWrap || !topGermplasmPreviewSlider) {
    return;
  }
  const summary = datasetStore.top_germplasm?.summary ?? null;
  const previewRows = Array.isArray(summary?.top_preview_rows) ? summary.top_preview_rows : [];
  const identifierColumns = Array.isArray(summary?.identifier_columns) ? summary.identifier_columns : [];
  const targetColumn = String(summary?.target_column ?? "").trim();
  const targetPredictedColumn = String(summary?.target_predicted_column ?? predictedYieldKey).trim() || predictedYieldKey;
  const targetPredictionMeanColumn = String(summary?.target_prediction_mean_column ?? "Target prediction mean").trim() || "Target prediction mean";
  const columns = [
    ...identifierColumns,
    ...(targetColumn ? [targetColumn] : []),
    targetPredictedColumn,
    targetPredictionMeanColumn,
  ];
  if (!previewRows.length || !columns.length || activeDataViewTab !== "top_germplasm") {
    topGermplasmPreview.hidden = true;
    topGermplasmPreviewTable.innerHTML = "";
    topGermplasmPreviewSliderWrap.hidden = true;
    topGermplasmPreviewStatus.textContent = "No preview rows available.";
    return;
  }
  topGermplasmPreviewStart = 0;
  const visibleRows = previewRows.slice(0, 10);
  const headerHtml = columns.map((column) => `<th>${escapeHtml(column)}</th>`).join("");
  const bodyHtml = visibleRows.map((row) => {
    const cells = columns.map((column) => `<td>${escapeHtml(formatAttributeValue(row?.[column] ?? ""))}</td>`).join("");
    return `<tr>${cells}</tr>`;
  }).join("");
  topGermplasmPreviewTable.innerHTML = `<thead><tr>${headerHtml}</tr></thead><tbody>${bodyHtml}</tbody>`;
  topGermplasmPreview.hidden = false;
  topGermplasmPreviewStatus.textContent = `Showing top ${visibleRows.length} rows`;
  topGermplasmPreviewSliderWrap.hidden = true;
  topGermplasmPreviewSlider.max = "0";
  topGermplasmPreviewSlider.value = "0";
  topGermplasmPreviewSlider.disabled = true;
};

function syncSummaryTabsForActiveView() {
  if (summaryTabCountriesButton) {
    summaryTabCountriesButton.hidden = false;
  }
  if (summaryTabStatsButton) {
    summaryTabStatsButton.hidden = false;
  }
  if (summaryTabLogButton) {
    summaryTabLogButton.hidden = activeDataViewTab !== "original";
  }
  if (activeDataViewTab !== "original" && activeSummaryTab === "log") {
    setActiveSummaryTab("countries");
  }
}

const updateTopGermplasmPanel = () => {
  if (topGermplasmPanel) {
    topGermplasmPanel.hidden = true;
  }
  if (topGermplasmDownload) {
    topGermplasmDownload.href = "#";
    topGermplasmDownload.download = "";
    topGermplasmDownload.toggleAttribute("disabled", true);
    topGermplasmDownload.setAttribute("aria-disabled", "true");
  }
  if (topGermplasmPreview) {
    topGermplasmPreview.hidden = true;
  }
};

const hasHighPotentialSitesAccess = () => Boolean(datasetStore.training);

const updateDataViewTabs = () => {
  const hasOriginalData = Boolean(datasetStore.original);
  const hasTrainingData = Boolean(datasetStore.training);
  const hasTopGermplasmData = TOP_GERMPLASM_ENABLED && Boolean(datasetStore.top_germplasm);
  const hasPredictionAccess = hasHighPotentialSitesAccess();
  if (activeDataViewTab === "prediction" && !hasPredictionAccess) {
    activeDataViewTab = hasTrainingData ? "training" : "original";
  } else if (activeDataViewTab === "top_germplasm" || (activeDataViewTab === "training" && !hasTrainingData)) {
    activeDataViewTab = hasTrainingData ? "training" : "original";
  } else if (activeDataViewTab === "original" && !hasOriginalData) {
    activeDataViewTab = hasTrainingData ? "training" : "original";
  }
  if (dataViewTabOriginalButton) {
    dataViewTabOriginalButton.classList.toggle("active", activeDataViewTab === "original");
    dataViewTabOriginalButton.disabled = !hasOriginalData;
  }
  if (dataViewTabTrainingButton) {
    dataViewTabTrainingButton.classList.toggle("active", activeDataViewTab === "training");
    dataViewTabTrainingButton.disabled = !hasTrainingData;
    dataViewTabTrainingButton.classList.toggle("is-disabled-flow", legacyPipelineDisabled && !hasTrainingData);
  }
  if (dataViewTabTopGermplasmButton) {
    dataViewTabTopGermplasmButton.hidden = !TOP_GERMPLASM_ENABLED;
    dataViewTabTopGermplasmButton.classList.toggle("active", TOP_GERMPLASM_ENABLED && activeDataViewTab === "top_germplasm");
    dataViewTabTopGermplasmButton.disabled = true;
  }
  if (dataViewTabPredictionButton) {
    dataViewTabPredictionButton.classList.toggle("active", activeDataViewTab === "prediction");
    dataViewTabPredictionButton.disabled = !hasPredictionAccess;
    dataViewTabPredictionButton.classList.toggle("is-disabled-flow", !hasPredictionAccess);
  }
  updateTrainingMetricVisibility();
  syncSummaryTabsForActiveView();
  updateForecastDatePanel();
  updateTopGermplasmPanel();
};

const mountLoadingPanelInPrediction = () => {
  if (!loadingPanel || !predictionLoadingSlot) {
    return;
  }
  predictionLoadingSlot.hidden = false;
  predictionLoadingSlot.appendChild(loadingPanel);
};

const restoreLoadingPanelHome = () => {
  if (!loadingPanel || !loadingPanelHomeParent) {
    return;
  }
  if (loadingPanelHomeNextSibling?.parentElement === loadingPanelHomeParent) {
    loadingPanelHomeParent.insertBefore(loadingPanel, loadingPanelHomeNextSibling);
  } else {
    loadingPanelHomeParent.appendChild(loadingPanel);
  }
  if (predictionLoadingSlot) {
    predictionLoadingSlot.hidden = true;
  }
};

const clearDataset = async (tab) => {
  datasetStore[tab] = null;
  if (activeDataViewTab === tab) {
    await showDatasetInView(tab, { force: true });
  } else {
    updateDataViewTabs();
  }
};

const buildFeatureCollectionSubset = (geojson, selectedNames, sourceName) => {
  const sourceFeatures = Array.isArray(geojson?.features) ? geojson.features : [];
  const selectedNameSet = new Set(selectedNames.map((name) => String(name ?? "").trim()).filter(Boolean));
  const templateFeatures = sourceFeatures.filter((feature) =>
    selectedNameSet.has(String(feature?.properties?.Name ?? "").trim()),
  );
  if (!templateFeatures.length) {
    return {
      type: "FeatureCollection",
      metadata: {
        ...(geojson?.metadata ?? {}),
        total_features: 0,
        source_file_name: sourceName ?? geojson?.metadata?.source_file_name ?? "prediction_subset",
      },
      features: [],
    };
  }

  let rowNumber = 2;
  const features = templateFeatures.flatMap((templateFeature, templateIndex) =>
    sourceFeatures.map((baseFeature, baseIndex) => {
      const templateProperties = templateFeature?.properties ?? {};
      const baseProperties = baseFeature?.properties ?? {};
      const properties = { ...baseProperties };
      germplasmAttributeKeys.forEach((column) => {
        if (column in templateProperties) {
          properties[column] = templateProperties[column];
        }
      });
      if ("Rank" in templateProperties) {
        properties.Rank = templateProperties.Rank;
      }
      if ("idPK" in templateProperties) {
        properties.idPK = `${templateProperties.idPK}::${baseIndex + 1}::${templateIndex + 1}`;
      }
      properties.row_number = rowNumber++;
      properties["Selected germplasm projection"] = String(templateProperties.Name ?? "");
      return {
        type: "Feature",
        geometry: baseFeature.geometry,
        properties,
      };
    }),
  );
  return {
    type: "FeatureCollection",
    metadata: {
      ...(geojson?.metadata ?? {}),
      total_features: features.length,
      source_file_name: sourceName ?? geojson?.metadata?.source_file_name ?? "prediction_subset",
    },
    features,
  };
};

const isAllMarkersPredictionProjection = (summary = null) =>
  String(summary?.selected_germplasm_projection_mode ?? "").trim() === "all_markers";

const collapseBridgePredictionFeatures = (geojson) => {
  const sourceFeatures = Array.isArray(geojson?.features) ? geojson.features : [];
  const deduplicatedFeatures = [];
  const seenKeys = new Map();
  let collapsedCount = 0;

  sourceFeatures.forEach((feature) => {
    const coordinates = feature?.geometry?.coordinates;
    if (!Array.isArray(coordinates) || coordinates.length < 2) {
      deduplicatedFeatures.push(feature);
      return;
    }
    const longitude = Number(coordinates[0]);
    const latitude = Number(coordinates[1]);
    if (!Number.isFinite(longitude) || !Number.isFinite(latitude)) {
      deduplicatedFeatures.push(feature);
      return;
    }
    const projectedName = String(
      feature?.properties?.["Selected germplasm projection"] ?? feature?.properties?.Name ?? "",
    ).trim();
    const key = `${longitude.toFixed(6)}|${latitude.toFixed(6)}|${projectedName}`;
    const existingIndex = seenKeys.get(key);
    if (existingIndex === undefined) {
      const clonedFeature = {
        ...feature,
        geometry: feature?.geometry ? { ...feature.geometry } : feature.geometry,
        properties: {
          ...(feature?.properties ?? {}),
          "Collapsed Geocoordinate count": 1,
        },
      };
      seenKeys.set(key, deduplicatedFeatures.length);
      deduplicatedFeatures.push(clonedFeature);
      return;
    }

    collapsedCount += 1;
    const existingFeature = deduplicatedFeatures[existingIndex];
    existingFeature.properties["Collapsed Geocoordinate count"] = Number(
      existingFeature.properties["Collapsed Geocoordinate count"] ?? 1,
    ) + 1;
  });

  return {
    ...geojson,
    metadata: {
      ...(geojson?.metadata ?? {}),
      total_features: deduplicatedFeatures.length,
      bridge_all_markers_projection: true,
      collapsed_duplicate_rows: collapsedCount,
    },
    features: deduplicatedFeatures,
  };
};

const preparePredictionGeojsonForDisplay = (geojson, summary = null) => {
  if (!isAllMarkersPredictionProjection(summary)) {
    return geojson;
  }
  return collapseBridgePredictionFeatures(geojson);
};

const filterPredictionGeojsonToSelectedNames = (geojson, selectedNames = []) => {
  const normalizedSelectedNames = new Set(
    selectedNames.map((name) => String(name ?? "").trim()).filter(Boolean),
  );
  if (!normalizedSelectedNames.size) {
    return geojson;
  }
  const sourceFeatures = Array.isArray(geojson?.features) ? geojson.features : [];
  const filteredFeatures = sourceFeatures.filter((feature) => {
    const properties = feature?.properties ?? {};
    const featureName = String(properties.Name ?? "").trim();
    const projectedName = String(properties["Selected germplasm projection"] ?? "").trim();
    return (
      normalizedSelectedNames.has(featureName) ||
      normalizedSelectedNames.has(projectedName)
    );
  });
  return {
    ...geojson,
    metadata: {
      ...(geojson?.metadata ?? {}),
      total_features: filteredFeatures.length,
      selected_germplasm_count: normalizedSelectedNames.size,
    },
    features: filteredFeatures,
  };
};

const excelSerialToDate = (serial) => {
  const baseTime = Date.UTC(1899, 11, 30);
  return new Date(baseTime + Number(serial) * 24 * 60 * 60 * 1000);
};

const deriveCurrentYearForecastDate = (rawValue) => {
  const text = String(rawValue ?? "").trim();
  if (!text) {
    return "";
  }

  let parsedDate = null;
  const numericValue = Number(text);
  if (Number.isFinite(numericValue) && text !== "") {
    if (numericValue > 20000 && numericValue < 60000) {
      parsedDate = excelSerialToDate(numericValue);
    }
  }

  if (!parsedDate) {
    const normalized = text.replace(/\./g, "/").replace(/-/g, "/");
    const parts = normalized.split("/").map((part) => part.trim()).filter(Boolean);
    if (parts.length === 3) {
      const [first, second, third] = parts.map((part) => Number(part));
      if ([first, second, third].every(Number.isFinite)) {
        if (String(parts[0]).length === 4) {
          parsedDate = new Date(Date.UTC(first, second - 1, third));
        } else if (first > 12 && second <= 12) {
          parsedDate = new Date(Date.UTC(third, second - 1, first));
        } else {
          parsedDate = new Date(Date.UTC(third, first - 1, second));
        }
      }
    }
  }

  if (!parsedDate || Number.isNaN(parsedDate.getTime())) {
    return "";
  }

  const currentYear = new Date().getFullYear();
  const month = String(parsedDate.getUTCMonth() + 1).padStart(2, "0");
  const day = String(parsedDate.getUTCDate()).padStart(2, "0");
  return `${currentYear}-${month}-${day}`;
};

const getFirstOriginalPropertyValue = (propertyName) => {
  const features = datasetStore.original?.geojson?.features ?? [];
  for (const feature of features) {
    const value = feature?.properties?.[propertyName];
    if (String(value ?? "").trim()) {
      return value;
    }
  }
  return "";
};

const renderClimateScopeOptions = () => {
  if (!climateScopeSelect) {
    return;
  }
  const currentValue = selectedClimateScope;
  climateScopeSelect.innerHTML = "";

  const option = document.createElement("option");
  option.value = "regional_manual";
  option.textContent = "Manual bounding box climate grid";
  climateScopeSelect.append(option);

  climateScopeSelect.value = currentValue === "regional_manual" ? currentValue : "regional_manual";
  if (currentValue !== "regional_manual") {
    selectedClimateScope = "regional_manual";
  }
};

const hasCompleteManualBounds = () =>
  parseRegionalBoundNumber(regionalBoundsLatitudeMinInput) !== null &&
  parseRegionalBoundNumber(regionalBoundsLatitudeMaxInput) !== null &&
  parseRegionalBoundNumber(regionalBoundsLongitudeMinInput) !== null &&
  parseRegionalBoundNumber(regionalBoundsLongitudeMaxInput) !== null;

const hasPredictionUploadPrerequisites = () => {
  if (!isPredictionWorkflowMode()) {
    return true;
  }
  if (!selectedSavedModelId) {
    return false;
  }
  if (!selectedClimateScope) {
    return false;
  }
  if (selectedClimateScope === "regional_manual") {
    return hasCompleteManualBounds();
  }
  return true;
};

const updateFileUploadAvailability = () => {
  const disabled = isPredictionWorkflowMode() && !hasPredictionUploadPrerequisites();
  const originalDisabled = !predictionBridgeState?.isAvailable;
  if (fileInput) {
    fileInput.disabled = disabled;
  }
  if (predictionPointUploadButton) {
    predictionPointUploadButton.disabled = disabled;
  }
  if (predictionPointOriginalButton) {
    predictionPointOriginalButton.disabled = originalDisabled;
    predictionPointOriginalButton.title = originalDisabled
      ? "Load a workspace with Training first to explore the original germplasm list."
      : "Load the original workspace germplasm list";
  }
  fileUploadTriggers.forEach((trigger) => {
    trigger.classList.toggle("is-disabled", disabled);
    trigger.setAttribute("aria-disabled", disabled ? "true" : "false");
    trigger.title = disabled
      ? "Select the workspace model context, complete the bounding box, and use the workbook planting and harvesting dates before loading the workbook."
      : "Select an .xlsx file";
  });
};

const resetPredictionControls = () => {
  selectedSavedModelId = predictionBridgeState?.modelId ?? selectedSavedModelId;
  selectedClimateScope = "regional_manual";
  if (savedModelSelect) {
    savedModelSelect.value = selectedSavedModelId;
  }
  if (climateScopeSelect) {
    renderClimateScopeOptions();
  }
  if (regionalCountrySelect) {
    regionalCountrySelect.value = "";
  }
  [
    forecastPlantingDateInput,
    forecastHarvestingDateInput,
    regionalBoundsLatitudeMinInput,
    regionalBoundsLatitudeMaxInput,
    regionalBoundsLongitudeMinInput,
    regionalBoundsLongitudeMaxInput,
  ].forEach((input) => {
    if (input) {
      input.value = "";
    }
  });
  if (fileInput) {
    fileInput.value = "";
  }
  regionalManualPreviewGridCellCount = null;
  regionalManualPreviewGrid = null;
  resetPreprocessValidationState();
  resetPendingGermplasmSelection();
  clearMapBoundingBoxSelection({ clearInputs: true });
  syncSelectedModelControl();
  updateClimateScopePanel();
  updateFileUploadAvailability();
};

const resetDatasetStore = () => {
  datasetStore = {
    original: null,
    training: null,
    top_germplasm: null,
    prediction: null,
  };
  activeDataViewTab = "original";
  updateDataViewTabs();
};

const updateForecastDatePanel = () => {
  updateDetailsTabLabels();
  if (legacyPipelineDisabled) {
    if (predictionControlsPanel) {
      predictionControlsPanel.hidden = true;
    }
    if (savedModelGroup) {
      savedModelGroup.hidden = true;
      savedModelGroup.style.display = "none";
    }
    if (forecastDatesPanel) {
      forecastDatesPanel.hidden = true;
    }
    if (climateScopeGroup) {
      climateScopeGroup.hidden = true;
      climateScopeGroup.style.display = "none";
    }
    updateClimateScopePanel();
    return;
  }
  const predictionWorkflowSelected = isPredictionWorkflowMode();
  const predictionModeEnabled = predictionWorkflowSelected && activeDataViewTab === "prediction";
  if (predictionControlsPanel) {
    predictionControlsPanel.hidden = !predictionModeEnabled;
  }
  if (savedModelGroup) {
    savedModelGroup.hidden = !predictionModeEnabled;
    savedModelGroup.style.display = predictionModeEnabled ? "" : "none";
  }
  if (!forecastDatesPanel) {
    updateClimateScopePanel();
    return;
  }
  forecastDatesPanel.hidden = !(predictionModeEnabled && isSavedModelForecastMode());
  if (climateScopeGroup) {
    const showClimateScopeGroup = predictionModeEnabled && isSavedModelForecastMode();
    climateScopeGroup.hidden = !showClimateScopeGroup;
    climateScopeGroup.style.display = showClimateScopeGroup ? "" : "none";
  }
  if (!predictionWorkflowSelected) {
    resetPendingGermplasmSelection();
  }
  updateClimateScopePanel();
  updateFileUploadAvailability();
};

const applyPreprocessValidationVisibility = () => {
  if (!preprocessValidationPanel) {
    return;
  }
  if (!preprocessValidationEnabled) {
    preprocessValidationPanel.hidden = true;
  }
};

const predictionIdFieldPrefixPattern = /^(DG\d+|D01\d+)/i;

const isPredictionIdFieldExcluded = (header) => {
  const normalized = String(header ?? "").trim();
  if (!normalized) {
    return true;
  }
  return predictionIdFieldPrefixPattern.test(normalized);
};

const getPredictionIdFieldCandidatesFromPayload = (payload = {}) => {
  const payloadCandidates = Array.isArray(payload?.id_field_candidates) ? payload.id_field_candidates : [];
  const payloadHeaders = Array.isArray(payload?.headers) ? payload.headers : [];
  const candidateSource = payloadCandidates.length ? payloadCandidates : payloadHeaders;
  const excludedWorkspaceColumns = new Set([
    ...selectionPropertiesState.categoricalColumns,
    ...selectionPropertiesState.quantitativeColumns,
  ].map((column) => String(column ?? "").trim()).filter(Boolean));
  return sortSelectionValues(
    candidateSource
      .map((header) => String(header ?? "").trim())
      .filter((header) => header && !excludedWorkspaceColumns.has(header) && !isPredictionIdFieldExcluded(header)),
  );
};

const normalizeSelectedPredictionIdHeader = (value) => {
  const normalized = String(value ?? "").trim();
  return normalized === clearSelectionIdSentinel ? "" : normalized;
};

const buildPredictionIdPickerOptions = (payload = {}) => {
  const candidates = getPredictionIdFieldCandidatesFromPayload(payload);
  return [
    { value: clearSelectionIdSentinel, label: "Clear Selection" },
    ...candidates.map((header) => ({ value: header, label: header })),
  ];
};

const refreshGermplasmSelectionIdPicker = (payload = {}) => {
  if (!germplasmSelectionIdPicker || !germplasmSelectionIdSelect) {
    return;
  }
  const options = buildPredictionIdPickerOptions(payload);
  const selectedHeader = normalizeSelectedPredictionIdHeader(
    selectedPredictionIdField || payload?.selected_id_header || payload?.default_selected_id_header || "",
  );
  populateSelectionListbox(
    germplasmSelectionIdSelect,
    options,
    options.length ? "Select id field" : "No fields available",
    selectedHeader || clearSelectionIdSentinel,
    !pendingSavedModelFile || !options.length,
  );
  germplasmSelectionIdSelect.disabled = !pendingSavedModelFile || !options.length;
  germplasmSelectionIdPicker.hidden = !pendingSavedModelFile || !options.length;
};

const closePredictionIdModal = ({ keepFocus = true } = {}) => {
  if (predictionIdModal) {
    predictionIdModal.hidden = true;
    predictionIdModal.setAttribute("inert", "");
    predictionIdModal.setAttribute("aria-hidden", "true");
  }
  if (predictionIdModalCard) {
    predictionIdModalCard.removeAttribute("role");
    predictionIdModalCard.removeAttribute("aria-modal");
  }
  pendingPredictionIdModalPayload = null;
  if (keepFocus && lastFocusedElement instanceof HTMLElement) {
    lastFocusedElement.focus();
  }
  lastFocusedElement = null;
};

const updatePredictionIdModalAcceptState = () => {
  if (predictionIdModalAccept) {
    predictionIdModalAccept.disabled = !String(predictionIdColumnSelect?.value ?? "").trim();
  }
};

const openPredictionIdModal = (payload) => {
  pendingPredictionIdModalPayload = payload;
  availablePredictionIdFields = getPredictionIdFieldCandidatesFromPayload(payload);
  selectedPredictionIdField = normalizeSelectedPredictionIdHeader(
    payload?.selected_id_header || payload?.default_selected_id_header || "",
  );
  availablePredictionIdValuesByName = {};
  const modalOptions = buildPredictionIdPickerOptions(payload);
  const modalSelectedValue = selectedPredictionIdField || clearSelectionIdSentinel;
  if (predictionIdModalDescription) {
    predictionIdModalDescription.textContent = availablePredictionIdFields.length
      ? "Choose the workbook field that should be shown as the Id beside each germplasm in the selection list."
      : "No additional Id fields are available for this workbook after excluding the workspace categorical and quantitative columns.";
  }
  populateSelectionListbox(
    predictionIdColumnSelect,
    modalOptions.map((option) => option.value),
    modalOptions.length ? "Select id field" : "No fields available",
    modalSelectedValue,
    !modalOptions.length,
  );
  updatePredictionIdModalAcceptState();
  if (!predictionIdModal) {
    return;
  }
  lastFocusedElement = document.activeElement instanceof HTMLElement ? document.activeElement : null;
  predictionIdModal.hidden = false;
  predictionIdModal.removeAttribute("inert");
  predictionIdModal.setAttribute("aria-hidden", "false");
  predictionIdModalCard?.setAttribute("role", "dialog");
  predictionIdModalCard?.setAttribute("aria-modal", "true");
  window.setTimeout(() => {
    const choicesInstance = selectionChoices.get(predictionIdColumnSelect);
    const searchInput = choicesInstance?.input?.element;
    if (searchInput) {
      searchInput.focus();
      return;
    }
    predictionIdColumnSelect?.focus();
  }, 0);
};

const resetPendingGermplasmSelection = () => {
  pendingSavedModelFile = null;
  predictionGermplasmSourceMode = "uploaded";
  availableGermplasmNames = [];
  availableGermplasmProfilesByName = {};
  availablePredictionIdFields = [];
  selectedPredictionIdField = "";
  availablePredictionIdValuesByName = {};
  pendingPredictionIdModalPayload = null;
  selectedGermplasmNames = new Set();
  if (germplasmSelectionPanel) {
    germplasmSelectionPanel.hidden = true;
  }
  if (germplasmSelectionList) {
    germplasmSelectionList.innerHTML = "";
  }
  if (germplasmSelectionCount) {
    germplasmSelectionCount.textContent = "0 selected";
  }
  if (germplasmSelectionIdPicker) {
    germplasmSelectionIdPicker.hidden = true;
  }
  if (germplasmSelectionIdSelect) {
    germplasmSelectionIdSelect.innerHTML = '<option value="">No fields available</option>';
    germplasmSelectionIdSelect.disabled = true;
  }
  if (germplasmSelectionTitle) {
    germplasmSelectionTitle.textContent = "";
  }
  if (germplasmSelectionHelp) {
    germplasmSelectionHelp.textContent =
      "Load an Excel file with a saved model selected to preview distinct germplasm names and any repeated-name profiles.";
  }
  if (executeGermplasmSelectionButton) {
    executeGermplasmSelectionButton.disabled = true;
  }
  closePredictionIdModal({ keepFocus: false });
};

const updateGermplasmSelectionCount = () => {
  if (germplasmSelectionCount) {
    if (isPredictionWorkflowMode()) {
      const detected = `${availableGermplasmNames.length} germplasm${availableGermplasmNames.length === 1 ? "" : "s"} detected`;
      const selected = selectedGermplasmNames.size === 1 ? "1 selected" : `${selectedGermplasmNames.size} selected`;
      germplasmSelectionCount.textContent = `${detected} | ${selected}`;
    } else {
      germplasmSelectionCount.textContent =
        selectedGermplasmNames.size === 1 ? "1 selected" : "0 selected";
    }
  }
  if (executeGermplasmSelectionButton) {
    const canRunPredictionSelection =
      isPredictionWorkflowMode()
      && !selectedGermplasmRunInProgress
      && Boolean(pendingSavedModelFile)
      && selectedGermplasmNames.size > 0
      && hasPredictionUploadPrerequisites();
    executeGermplasmSelectionButton.disabled =
      isPredictionWorkflowMode()
        ? !canRunPredictionSelection
        : selectedGermplasmRunInProgress || !pendingSavedModelFile || !selectedGermplasmNames.size;
  }
};

const renderGermplasmSelectionList = () => {
  if (!germplasmSelectionList) {
    return;
  }
  germplasmSelectionList.innerHTML = "";
  const isOriginalMode = predictionGermplasmSourceMode === "original";
  availableGermplasmNames.forEach((name) => {
    const label = document.createElement("label");
    label.className = "germplasm-selection-option";
    const input = document.createElement("input");
    input.type = isOriginalMode ? "radio" : "checkbox";
    input.name = "prediction-germplasm-selection";
    input.checked = selectedGermplasmNames.has(name);
    input.addEventListener("change", () => {
      if (isOriginalMode && input.checked) {
        selectedGermplasmNames = new Set([name]);
      } else if (input.checked) {
        selectedGermplasmNames = new Set([...selectedGermplasmNames, name]);
      } else {
        selectedGermplasmNames.delete(name);
        selectedGermplasmNames = new Set(selectedGermplasmNames);
      }
      if (predictionBridgeState?.isAvailable) {
        predictionBridgeState.selectedNames = Array.from(selectedGermplasmNames);
      }
      renderGermplasmSelectionList();
    });
    const metadata = availableGermplasmProfilesByName?.[name] ?? null;
    const rowCount = Number(metadata?.row_count ?? 0);
    const profileCount = Number(metadata?.profile_count ?? 0);
    const idValues = Array.isArray(availablePredictionIdValuesByName?.[name])
      ? availablePredictionIdValuesByName[name].map((value) => String(value ?? "").trim()).filter(Boolean)
      : [];
    const idSuffix = selectedPredictionIdField && idValues.length
      ? ` - Id : ${idValues.join(" / ")}`
      : "";
    const hasSelectedIdField = Boolean(normalizeSelectedPredictionIdHeader(selectedPredictionIdField));
    const text = document.createElement("span");
    text.textContent = isOriginalMode
      ? `${name}${idSuffix}`
      : !hasSelectedIdField && rowCount > 1
        ? `${name} (${rowCount} reps)`
        : rowCount > 1
          ? `${name} (${rowCount} rows${profileCount > 1 ? `, ${profileCount} profiles` : ""})${idSuffix}`
          : `${name}${idSuffix}`;
    label.title = !isOriginalMode && Array.isArray(metadata?.varying_columns) && metadata.varying_columns.length
      ? `Varying columns: ${metadata.varying_columns.map((entry) => entry.header).join(", ")}`
      : name;
    label.append(input, text);
    germplasmSelectionList.append(label);
  });
  updateGermplasmSelectionCount();
};

const isRegionalCountryMode = () => selectedClimateScope === "country_localities";
const isRegionalManualMode = () => selectedClimateScope === "regional_manual";
const isPointUploadMode = () => selectedClimateScope === "point";
const isPredictionBridgeModelLocked = () => Boolean(predictionBridgeState?.isAvailable);

const promptPredictionPointWorkbookSelection = () => {
  predictionGermplasmSourceMode = "uploaded";
  updatePredictionSourceButtons();
  if (!isPredictionWorkflowMode() || !isRegionalManualMode()) {
    return;
  }
  if (!hasPredictionUploadPrerequisites()) {
    updateFileUploadAvailability();
    window.alert(
      "Complete the workspace model context and the manual bounding box before loading the workbook to test. The uploaded workbook dates will drive the climate windows.",
    );
    return;
  }
  if (!fileInput) {
    return;
  }
  // Reset the file input so selecting the same workbook again still fires `change`.
  fileInput.value = "";
  try {
    if (typeof fileInput.showPicker === "function") {
      fileInput.showPicker();
      return;
    }
  } catch (error) {
    console.error(error);
  }
  fileInput.click();
};

const updatePredictionSourceButtons = () => {
  const isOriginalMode = predictionGermplasmSourceMode === "original";
  if (predictionPointOriginalButton) {
    predictionPointOriginalButton.classList.toggle("is-selected-source", isOriginalMode);
    predictionPointOriginalButton.classList.toggle("is-unselected-source", !isOriginalMode);
  }
  if (predictionPointUploadButton) {
    predictionPointUploadButton.classList.toggle("is-selected-source", !isOriginalMode);
    predictionPointUploadButton.classList.toggle("is-unselected-source", isOriginalMode);
  }
};

const updateGermplasmSelectionTitle = () => {
  if (!germplasmSelectionTitle) {
    return;
  }
  if (predictionGermplasmSourceMode === "original") {
    germplasmSelectionTitle.textContent = "Explor Original Data";
    return;
  }
  if (predictionGermplasmSourceMode === "uploaded") {
    germplasmSelectionTitle.textContent = "Load Data to Predict";
    return;
  }
  germplasmSelectionTitle.textContent = "";
};

const updateClimateScopePanel = () => {
  const forecastModeEnabled = isPredictionWorkflowMode() && isSavedModelForecastMode();
  const showRegionalCountryPanel = false;
  const showRegionalManualPanel = forecastModeEnabled && isRegionalManualMode();
  const showPointUploadPanel = forecastModeEnabled && isRegionalManualMode();
  if (climateScopeSelect) {
    renderClimateScopeOptions();
    climateScopeSelect.value = selectedClimateScope;
    climateScopeSelect.disabled = true;
  }
  if (predictionPointUploadPanel) {
    predictionPointUploadPanel.hidden = !showPointUploadPanel;
    predictionPointUploadPanel.style.display = showPointUploadPanel ? "" : "none";
  }
  updatePredictionSourceButtons();
  updateGermplasmSelectionTitle();
  if (predictionPointUploadButton) {
    predictionPointUploadButton.disabled = !hasPredictionUploadPrerequisites();
  }
  if (predictionPointUploadCopy) {
    predictionPointUploadCopy.innerHTML = predictionBridgeState?.isAvailable
      ? "Load the workbook you want to evaluate. The workspace model will stay fixed, the bounding-box climate grid will be applied, and the planting/harvesting dates will be read from the uploaded workbook rows."
      : "Load the workbook you want to evaluate after defining the bounding box. The uploaded workbook dates will be used for the climate windows.";
  }
  if (regionalCountryPanel) {
    regionalCountryPanel.hidden = !showRegionalCountryPanel;
    regionalCountryPanel.style.display = showRegionalCountryPanel ? "" : "none";
  }
  if (regionalManualPanel) {
    regionalManualPanel.hidden = !showRegionalManualPanel;
    regionalManualPanel.style.display = showRegionalManualPanel ? "" : "none";
  }
  if (climateScopeHelp) {
    climateScopeHelp.textContent = "Manual bounding-box climate grid is fixed for each workspace. Define the bounding box, then load the workbook you want to evaluate. The planting and harvesting dates will be taken from the workbook rows.";
  }
  if (regionalManualMapHelp) {
    regionalManualMapHelp.textContent = mapBoundingBoxSelectionMode
      ? "Drag directly on the map to define the bounding box. Release the pointer to populate the latitude and longitude fields."
      : mapBoundingBoxDraft
        ? "The selected bounding box stays visible on the map. Use Select Bounding Box On Map again to redraw it larger or smaller."
        : "Start map selection, then drag directly on the map to define the bounding box.";
  }
  if (regionalBoundsDrawMapButton) {
    regionalBoundsDrawMapButton.classList.toggle("is-active", mapBoundingBoxSelectionMode);
  }
  if (mapFrame) {
    mapFrame.classList.toggle(
      "map-frame-selecting",
      mapBoundingBoxSelectionMode && isPredictionWorkflowMode() && isRegionalManualMode(),
    );
  }
  refreshMapAvailability();
  updateFileUploadAvailability();
  if (mapContext) {
    mapContext.renderBase(currentTransform);
  }
};

const renderRegionalCountryPreview = () => {
  if (!regionalCountryPreview) {
    return;
  }
  const selectedCountry = String(regionalCountrySelect?.value ?? "").trim();
  const payload = regionalCountryBoundsCache.find((item) => item?.iso2 === selectedCountry);
  if (!selectedCountry) {
    regionalCountryPreview.textContent = "Choose an African country to expand its localities during the forecast run.";
    return;
  }
  if (!payload?.country) {
    regionalCountryPreview.textContent = "The selected country is unavailable for locality expansion.";
    return;
  }
  regionalCountryPreview.textContent =
    `Country: ${payload.country} (${payload.iso2 ?? ""}) | ` +
    `Locality rows will be generated from GeoNames and paired with every uploaded germplasm record.`;
};

const refreshRegionalCountryPreviewSample = async () => {
  if (!regionalCountryPreview) {
    return;
  }
  const selectedCountry = String(regionalCountrySelect?.value ?? "").trim();
  if (!selectedCountry) {
    renderRegionalCountryPreview();
    return;
  }
  try {
    regionalCountryPreview.textContent = "Loading GeoNames localities for the selected country...";
    const response = await fetch(`/api/country-localities?country=${encodeURIComponent(selectedCountry)}`);
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.error ?? "The country-locality preview could not be loaded.");
    }
    const sampleNames = Array.isArray(payload.sample)
      ? payload.sample
          .slice(0, 3)
          .map((item) => item?.name)
          .filter(Boolean)
          .join(", ")
      : "";
    regionalCountryPreview.textContent =
      `Country: ${payload.country} (${payload.iso2 ?? ""}) | ` +
      `Localities: ${payload.locality_count ?? 0}` +
      (sampleNames ? ` | Sample: ${sampleNames}` : "");
  } catch (error) {
    console.error(error);
    regionalCountryPreview.textContent =
      error instanceof Error
        ? error.message
        : "The country-locality preview is unavailable right now.";
  }
};

const refreshRegionalCountryBounds = async () => {
  if (!regionalCountrySelect) {
    return;
  }
  try {
    const response = await fetch("/api/african-countries");
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.error ?? "The African country list could not be loaded.");
    }
    regionalCountryBoundsCache = Array.isArray(payload.countries) ? payload.countries : [];
    regionalCountrySelect.innerHTML = "";
    const placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = "Select a country";
    regionalCountrySelect.append(placeholder);
    regionalCountryBoundsCache.forEach((item) => {
      const option = document.createElement("option");
      option.value = item.iso2 ?? "";
      option.textContent = item.country ?? "Unnamed country";
      regionalCountrySelect.append(option);
    });
    renderRegionalCountryPreview();
  } catch (error) {
    console.error(error);
    regionalCountryBoundsCache = [];
    regionalCountrySelect.innerHTML = "";
    const unavailable = document.createElement("option");
    unavailable.value = "";
    unavailable.textContent = "African country list unavailable";
    regionalCountrySelect.append(unavailable);
    if (regionalCountryPreview) {
      regionalCountryPreview.textContent = "The African country list is unavailable right now.";
    }
  }
};

const parseRegionalBoundNumber = (input) => {
  const rawValue = input?.value?.trim?.() ?? "";
  if (!rawValue) {
    return null;
  }
  const numeric = Number(rawValue);
  return Number.isFinite(numeric) ? numeric : null;
};

const syncManualBoundsDraftFromInputs = () => {
  const latitudeMin = parseRegionalBoundNumber(regionalBoundsLatitudeMinInput);
  const latitudeMax = parseRegionalBoundNumber(regionalBoundsLatitudeMaxInput);
  const longitudeMin = parseRegionalBoundNumber(regionalBoundsLongitudeMinInput);
  const longitudeMax = parseRegionalBoundNumber(regionalBoundsLongitudeMaxInput);
  if (
    latitudeMin === null ||
    latitudeMax === null ||
    longitudeMin === null ||
    longitudeMax === null
  ) {
    mapBoundingBoxDraft = null;
    return null;
  }
  mapBoundingBoxDraft = {
    latitudeMin: Math.min(latitudeMin, latitudeMax),
    latitudeMax: Math.max(latitudeMin, latitudeMax),
    longitudeMin: Math.min(longitudeMin, longitudeMax),
    longitudeMax: Math.max(longitudeMin, longitudeMax),
  };
  return mapBoundingBoxDraft;
};

const renderManualRegionalPreview = async () => {
  if (!regionalManualPreview) {
    return;
  }
  const latitudeMin = parseRegionalBoundNumber(regionalBoundsLatitudeMinInput);
  const latitudeMax = parseRegionalBoundNumber(regionalBoundsLatitudeMaxInput);
  const longitudeMin = parseRegionalBoundNumber(regionalBoundsLongitudeMinInput);
  const longitudeMax = parseRegionalBoundNumber(regionalBoundsLongitudeMaxInput);
  if (
    latitudeMin === null ||
    latitudeMax === null ||
    longitudeMin === null ||
    longitudeMax === null
  ) {
    regionalManualPreviewGridCellCount = null;
    regionalManualPreviewGrid = null;
    mapBoundingBoxDraft = null;
    regionalManualPreview.textContent =
      "Enter latitude and longitude bounds to preview the climate grid that will be generated inside the bounding box.";
    if (mapContext) {
      mapContext.renderBase(currentTransform);
    }
    return;
  }
  try {
    syncManualBoundsDraftFromInputs();
    regionalManualPreview.textContent = "Loading climate grid cells inside the bounding box...";
    const params = new URLSearchParams({
      latitude_min: String(latitudeMin),
      latitude_max: String(latitudeMax),
      longitude_min: String(longitudeMin),
      longitude_max: String(longitudeMax),
      resolution_km: String(featureheroSettings.nasa_power_resolution_km ?? 5),
    });
    const response = await fetch(`/api/bbox-grid?${params.toString()}`);
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.error ?? "The manual bounding-box climate grid could not be previewed.");
    }
    regionalManualPreviewGridCellCount = Number(payload.grid_cell_count ?? 0);
    regionalManualPreviewGrid = payload && typeof payload === "object" ? payload : null;
    regionalManualPreview.textContent =
      `Lat ${payload?.bounds?.latitude_min} to ${payload?.bounds?.latitude_max} | ` +
      `Lon ${payload?.bounds?.longitude_min} to ${payload?.bounds?.longitude_max} | ` +
      `Grid cells: ${payload.grid_cell_count ?? 0} | ` +
      `Grid resolution: ${payload.grid_resolution_km ?? featureheroSettings.nasa_power_resolution_km ?? 5} km`;
    if (mapContext) {
      mapContext.renderBase(currentTransform);
    }
  } catch (error) {
    console.error(error);
    regionalManualPreviewGridCellCount = null;
    regionalManualPreviewGrid = null;
    regionalManualPreview.textContent =
      error instanceof Error
        ? error.message
        : "The manual bounding-box climate grid preview is unavailable right now.";
    if (mapContext) {
      mapContext.renderBase(currentTransform);
    }
  }
};

const setManualBoundsInputs = (bounds) => {
  if (!bounds) {
    return;
  }
  if (regionalBoundsLatitudeMinInput) {
    regionalBoundsLatitudeMinInput.value = bounds.latitudeMin.toFixed(6);
  }
  if (regionalBoundsLatitudeMaxInput) {
    regionalBoundsLatitudeMaxInput.value = bounds.latitudeMax.toFixed(6);
  }
  if (regionalBoundsLongitudeMinInput) {
    regionalBoundsLongitudeMinInput.value = bounds.longitudeMin.toFixed(6);
  }
  if (regionalBoundsLongitudeMaxInput) {
    regionalBoundsLongitudeMaxInput.value = bounds.longitudeMax.toFixed(6);
  }
};

const clearMapBoundingBoxSelection = ({ clearInputs = false, preserveDraft = false } = {}) => {
  mapBoundingBoxSelectionMode = false;
  mapBoundingBoxSelectionStart = null;
  if (!preserveDraft) {
    mapBoundingBoxDraft = null;
  }
  if (clearInputs) {
    regionalManualPreviewGridCellCount = null;
    regionalManualPreviewGrid = null;
    [
      regionalBoundsLatitudeMinInput,
      regionalBoundsLatitudeMaxInput,
      regionalBoundsLongitudeMinInput,
      regionalBoundsLongitudeMaxInput,
    ].forEach((input) => {
      if (input) {
        input.value = "";
      }
    });
  }
  if (mapContext) {
    mapContext.renderBase(currentTransform);
  }
  updateClimateScopePanel();
};

const beginMapBoundingBoxSelection = () => {
  if (!isPredictionWorkflowMode() || !isRegionalManualMode()) {
    return;
  }
  mapBoundingBoxSelectionMode = true;
  mapBoundingBoxSelectionStart = null;
  mapBoundingBoxDraft = null;
  if (mapContext) {
    mapContext.renderBase(currentTransform);
  }
  updateClimateScopePanel();
};

const resetPreprocessValidationState = () => {
  pausedPreprocessPayload = null;
  if (preprocessValidationPanel) {
    preprocessValidationPanel.hidden = true;
  }
  if (downloadPreprocessOutput) {
    downloadPreprocessOutput.href = "#";
  }
  if (continueAfterPreprocessButton) {
    continueAfterPreprocessButton.disabled = true;
  }
};

const rememberPausedPreprocessPayload = (payload) => {
  if (!payload?.continue_url || !payload?.job_id) {
    return;
  }
  const activeJob = readActivePipelineJob();
  const workflowMode =
    activeJob?.workflowMode === "prediction" || activeJob?.predictionMode
      ? "prediction"
      : isPredictionWorkflowMode()
        ? "prediction"
        : "training";
  persistActivePipelineJob({
    jobId: payload.job_id,
    statusUrl: `/api/process-xlsx/status/${payload.job_id}`,
    sourceName: payload.source_name ?? "",
    pausedPayload: {
      continue_url: payload.continue_url,
      phase06_download_url: payload.phase06_download_url ?? "",
      phase06_xlsx: payload.phase06_xlsx ?? "",
    },
    state: "paused",
    workflowMode,
    predictionMode: workflowMode === "prediction",
  });
};

const updateSelectedModelHelp = () => {
  if (!savedModelsCache.length) {
    savedModelHelp.textContent = isPredictionWorkflowMode()
      ? "This workspace does not have a model available yet."
      : "No saved models are available yet. FeatureHero will run normally.";
    updateForecastDatePanel();
    resetPendingGermplasmSelection();
    updateFileUploadAvailability();
    return;
  }
  const selectedModel = getSelectedSavedModel();
  if (!selectedModel) {
    savedModelHelp.textContent = isPredictionWorkflowMode()
      ? "The workspace model will appear here when Training finishes."
      : "No saved model selected. Uploading a file will run FeatureHero and then save a new model.";
    updateForecastDatePanel();
    resetPendingGermplasmSelection();
    updateFileUploadAvailability();
    return;
  }
  savedModelHelp.textContent = `${selectedModel.model_id}: ${selectedModel.description ?? "Workspace model selected."} This workspace uses a single locked model for High-Potential Sites.`;
  updateForecastDatePanel();
  updateFileUploadAvailability();
};

const syncSelectedModelControl = () => {
  if (!savedModelSelect) {
    return;
  }
  savedModelSelect.value = selectedSavedModelId;
  savedModelSelect.disabled = true;
  updateSelectedModelHelp();
};

const updateModelScrollerControls = () => {
  if (!modelScroller || !modelScrollPrev || !modelScrollNext) {
    return;
  }
  const maxScroll = Math.max(0, modelScroller.scrollWidth - modelScroller.clientWidth);
  modelScrollPrev.disabled = modelScroller.scrollLeft <= 2;
  modelScrollNext.disabled = modelScroller.scrollLeft >= maxScroll - 2 || maxScroll <= 0;
};

const scrollModelCards = (direction) => {
  if (!modelScroller) {
    return;
  }
  const amount = Math.max(280, Math.round(modelScroller.clientWidth * 0.82));
  modelScroller.scrollBy({
    left: direction * amount,
    behavior: "smooth",
  });
};

const closeModelModal = () => {
  activeModalModelId = "";
  if (modelModal) {
    modelModal.hidden = true;
    modelModal.setAttribute("inert", "");
    modelModal.setAttribute("aria-hidden", "true");
  }
  if (modelModalCard) {
    modelModalCard.removeAttribute("role");
    modelModalCard.removeAttribute("aria-modal");
  }
  if (lastFocusedElement instanceof HTMLElement) {
    lastFocusedElement.focus();
  }
  lastFocusedElement = null;
};

const openWorkspaceSettingsModal = async (modelId) => {
  const model = savedModelsCache.find((item) => item.model_id === modelId);
  if (!model || !modelModal) {
    return;
  }

  const settingsTitle = model.display_name?.trim()
    ? `${model.display_name} | ${model.model_id ?? "Saved workspace"}`
    : model.model_id ?? "Saved workspace";
  lastFocusedElement = document.activeElement instanceof HTMLElement ? document.activeElement : null;
  activeModalModelId = model.model_id;
  modelModalTitle.textContent = settingsTitle;
  modelModalDescription.textContent = "Workspace model artifacts available for download.";

  const metricValue =
    typeof model.metric_value === "number" ? model.metric_value.toFixed(4) : "N/A";
  modelModalGrid.innerHTML = `
    <article class="model-modal-metric"><strong>Machine</strong><span>${escapeHtml(model.machine_name ?? "Unknown")}</span></article>
    <article class="model-modal-metric"><strong>Number Generation</strong><span>${escapeHtml(model.number_generation ?? "N/A")}</span></article>
    <article class="model-modal-metric"><strong>Number Population</strong><span>${escapeHtml(model.number_population ?? "N/A")}</span></article>
    <article class="model-modal-metric"><strong>Metric</strong><span>${escapeHtml(model.metric_name ?? "Metric")}: ${escapeHtml(metricValue)}</span></article>
    <article class="model-modal-metric"><strong>Created</strong><span>${escapeHtml(formatDateTime(model.created_at))}</span></article>
    <article class="model-modal-metric"><strong>Selected Features</strong><span>${escapeHtml(model.selected_feature_count ?? 0)}</span></article>
  `;

  const modalSections = Array.from(modelModalCard.querySelectorAll('.model-modal-section'));
  if (modalSections[0]) {
    modalSections[0].hidden = false;
    modalSections[0].querySelector('h4').textContent = 'Workspace';
    modelModalMachines.innerHTML = '';
    const workspaceLabels = Array.isArray(model.machine_keys) && model.machine_keys.length
      ? model.machine_keys
      : [model.machine_name ?? 'Unknown'];
    workspaceLabels.forEach((label) => {
      const tag = document.createElement('span');
      tag.textContent = String(label ?? '').trim() || 'Unknown';
      modelModalMachines.append(tag);
    });
  }
  if (modalSections[1]) {
    modalSections[1].hidden = false;
    const sectionTitle = modalSections[1].querySelector('h4');
    if (sectionTitle) {
      sectionTitle.textContent = '';
      sectionTitle.style.display = 'none';
    }
    modelModalDownloads.innerHTML = '';
  }

  modelDeleteButton.disabled = false;
  modelModal.hidden = false;
  modelModal.removeAttribute('inert');
  modelModal.setAttribute('aria-hidden', 'false');
  modelModalCard.setAttribute('role', 'dialog');
  modelModalCard.setAttribute('aria-modal', 'true');
  modelModalClose.focus();
};

const openModelModal = (modelId) => {
  const model = savedModelsCache.find((item) => item.model_id === modelId);
  if (!model || !modelModal) {
    return;
  }

  lastFocusedElement =
    document.activeElement instanceof HTMLElement ? document.activeElement : null;
  activeModalModelId = model.model_id;
  modelModalTitle.textContent = "Model Summary Downloads";
  modelModalDescription.textContent = "Download the saved model artifacts for this workspace.";
  modelModalGrid.innerHTML = "";

  const modalSections = Array.from(modelModalCard.querySelectorAll('.model-modal-section'));
  if (modalSections[0]) {
    modalSections[0].hidden = true;
    modelModalMachines.innerHTML = "";
  }
  if (modalSections[1]) {
    modalSections[1].hidden = false;
    const sectionTitle = modalSections[1].querySelector('h4');
    if (sectionTitle) {
      sectionTitle.textContent = '';
      sectionTitle.style.display = 'none';
    }
  }

  modelModalDownloads.innerHTML = "";
  [
    ["Best Model PKL", model.download_urls?.best_model_pkl],
    ["Best Features", model.download_urls?.best_features_csv],
    ["Optimization", model.download_urls?.optimization_csv],
    ["Selecction Summary", model.download_urls?.selection_summary_csv],
  ].forEach(([label, url]) => {
    if (!url) {
      return;
    }
    const link = document.createElement("a");
    link.className = "model-download-link";
    link.href = url;
    link.download = "";
    link.textContent = label;
    modelModalDownloads.append(link);
  });

  modelDeleteButton.disabled = false;
  modelModal.hidden = false;
  modelModal.removeAttribute("inert");
  modelModal.setAttribute("aria-hidden", "false");
  modelModalCard.setAttribute("role", "dialog");
  modelModalCard.setAttribute("aria-modal", "true");
  modelModalClose.focus();
};

const settleModelNameRequest = (payload) => {
  if (!pendingModelNameRequest) {
    return;
  }
  const { resolve } = pendingModelNameRequest;
  pendingModelNameRequest = null;
  resolve(payload);
};

const closeModelNameModal = ({ keepFocus = true } = {}) => {
  if (modelNameModal) {
    modelNameModal.hidden = true;
    modelNameModal.setAttribute("inert", "");
    modelNameModal.setAttribute("aria-hidden", "true");
  }
  if (modelNameModalCard) {
    modelNameModalCard.removeAttribute("role");
    modelNameModalCard.removeAttribute("aria-modal");
  }
  if (modelNameInput) {
    modelNameInput.value = "";
  }
  if (keepFocus && lastFocusedElement instanceof HTMLElement) {
    lastFocusedElement.focus();
  }
  lastFocusedElement = null;
};

const saveModelNameFromDialog = () => {
  const normalizedName = String(modelNameInput?.value ?? "").trim();
  if (!normalizedName) {
    if (modelNameInput) {
      modelNameInput.focus();
    }
    return;
  }
  closeModelNameModal();
  settleModelNameRequest({ action: "save", value: normalizedName });
};

const deferModelNameDialog = () => {
  closeModelNameModal();
  settleModelNameRequest({ action: "later", value: "" });
};

const openModelNameModal = ({ modelId, createdAt, suggestedName = "" }) =>
  new Promise((resolve) => {
    if (!modelNameModal || !modelNameInput) {
      resolve({ action: "later", value: "" });
      return;
    }
    lastFocusedElement =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;
    pendingModelNameRequest = { resolve };
    modelNameModalDescription.textContent =
      "Enter a clear model name. The system will keep the model id and creation date unchanged for tracking.";
    modelNameModalMeta.textContent =
      `Model ID: ${modelId} | Created: ${formatDateTime(createdAt)}`;
    modelNameInput.value = suggestedName;
    modelNameModal.hidden = false;
    modelNameModal.removeAttribute("inert");
    modelNameModal.setAttribute("aria-hidden", "false");
    modelNameModalCard.setAttribute("role", "dialog");
    modelNameModalCard.setAttribute("aria-modal", "true");
    window.setTimeout(() => {
      modelNameInput.focus();
      modelNameInput.select();
    }, 0);
  });

const deleteModel = async (modelId) => {
  const model = savedModelsCache.find((item) => item.model_id === modelId);
  if (!model) {
    return;
  }

  const confirmed = window.confirm(`Delete saved model ${model.model_id}?`);
  if (!confirmed) {
    return;
  }

  modelDeleteButton.disabled = true;
  try {
    const response = await fetch(`/api/models/${encodeURIComponent(modelId)}`, {
      method: "DELETE",
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.error ?? "The model could not be deleted.");
    }

    if (selectedSavedModelId === modelId) {
      selectedSavedModelId = "";
    }
    closeModelModal();
    await refreshSavedModels();
  } catch (error) {
    console.error(error);
    modelDeleteButton.disabled = false;
    window.alert(error instanceof Error ? error.message : "The model could not be deleted.");
  }
};

const renderSavedModels = (models = []) => {
  modelList.innerHTML = "";

  if (!Array.isArray(models) || !models.length) {
    modelCount.textContent = "0 saved workspaces";
    modelEmpty.hidden = false;
    updateModelScrollerControls();
    return;
  }

  modelEmpty.hidden = true;
  modelCount.textContent = `${models.length} saved workspace${models.length === 1 ? "" : "s"}`;

  models.forEach((model) => {
    const item = document.createElement("article");
    const isSelected = model.model_id === selectedSavedModelId;
    const displayTitle = model.display_name?.trim()
      ? model.display_name
      : model.model_id ?? "Unnamed workspace";
    item.className = `model-item${model.is_active ? " active" : ""}${isSelected ? " selected" : ""}`;
    const metricValue =
      typeof model.metric_value === "number" ? model.metric_value.toFixed(4) : "N/A";
    item.innerHTML = `
      <div class="model-item-top">
        <strong>${escapeHtml(displayTitle)}</strong>
        <span class="model-badge">${isSelected ? "Selected" : model.is_active ? "Active" : "Saved"}</span>
      </div>
      <p class="model-description">Workspace ready to load.</p>
      <dl class="model-meta">
        <div><dt>Created</dt><dd>${escapeHtml(formatDateTime(model.created_at))}</dd></div>
        <div><dt>Machine</dt><dd>${escapeHtml(model.machine_name ?? "Unknown")}</dd></div>
        <div><dt>Features</dt><dd>${escapeHtml(model.selected_feature_count ?? 0)}</dd></div>
        <div><dt>Metric</dt><dd>${escapeHtml(model.metric_name ?? "Metric")}: ${escapeHtml(metricValue)}</dd></div>
      </dl>
      <div class="model-card-actions">
        <button class="model-card-link" type="button" data-model-action="load-workspace" data-model-id="${escapeHtml(model.model_id ?? "")}">Load WorkSpace</button>
        <button class="model-card-link" type="button" data-model-action="details" data-model-id="${escapeHtml(model.model_id ?? "")}">Model Setting</button>
        <button class="model-card-link" type="button" data-model-action="summary" data-model-id="${escapeHtml(model.model_id ?? "")}">Model Summary (Download)</button>
      </div>
    `;
    modelList.append(item);
  });
  if (modelScroller) {
    modelScroller.scrollLeft = 0;
  }
  updateModelScrollerControls();
};

const refreshSavedModels = async () => {
  try {
    const response = await fetch("/api/models");
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.error ?? "The saved workspace registry could not be loaded.");
    }
    savedModelsCache = Array.isArray(payload.models) ? payload.models : [];
    const bridgeModelLocked = isPredictionBridgeModelLocked();
    if (selectedSavedModelId && !savedModelsCache.some((model) => model.model_id === selectedSavedModelId)) {
      selectedSavedModelId = bridgeModelLocked ? predictionBridgeState?.modelId ?? "" : "";
    }
    if (savedModelSelect) {
      savedModelSelect.innerHTML = "";

      if (bridgeModelLocked) {
        const selectedModel =
          savedModelsCache.find((model) => model.model_id === (predictionBridgeState?.modelId ?? "")) ?? null;
        const lockedOption = document.createElement("option");
        lockedOption.value = predictionBridgeState?.modelId ?? "";
        lockedOption.textContent = selectedModel
          ? buildModelOptionLabel(selectedModel)
          : predictionBridgeState?.modelDisplayName?.trim()
            ? `${predictionBridgeState.modelDisplayName} | ${predictionBridgeState.modelId}`
            : predictionBridgeState?.modelId ?? "Saved model";
        lockedOption.selected = true;
        savedModelSelect.append(lockedOption);
      } else if (isPredictionWorkflowMode()) {
        const placeholderOption = document.createElement("option");
        placeholderOption.value = "";
        placeholderOption.textContent = `Select saved ${getObservedTargetColumnLabel()} model`;
        savedModelSelect.append(placeholderOption);

        savedModelsCache.forEach((model) => {
          const option = document.createElement("option");
          option.value = model.model_id ?? "";
          option.textContent = buildModelOptionLabel(model);
          option.selected = option.value === selectedSavedModelId;
          savedModelSelect.append(option);
        });
      } else {
        const automaticOption = document.createElement("option");
        automaticOption.value = "";
        automaticOption.textContent = "Automatic | Run FeatureHero and create or refresh the active model";
        savedModelSelect.append(automaticOption);

        savedModelsCache.forEach((model) => {
          const option = document.createElement("option");
          option.value = model.model_id ?? "";
          option.textContent = buildModelOptionLabel(model);
          option.selected = option.value === selectedSavedModelId;
          savedModelSelect.append(option);
        });
      }
      syncSelectedModelControl();
    }
    renderSavedModels(savedModelsCache);
  } catch (error) {
    console.error(error);
    savedModelsCache = [];
    selectedSavedModelId = "";
    modelCount.textContent = "Workspace registry unavailable";
    modelEmpty.hidden = false;
    modelEmpty.textContent = "The app could not load the saved workspace list.";
    modelList.innerHTML = "";
    if (savedModelSelect) {
      savedModelSelect.innerHTML = "";
      const unavailableOption = document.createElement("option");
      unavailableOption.value = "";
      unavailableOption.textContent = "Model registry unavailable";
      savedModelSelect.append(unavailableOption);
    }
    updateSelectedModelHelp();
    updateModelScrollerControls();
  }
};

const formatLoadingPercentLabel = (percent) => {
  if (!Number.isFinite(percent)) {
    return "0%";
  }
  const rounded = Math.round(percent * 10) / 10;
  return Number.isInteger(rounded) ? `${rounded}%` : `${rounded.toFixed(1)}%`;
};

const setLoadingState = async (percent, stage, message, visible = true) => {
  if (visible) {
    if (loadingPanelResetTimer) {
      window.clearTimeout(loadingPanelResetTimer);
      loadingPanelResetTimer = null;
    }
  }
  loadingPanel.hidden = !visible;
  loadingBarFill.style.width = `${percent}%`;
  loadingStage.textContent = stage;
  loadingPercent.textContent = formatLoadingPercentLabel(percent);
  loadingMessage.textContent = message;
  await sleepFrame();
};

const scheduleLoadingPanelReset = (delayMs = 5000) => {
  if (loadingPanelResetTimer) {
    window.clearTimeout(loadingPanelResetTimer);
  }
  loadingPanelResetTimer = window.setTimeout(() => {
    loadingPanelResetTimer = null;
    if (pausedPreprocessPayload) {
      return;
    }
    if (readActivePipelineJob()?.statusUrl) {
      return;
    }
    setLoadingState(0, "Waiting for file", "Upload a file to start processing.", false).catch(
      (error) => {
        console.error(error);
      },
    );
  }, delayMs);
};

const startPipelineJob = async (
  file,
  {
    selectedModelId = "",
    selectedGermplasmNames = [],
    selectedIdHeader = "",
    selectedGermplasmProjectionMode = "",
    projectionTemplateWorkbook = "",
    forecastPlantingDate = "",
    forecastHarvestingDate = "",
    pauseAfterPreprocess = false,
    climateScope = "point",
    regionalCountry = "",
    regionalBounds = null,
  } = {},
) => {
  const headers = {
    "Content-Type":
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "X-File-Name": file.name,
  };
  // High-Potential Sites date rule:
  // - Explore Original Data => use forecast/system dates from the UI
  // - Load Data to Predict => use planting/harvesting dates from the uploaded workbook
  const useSourceRowDates =
    isPredictionWorkflowMode() &&
    climateScope === "regional_manual" &&
    predictionGermplasmSourceMode !== "original";
  if (selectedModelId) {
    headers["X-Selected-Model-Id"] = selectedModelId;
  }
  if (selectedGermplasmNames.length) {
    headers["X-Selected-Germplasm-Names"] = JSON.stringify(selectedGermplasmNames);
  }
  if (selectedIdHeader) {
    headers["X-Selected-Id-Header"] = selectedIdHeader;
  }
  if (selectedGermplasmProjectionMode) {
    headers["X-Selected-Germplasm-Projection-Mode"] = selectedGermplasmProjectionMode;
  }
  const bridgeSourceFile = predictionBridgeState?.sourceFile ?? predictionBridgeState?.file ?? null;
  const usingBridgeSourceFile = Boolean(bridgeSourceFile) && file === bridgeSourceFile;
  if (isPredictionWorkflowMode() && predictionBridgeState?.isAvailable && climateScope === "regional_manual" && usingBridgeSourceFile) {
    headers["X-Selected-Germplasm-Selection-Mode"] = "first_match_only";
  }
  if (isPredictionWorkflowMode() && climateScope === "regional_manual") {
    headers["X-Use-Source-Row-Dates"] = useSourceRowDates ? "1" : "0";
  }
  if (projectionTemplateWorkbook) {
    headers["X-Projection-Template-Workbook"] = projectionTemplateWorkbook;
  }
  if (!useSourceRowDates && forecastPlantingDate) {
    headers["X-Forecast-Planting-Date"] = forecastPlantingDate;
  }
  if (!useSourceRowDates && forecastHarvestingDate) {
    headers["X-Forecast-Harvesting-Date"] = forecastHarvestingDate;
  }
  if (pauseAfterPreprocess) {
    headers["X-Pause-After-Preprocess"] = "1";
  }
  if (climateScope) {
    headers["X-Climate-Scope"] = climateScope;
  }
  if (regionalCountry) {
    headers["X-Regional-Country"] = regionalCountry;
  }
  if (regionalBounds) {
    headers["X-Regional-Bounds-Label"] = regionalBounds.label ?? "Manual bounds";
    headers["X-Regional-Bounds-Latitude-Min"] = String(regionalBounds.latitudeMin ?? "");
    headers["X-Regional-Bounds-Latitude-Max"] = String(regionalBounds.latitudeMax ?? "");
    headers["X-Regional-Bounds-Longitude-Min"] = String(regionalBounds.longitudeMin ?? "");
    headers["X-Regional-Bounds-Longitude-Max"] = String(regionalBounds.longitudeMax ?? "");
    headers["X-Nasa-Grid-Resolution-Km"] = String(featureheroSettings.nasa_power_resolution_km ?? 5);
  }
  const response = await fetch("/api/process-xlsx/start", {
    method: "POST",
    headers,
    body: file,
  });

  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.error ?? "The pipeline could not process the uploaded file.");
  }

  return payload;
};

const loadGermplasmOptions = async (file, { selectedIdHeader = "", mode = predictionGermplasmSourceMode } = {}) => {
  const headers = {
    "Content-Type":
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "X-File-Name": file.name,
    "X-Prediction-Germplasm-Mode": mode,
  };
  if (isPredictionWorkflowMode() && selectedSavedModelId) {
    headers["X-Selected-Model-Id"] = selectedSavedModelId;
    headers["X-Climate-Scope"] = getEffectiveClimateScope() || selectedClimateScope || "regional_manual";
  }
  if (selectedIdHeader) {
    headers["X-Selected-Id-Header"] = selectedIdHeader;
  }
  const response = await fetch("/api/process-xlsx/germplasm-options", {
    method: "POST",
    headers,
    body: file,
  });

  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.error ?? "The germplasm list could not be loaded from the selected workbook.");
  }

  return payload;
};

const loadOriginalDataPreview = async (file) => {
  const response = await fetch("/api/process-xlsx/original-data", {
    method: "POST",
    headers: {
      "Content-Type":
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      "X-File-Name": file.name,
    },
    body: file,
  });

  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.error ?? "The original workbook preview could not be loaded.");
  }

  return payload;
};


const loadSelectionPropertiesMetadata = async (file) => {
  const response = await fetch("/api/process-xlsx/selecction-properties", {
    method: "POST",
    headers: {
      "Content-Type":
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      "X-File-Name": file.name,
    },
    body: file,
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.error ?? "The workbook columns could not be loaded.");
  }
  return payload;
};

const startSelectionPropertiesSummaryExecution = async (file, summarySelection) => {
  const response = await fetch("/api/process-xlsx/selecction-properties/summary", {
    method: "POST",
    headers: {
      "Content-Type":
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      "X-File-Name": file.name,
      "X-Target-Column": summarySelection.targetColumn,
      "X-Latitude-Column": summarySelection.latitudeColumn,
      "X-Longitude-Column": summarySelection.longitudeColumn,
      "X-Planting-Date-Column": summarySelection.plantingDateColumn,
      "X-Harvesting-Date-Column": summarySelection.harvestingDateColumn,
      "X-Soil-Texture-Column": summarySelection.soilTextureColumn,
      "X-Soil-Depth-Column": summarySelection.soilDepthColumn,
      "X-Identifier-Columns": JSON.stringify(summarySelection.identifierColumns ?? []),
      "X-Categorical-Columns": JSON.stringify(summarySelection.categoricalColumns ?? []),
      "X-Quantitative-Columns": JSON.stringify(summarySelection.quantitativeColumns ?? []),
      "X-No-Defined-Columns": JSON.stringify(summarySelection.noDefinedColumns ?? []),
      "X-Workspace-Name": String(summarySelection.workspaceName ?? "").trim(),
    },
    body: file,
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.error ?? "The Summary execution could not create the run files.");
  }
  return payload;
};

const parseSelectionPropertiesSummaryPayload = async (response) => {
  const raw = await response.text();
  if (!raw.trim()) {
    return {};
  }
  try {
    return JSON.parse(raw);
  } catch (error) {
    throw new Error(`The ce_pipeline status response could not be parsed (${response.status}).`);
  }
};

const fetchSelectionPropertiesSummaryResult = async (resultUrl, fallbackPayload = null) => {
  const resolvedUrl = String(resultUrl ?? "").trim();
  if (!resolvedUrl) {
    return fallbackPayload ?? {};
  }
  const response = await fetch(resolvedUrl, { method: "GET" });
  const payload = await parseSelectionPropertiesSummaryPayload(response);
  if (!response.ok || payload?.status === "error") {
    throw new Error(payload.error ?? "The ce_pipeline result could not be loaded.");
  }
  return payload;
};

const pollSelectionPropertiesSummaryStatus = async (statusUrl, resultUrl = "") => {
  let consecutiveFailures = 0;
  while (true) {
    await sleep(
      consecutiveFailures
        ? Math.min(PIPELINE_POLL_MAX_DELAY_MS, PIPELINE_POLL_BASE_DELAY_MS * 2 ** consecutiveFailures)
        : PIPELINE_POLL_BASE_DELAY_MS,
    );
    let response;
    try {
      response = await fetch(statusUrl, { method: "GET" });
    } catch (error) {
      consecutiveFailures += 1;
      await setLoadingState(
        12,
        "Reconnecting to ce_pipeline",
        `The connection dropped while executing ce_pipeline. Retrying (${consecutiveFailures})...`,
        true,
      );
      continue;
    }
    const payload = await parseSelectionPropertiesSummaryPayload(response);
    const progress = payload?.progress ?? {};
    const status = payload?.status ?? progress?.status ?? "running";
    const percent = Number(progress?.percent ?? 10);
    const stage = progress?.stage ?? "Executing ce_pipeline";
    const message = progress?.message ?? "The backend is processing the ce_pipeline run.";

    setSelectionPropertiesBadge(stage);
    setSelectionPropertiesStatus(message);
    await setLoadingState(percent, stage, message, true);

    if (
      response.ok &&
      status !== "completed" &&
      !selectionPropertiesState.previewOriginalLoaded &&
      payload?.geojson &&
      payload?.summary
    ) {
      registerDataset(
        "original",
        validateFeatureCollection(payload.geojson),
        payload.phase3_name ?? payload.source_name ?? "phase03.xlsx",
        "original",
        payload.summary,
      );
      selectionPropertiesState.previewOriginalLoaded = true;
      await showDatasetInView("original", { force: true });
    }

    if (response.ok && status !== "completed" && payload?.training_geojson && payload?.training_summary) {
      const currentTrainingModelId = String(datasetStore.training?.summary?.prediction_model_id ?? datasetStore.training?.summary?.phase_analysis_model_id ?? "").trim();
      const nextTrainingModelId = String(payload.training_summary?.prediction_model_id ?? payload.training_summary?.phase_analysis_model_id ?? "").trim();
      registerDataset(
        "training",
        validateFeatureCollection(payload.training_geojson),
        payload.phase4_name ?? payload.source_name ?? "phase04.xlsx",
        "automatic",
        payload.training_summary,
      );
      primePredictionBridgeFromTraining(selectionPropertiesState.file, payload.training_summary ?? null);
      if (nextTrainingModelId && nextTrainingModelId !== currentTrainingModelId) {
        await refreshSavedModels();
      }
    }

    if (TOP_GERMPLASM_ENABLED && response.ok && status !== "completed" && payload?.top_germplasm_geojson && payload?.top_germplasm_summary) {
      registerDataset(
        "top_germplasm",
        validateFeatureCollection(payload.top_germplasm_geojson),
        payload.top_germplasm_summary?.top_germplasm_xlsx ?? payload.source_name ?? "top_germplasm.xlsx",
        "saved_model",
        payload.top_germplasm_summary,
      );
    }

    if (response.ok) {
      consecutiveFailures = 0;
    }
    if (!response.ok || status === "error") {
      throw new Error(payload.error ?? message ?? "The Summary execution failed.");
    }
    if (status === "completed") {
      return fetchSelectionPropertiesSummaryResult(payload?.result_url ?? resultUrl, payload);
    }
  }
};

const triggerSelectionPropertiesDownload = (downloadUrl, filename = "phase02.xlsx") => {
  const resolvedUrl = String(downloadUrl ?? "").trim();
  if (!resolvedUrl) {
    return;
  }
  const anchor = document.createElement("a");
  anchor.href = resolvedUrl;
  anchor.download = filename;
  anchor.rel = "noopener";
  anchor.style.display = "none";
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
};

const loadSelectionPropertiesPreview = async (file, selection) => {
  const response = await fetch("/api/process-xlsx/selecction-properties/preview", {
    method: "POST",
    headers: {
      "Content-Type":
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      "X-File-Name": file.name,
      "X-Target-Column": selection.targetColumn,
      "X-Latitude-Column": selection.latitudeColumn,
      "X-Longitude-Column": selection.longitudeColumn,
    },
    body: file,
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.error ?? "The workbook preview could not be generated.");
  }
  return payload;
};

const resetSelectionPropertiesState = ({ preserveFile = false } = {}) => {
  selectionPropertiesState = {
    file: preserveFile ? selectionPropertiesState.file : null,
    sourceName: preserveFile ? selectionPropertiesState.sourceName : "",
    workspaceName: preserveFile ? selectionPropertiesState.workspaceName : "",
    headers: [],
    columnProfiles: {},
    columnAssignments: {},
    enabledClassifierColumns: [],
    classifierListScrollTop: 0,
    noDefinedColumns: [],
    rowCount: 0,
    attributeCount: 0,
    targetColumn: "",
    latitudeColumn: "",
    longitudeColumn: "",
    plantingDateColumn: "",
    harvestingDateColumn: "",
    soilTextureColumn: "",
    soilDepthColumn: "",
    identifierColumns: [],
    identifierConfirmed: false,
    categoricalColumns: [],
    categoricalConfirmed: false,
    quantitativeColumns: [],
    quantitativeConfirmed: false,
    columnClassificationConfirmed: false,
    excludedColumns: [],
    summaryReady: false,
    summaryExecuting: false,
    statusUnlocked: false,
    collapsed: false,
    latestSummaryRun: null,
    previewOriginalLoaded: false,
    workspaceReadonlyLoaded: false,
    activeStep: "initial",
    highlightedIdentifierColumn: "",
    highlightedCategoricalColumn: "",
    highlightedQuantitativeColumn: "",
    identifierListScrollTop: 0,
    categoricalListScrollTop: 0,
    quantitativeListScrollTop: 0,
    mappedFeatureCount: 0,
    search: {
      target: "",
      longitude: "",
      latitude: "",
      plantingDate: "",
      harvestingDate: "",
      soilTexture: "",
      soilDepth: "",
      identifiers: "",
      categoric: "",
      cuantitative: "",
      excluded: "",
    },
  };
};

const formatSelectionCount = (count) => `${count} column${count === 1 ? "" : "s"}`;

const sortSelectionValues = (values = []) =>
  [...values]
    .map((value) => String(value ?? "").trim())
    .filter(Boolean)
    .sort((left, right) => left.localeCompare(right, undefined, { sensitivity: "base", numeric: true }));

const getAutoSelectedIdentifierColumns = (columns = []) =>
  preferredIdentifierColumns.filter((column) => columns.includes(column));

const sortIdentifierSelectionValues = (values = []) => {
  const normalizedValues = sortSelectionValues(values);
  const prioritized = getAutoSelectedIdentifierColumns(normalizedValues);
  const prioritizedSet = new Set(prioritized);
  return [
    ...prioritized,
    ...normalizedValues.filter((value) => !prioritizedSet.has(value)),
  ];
};

const filterSelectionValues = (values = [], query = "") => {
  const normalizedQuery = String(query ?? "").trim().toLowerCase();
  const sortedValues = sortSelectionValues(values);
  if (!normalizedQuery || normalizedQuery.length < 3) {
    return sortedValues;
  }
  return sortedValues.filter((value) => value.toLowerCase().includes(normalizedQuery));
};

const syncSelectionSearchInput = (element, { disabled = true, value = "", placeholder = "" } = {}) => {
  if (!element) {
    return;
  }
  element.disabled = disabled;
  element.value = value;
  if (placeholder) {
    element.placeholder = placeholder;
  }
};

const populateSelectionMultiListbox = (element, values = [], { disabled = true } = {}) => {
  if (!element) {
    return;
  }
  element.innerHTML = "";
  values.forEach((value) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    option.selected = true;
    element.append(option);
  });
  if (!values.length) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = disabled ? "Upload and configure the workbook first" : "No matching columns";
    element.append(option);
  }
  element.disabled = disabled;
};

const updateSelectionCounter = (element, count) => {
  if (element) {
    element.textContent = formatSelectionCount(count);
  }
};

const renderSelectionPropertiesOverview = () => {
  if (selectionOverviewTarget) {
    selectionOverviewTarget.textContent = selectionPropertiesState.targetColumn || "Pending";
  }
  if (selectionOverviewLongitude) {
    selectionOverviewLongitude.textContent = selectionPropertiesState.longitudeColumn || "Pending";
  }
  if (selectionOverviewLatitude) {
    selectionOverviewLatitude.textContent = selectionPropertiesState.latitudeColumn || "Pending";
  }
  if (selectionOverviewColumns) {
    selectionOverviewColumns.textContent = String(selectionPropertiesState.attributeCount || selectionPropertiesState.headers.length || 0);
  }
  if (selectionOverviewRows) {
    selectionOverviewRows.textContent = String(selectionPropertiesState.rowCount || 0);
  }
  if (selectionOverviewPoints) {
    selectionOverviewPoints.textContent = String(selectionPropertiesState.mappedFeatureCount || 0);
  }
};

const updateSelectionPropertiesCollapseState = () => {
  const isCollapsed = Boolean(selectionPropertiesState.collapsed);
  const canHideWorkflow = !isCollapsed && (
    selectionPropertiesState.summaryExecuting
    || selectionPropertiesState.summaryReady
    || Boolean(selectionPropertiesState.latestSummaryRun)
  );
  if (selectionPropertiesCollapsed) {
    selectionPropertiesCollapsed.hidden = !isCollapsed;
  }
  if (selectionPropertiesCollapsedCopy) {
    const latestRun = selectionPropertiesState.latestSummaryRun;
    selectionPropertiesCollapsedCopy.textContent = selectionPropertiesState.summaryExecuting
      ? "Executing ce_pipeline. Follow the phase progress in the status bar below Select File."
      : latestRun
        ? `Summary executed. Files created: ${latestRun.new_input_name}, ${latestRun.phase1_name ?? "phase1.xlsx"}, ${latestRun.phase2_name ?? "phase02.xlsx"}, ${latestRun.phase3_name ?? "phase03.xlsx"}, ${latestRun.phase4_name ?? "phase04.xlsx"}, and ${latestRun.phase4_training_input_name ?? "phase04_training_input.xlsx"}`
        : "Summary execution completed.";
  }
  if (selectionPropertiesHide) {
    selectionPropertiesHide.hidden = !canHideWorkflow;
  }
  if (selectionPropertiesStepper) {
    selectionPropertiesStepper.hidden = isCollapsed;
  }
  if (selectionInitialSettingsCard) {
    selectionInitialSettingsCard.hidden = isCollapsed || selectionPropertiesState.activeStep !== "initial";
  }
  if (selectionSelectColumnsCard) {
    selectionSelectColumnsCard.hidden = isCollapsed || selectionPropertiesState.activeStep !== "select-columns";
  }
  if (selectionSummaryCard) {
    selectionSummaryCard.hidden = isCollapsed || !selectionPropertiesState.summaryReady || selectionPropertiesState.activeStep !== "summary";
  }
};

const handleSelectionSummaryPlay = async () => {
  if (!selectionPropertiesState.file || !selectionPropertiesState.summaryReady || selectionPropertiesState.summaryExecuting) {
    return;
  }
  selectionPropertiesState.summaryExecuting = true;
  selectionPropertiesState.statusUnlocked = true;
  selectionPropertiesState.previewOriginalLoaded = false;
  selectionPropertiesState.collapsed = true;
  renderSelectionWorkbench();
  updateSelectionPropertiesCollapseState();
  restoreLoadingPanelHome();
  setSelectionPropertiesBadge("Preparing ce_pipeline");
  setSelectionPropertiesStatus("Preparing ce_pipeline files for this run.");
  await setLoadingState(6, "Preparing ce_pipeline", "Preparing ce_pipeline files for this run.", true);
  try {
    const startPayload = await startSelectionPropertiesSummaryExecution(selectionPropertiesState.file, {
      targetColumn: selectionPropertiesState.targetColumn,
      longitudeColumn: selectionPropertiesState.longitudeColumn,
      latitudeColumn: selectionPropertiesState.latitudeColumn,
      plantingDateColumn: selectionPropertiesState.plantingDateColumn,
      harvestingDateColumn: selectionPropertiesState.harvestingDateColumn,
      soilTextureColumn: selectionPropertiesState.soilTextureColumn,
      soilDepthColumn: selectionPropertiesState.soilDepthColumn,
      identifierColumns: selectionPropertiesState.identifierColumns,
      categoricalColumns: selectionPropertiesState.categoricalColumns,
      quantitativeColumns: selectionPropertiesState.quantitativeColumns,
      noDefinedColumns: selectionPropertiesState.noDefinedColumns,
      workspaceName: selectionPropertiesState.workspaceName,
    });
    const statusUrl = String(startPayload?.status_url ?? "").trim();
    const resultUrl = String(startPayload?.result_url ?? "").trim();
    if (!statusUrl) {
      throw new Error("The Summary execution did not return a valid status URL.");
    }
    const payload = await pollSelectionPropertiesSummaryStatus(statusUrl, resultUrl);
    selectionPropertiesState.latestSummaryRun = payload;
    selectionPropertiesState.collapsed = true;
    if (payload?.geojson && payload?.summary) {
      registerDataset(
        "original",
        validateFeatureCollection(payload.geojson),
        payload.phase3_name ?? payload.source_name ?? "phase03.xlsx",
        "original",
        payload.summary,
      );
      datasetStore.prediction = null;
      await showDatasetInView("original", { force: true });
    }
    if (payload?.training_geojson && payload?.training_summary) {
      registerDataset(
        "training",
        validateFeatureCollection(payload.training_geojson),
        payload.phase4_name ?? payload.source_name ?? "phase04.xlsx",
        "automatic",
        payload.training_summary,
      );
      datasetStore.prediction = null;
      await promptForGeneratedModelNameIfNeeded(payload.training_summary ?? null);
      primePredictionBridgeFromTraining(selectionPropertiesState.file, payload.training_summary ?? null);
      await refreshSavedModels();
    } else {
      datasetStore.training = null;
    }
    datasetStore.prediction = null;
    datasetStore.top_germplasm = null;
    setSelectionPropertiesBadge("Summary executed");
    setSelectionPropertiesStatus(`Summary files created. ${payload.new_input_name}, ${payload.phase1_name ?? "phase1.xlsx"}, ${payload.phase2_name ?? "phase02.xlsx"}, ${payload.phase3_name ?? "phase03.xlsx"}, ${payload.phase4_name ?? "phase04.xlsx"}, and ${payload.phase4_training_input_name ?? "phase04_training_input.xlsx"} are ready for this run.`);
    await setLoadingState(
      100,
      "ce_pipeline complete",
      `Original Data now reflects ${payload.phase3_name ?? "phase03.xlsx"} and Training now reflects ${payload.phase4_name ?? "phase04.xlsx"}.`,
      true,
    );
  } catch (error) {
    setSelectionPropertiesBadge("Summary error");
    setSelectionPropertiesStatus(error instanceof Error ? error.message : "The Summary execution failed.");
    await setLoadingState(
      100,
      "ce_pipeline error",
      error instanceof Error ? error.message : "The Summary execution failed.",
      true,
    );
  } finally {
    selectionPropertiesState.summaryExecuting = false;
    renderSelectionWorkbench();
    updateSelectionPropertiesCollapseState();
  }
};

const renderSelectionSummaryPanel = () => {
  const isWorkspaceReadonly = Boolean(selectionPropertiesState.workspaceReadonlyLoaded);
  renderSelectionSummary({
    mountNode: selectionSummaryRoot,
    initialSettings: {
      targetColumn: selectionPropertiesState.targetColumn,
      longitudeColumn: selectionPropertiesState.longitudeColumn,
      latitudeColumn: selectionPropertiesState.latitudeColumn,
      plantingDateColumn: selectionPropertiesState.plantingDateColumn,
      harvestingDateColumn: selectionPropertiesState.harvestingDateColumn,
      soilTextureColumn: selectionPropertiesState.soilTextureColumn,
      soilDepthColumn: selectionPropertiesState.soilDepthColumn,
      rowCount: selectionPropertiesState.rowCount,
    },
    divisions: {
      selectedColumns: sortSelectionValues([
        ...selectionPropertiesState.identifierColumns,
        ...selectionPropertiesState.categoricalColumns,
        ...selectionPropertiesState.quantitativeColumns,
      ]),
      identifierColumns: selectionPropertiesState.identifierColumns,
      categoricalColumns: selectionPropertiesState.categoricalColumns,
      quantitativeColumns: selectionPropertiesState.quantitativeColumns,
      noDefinedColumns: selectionPropertiesState.noDefinedColumns,
    },
    disabled: !selectionPropertiesState.summaryReady || selectionPropertiesState.summaryExecuting || isWorkspaceReadonly,
    onPlay: () => {
      handleSelectionSummaryPlay().catch((error) => {
        console.error(error);
        setSelectionPropertiesBadge("Summary error");
        setSelectionPropertiesStatus(error instanceof Error ? error.message : "The Summary execution failed.");
      });
    },
  });
  if (selectionSummaryBadge) {
    selectionSummaryBadge.textContent = selectionPropertiesState.summaryReady ? "Ready" : "Pending";
  }
};

const hasAllRequiredInitialSelections = () =>
  Boolean(
    selectionPropertiesState.targetColumn &&
    selectionPropertiesState.longitudeColumn &&
    selectionPropertiesState.latitudeColumn &&
    selectionPropertiesState.plantingDateColumn &&
    selectionPropertiesState.harvestingDateColumn &&
    selectionPropertiesState.soilTextureColumn &&
    selectionPropertiesState.soilDepthColumn,
  );

const isSelectionPropertiesConfigured = () => hasAllRequiredInitialSelections();

const isSelectionSummaryReady = () => Boolean(selectionPropertiesState.summaryReady);

const initializeSelectionChoices = () => {
  const ChoicesCtor = window.Choices;
  if (typeof ChoicesCtor !== "function") {
    return;
  }
  selectionChoiceConfigs.forEach((config, element) => {
    if (!element || selectionChoices.has(element)) {
      return;
    }
    const instance = new ChoicesCtor(element, {
      allowHTML: false,
      itemSelectText: "",
      searchEnabled: config.searchEnabled,
      searchChoices: config.searchEnabled,
      searchFloor: 1,
      searchResultLimit: 100,
      shouldSort: false,
      placeholder: true,
      placeholderValue: config.placeholderValue,
      searchPlaceholderValue: config.searchPlaceholderValue,
      noResultsText: "No matching fields",
      noChoicesText: "No fields available",
      renderChoiceLimit: -1,
    });
    if (config.searchEnabled && instance?.containerOuter?.element) {
      const focusSearchInput = (selectExistingText = false) => {
        window.setTimeout(() => {
          const inputElement = instance.input?.element;
          inputElement?.removeAttribute("readonly");
          inputElement?.focus();
          if (selectExistingText && inputElement?.value) {
            inputElement.select?.();
          }
        }, 0);
      };
      instance.containerOuter.element.addEventListener("showDropdown", () => {
        focusSearchInput(false);
      });
      instance.containerOuter.element.addEventListener("click", (event) => {
        const inputElement = instance.input?.element;
        if (inputElement && event.target === inputElement) {
          return;
        }
        focusSearchInput(false);
      });
    }
    selectionChoices.set(element, instance);
  });
};

const updateSelectionFieldRequiredState = (_searchElement, selectElement, isMissing) => {
  selectElement?.classList.toggle("is-required-empty", isMissing);
  selectElement?.closest(".selection-field-control")?.classList.toggle("is-required-empty", isMissing);
  const choicesContainer = selectElement?.closest(".selection-field-control")?.querySelector(".choices");
  choicesContainer?.classList.toggle("is-required-empty", isMissing);
};

const updateSelectionStepperState = () => {
  const hasHeaders = Boolean(selectionPropertiesState.headers.length);
  const isConfigured = isSelectionPropertiesConfigured();
  const isSummaryReady = isSelectionSummaryReady();
  selectionStepItems.forEach((item) => {
    if (!item) {
      return;
    }
    const stepKey = item.dataset.stepKey ?? "";
    item.classList.remove("selection-step-active", "selection-step-pending", "selection-step-complete");
    if (!hasHeaders) {
      item.classList.add(stepKey === "initial" ? "selection-step-active" : "selection-step-pending");
      return;
    }
    if (stepKey === "initial") {
      item.classList.add(selectionPropertiesState.activeStep === "initial" ? "selection-step-active" : "selection-step-complete");
      return;
    }
    if (stepKey === "select-columns") {
      item.classList.add(isConfigured ? (selectionPropertiesState.activeStep === "select-columns" ? "selection-step-active" : "selection-step-complete") : "selection-step-pending");
      return;
    }
    if (stepKey === "summary") {
      item.classList.add(isSummaryReady ? (selectionPropertiesState.activeStep === "summary" ? "selection-step-active" : "selection-step-complete") : "selection-step-pending");
    }
  });
};

const getReservedSelectionColumns = () => [
  selectionPropertiesState.targetColumn,
  selectionPropertiesState.latitudeColumn,
  selectionPropertiesState.longitudeColumn,
  selectionPropertiesState.plantingDateColumn,
  selectionPropertiesState.harvestingDateColumn,
  selectionPropertiesState.soilTextureColumn,
  selectionPropertiesState.soilDepthColumn,
].filter(Boolean);

const getAvailableIdentifierColumns = () =>
  buildSelectableColumnOptions(selectionPropertiesState.headers, getReservedSelectionColumns())
    .filter((column) => !isDGColumn(column));

const getAvailableClassifierColumns = () =>
  buildSelectableColumnOptions(
    selectionPropertiesState.headers,
    [
      ...getReservedSelectionColumns(),
      ...selectionPropertiesState.identifierColumns,
    ],
  ).filter((column) => !isDGColumn(column));

const preferredIdentifierColumns = [
  "Trial series name",
  "Rep",
  "Farm",
  "Site Number",
  "Plot",
  "Entry",
  "EntryCode",
  "Name",
  "Local check, Name of variety provided by farmer",
];

const maybeAutoSelectIdentifierColumns = () => {
  if (!isSelectionPropertiesConfigured() || selectionPropertiesState.identifierConfirmed) {
    return;
  }
  if (Array.isArray(selectionPropertiesState.identifierColumns) && selectionPropertiesState.identifierColumns.length) {
    return;
  }
  const availableIdentifierColumns = getAvailableIdentifierColumns();
  const autoSelectedColumns = preferredIdentifierColumns.filter((column) => availableIdentifierColumns.includes(column));
  if (!autoSelectedColumns.length) {
    return;
  }
  selectionPropertiesState.identifierColumns = sortIdentifierSelectionValues(autoSelectedColumns);
  selectionPropertiesState.highlightedIdentifierColumn = selectionPropertiesState.identifierColumns[0] || "";
};

const getRecommendedColumnClassification = (column) => {
  const profile = selectionPropertiesState.columnProfiles?.[column] ?? {};
  const recommended = String(profile.recommended_classification ?? "").trim();
  if (["categorical", "quantitative", "no_defined"].includes(recommended)) {
    return recommended;
  }
  return "no_defined";
};

const syncClassifiedColumnGroupsFromAssignments = () => {
  const enabledSet = new Set((selectionPropertiesState.enabledClassifierColumns ?? []).map((column) => String(column ?? "").trim()).filter(Boolean));
  const entries = Object.entries(selectionPropertiesState.columnAssignments ?? {})
    .filter(([column]) => enabledSet.has(String(column ?? "").trim()));
  selectionPropertiesState.categoricalColumns = sortSelectionValues(
    entries.filter(([, value]) => value === "categorical").map(([column]) => column),
  );
  selectionPropertiesState.quantitativeColumns = sortSelectionValues(
    entries.filter(([, value]) => value === "quantitative").map(([column]) => column),
  );
  selectionPropertiesState.noDefinedColumns = sortSelectionValues(
    entries.filter(([, value]) => value === "no_defined").map(([column]) => column),
  );
  selectionPropertiesState.summaryReady = Boolean(
    selectionPropertiesState.identifierConfirmed
    && selectionPropertiesState.columnClassificationConfirmed
    && (selectionPropertiesState.categoricalColumns.length || selectionPropertiesState.quantitativeColumns.length)
  );
};

const syncColumnAssignments = ({ resetConfirmation = false } = {}) => {
  const availableClassifierColumns = getAvailableClassifierColumns();
  const nextAssignments = {};
  const existingAssignments = selectionPropertiesState.columnAssignments ?? {};
  const existingEnabled = new Set((selectionPropertiesState.enabledClassifierColumns ?? []).map((column) => String(column ?? "").trim()).filter(Boolean));
  const nextEnabledColumns = [];
  availableClassifierColumns.forEach((column) => {
    const current = String(existingAssignments[column] ?? "").trim();
    const resolvedValue = ["categorical", "quantitative", "no_defined"].includes(current)
      ? current
      : getRecommendedColumnClassification(column);
    nextAssignments[column] = resolvedValue;
    if (resolvedValue !== "no_defined" && (!existingEnabled.size || existingEnabled.has(column))) {
      nextEnabledColumns.push(column);
    }
  });
  selectionPropertiesState.columnAssignments = nextAssignments;
  selectionPropertiesState.enabledClassifierColumns = sortSelectionValues(nextEnabledColumns);
  if (resetConfirmation) {
    selectionPropertiesState.classifierListScrollTop = 0;
    selectionPropertiesState.columnClassificationConfirmed = false;
    selectionPropertiesState.categoricalConfirmed = false;
    selectionPropertiesState.quantitativeConfirmed = false;
  }
  syncClassifiedColumnGroupsFromAssignments();
};

const recalculateSelectionPropertiesGroups = ({ resetClassificationConfirmation = false } = {}) => {
  const availableIdentifierColumns = getAvailableIdentifierColumns();
  selectionPropertiesState.identifierColumns = sortIdentifierSelectionValues(selectionPropertiesState.identifierColumns)
    .filter((column) => availableIdentifierColumns.includes(column));
  if (
    selectionPropertiesState.highlightedIdentifierColumn
    && !selectionPropertiesState.identifierColumns.includes(selectionPropertiesState.highlightedIdentifierColumn)
    && !availableIdentifierColumns.includes(selectionPropertiesState.highlightedIdentifierColumn)
  ) {
    selectionPropertiesState.highlightedIdentifierColumn = "";
  }

  selectionPropertiesState.excludedColumns = getReservedSelectionColumns();
  syncColumnAssignments({ resetConfirmation: resetClassificationConfirmation });
};

const setIdentifierColumnsSelection = (columns = [], highlightedColumn = "", scrollTop = 0) => {
  if (!isSelectionPropertiesConfigured() || selectionPropertiesState.identifierConfirmed) {
    return;
  }
  selectionPropertiesState.identifierColumns = sortIdentifierSelectionValues(columns);
  selectionPropertiesState.highlightedIdentifierColumn = String(highlightedColumn ?? "").trim() || selectionPropertiesState.identifierColumns[0] || "";
  selectionPropertiesState.identifierListScrollTop = Number(scrollTop ?? 0);
  selectionPropertiesState.columnAssignments = {};
  selectionPropertiesState.enabledClassifierColumns = [];
  selectionPropertiesState.classifierListScrollTop = 0;
  selectionPropertiesState.columnClassificationConfirmed = false;
  selectionPropertiesState.categoricalConfirmed = false;
  selectionPropertiesState.quantitativeConfirmed = false;
  selectionPropertiesState.categoricalColumns = [];
  selectionPropertiesState.quantitativeColumns = [];
  selectionPropertiesState.noDefinedColumns = [];
  selectionPropertiesState.summaryReady = false;
  recalculateSelectionPropertiesGroups({ resetClassificationConfirmation: true });
  renderSelectionWorkbench();
  setSelectionActiveStep(selectionPropertiesState.activeStep);
};

const applyIdentifierColumnsSelection = (columns = []) => {
  const normalizedColumns = sortIdentifierSelectionValues(columns);
  if (!normalizedColumns.length) {
    setSelectionPropertiesBadge("Select Columns required");
    setSelectionPropertiesStatus("Select at least one identifier before confirming Identifiers.");
    renderSelectionWorkbench();
    return;
  }
  selectionPropertiesState.identifierColumns = normalizedColumns;
  selectionPropertiesState.identifierConfirmed = true;
  selectionPropertiesState.highlightedIdentifierColumn = selectionPropertiesState.highlightedIdentifierColumn || normalizedColumns[0] || "";
  selectionPropertiesState.columnAssignments = {};
  recalculateSelectionPropertiesGroups({ resetClassificationConfirmation: true });
  renderSelectionWorkbench();
  selectionCategoricalCard?.scrollIntoView({ behavior: "smooth", block: "start" });
  setSelectionPropertiesBadge("Select Columns enabled");
  setSelectionPropertiesStatus("Identifiers confirmed. Attributes is now available in Step 2.");
};

const reviewIdentifierColumn = (column) => {
  const normalizedColumn = String(column ?? "").trim() || selectionPropertiesState.identifierColumns[0] || "";
  selectionPropertiesState.highlightedIdentifierColumn = normalizedColumn;
  renderSelectionWorkbench();
  if (normalizedColumn) {
    setSelectionPropertiesStatus(`Reviewing ${normalizedColumn} inside Identifiers. Preprocess, training, prediction, and Original Data rendering remain disabled.`);
  }
};

const setColumnClassificationValue = (column, value, scrollTop = selectionPropertiesState.classifierListScrollTop) => {
  if (!isSelectionPropertiesConfigured() || !selectionPropertiesState.identifierConfirmed) {
    return;
  }
  const normalizedColumn = String(column ?? "").trim();
  const normalizedValue = ["categorical", "quantitative", "no_defined"].includes(String(value ?? "").trim())
    ? String(value ?? "").trim()
    : "no_defined";
  selectionPropertiesState.columnAssignments = {
    ...(selectionPropertiesState.columnAssignments ?? {}),
    [normalizedColumn]: normalizedValue,
  };
  const enabledSet = new Set((selectionPropertiesState.enabledClassifierColumns ?? []).map((value) => String(value ?? "").trim()).filter(Boolean));
  if (normalizedValue === "no_defined") {
    enabledSet.delete(normalizedColumn);
  } else {
    enabledSet.add(normalizedColumn);
  }
  selectionPropertiesState.enabledClassifierColumns = sortSelectionValues([...enabledSet]);
  selectionPropertiesState.classifierListScrollTop = Number(scrollTop ?? 0);
  selectionPropertiesState.columnClassificationConfirmed = false;
  selectionPropertiesState.categoricalConfirmed = false;
  selectionPropertiesState.quantitativeConfirmed = false;
  syncClassifiedColumnGroupsFromAssignments();
  renderSelectionWorkbench();
};

const setColumnClassificationEnabled = (column, isEnabled, scrollTop = selectionPropertiesState.classifierListScrollTop) => {
  if (!isSelectionPropertiesConfigured() || !selectionPropertiesState.identifierConfirmed) {
    return;
  }
  const normalizedColumn = String(column ?? "").trim();
  const enabledSet = new Set((selectionPropertiesState.enabledClassifierColumns ?? []).map((value) => String(value ?? "").trim()).filter(Boolean));
  if (isEnabled) {
    enabledSet.add(normalizedColumn);
  } else {
    enabledSet.delete(normalizedColumn);
  }
  selectionPropertiesState.enabledClassifierColumns = sortSelectionValues([...enabledSet]);
  selectionPropertiesState.classifierListScrollTop = Number(scrollTop ?? 0);
  selectionPropertiesState.columnClassificationConfirmed = false;
  selectionPropertiesState.categoricalConfirmed = false;
  selectionPropertiesState.quantitativeConfirmed = false;
  syncClassifiedColumnGroupsFromAssignments();
  renderSelectionWorkbench();
};

const applyColumnClassificationSelection = () => {
  const availableClassifierColumns = getAvailableClassifierColumns();
  const enabledClassifierColumns = (selectionPropertiesState.enabledClassifierColumns ?? []).filter((column) => availableClassifierColumns.includes(column));
  if (!availableClassifierColumns.length) {
    setSelectionPropertiesBadge("Select Columns unavailable");
    setSelectionPropertiesStatus("No remaining columns are available after Initial Settings and Identifiers were selected.");
    renderSelectionWorkbench();
    return;
  }
  if (!enabledClassifierColumns.length) {
    setSelectionPropertiesBadge("Classification required");
    setSelectionPropertiesStatus("Enable at least one column in Select Columns before continuing to Summary.");
    renderSelectionWorkbench();
    return;
  }
  if (!selectionPropertiesState.categoricalColumns.length && !selectionPropertiesState.quantitativeColumns.length) {
    setSelectionPropertiesBadge("Classification required");
    setSelectionPropertiesStatus("Classify at least one column as Categorical or Quantitative before continuing to Summary.");
    renderSelectionWorkbench();
    return;
  }
  selectionPropertiesState.columnClassificationConfirmed = true;
  selectionPropertiesState.categoricalConfirmed = true;
  selectionPropertiesState.quantitativeConfirmed = true;
  syncClassifiedColumnGroupsFromAssignments();
  renderSelectionWorkbench();
  setSelectionPropertiesBadge("Summary enabled");
  setSelectionPropertiesStatus(`Column classification confirmed. ${selectionPropertiesState.categoricalColumns.length} categorical and ${selectionPropertiesState.quantitativeColumns.length} quantitative columns are ready for Summary.`);
};

const renderSelectionWorkbench = () => {
  const isConfigured = isSelectionPropertiesConfigured();
  const isWorkspaceReadonly = Boolean(selectionPropertiesState.workspaceReadonlyLoaded);
  maybeAutoSelectIdentifierColumns();
  const isSummaryReady = isSelectionSummaryReady();
  const availableIdentifierColumns = getAvailableIdentifierColumns();
  const availableClassifierColumns = getAvailableClassifierColumns();

  if (selectionSelectColumnsCard) {
    selectionSelectColumnsCard.classList.toggle("selection-properties-card-disabled", !isConfigured);
    selectionSelectColumnsCard.hidden = !isConfigured || selectionPropertiesState.activeStep !== "select-columns";
  }
  if (selectionCategoricalCard) {
    selectionCategoricalCard.hidden = !isConfigured || !selectionPropertiesState.identifierConfirmed;
    selectionCategoricalCard.classList.remove("selection-step-two-panel-disabled");
  }
  if (selectionQuantitativeCard) {
    selectionQuantitativeCard.hidden = true;
  }
  if (selectionSummaryCard) {
    selectionSummaryCard.hidden = !isSummaryReady || selectionPropertiesState.activeStep !== "summary";
  }

  renderSelectColumnm({
    mountNode: selectionSelectColumnsRoot,
    title: "Identifiers",
    helperText: "",
    columns: availableIdentifierColumns,
    priorityColumns: getAutoSelectedIdentifierColumns(availableIdentifierColumns),
    selectedColumns: selectionPropertiesState.identifierColumns,
    highlightedColumn: selectionPropertiesState.highlightedIdentifierColumn,
    scrollTop: selectionPropertiesState.identifierListScrollTop,
    disabled: !isConfigured || selectionPropertiesState.identifierConfirmed || isWorkspaceReadonly,
    disabledMessage: selectionPropertiesState.identifierConfirmed ? "" : "Complete Initial Settings to enable Select Columns",
    showHeader: false,
    showCounter: false,
    onSelectionChange: (columns, highlightedColumn, scrollTop) => {
      setIdentifierColumnsSelection(columns, highlightedColumn, scrollTop);
    },
    onApplySelection: (columns) => {
      applyIdentifierColumnsSelection(columns);
    },
    onReviewSelection: (column) => {
      reviewIdentifierColumn(column);
    },
    onClearSelection: (columns, highlightedColumn, scrollTop) => {
      setIdentifierColumnsSelection(columns, highlightedColumn, scrollTop);
    },
  });

  renderSelectColumnClassifier({
    mountNode: selectionCategoricalRoot,
    title: "Attributes",
    columns: availableClassifierColumns,
    assignments: selectionPropertiesState.columnAssignments,
    enabledColumns: selectionPropertiesState.enabledClassifierColumns,
    profiles: selectionPropertiesState.columnProfiles,
    scrollTop: selectionPropertiesState.classifierListScrollTop,
    disabled: !isConfigured || !selectionPropertiesState.identifierConfirmed || isWorkspaceReadonly,
    disabledMessage: "Confirm Identifiers to classify the remaining columns.",
    onAssignmentChange: (column, value, scrollTop) => {
      setColumnClassificationValue(column, value, scrollTop);
    },
    onEnabledChange: (column, isEnabled, scrollTop) => {
      setColumnClassificationEnabled(column, isEnabled, scrollTop);
    },
    onScroll: (scrollTop) => {
      selectionPropertiesState.classifierListScrollTop = Number(scrollTop ?? 0);
    },
    onApplySelection: () => {
      applyColumnClassificationSelection();
    },
  });

  if (selectionSelectColumnsCount) {
    selectionSelectColumnsCount.textContent = "2 panels";
  }
  renderSelectionSummaryPanel();
  updateSelectionStepperState();
  updateSelectionStepNavigation();
  renderSelectionPropertiesOverview();
  updateSelectionPropertiesCollapseState();
};

const setSelectionPropertiesBadge = (message) => {
  if (selectionPropertiesBadge) {
    selectionPropertiesBadge.textContent = message;
  }
};

const setSelectionPropertiesStatus = (message) => {
  if (!selectionPropertiesStatus) {
    return;
  }
  if (selectionPropertiesState.file && !selectionPropertiesState.statusUnlocked) {
    selectionPropertiesStatus.textContent = "";
    return;
  }
  selectionPropertiesStatus.textContent = message;
};

const selectionStepContentMap = {
  initial: selectionInitialSettingsCard,
  "select-columns": selectionSelectColumnsCard,
  summary: selectionSummaryCard,
};

const setSelectionActiveStep = (stepKey) => {
  selectionPropertiesState.activeStep = stepKey === "summary" ? "summary" : stepKey === "select-columns" ? "select-columns" : "initial";
  updateSelectionStepperState();
  updateSelectionStepNavigation();
  updateSelectionPropertiesCollapseState();
};

const focusSelectionStep = (stepKey) => {
  setSelectionActiveStep(stepKey);
  const target = selectionStepContentMap[stepKey];
  if (!target) {
    return;
  }
  target.scrollIntoView({ behavior: "smooth", block: "start" });
};

const updateSelectionStepNavigation = () => {
  const isConfigured = isSelectionPropertiesConfigured();
  const isSummaryReady = isSelectionSummaryReady();
  if (selectionStepNextButton) {
    selectionStepNextButton.hidden = !isConfigured || selectionPropertiesState.activeStep === "select-columns";
    selectionStepNextButton.disabled = !isConfigured;
  }
  if (selectionSummaryNextButton) {
    selectionSummaryNextButton.hidden = !isSummaryReady || selectionPropertiesState.activeStep !== "select-columns";
    selectionSummaryNextButton.disabled = !isSummaryReady;
  }
  selectionStepItems.forEach((item) => {
    if (!item) {
      return;
    }
    const stepKey = item.dataset.stepKey ?? "";
    const isClickable = stepKey === "summary" ? isSummaryReady : stepKey === "select-columns" ? isConfigured : stepKey === "initial";
    item.classList.toggle("is-clickable", isClickable);
    item.setAttribute("tabindex", isClickable ? "0" : "-1");
    item.setAttribute("aria-disabled", isClickable ? "false" : "true");
  });
};

const notifyLegacyFlowBlocked = (surface = "this action") => {
  const message = `${surface} is disabled while the selecctionProperties workflow is active. Preprocess, training, and prediction will not run in this mode.`;
  setSelectionPropertiesBadge("Legacy flow blocked");
  setSelectionPropertiesStatus(message);
  setLoadingState(0, "Legacy flow blocked", message, false).catch((error) => {
    console.error(error);
  });
  return true;
};

const populateSelectionListbox = (element, options, placeholder, selectedValue = "", disabled = false) => {
  if (!element) {
    return;
  }
  const normalizedOptions = Array.isArray(options)
    ? options.map((option) => (
      typeof option === "object" && option !== null
        ? {
            value: String(option.value ?? "").trim(),
            label: String(option.label ?? option.value ?? "").trim(),
          }
        : {
            value: String(option ?? "").trim(),
            label: String(option ?? "").trim(),
          }
    )).filter((option) => option.value)
    : [];
  const shouldPreserveOptionOrder = normalizedOptions.some((option) => option.value === clearSelectionIdSentinel);
  const sortedOptions = shouldPreserveOptionOrder
    ? normalizedOptions
    : normalizedOptions.every((option) => option.value === option.label)
      ? sortSelectionValues(normalizedOptions.map((option) => option.value)).map((value) => ({ value, label: value }))
      : normalizedOptions;
  const choicesInstance = selectionChoices.get(element);
  if (choicesInstance) {
    const normalizedSelectedValue = String(selectedValue ?? "").trim();
    const allowedValues = new Set(sortedOptions.map((option) => String(option.value ?? "").trim()));
    choicesInstance.clearChoices();
    choicesInstance.setChoices(
      [
        { value: "", label: placeholder, selected: !allowedValues.has(normalizedSelectedValue), disabled: true, placeholder: true },
        ...sortedOptions.map((optionPayload) => ({
          value: optionPayload.value,
          label: optionPayload.label,
          selected: String(optionPayload.value ?? "").trim() === normalizedSelectedValue,
        })),
      ],
      "value",
      "label",
      true,
    );
    if (allowedValues.has(normalizedSelectedValue)) {
      choicesInstance.setChoiceByValue(normalizedSelectedValue);
    }
    element.disabled = disabled;
    if (disabled) {
      choicesInstance.disable();
    } else {
      choicesInstance.enable();
    }
    element.size = 1;
    return;
  }
  element.innerHTML = "";
  const placeholderOption = document.createElement("option");
  placeholderOption.value = "";
  placeholderOption.textContent = placeholder;
  element.append(placeholderOption);
  sortedOptions.forEach((optionPayload) => {
    const option = document.createElement("option");
    option.value = optionPayload.value;
    option.textContent = optionPayload.label;
    element.append(option);
  });
  element.disabled = disabled;
  const normalizedSelectedValue = String(selectedValue ?? "").trim();
  const allowedValues = new Set(sortedOptions.map((option) => String(option.value ?? "").trim()));
  element.value = allowedValues.has(normalizedSelectedValue) ? normalizedSelectedValue : "";
  const visibleOptionCount = disabled
    ? 1
    : Math.min(Math.max(sortedOptions.length + 1, 5), 10);
  element.size = visibleOptionCount;
};

const renderSelectionPropertiesControls = () => {
  initializeSelectionChoices();
  const isWorkspaceReadonly = Boolean(selectionPropertiesState.workspaceReadonlyLoaded);
  const headers = Array.isArray(selectionPropertiesState.headers)
    ? selectionPropertiesState.headers.map((header) => String(header ?? "").trim()).filter(Boolean)
    : [];
  const hasHeaders = headers.length > 0;
  const isConfigured = isSelectionPropertiesConfigured();
  const targetOptions = sortSelectionValues(headers);
  const longitudeOptions = buildInitialSettingOptions(headers, [
    selectionPropertiesState.targetColumn,
    selectionPropertiesState.latitudeColumn,
    selectionPropertiesState.plantingDateColumn,
    selectionPropertiesState.harvestingDateColumn,
    selectionPropertiesState.soilTextureColumn,
    selectionPropertiesState.soilDepthColumn,
  ]);
  const latitudeOptions = buildInitialSettingOptions(headers, [
    selectionPropertiesState.targetColumn,
    selectionPropertiesState.longitudeColumn,
    selectionPropertiesState.plantingDateColumn,
    selectionPropertiesState.harvestingDateColumn,
    selectionPropertiesState.soilTextureColumn,
    selectionPropertiesState.soilDepthColumn,
  ]);
  const plantingDateOptions = buildInitialSettingOptions(headers, [
    selectionPropertiesState.targetColumn,
    selectionPropertiesState.longitudeColumn,
    selectionPropertiesState.latitudeColumn,
    selectionPropertiesState.harvestingDateColumn,
    selectionPropertiesState.soilTextureColumn,
    selectionPropertiesState.soilDepthColumn,
  ]);
  const harvestingDateOptions = buildInitialSettingOptions(headers, [
    selectionPropertiesState.targetColumn,
    selectionPropertiesState.longitudeColumn,
    selectionPropertiesState.latitudeColumn,
    selectionPropertiesState.plantingDateColumn,
    selectionPropertiesState.soilTextureColumn,
    selectionPropertiesState.soilDepthColumn,
  ]);
  const soilTextureOptions = buildInitialSettingOptions(headers, [
    selectionPropertiesState.targetColumn,
    selectionPropertiesState.longitudeColumn,
    selectionPropertiesState.latitudeColumn,
    selectionPropertiesState.plantingDateColumn,
    selectionPropertiesState.harvestingDateColumn,
    selectionPropertiesState.soilDepthColumn,
  ]);
  const soilDepthOptions = buildInitialSettingOptions(headers, [
    selectionPropertiesState.targetColumn,
    selectionPropertiesState.longitudeColumn,
    selectionPropertiesState.latitudeColumn,
    selectionPropertiesState.plantingDateColumn,
    selectionPropertiesState.harvestingDateColumn,
    selectionPropertiesState.soilTextureColumn,
  ]);
  if (selectionPropertiesPanel) {
    selectionPropertiesPanel.hidden = !(hasHeaders || forceOpenStepperAfterReload);
  }
  if (selectionWorkspaceNameInput) {
    selectionWorkspaceNameInput.value = selectionPropertiesState.workspaceName ?? "";
    selectionWorkspaceNameInput.disabled = isWorkspaceReadonly;
  }
  if (selectionPropertiesFileName) {
    selectionPropertiesFileName.textContent = selectionPropertiesState.sourceName
      ? `Selected file: ${selectionPropertiesState.sourceName}`
      : "No file selected";
  }
  if (selectionPropertiesUploadTrigger) {
    selectionPropertiesUploadTrigger.classList.toggle("is-disabled", isWorkspaceReadonly);
    selectionPropertiesUploadTrigger.setAttribute("aria-disabled", isWorkspaceReadonly ? "true" : "false");
    selectionPropertiesUploadTrigger.title = isWorkspaceReadonly ? "This workspace was loaded from a saved card and the source file cannot be changed." : "Load workbook";
    selectionPropertiesUploadTrigger.disabled = isWorkspaceReadonly;
  }
  populateSelectionListbox(
    selectionTargetVariableSelect,
    targetOptions,
    hasHeaders ? "Select target variable" : "Upload a workbook first",
    selectionPropertiesState.targetColumn,
    !hasHeaders || isWorkspaceReadonly,
  );
  populateSelectionListbox(
    selectionLongitudeColumnSelect,
    longitudeOptions,
    hasHeaders ? "Select longitude column" : "Select target variable first",
    selectionPropertiesState.longitudeColumn,
    (!hasHeaders || !selectionPropertiesState.targetColumn) || isWorkspaceReadonly,
  );
  populateSelectionListbox(
    selectionLatitudeColumnSelect,
    latitudeOptions,
    hasHeaders ? "Select latitude column" : "Select target variable first",
    selectionPropertiesState.latitudeColumn,
    (!hasHeaders || !selectionPropertiesState.targetColumn) || isWorkspaceReadonly,
  );
  populateSelectionListbox(
    selectionPlantingDateColumnSelect,
    plantingDateOptions,
    hasHeaders ? "Select Date of Plating" : "Select target variable first",
    selectionPropertiesState.plantingDateColumn,
    (!hasHeaders || !selectionPropertiesState.targetColumn) || isWorkspaceReadonly,
  );
  populateSelectionListbox(
    selectionHarvestingDateColumnSelect,
    harvestingDateOptions,
    hasHeaders ? "Select Date of Harvesting" : "Select target variable first",
    selectionPropertiesState.harvestingDateColumn,
    (!hasHeaders || !selectionPropertiesState.targetColumn) || isWorkspaceReadonly,
  );
  populateSelectionListbox(
    selectionSoilTextureColumnSelect,
    soilTextureOptions,
    hasHeaders ? "Select Soil type/texture" : "Select target variable first",
    selectionPropertiesState.soilTextureColumn,
    (!hasHeaders || !selectionPropertiesState.targetColumn) || isWorkspaceReadonly,
  );
  populateSelectionListbox(
    selectionSoilDepthColumnSelect,
    soilDepthOptions,
    hasHeaders ? "Select Soil Depth (cm)" : "Select target variable first",
    selectionPropertiesState.soilDepthColumn,
    (!hasHeaders || !selectionPropertiesState.targetColumn) || isWorkspaceReadonly,
  );
  updateSelectionFieldRequiredState(null, selectionTargetVariableSelect, hasHeaders && !selectionPropertiesState.targetColumn);
  updateSelectionFieldRequiredState(null, selectionLongitudeColumnSelect, hasHeaders && !selectionPropertiesState.longitudeColumn);
  updateSelectionFieldRequiredState(null, selectionLatitudeColumnSelect, hasHeaders && !selectionPropertiesState.latitudeColumn);
  updateSelectionFieldRequiredState(null, selectionPlantingDateColumnSelect, hasHeaders && !selectionPropertiesState.plantingDateColumn);
  updateSelectionFieldRequiredState(null, selectionHarvestingDateColumnSelect, hasHeaders && !selectionPropertiesState.harvestingDateColumn);
  updateSelectionFieldRequiredState(null, selectionSoilTextureColumnSelect, hasHeaders && !selectionPropertiesState.soilTextureColumn);
  updateSelectionFieldRequiredState(null, selectionSoilDepthColumnSelect, hasHeaders && !selectionPropertiesState.soilDepthColumn);
  if (!isConfigured && hasHeaders) {
    setSelectionPropertiesStatus(
      "Complete the target variable, longitude column, latitude column, Date of Plating, Date of Harvesting, Soil type/texture, and Soil Depth (cm) selections to enable Select Columns",
    );
  }
  renderSelectionWorkbench();
};

const maybeAutoSelectCoordinateColumns = () => {
  const headers = Array.isArray(selectionPropertiesState.headers)
    ? selectionPropertiesState.headers.map((header) => String(header ?? "").trim()).filter(Boolean)
    : [];
  if (!headers.length) {
    return;
  }
  const reserved = new Set([String(selectionPropertiesState.targetColumn ?? "").trim()].filter(Boolean));
  [
    "longitudeColumn",
    "latitudeColumn",
    "plantingDateColumn",
    "harvestingDateColumn",
    "soilTextureColumn",
    "soilDepthColumn",
  ].forEach((stateKey) => {
    autoSelectInitialSettingColumn(stateKey, headers, [...reserved]);
    const selectedValue = String(selectionPropertiesState[stateKey] ?? "").trim();
    if (selectedValue) {
      reserved.add(selectedValue);
    }
  });
};

const buildInitialSettingOptions = (headers, excludedValues = [], searchValue = "") =>
  filterSelectionValues(
    buildSelectableColumnOptions(headers, excludedValues),
    searchValue,
  );

const normalizeSelectionHeaderKey = (value = "") =>
  String(value ?? "")
    .toLowerCase()
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/[^a-z0-9]+/g, " ")
    .trim();

const selectionAutoMatchPatterns = {
  longitudeColumn: [
    ["longitude"],
    ["gps", "longitude"],
    ["longitud"],
    ["lon"],
    ["x", "coordinate"],
  ],
  latitudeColumn: [
    ["latitude"],
    ["gps", "latitude"],
    ["latitud"],
    ["lat"],
    ["y", "coordinate"],
  ],
  plantingDateColumn: [
    ["date", "planting"],
    ["planting", "date"],
    ["date", "plating"],
    ["plating", "date"],
    ["sowing", "date"],
    ["fecha", "siembra"],
    ["planting"],
    ["plating"],
  ],
  harvestingDateColumn: [
    ["date", "harvesting"],
    ["harvesting", "date"],
    ["harvest", "date"],
    ["date", "harvest"],
    ["fecha", "cosecha"],
    ["harvesting"],
    ["harvest"],
  ],
  soilTextureColumn: [
    ["soil", "texture"],
    ["soil", "type"],
    ["soil", "type", "texture"],
    ["soil", "class"],
    ["textura", "suelo"],
    ["tipo", "suelo"],
  ],
  soilDepthColumn: [
    ["soil", "depth"],
    ["depth", "cm"],
    ["soil", "depth", "cm"],
    ["profundidad", "suelo"],
    ["root", "depth"],
  ],
};

const scoreSelectionAutoMatch = (header, patterns) => {
  const normalized = normalizeSelectionHeaderKey(header);
  if (!normalized) {
    return -1;
  }
  let bestScore = -1;
  patterns.forEach((tokens, index) => {
    if (!tokens.every((token) => normalized.includes(token))) {
      return;
    }
    let score = 100 - index * 5;
    tokens.forEach((token) => {
      if (normalized === token) {
        score += 60;
      }
      if (normalized.startsWith(token)) {
        score += 15;
      }
    });
    if (bestScore < score) {
      bestScore = score;
    }
  });
  return bestScore;
};

const autoSelectInitialSettingColumn = (stateKey, headers, excludedValues = []) => {
  const currentValue = String(selectionPropertiesState[stateKey] ?? "").trim();
  if (currentValue && headers.includes(currentValue)) {
    return;
  }
  const patterns = selectionAutoMatchPatterns[stateKey] ?? [];
  if (!patterns.length) {
    return;
  }
  const excluded = new Set(
    excludedValues
      .map((value) => String(value ?? "").trim())
      .filter(Boolean),
  );
  const ranked = headers
    .filter((header) => !excluded.has(header))
    .map((header) => ({ header, score: scoreSelectionAutoMatch(header, patterns) }))
    .filter((entry) => entry.score >= 0)
    .sort((left, right) => right.score - left.score || left.header.localeCompare(right.header, undefined, { sensitivity: "base", numeric: true }));
  if (!ranked.length) {
    return;
  }
  selectionPropertiesState[stateKey] = ranked[0].header;
};


const resetSelectionColumnsFlow = () => {
  selectionPropertiesState.identifierConfirmed = false;
  selectionPropertiesState.categoricalConfirmed = false;
  selectionPropertiesState.quantitativeConfirmed = false;
  selectionPropertiesState.columnClassificationConfirmed = false;
  selectionPropertiesState.summaryReady = false;
  selectionPropertiesState.summaryExecuting = false;
  selectionPropertiesState.statusUnlocked = false;
  selectionPropertiesState.collapsed = false;
  selectionPropertiesState.latestSummaryRun = null;
  selectionPropertiesState.identifierColumns = [];
  selectionPropertiesState.columnAssignments = {};
  selectionPropertiesState.enabledClassifierColumns = [];
  selectionPropertiesState.classifierListScrollTop = 0;
  selectionPropertiesState.categoricalColumns = [];
  selectionPropertiesState.quantitativeColumns = [];
  selectionPropertiesState.noDefinedColumns = [];
  selectionPropertiesState.highlightedIdentifierColumn = "";
  selectionPropertiesState.highlightedCategoricalColumn = "";
  selectionPropertiesState.highlightedQuantitativeColumn = "";
  selectionPropertiesState.identifierListScrollTop = 0;
  selectionPropertiesState.categoricalListScrollTop = 0;
  selectionPropertiesState.quantitativeListScrollTop = 0;
  selectionPropertiesState.activeStep = "initial";
  setSelectionActiveStep("initial");
};

const applySelectionPropertiesPreview = async () => {
  if (!selectionPropertiesState.file) {
    return;
  }
  const { targetColumn, latitudeColumn, longitudeColumn } = selectionPropertiesState;
  if (!targetColumn || !latitudeColumn || !longitudeColumn) {
    setSelectionPropertiesStatus(
      "Select the target variable, longitude column, and latitude column to validate the workbook setup.",
    );
    return;
  }
  await setLoadingState(
    22,
    "Validating workbook setup",
    `Checking ${selectionPropertiesState.sourceName} with ${latitudeColumn} and ${longitudeColumn}.`,
    false,
  );
  const payload = await loadSelectionPropertiesPreview(selectionPropertiesState.file, {
    targetColumn,
    latitudeColumn,
    longitudeColumn,
  });
  const geojson = validateFeatureCollection(payload.geojson);
  if (payload && typeof payload.column_profiles === "object" && payload.column_profiles !== null) {
    selectionPropertiesState.columnProfiles = payload.column_profiles;
  }
  selectionPropertiesState.mappedFeatureCount = Number(payload.count ?? geojson.features.length ?? 0);
  const nextActiveStep = selectionPropertiesState.activeStep === "select-columns" && hasAllRequiredInitialSelections()
    ? "select-columns"
    : selectionPropertiesState.activeStep === "summary" && isSelectionSummaryReady()
      ? "summary"
      : "initial";
  recalculateSelectionPropertiesGroups();
  setSelectionActiveStep(nextActiveStep);
  renderSelectionWorkbench();
  datasetStore.original = null;
  datasetStore.training = null;
  datasetStore.prediction = null;
  clearMarkers();
  renderEmptyStats();
  updateDataViewTabs();
  setSelectionPropertiesBadge("");
  setSelectionActiveStep(nextActiveStep);
  updateSelectionStepperState();
  updateSelectionStepNavigation();
  if (selectionStepNextButton && hasAllRequiredInitialSelections()) {
    selectionStepNextButton.hidden = false;
    selectionStepNextButton.disabled = false;
  }
  setSelectionPropertiesStatus("");
  await setLoadingState(
    100,
    "",
    "",
    false,
  );
};

const handleSelectionPropertiesUpload = async (file) => {
  const preservedWorkspaceName = String(selectionWorkspaceNameInput?.value ?? selectionPropertiesState.workspaceName ?? "");
  restoreLoadingPanelHome();
  resetLoadedResults();
  resetSelectionPropertiesState();
  selectionPropertiesState.workspaceName = preservedWorkspaceName;
  selectionPropertiesState.file = file;
  selectionPropertiesState.sourceName = file.name;
  selectionPropertiesState.statusUnlocked = false;
  selectionPropertiesState.collapsed = false;
  selectionPropertiesState.latestSummaryRun = null;
  setSelectionPropertiesBadge("Reading workbook");
  setSelectionPropertiesStatus(`Loading columns from ${file.name}.`);
  await setLoadingState(8, "Reading workbook", `Loading column names from ${file.name}.`, false);
  const payload = await loadSelectionPropertiesMetadata(file);
  selectionPropertiesState.headers = Array.isArray(payload.headers) ? payload.headers : [];
  selectionPropertiesState.columnProfiles = payload && typeof payload.column_profiles === "object" && payload.column_profiles !== null
    ? payload.column_profiles
    : {};
  selectionPropertiesState.rowCount = Number(payload.row_count ?? 0);
  selectionPropertiesState.attributeCount = Number(payload.attribute_count ?? selectionPropertiesState.headers.length);
  selectionPropertiesState.sourceName = payload.source_name ?? file.name;
  recalculateSelectionPropertiesGroups();
  maybeAutoSelectCoordinateColumns();
  recalculateSelectionPropertiesGroups();
  selectionPropertiesState.activeStep = "initial";
  setSelectionActiveStep("initial");
  renderSelectionPropertiesControls();
  setSelectionPropertiesBadge("Awaiting selections");
  setSelectionPropertiesStatus(
    "Complete the target variable, longitude column, latitude column, Date of Plating, Date of Harvesting, Soil type/texture, and Soil Depth (cm) selections to enable Select Columns",
  );
  await setLoadingState(
    0,
    "Awaiting initial settings",
    "Select the target variable, longitude, latitude, Date of Plating, Date of Harvesting, Soil type/texture, and Soil Depth (cm) columns in the new stepper.",
    false,
  );
};

const syncSelectionPropertiesSelection = async () => {
  const previousSelectionSignature = [
    selectionPropertiesState.targetColumn,
    selectionPropertiesState.longitudeColumn,
    selectionPropertiesState.latitudeColumn,
    selectionPropertiesState.plantingDateColumn,
    selectionPropertiesState.harvestingDateColumn,
    selectionPropertiesState.soilTextureColumn,
    selectionPropertiesState.soilDepthColumn,
  ].join("||");
  selectionPropertiesState.targetColumn = selectionTargetVariableSelect?.value?.trim() ?? "";
  selectionPropertiesState.longitudeColumn = selectionLongitudeColumnSelect?.value?.trim() ?? selectionPropertiesState.longitudeColumn ?? "";
  selectionPropertiesState.latitudeColumn = selectionLatitudeColumnSelect?.value?.trim() ?? selectionPropertiesState.latitudeColumn ?? "";
  selectionPropertiesState.plantingDateColumn = selectionPlantingDateColumnSelect?.value?.trim() ?? selectionPropertiesState.plantingDateColumn ?? "";
  selectionPropertiesState.harvestingDateColumn = selectionHarvestingDateColumnSelect?.value?.trim() ?? selectionPropertiesState.harvestingDateColumn ?? "";
  selectionPropertiesState.soilTextureColumn = selectionSoilTextureColumnSelect?.value?.trim() ?? selectionPropertiesState.soilTextureColumn ?? "";
  selectionPropertiesState.soilDepthColumn = selectionSoilDepthColumnSelect?.value?.trim() ?? selectionPropertiesState.soilDepthColumn ?? "";

  const uniqueSelections = [
    "targetColumn",
    "longitudeColumn",
    "latitudeColumn",
    "plantingDateColumn",
    "harvestingDateColumn",
    "soilTextureColumn",
    "soilDepthColumn",
  ];
  const seenColumns = new Set();
  uniqueSelections.forEach((key) => {
    const value = String(selectionPropertiesState[key] ?? "").trim();
    if (!value) {
      return;
    }
    if (seenColumns.has(value)) {
      selectionPropertiesState[key] = "";
      return;
    }
    seenColumns.add(value);
  });

  const nextSelectionSignature = [
    selectionPropertiesState.targetColumn,
    selectionPropertiesState.longitudeColumn,
    selectionPropertiesState.latitudeColumn,
    selectionPropertiesState.plantingDateColumn,
    selectionPropertiesState.harvestingDateColumn,
    selectionPropertiesState.soilTextureColumn,
    selectionPropertiesState.soilDepthColumn,
  ].join("||");
  if (previousSelectionSignature !== nextSelectionSignature) {
    resetSelectionColumnsFlow();
  }
  maybeAutoSelectCoordinateColumns();
  recalculateSelectionPropertiesGroups();
  renderSelectionPropertiesControls();
  if (
    selectionPropertiesState.targetColumn &&
    selectionPropertiesState.longitudeColumn &&
    selectionPropertiesState.latitudeColumn &&
    selectionPropertiesState.plantingDateColumn &&
    selectionPropertiesState.harvestingDateColumn &&
    selectionPropertiesState.soilTextureColumn &&
    selectionPropertiesState.soilDepthColumn
  ) {
    await applySelectionPropertiesPreview();
    return;
  }
  setSelectionPropertiesBadge("Awaiting selections");
  setSelectionPropertiesStatus(
    "Complete the target variable, longitude column, latitude column, Date of Plating, Date of Harvesting, Soil type/texture, and Soil Depth (cm) selections to enable Select Columns",
  );
};

const renameSavedModel = async (modelId, displayName) => {
  const response = await fetch(`/api/models/${encodeURIComponent(modelId)}/name`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ display_name: displayName }),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.error ?? "The model name could not be saved.");
  }
  return payload;
};

const promptForGeneratedModelNameIfNeeded = async () => {};

const fetchSavedWorkspace = async (modelId) => {
  const response = await fetch(`/api/models/${encodeURIComponent(modelId)}/workspace`);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.error ?? "The saved workspace could not be loaded.");
  }
  return payload;
};

const fetchWorkspaceDatasetGeojson = async (dataset) => {
  const inlineGeojson = dataset?.geojson ? validateFeatureCollection(dataset.geojson) : null;
  const geojsonUrl = String(dataset?.geojson_url ?? "").trim();
  if (!geojsonUrl) {
    return inlineGeojson;
  }
  try {
    const response = await fetch(geojsonUrl);
    const payload = await response.json().catch(() => null);
    if (!response.ok || !payload) {
      if (inlineGeojson) {
        return inlineGeojson;
      }
      throw new Error("The saved workspace dataset geojson could not be loaded.");
    }
    return validateFeatureCollection(payload);
  } catch (error) {
    if (inlineGeojson) {
      return inlineGeojson;
    }
    throw error;
  }
};

const loadWorkspaceSourceFile = async (workspacePayload) => {
  const sourceUrl = String(workspacePayload?.source_workbook?.url ?? "").trim();
  const sourceName = String(
    workspacePayload?.source_workbook?.name
      ?? workspacePayload?.selection_state?.sourceName
      ?? workspacePayload?.selection_summary?.source_name
      ?? "workspace.xlsx",
  ).trim() || "workspace.xlsx";
  if (!sourceUrl) {
    return null;
  }
  const response = await fetch(sourceUrl);
  if (!response.ok) {
    throw new Error("The saved workspace source workbook could not be downloaded.");
  }
  const blob = await response.blob();
  return new File([blob], sourceName, {
    type: blob.type || "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  });
};

const loadSavedWorkspace = async (modelId) => {
  await setLoadingState(8, "Loading workspace", "Reading the saved workspace definition and datasets.", true);
  const workspacePayload = await fetchSavedWorkspace(modelId);
  let workspaceFile = null;
  try {
    workspaceFile = await loadWorkspaceSourceFile(workspacePayload);
  } catch (error) {
    console.error(error);
  }

  resetLoadedResults();
  resetPredictionControls();
  resetSelectionPropertiesState();

  const selectionState = workspacePayload?.selection_state ?? {};
  const selectionSummary = workspacePayload?.selection_summary ?? {};
  selectionPropertiesState.file = workspaceFile;
  selectionPropertiesState.workspaceName = String(
    workspacePayload?.workspace_name
      ?? selectionState.workspaceName
      ?? selectionSummary.workspace_name
      ?? "",
  ).trim();
  selectionPropertiesState.sourceName = String(
    selectionState.sourceName ?? selectionSummary.source_name ?? workspacePayload?.source_workbook?.name ?? "",
  ).trim();
  selectionPropertiesState.headers = Array.isArray(selectionState.headers) ? selectionState.headers : [];
  selectionPropertiesState.columnProfiles = selectionState.columnProfiles && typeof selectionState.columnProfiles === "object"
    ? selectionState.columnProfiles
    : {};
  selectionPropertiesState.rowCount = Number(selectionState.rowCount ?? selectionSummary.row_count ?? 0);
  selectionPropertiesState.attributeCount = Number(selectionState.attributeCount ?? selectionSummary.attribute_count ?? selectionPropertiesState.headers.length ?? 0);
  selectionPropertiesState.targetColumn = String(selectionState.targetColumn ?? "").trim();
  selectionPropertiesState.longitudeColumn = String(selectionState.longitudeColumn ?? "").trim();
  selectionPropertiesState.latitudeColumn = String(selectionState.latitudeColumn ?? "").trim();
  selectionPropertiesState.plantingDateColumn = String(selectionState.plantingDateColumn ?? "").trim();
  selectionPropertiesState.harvestingDateColumn = String(selectionState.harvestingDateColumn ?? "").trim();
  selectionPropertiesState.soilTextureColumn = String(selectionState.soilTextureColumn ?? "").trim();
  selectionPropertiesState.soilDepthColumn = String(selectionState.soilDepthColumn ?? "").trim();
  selectionPropertiesState.identifierColumns = Array.isArray(selectionState.identifierColumns) ? selectionState.identifierColumns : [];
  selectionPropertiesState.identifierConfirmed = Boolean(selectionState.identifierConfirmed ?? true);
  selectionPropertiesState.categoricalColumns = Array.isArray(selectionState.categoricalColumns) ? selectionState.categoricalColumns : [];
  selectionPropertiesState.quantitativeColumns = Array.isArray(selectionState.quantitativeColumns) ? selectionState.quantitativeColumns : [];
  selectionPropertiesState.noDefinedColumns = Array.isArray(selectionState.noDefinedColumns) ? selectionState.noDefinedColumns : [];
  selectionPropertiesState.columnAssignments = selectionState.columnAssignments && typeof selectionState.columnAssignments === "object"
    ? selectionState.columnAssignments
    : {};
  selectionPropertiesState.enabledClassifierColumns = Array.isArray(selectionState.enabledClassifierColumns)
    ? selectionState.enabledClassifierColumns
    : [];
  selectionPropertiesState.columnClassificationConfirmed = Boolean(selectionState.columnClassificationConfirmed ?? true);
  selectionPropertiesState.summaryReady = Boolean(selectionState.summaryReady ?? true);
  selectionPropertiesState.statusUnlocked = true;
  selectionPropertiesState.previewOriginalLoaded = true;
  selectionPropertiesState.workspaceReadonlyLoaded = true;
  selectionPropertiesState.collapsed = true;
  selectionPropertiesState.activeStep = "initial";
  selectionPropertiesState.latestSummaryRun = null;

  const originalDataset = workspacePayload?.original_dataset ?? null;
  const trainingDataset = workspacePayload?.training_dataset ?? null;
  const topGermplasmDataset = TOP_GERMPLASM_ENABLED ? workspacePayload?.top_germplasm_dataset ?? null : null;

  const [originalGeojson, trainingGeojson, topGermplasmGeojson] = await Promise.all([
    fetchWorkspaceDatasetGeojson(originalDataset),
    fetchWorkspaceDatasetGeojson(trainingDataset),
    TOP_GERMPLASM_ENABLED ? fetchWorkspaceDatasetGeojson(topGermplasmDataset) : Promise.resolve(null),
  ]);

  if (originalGeojson) {
    selectionPropertiesState.mappedFeatureCount = Number(originalGeojson.features.length ?? 0);
    registerDataset(
      "original",
      originalGeojson,
      originalDataset?.source_name ?? selectionPropertiesState.sourceName ?? "phase03.xlsx",
      "original",
      originalDataset?.summary ?? null,
    );
  }
  if (trainingGeojson) {
    registerDataset(
      "training",
      trainingGeojson,
      trainingDataset?.source_name ?? selectionPropertiesState.sourceName ?? "phase04.xlsx",
      "automatic",
      trainingDataset?.summary ?? null,
    );
  }
  datasetStore.prediction = null;
  datasetStore.top_germplasm = null;

  selectedSavedModelId = modelId;
  renderSelectionPropertiesControls();
  setSelectionActiveStep(selectionPropertiesState.activeStep);
  renderSavedModels(savedModelsCache);
  syncSelectedModelControl();
  if (trainingDataset?.summary) {
    primePredictionBridgeFromTraining(workspaceFile, trainingDataset.summary);
  }
  await showDatasetInView("original", { force: true });
  setSelectionPropertiesBadge("Workspace loaded");
  setSelectionPropertiesStatus(`Workspace ${selectionPropertiesState.workspaceName || modelId} loaded.`);
  await setLoadingState(100, "Workspace loaded", `Original Data and Training were restored for ${selectionPropertiesState.workspaceName || modelId}. High-Potential Sites is ready, but no prediction map is loaded until you run a new prediction.`, true);
};

const getTrainingBridgeTemplateWorkbookPath = (summary) => {
  const phase06Path = String(summary?.phase06_xlsx ?? "").trim();
  if (phase06Path) {
    return phase06Path;
  }
  const taskReport = Array.isArray(summary?.task_report) ? summary.task_report : [];
  const phase2Task = taskReport.find((task) => String(task?.phase ?? "").trim() === "phase2");
  const phase2Output = String(phase2Task?.output_file ?? "").trim();
  if (phase2Output) {
    return phase2Output;
  }
  return String(summary?.input_workbook ?? "").trim();
};

const primePredictionBridgeFromTraining = (file, summary) => {
  const trainingGeojson = datasetStore.training?.geojson;
  const modelId = String(summary?.prediction_model_id ?? summary?.phase_analysis_model_id ?? "").trim();
  if (!file || !trainingGeojson || !modelId) {
    predictionBridgeState = null;
    return;
  }
  const names = Array.from(
    new Set(
      (trainingGeojson.features ?? [])
        .map((feature) => String(feature?.properties?.Name ?? "").trim())
        .filter(Boolean),
    ),
  ).sort((left, right) => left.localeCompare(right));
  if (!names.length) {
    predictionBridgeState = null;
    return;
  }
  predictionBridgeState = {
    isAvailable: true,
    file,
    sourceFile: file,
    templateWorkbookPath: getTrainingBridgeTemplateWorkbookPath(summary),
    modelId,
    modelDisplayName: String(summary?.prediction_model_display_name ?? "").trim(),
    sourceGeojson: trainingGeojson,
    sourceName: datasetStore.training?.sourceName ?? file.name,
    summary,
    germplasmNames: names,
    selectedNames: [names[0]],
    plantingDate: deriveCurrentYearForecastDate(getFirstOriginalPropertyValue("Date of planting")),
    harvestingDate: deriveCurrentYearForecastDate(getFirstOriginalPropertyValue("Date_of_harvesting")),
    hydrated: false,
    autoRunTriggered: false,
  };
};

const hydratePredictionBridge = async () => {
  if (!predictionBridgeState?.isAvailable) {
    return;
  }
  if (!predictionBridgeState.hydrated) {
    selectedSavedModelId = predictionBridgeState.modelId;
    selectedClimateScope = "regional_manual";
    if (forecastPlantingDateInput) {
      forecastPlantingDateInput.value = predictionBridgeState.plantingDate ?? "";
    }
    if (forecastHarvestingDateInput) {
      forecastHarvestingDateInput.value = predictionBridgeState.harvestingDate ?? "";
    }
    availableGermplasmNames = [];
    availableGermplasmProfilesByName = {};
    selectedGermplasmNames = new Set();
    predictionBridgeState.selectedNames = [];
    predictionBridgeState.hydrated = true;
  }
  if (germplasmSelectionPanel) {
    germplasmSelectionPanel.hidden = false;
  }
  if (germplasmSelectionHelp) {
    germplasmSelectionHelp.textContent =
      "Choose Explor Original Data to inspect the original workspace germplasm list, or Load Data to Predict to read a new workbook before running High-Potential Sites.";
  }
  updateGermplasmSelectionTitle();
  syncSelectedModelControl();
  updateForecastDatePanel();
  renderGermplasmSelectionList();
};

const loadPredictionGermplasmList = async (file, { sourceLabel = "workbook", mode = "uploaded" } = {}) => {
  predictionGermplasmSourceMode = mode;
  updatePredictionSourceButtons();
  updateGermplasmSelectionTitle();
  pendingSavedModelFile = file;
  await clearDataset("prediction");
  resetPreprocessValidationState();
  await setLoadingState(
    8,
    "Reading workbook",
    `Loading distinct germplasm names from ${sourceLabel} before running the selected model.`,
  );
  const payload = await loadGermplasmOptions(file, { mode });
  availableGermplasmNames = Array.isArray(payload.germplasm_names) ? payload.germplasm_names : [];
  availableGermplasmProfilesByName = payload?.germplasm_profiles_by_name && typeof payload.germplasm_profiles_by_name === "object"
    ? payload.germplasm_profiles_by_name
    : {};
  availablePredictionIdFields = getPredictionIdFieldCandidatesFromPayload(payload);
  selectedPredictionIdField = normalizeSelectedPredictionIdHeader(
    payload?.selected_id_header || payload?.default_selected_id_header || "",
  );
  availablePredictionIdValuesByName = payload?.germplasm_id_values_by_name && typeof payload.germplasm_id_values_by_name === "object"
    ? payload.germplasm_id_values_by_name
    : {};
  selectedGermplasmNames = new Set();
  if (predictionBridgeState?.isAvailable && mode === "original") {
    predictionBridgeState.germplasmNames = [...availableGermplasmNames];
    predictionBridgeState.germplasmProfilesByName = availableGermplasmProfilesByName;
    predictionBridgeState.selectedNames = [];
  }
  if (germplasmSelectionPanel) {
    germplasmSelectionPanel.hidden = false;
  }
  if (germplasmSelectionHelp) {
    germplasmSelectionHelp.textContent =
      `${payload.count ?? availableGermplasmNames.length} distinct germplasm names were loaded from ${payload.source_name ?? sourceLabel}. If a selected Name contains repeated rows, High-Potential Sites will use the planting and harvesting dates from the workbook and evaluate each internal profile before keeping the profiles above the germplasm target mean.`;
  }
  refreshGermplasmSelectionIdPicker(payload);
  renderGermplasmSelectionList();
  await setLoadingState(
    0,
    "Ready to run",
    "Choose a germplasm from the list and then click Run to start the prediction flow using the workbook planting and harvesting dates.",
    false,
  );
};

const applyPredictionIdFieldSelection = async (requestedHeader = String(predictionIdColumnSelect?.value ?? "").trim()) => {
  const selectedHeader = String(requestedHeader ?? "").trim();
  if (!selectedHeader || !pendingSavedModelFile) {
    updatePredictionIdModalAcceptState();
    return;
  }
  await setLoadingState(
    10,
    "Loading id field",
    `Reading ${selectedHeader} from the uploaded workbook to annotate the germplasm list.`,
    true,
  );
  const payload = await loadGermplasmOptions(pendingSavedModelFile, {
    selectedIdHeader: selectedHeader,
    mode: predictionGermplasmSourceMode,
  });
  selectedPredictionIdField = normalizeSelectedPredictionIdHeader(selectedHeader);
  availableGermplasmNames = Array.isArray(payload.germplasm_names) ? payload.germplasm_names : [];
  availableGermplasmProfilesByName = payload?.germplasm_profiles_by_name && typeof payload.germplasm_profiles_by_name === "object"
    ? payload.germplasm_profiles_by_name
    : {};
  availablePredictionIdValuesByName = payload?.germplasm_id_values_by_name && typeof payload.germplasm_id_values_by_name === "object"
    ? payload.germplasm_id_values_by_name
    : {};
  selectedGermplasmNames = new Set();
  refreshGermplasmSelectionIdPicker(payload);
  renderGermplasmSelectionList();
  closePredictionIdModal();
  await setLoadingState(
    0,
    "Ready to run",
    "Choose a germplasm from the list and then click Run to start the prediction flow using the workbook planting and harvesting dates.",
    false,
  );
};

const continuePipelineJob = async (continueUrl) => {
  if (legacyPipelineDisabled) {
    throw new Error("The legacy prediction continuation flow is disabled while selecctionProperties is active.");
  }
  const response = await fetch(continueUrl, { method: "POST" });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.error ?? "The pipeline could not continue after preprocess validation.");
  }
  return payload;
};

const pollPipelineStatus = async (statusUrl, jobContext = {}) => {
  let activeStatusUrl = statusUrl;
  let consecutiveFailures = 0;
  while (true) {
    await sleep(consecutiveFailures ? Math.min(PIPELINE_POLL_MAX_DELAY_MS, PIPELINE_POLL_BASE_DELAY_MS * 2 ** consecutiveFailures) : PIPELINE_POLL_BASE_DELAY_MS);
    let response;
    try {
      response = await fetch(activeStatusUrl, { method: "GET" });
    } catch (error) {
      consecutiveFailures += 1;
      await setLoadingState(
        Number(jobContext.lastPercent ?? 12),
        "Reconnecting to pipeline",
        `The connection dropped while processing ${jobContext.sourceName ?? "the uploaded workbook"}. Retrying (${consecutiveFailures})...`,
      );
      continue;
    }
    const payload = await response.json().catch(() => ({}));
    const progress = payload?.progress ?? {};
    const status = payload?.status ?? progress?.status ?? "running";
    const percent = Number(progress?.percent ?? jobContext.lastPercent ?? 10);
    const fallbackProgress = getFallbackPipelineProgress(jobContext.workflowMode ?? "training");
    const stage = progress?.stage ?? fallbackProgress.stage;
    const message = progress?.message ?? fallbackProgress.message;
    jobContext.lastPercent = percent;
    jobContext.lastStage = stage;
    jobContext.lastMessage = message;
    await setLoadingState(percent, stage, message);

    if (response.ok) {
      consecutiveFailures = 0;
    }

    if (
      response.ok &&
      !jobContext.predictionMode &&
      !jobContext.preprocessOriginalRendered &&
      payload?.preprocess_geojson
    ) {
      const renderedPreprocess = await renderPreprocessOriginalMapFromPayload(
        payload,
        jobContext.sourceName ?? "the uploaded workbook",
      );
      if (renderedPreprocess) {
        jobContext.preprocessOriginalRendered = true;
      }
    }

    if (status === "completed") {
      clearActivePipelineJob();
      return payload;
    }
    if (status === "paused") {
      if (!jobContext.predictionMode) {
        await renderPreprocessOriginalMapFromPayload(
          payload,
          jobContext.sourceName ?? "the uploaded workbook",
        );
      }
      if (!preprocessValidationEnabled && payload?.continue_url) {
        await setLoadingState(
          Math.max(percent, 54),
          "Continuing after preprocess",
          "The preprocess output has been mapped in Original Data. Continuing automatically with the downstream pipeline.",
        );
        const continuePayload = await continuePipelineJob(payload.continue_url);
        const continuedStatusUrl = continuePayload?.status_url;
        if (!continuedStatusUrl) {
          clearActivePipelineJob();
          throw new Error("The pipeline did not return a valid status URL when continuing automatically.");
        }
        activeStatusUrl = continuedStatusUrl;
        persistActivePipelineJob({
          jobId: continuePayload?.job_id ?? payload?.job_id ?? "",
          statusUrl: continuedStatusUrl,
          sourceName: jobContext.sourceName ?? "the uploaded workbook",
          state: "running",
        });
        consecutiveFailures = 0;
        continue;
      }
      rememberPausedPreprocessPayload(payload);
      return payload;
    }
    if (!response.ok) {
      if (TRANSIENT_PIPELINE_STATUS_CODES.has(response.status) && status !== "error") {
        consecutiveFailures += 1;
        await setLoadingState(
          percent,
          "Reconnecting to pipeline",
          `The connection to the local pipeline was interrupted. Retrying (${consecutiveFailures})...`,
        );
        continue;
      }
      clearActivePipelineJob();
      throw new Error(payload.error ?? message ?? "The pipeline could not process the uploaded file.");
    }
    if (status === "error") {
      clearActivePipelineJob();
      throw new Error(payload.error ?? message ?? "The pipeline could not process the uploaded file.");
    }
  }
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

const getActiveDatasetSummary = () => datasetStore[activeDataViewTab]?.summary ?? null;

const SUMMARY_LOG_DESCRIPTIONS = {
  "Input rows": "Total rows received by cimmyt_app/preprocess before any cleaning or exclusions.",
  "Quality output rows": "Rows that remain after the preprocess quality checks and exclusions.",
  "Climate exportable rows": "Rows that still have enough information to continue into the climate enrichment stage.",
  "Phase02 source rows": "Rows passed into phase02 before climate joins and window calculations are written back.",
  "Climate unique queries": "Total unique climate query keys available in the loaded cache after this run.",
  "Name updates": "Rows whose germplasm naming was normalized or harmonized during preprocess.",
  "Deleted by name rule": "Rows removed because the preprocess naming rules marked them as invalid or deletable.",
  "Missing yield": "Rows excluded because yield information needed by preprocess was missing.",
  "Rank blank with zero yield": "Rows excluded because rank was blank while yield resolved to zero.",
  "Wrong coordinates": "Rows excluded because the geographic coordinates were invalid, implausible, or unusable.",
  "Source rows": "Rows considered by the climate stage before any climate-specific filtering is applied.",
  "Climate input rows": "Rows exported to climate processing with valid date windows and coordinates.",
  "Skipped missing climate fields": "Rows skipped in the climate stage because required date or coordinate fields were incomplete.",
  "Matched rows": "Rows that successfully received climate outputs and were joined back into the preprocess dataset.",
  "Unmatched rows": "Rows that reached the climate stage but did not receive a matching climate result.",
  "Expanded row count": "Extra rows created by locality or projection expansions before climate enrichment.",
  "Projected germplasm": "Projected germplasm rows generated for forecast or bridge-style preprocessing workflows.",
  "Locality count": "Distinct localities or manual grid cells used to expand the climate extraction stage.",
};

const createSummaryLogMetricCard = (label, value, tone = "", description = "") => {
  const article = document.createElement("article");
  article.className = `summary-log-metric${tone ? ` summary-log-metric-${tone}` : ""}`;
  if (description) {
    article.title = description;
  }
  article.innerHTML = `
    <span class="summary-log-metric-label">${label}${description ? ` <span class="summary-log-help" title="${description.replace(/"/g, "&quot;")}">i</span>` : ""}</span>
    <strong class="summary-log-metric-value">${formatAttributeValue(value)}</strong>
  `;
  return article;
};

const createSummaryLogSection = (title, metrics, toneByKey = {}) => {
  const section = document.createElement("section");
  section.className = "summary-log-section";
  const heading = document.createElement("div");
  heading.className = "summary-log-section-header";
  heading.textContent = title;
  const grid = document.createElement("div");
  grid.className = "summary-log-metrics";
  Object.entries(metrics).forEach(([label, value]) => {
    grid.append(
      createSummaryLogMetricCard(
        label,
        value,
        toneByKey[label] ?? "",
        SUMMARY_LOG_DESCRIPTIONS[label] ?? "",
      ),
    );
  });
  section.append(heading, grid);
  return section;
};

const renderSummaryLog = (summary = getActiveDatasetSummary()) => {
  if (!summaryLog) {
    return;
  }
  summaryLog.innerHTML = "";
  const summaryCandidate =
    summary && typeof summary === "object"
      ? summary
      : datasetStore.original?.summary && typeof datasetStore.original.summary === "object"
        ? datasetStore.original.summary
        : null;
  const preprocessLog =
    summaryCandidate &&
    typeof summaryCandidate === "object" &&
    summaryCandidate.preprocess_log &&
    typeof summaryCandidate.preprocess_log === "object"
      ? summaryCandidate.preprocess_log
      : null;
  const cePipelineLog =
    summaryCandidate &&
    typeof summaryCandidate === "object" &&
    summaryCandidate.ce_pipeline_log &&
    typeof summaryCandidate.ce_pipeline_log === "object"
      ? summaryCandidate.ce_pipeline_log
      : null;
  if (!preprocessLog && !cePipelineLog) {
    const empty = document.createElement("p");
    empty.className = "summary-log-empty";
    empty.textContent =
      "Run the preprocess flow to see the operational summary for quality filters, climate enrichment, and phase outputs.";
    summaryLog.append(empty);
    return;
  }

  if (cePipelineLog) {
    const overviewSection = createSummaryLogSection("Overview", {
      "Input rows": cePipelineLog?.overview?.input_rows ?? 0,
      "Phase02 kept rows": cePipelineLog?.overview?.phase02_kept_rows ?? 0,
      "Phase03 output rows": cePipelineLog?.overview?.phase03_output_rows ?? 0,
      "Climate unique queries": cePipelineLog?.overview?.nasa_unique_queries ?? 0,
    });
    const qualitySection = createSummaryLogSection(
      "Quality Filters",
      {
        "Missing required Initial Settings": cePipelineLog?.quality_filters?.missing_required_initial_settings ?? 0,
        "Invalid target value": cePipelineLog?.quality_filters?.invalid_target_value ?? 0,
        "Invalid initial setting dates": cePipelineLog?.quality_filters?.invalid_initial_setting_dates ?? 0,
        "Water or lake point": cePipelineLog?.quality_filters?.water_or_lake_point ?? 0,
      },
      {
        "Invalid target value": "warning",
        "Invalid initial setting dates": "warning",
        "Water or lake point": "danger",
      },
    );
    const climateSection = createSummaryLogSection("Climate Stage", {
      "Source rows": cePipelineLog?.climate?.source_rows ?? 0,
      "Climate input rows": cePipelineLog?.climate?.climate_input_rows ?? 0,
      "Matched rows": cePipelineLog?.climate?.matched_rows ?? 0,
      "Climate cache hits": cePipelineLog?.climate?.nasa_cache_hits ?? 0,
      "Climate fresh queries": cePipelineLog?.climate?.nasa_fresh_queries_this_run ?? 0,
      "Soil skipped": cePipelineLog?.climate?.soil_skipped ? "Yes" : "No",
    });
    summaryLog.append(overviewSection, qualitySection, climateSection);
    return;
  }

  const overviewSection = createSummaryLogSection("Overview", {
    "Input rows": preprocessLog?.overview?.input_rows ?? 0,
    "Quality output rows": preprocessLog?.overview?.quality_output_rows ?? 0,
    "Climate exportable rows": preprocessLog?.overview?.climate_exportable_rows ?? 0,
    "Phase02 source rows": preprocessLog?.overview?.phase02_source_rows ?? 0,
    "Climate unique queries": preprocessLog?.overview?.nasa_unique_queries ?? 0,
  });
  const qualitySection = createSummaryLogSection(
    "Quality Filters",
    {
      "Name updates": preprocessLog?.quality_filters?.name_updates ?? 0,
      "Deleted by name rule": preprocessLog?.quality_filters?.deleted_by_name_rule ?? 0,
      "Missing yield": preprocessLog?.quality_filters?.excluded_missing_yield ?? 0,
      "Rank blank with zero yield": preprocessLog?.quality_filters?.excluded_rank_yield_zero ?? 0,
      "Wrong coordinates": preprocessLog?.quality_filters?.wrong_coordinates ?? 0,
    },
    {
      "Deleted by name rule": "warning",
      "Missing yield": "warning",
      "Rank blank with zero yield": "warning",
      "Wrong coordinates": "danger",
    },
  );
  const climateSection = createSummaryLogSection("Climate Stage", {
    "Source rows": preprocessLog?.climate?.source_rows ?? 0,
    "Climate input rows": preprocessLog?.climate?.climate_input_rows ?? 0,
    "Skipped missing climate fields": preprocessLog?.climate?.skipped_rows_missing_climate_fields ?? 0,
    "Matched rows": preprocessLog?.climate?.matched_rows ?? 0,
    "Unmatched rows": preprocessLog?.climate?.unmatched_rows ?? 0,
    "Expanded row count": preprocessLog?.climate?.expanded_row_count ?? 0,
    "Projected germplasm": preprocessLog?.climate?.projected_germplasm_count ?? 0,
    "Locality count": preprocessLog?.climate?.locality_count ?? 0,
  });

  summaryLog.append(
    overviewSection,
    qualitySection,
    climateSection,
  );
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
  renderSummaryLog(null);
};

const formatAttributeValue = (value) => {
  if (value === null || value === undefined || value === "") {
    return "Sin dato";
  }
  return typeof value === "number" ? formatNumber(value) : String(value);
};

const asFloat = (value) => {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  const numeric = Number(String(value).replace(",", "."));
  return Number.isFinite(numeric) ? numeric : null;
};

const hasOwnProperty = (object, key) =>
  !!object && Object.prototype.hasOwnProperty.call(object, key);

const getConfiguredTargetColumn = () => {
  const candidates = [
    selectionPropertiesState?.targetColumn,
    datasetStore?.prediction?.summary?.target_column,
    datasetStore?.training?.summary?.target_column,
    datasetStore?.top_germplasm?.summary?.target_column,
    datasetStore?.original?.summary?.target_column,
  ];
  for (const candidate of candidates) {
    const normalized = String(candidate ?? "").trim();
    if (normalized) {
      return normalized;
    }
  }
  return actualYieldKey;
};

const getConfiguredPredictedTargetColumn = () => {
  const targetColumn = getConfiguredTargetColumn();
  const candidates = [
    datasetStore?.prediction?.summary?.target_predicted_column,
    datasetStore?.training?.summary?.target_predicted_column,
    datasetStore?.top_germplasm?.summary?.target_predicted_column,
    targetColumn ? `${targetColumn} predicted` : "",
    predictedYieldKey,
  ];
  for (const candidate of candidates) {
    const normalized = String(candidate ?? "").trim();
    if (normalized) {
      return normalized;
    }
  }
  return predictedYieldKey;
};

const getObservedTargetColumnKey = (properties = null) => {
  const configured = getConfiguredTargetColumn();
  const candidates = [configured, actualYieldKey];
  for (const candidate of candidates) {
    if (candidate && hasOwnProperty(properties, candidate)) {
      return candidate;
    }
  }
  const inferred = Object.keys(properties ?? {}).find((key) => {
    const normalized = String(key ?? "").trim().toLowerCase();
    if (!normalized) {
      return false;
    }
    if (normalized.includes("predicted") || normalized.includes("prediction mean")) {
      return false;
    }
    return normalized.includes("yield") || normalized === "target";
  });
  return inferred || configured || actualYieldKey;
};

const getPredictedTargetColumnKey = (properties = null) => {
  const configured = getConfiguredPredictedTargetColumn();
  const observedKey = getObservedTargetColumnKey(properties);
  const candidates = [
    configured,
    observedKey ? `${observedKey} predicted` : "",
    predictedYieldKey,
  ];
  for (const candidate of candidates) {
    if (candidate && hasOwnProperty(properties, candidate)) {
      return candidate;
    }
  }
  const inferred = Object.keys(properties ?? {}).find((key) => {
    const normalized = String(key ?? "").trim().toLowerCase();
    if (!normalized) {
      return false;
    }
    return normalized.includes("predicted") || normalized.includes("prediction mean");
  });
  return inferred || configured || predictedYieldKey;
};

const getObservedTargetValue = (properties = null) =>
  properties?.[getObservedTargetColumnKey(properties)];

const getPredictedTargetValue = (properties = null) =>
  properties?.[getPredictedTargetColumnKey(properties)];

const getObservedTargetColumnLabel = () => getConfiguredTargetColumn() || "Target";

const getPredictedTargetColumnLabel = ({ training = false } = {}) =>
  training
    ? `${getObservedTargetColumnLabel()} Predicted Training`
    : getConfiguredPredictedTargetColumn();


const getYieldDifference = (properties) => {
  const mean = predictedYieldStats?.mean;
  const predicted = asFloat(getPredictedTargetValue(properties));
  if (isSavedModelRenderMode()) {
    if (!Number.isFinite(mean) || predicted === null) {
      return null;
    }
    return mean - predicted;
  }
  const actual = asFloat(getObservedTargetValue(properties));
  if (actual === null || predicted === null) {
    return null;
  }
  return predicted - actual;
};

const formatYieldDifference = (value) => {
  if (value === null || value === undefined) {
    return "Sin dato";
  }
  return formatSignedNumber(value);
};

const getAutomaticFlowMarkerColor = (feature) => {
  const actual = asFloat(getObservedTargetValue(feature?.properties));
  const predicted = asFloat(getPredictedTargetValue(feature?.properties));
  if (actual === null || predicted === null) {
    return "#c7512e";
  }
  const absoluteDifference = Math.abs(actual - predicted);
  const quartiles = trainingErrorQuartiles;
  if (!quartiles) {
    return "#c7512e";
  }
  if (absoluteDifference <= quartiles.q1) {
    return "#245c9f";
  }
  if (absoluteDifference <= quartiles.q2) {
    return "#8eb8e5";
  }
  if (absoluteDifference <= quartiles.q3) {
    return "#d46a6a";
  }
  return "#8f1d1d";
};

const getSavedModelPredictedColor = (predictedValue) => {
  const predicted = asFloat(predictedValue);
  if (predicted === null || !predictedYieldStats) {
    return "#c7512e";
  }
  const { min, mean, max } = predictedYieldStats;
  if (![min, mean, max].every(Number.isFinite)) {
    return "#c7512e";
  }
  if (max === min) {
    return "#4f86c6";
  }

  if (predicted <= mean) {
    const lowerMidpoint = min + (mean - min) / 2;
    return predicted <= lowerMidpoint ? "#8f1d1d" : "#d46a6a";
  }

  const upperMidpoint = mean + (max - mean) / 2;
  return predicted <= upperMidpoint ? "#245c9f" : "#8eb8e5";
};

const getMarkerColor = (feature) => {
  if (isOriginalDataRenderMode()) {
    return "#e2b93b";
  }
  if (!isSavedModelRenderMode()) {
    return getAutomaticFlowMarkerColor(feature);
  }
  if (isCategoricalPredictionColorMode()) {
    return getPredictionProfileColor(getPredictionCategoryLabelForFeature(feature));
  }
  return getSavedModelPredictedColor(getPredictedTargetValue(feature?.properties));
};

const toMarkerColorAlpha = (color, alpha) => {
  if (typeof color !== "string") {
    return `rgba(36, 58, 64, ${alpha})`;
  }
  const normalized = color.trim();
  const shortHexMatch = normalized.match(/^#([\da-fA-F]{3})$/);
  if (shortHexMatch) {
    const [r, g, b] = shortHexMatch[1].split("").map((channel) => Number.parseInt(channel + channel, 16));
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
  }
  const longHexMatch = normalized.match(/^#([\da-fA-F]{6})$/);
  if (longHexMatch) {
    const value = longHexMatch[1];
    const r = Number.parseInt(value.slice(0, 2), 16);
    const g = Number.parseInt(value.slice(2, 4), 16);
    const b = Number.parseInt(value.slice(4, 6), 16);
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
  }
  return color;
};

const getAvailablePredictionProfileSummaries = () => {
  if (isMultiGermplasmPredictionResult()) {
    return getPredictionDistinctGermplasmNames().map((name, index) => ({
      key: name,
      label: name,
      palette_index: index,
    }));
  }
  const summaries = Array.isArray(datasetStore.prediction?.summary?.profile_summaries)
    ? datasetStore.prediction.summary.profile_summaries
    : [];
  if (!summaries.length) {
    return [];
  }
  return summaries.filter((summary) => String(summary?.label ?? "").trim());
};

const getVisiblePredictionProfileSummaries = () => {
  const summaries = getAvailablePredictionProfileSummaries();
  if (!summaries.length) {
    return [];
  }
  const visibleLabels = new Set(
    loadedFeatures
      .map((feature) => getPredictionCategoryLabelForFeature(feature))
      .filter(Boolean),
  );
  return summaries.filter((summary) => visibleLabels.has(String(summary?.label ?? "").trim()));
};

const getActivePredictionProfileLabel = () => String(activePredictionProfileHighlight ?? "").trim();

const setActivePredictionProfileHighlight = (profileLabel = "") => {
  activePredictionProfileHighlight = String(profileLabel ?? "").trim();
};

const clearActivePredictionProfileHighlight = () => {
  setActivePredictionProfileHighlight("");
  updateProfileHighlightState();
  renderDetails();
};

const updateProfileHighlightState = () => {
  const highlightedLabel = getActivePredictionProfileLabel();
  if (mapContext?.markerGroups) {
    mapContext.markerGroups
      .classed("profile-highlighted", (feature) =>
        Boolean(highlightedLabel) &&
        getPredictionCategoryLabelForFeature(feature) === highlightedLabel,
      )
      .classed("profile-dimmed", (feature) =>
        Boolean(highlightedLabel) &&
        getPredictionCategoryLabelForFeature(feature) !== highlightedLabel,
      );
  }
  if (mapContext?.manualGridHeatLayer && isManualGridPredictionResult()) {
    mapContext.renderBase(currentTransform);
  }
};

const getBestFeatureForProfileLabel = (profileLabel) => {
  const normalizedLabel = String(profileLabel ?? "").trim();
  if (!normalizedLabel) {
    return null;
  }
  const candidateFeatures = loadedFeatures.length
    ? loadedFeatures
    : Array.isArray(datasetStore.prediction?.geojson?.features)
      ? datasetStore.prediction.geojson.features
      : [];
  let bestFeature = null;
  let bestPredictedValue = Number.NEGATIVE_INFINITY;
  candidateFeatures.forEach((feature) => {
    const featureLabel = getPredictionCategoryLabelForFeature(feature);
    if (featureLabel !== normalizedLabel) {
      return;
    }
    const predictedValue = asFloat(getPredictedTargetValue(feature?.properties));
    if (!Number.isFinite(predictedValue)) {
      if (!bestFeature) {
        bestFeature = feature;
      }
      return;
    }
    if (!bestFeature || predictedValue > bestPredictedValue) {
      bestFeature = feature;
      bestPredictedValue = predictedValue;
    }
  });
  return bestFeature;
};

const getBestPredictionCategoryLabelByMean = () => {
  const candidateFeatures = loadedFeatures.length
    ? loadedFeatures
    : Array.isArray(datasetStore.prediction?.geojson?.features)
      ? datasetStore.prediction.geojson.features
      : [];
  const groupedValues = new Map();
  candidateFeatures.forEach((feature) => {
    const label = getPredictionCategoryLabelForFeature(feature);
    const predictedValue = asFloat(getPredictedTargetValue(feature?.properties));
    if (!label || !Number.isFinite(predictedValue)) {
      return;
    }
    if (!groupedValues.has(label)) {
      groupedValues.set(label, []);
    }
    groupedValues.get(label).push(predictedValue);
  });
  let bestLabel = "";
  let bestMean = Number.NEGATIVE_INFINITY;
  groupedValues.forEach((values, label) => {
    if (!values.length) {
      return;
    }
    const meanValue = d3.mean(values);
    if (!Number.isFinite(meanValue)) {
      return;
    }
    if (meanValue > bestMean) {
      bestMean = meanValue;
      bestLabel = label;
    }
  });
  return bestLabel;
};

const focusFeatureOnMap = (feature, { zoomToFeature = false } = {}) => {
  if (!feature) {
    return;
  }
  if (isCategoricalPredictionColorMode()) {
    setActivePredictionProfileHighlight(getPredictionCategoryLabelForFeature(feature));
  } else {
    setActivePredictionProfileHighlight("");
  }
  selectedFeature = feature;
  currentPage = 0;
  if (mapContext?.markerGroups) {
    mapContext.markerGroups.classed("active", (datum) => datum === feature);
  }
  updateProfileHighlightState();
  renderDetails();
  if (!zoomToFeature || !zoomBehavior) {
    return;
  }
  const polygon = createBoundingPolygon([feature]);
  const transform = currentRenderedFlowMode === "saved_model"
    ? computeTransformFromPolygon(polygon)
    : computeTransformForMarkers(polygon, [feature], {
        baseMargin: 72,
        markerPadding: 28,
      });
  svg
    .transition()
    .duration(420)
    .call(zoomBehavior.transform, transform);
};

const getPredictedMeanLabel = () => {
  const mean = predictedYieldStats?.mean;
  return Number.isFinite(mean) ? formatAttributeValue(mean) : "Sin dato";
};

const getPredictedMeanValue = () => {
  const mean = predictedYieldStats?.mean;
  return Number.isFinite(mean) ? mean : null;
};

const createColorHelpItem = ({ color, label, tooltip, onClick = null, isActive = false }) => {
  const item = document.createElement("button");
  item.className = "color-help-item";
  item.type = "button";
  item.title = tooltip;
  item.setAttribute("aria-label", label);
  item.setAttribute("aria-description", tooltip);
  if (isActive) {
    item.classList.add("active");
  }
  if (typeof onClick === "function") {
    item.style.cursor = "pointer";
    item.addEventListener("click", onClick);
  }

  const swatch = document.createElement("span");
  swatch.className = "color-help-swatch";
  swatch.style.background = color;

  item.append(swatch);
  return item;
};

const buildTrainingColorHelpItems = () => [
  {
    color: "#8f1d1d",
    label: "High deviation",
    tooltip:
      `High deviation: the predicted values for ${getObservedTargetColumnLabel()} differ strongly from the observed values for ${getObservedTargetColumnLabel()} and clearly exceed the mean absolute error range.`,
  },
  {
    color: "#d46a6a",
    label: "Moderate deviation",
    tooltip:
      `Moderate deviation: the predicted values for ${getObservedTargetColumnLabel()} are outside the mean absolute error range, but not by a large margin.`,
  },
  {
    color: "#8eb8e5",
    label: "Close fit",
    tooltip:
      `Close fit: the predicted values for ${getObservedTargetColumnLabel()} remain within the mean absolute error range, but with a larger gap than the darkest blue markers.`,
  },
  {
    color: "#245c9f",
    label: "Very close fit",
    tooltip:
      `Very close fit: the predicted values for ${getObservedTargetColumnLabel()} are very close to the observed values for ${getObservedTargetColumnLabel()} and well within the mean absolute error range.`,
  },
];

const buildSavedModelColorHelpItems = () => [
  {
    color: "#8f1d1d",
    label: "Lower prediction",
    tooltip:
      `Lower prediction: this marker belongs to the lower end of predicted ${getObservedTargetColumnLabel()} values in the current prediction run.`,
  },
  {
    color: "#d46a6a",
    label: "Lower-mid prediction",
    tooltip:
      `Lower-mid prediction: this marker belongs to the lower-middle predicted ${getObservedTargetColumnLabel()} range in the current prediction run.`,
  },
  {
    color: "#8eb8e5",
    label: "Higher prediction",
    tooltip:
      `Higher prediction: this marker belongs to the upper end of predicted ${getObservedTargetColumnLabel()} values in the current prediction run.`,
  },
  {
    color: "#245c9f",
    label: "Upper-mid prediction",
    tooltip:
      `Upper-mid prediction: this marker belongs to the upper-middle predicted ${getObservedTargetColumnLabel()} range in the current prediction run.`,
  },
];

const buildManualBoundingBoxColorHelpItems = () => [
  {
    color: "#a42a2a",
    label: ">= 1.5",
    tooltip:
      "Absolute prediction difference of 1.5 or more: this grid area shows a strong departure from the prediction mean and is shown in dark red.",
  },
  {
    color: "#e8a29a",
    label: "1.05 to < 1.5",
    tooltip:
      "Absolute prediction difference from 1.05 to below 1.5: this grid area is in the red range.",
  },
  {
    color: "#78aee8",
    label: "0.5 to < 0.95",
    tooltip:
      "Absolute prediction difference from 0.5 to below 0.95: this grid area remains in the blue range.",
  },
  {
    color: "#1f4f99",
    label: "|Diff| < 0.5",
    tooltip:
      "Absolute prediction difference below 0.5: this grid area is very close to the prediction mean and is shown in intense blue.",
  },
];

const buildMultiProfileColorHelpItems = () => {
  const profiles = getAvailablePredictionProfileSummaries();
  return profiles.map((profile) => ({
    color: getPredictionProfileColor(profile?.label),
    label: getPredictionProfileDisplayLabel(profile?.label),
    tooltip: `${isMultiGermplasmPredictionResult() ? "Selected germplasm" : "Prediction profile"}: ${getPredictionProfileDisplayLabel(profile?.label)}`,
    isActive: String(profile?.label ?? "").trim() === getActivePredictionProfileLabel(),
    onClick: () => {
      const label = String(profile?.label ?? "").trim();
      const feature = getBestFeatureForProfileLabel(label);
      if (feature) {
        focusFeatureOnMap(feature, { zoomToFeature: true });
      }
    },
  }));
};

const renderColorHelp = () => {
  if (!colorHelpPanel || !colorHelpList) {
    return;
  }

  let items = [];
  if (activeDataViewTab === "training" && datasetStore.training?.geojson) {
    items = buildTrainingColorHelpItems();
  } else if (activeDataViewTab === "prediction" && datasetStore.prediction?.geojson) {
    items = isCategoricalPredictionColorMode()
      ? buildMultiProfileColorHelpItems()
      : datasetStore.prediction?.summary?.climate_scope === "regional_manual"
        ? buildManualBoundingBoxColorHelpItems()
        : buildSavedModelColorHelpItems();
  }

  colorHelpPanel.hidden = items.length === 0;
  colorHelpList.replaceChildren(...items.map(createColorHelpItem));
};

const isDefaultBridgeSavedModelMode = () =>
  isSavedModelRenderMode() &&
  activeDataViewTab === "prediction" &&
  selectedClimateScope === "default" &&
  predictionBridgeState?.isAvailable;

const getCurrentOriginalGermplasmDetailKeys = () => {
  const summary = datasetStore.original?.summary;
  const selectedKeys = Array.isArray(summary?.divisions?.germplams_identifiers)
    ? summary.divisions.germplams_identifiers
        .map((value) => String(value ?? "").trim())
        .filter(Boolean)
    : [];
  return selectedKeys.length ? selectedKeys : germplasmAttributeKeys;
};

const getProjectedSelectedGermplasmName = (fallbackValue = "") => {
  if (!isDefaultBridgeSavedModelMode()) {
    return String(fallbackValue ?? "");
  }
  const featureName = String(fallbackValue ?? "").trim();
  if (featureName) {
    return featureName;
  }
  const firstSelected = Array.from(selectedGermplasmNames).find((name) => String(name ?? "").trim());
  return String(firstSelected ?? "").trim();
};

const getPagedAttributes = (feature) => {
  const entries = Object.entries(feature.properties).filter(
    ([key]) =>
      key !== "row_number" &&
      !geoInformationAttributeKeys.has(key) &&
      !germplasmAttributeKeySet.has(key),
  );
  entries.sort(([left], [right]) => left.localeCompare(right));
  return entries;
};

const positionTooltip = (event) => {
  const container = mapFrame ?? svg.node()?.parentElement;
  if (!container) {
    return;
  }
  const bounds = container.getBoundingClientRect();
  const tooltipWidth = tooltip.offsetWidth || 260;
  const tooltipHeight = tooltip.offsetHeight || 120;
  const offsetX = 18;
  const offsetY = 12;
  const maxLeft = Math.max(bounds.width - tooltipWidth - 12, 12);
  const maxTop = Math.max(bounds.height - tooltipHeight - 12, 12);
  const nextLeft = Math.min(Math.max(event.clientX - bounds.left + offsetX, 12), maxLeft);
  const nextTop = Math.min(Math.max(event.clientY - bounds.top - offsetY, 12), maxTop);
  tooltip.style.left = `${nextLeft}px`;
  tooltip.style.top = `${nextTop}px`;
};

const showTooltip = (event, feature) => {
  try {
    const properties = feature?.properties ?? {};
    const coordinates = Array.isArray(feature?.geometry?.coordinates)
      ? feature.geometry.coordinates
      : [];
    const longitude = coordinates.length > 0 ? coordinates[0] : null;
    const latitude = coordinates.length > 1 ? coordinates[1] : null;
    const yieldDifference = getYieldDifference(properties);
    const projectedName = getProjectedSelectedGermplasmName(properties.Name);
    const title = projectedName || properties.idPK || `Row ${properties.row_number ?? "N/A"}`;
    const observedLabel = escapeHtml(getObservedTargetColumnLabel() || "Target");
    const predictedLabel = escapeHtml(getPredictedTargetColumnLabel() || "Target predicted");
    const trainingPredictedLabel = escapeHtml(
      getPredictedTargetColumnLabel({ training: true }) || "Target Predicted Training",
    );
    const grainYieldLine = isSavedModelRenderMode()
      ? ""
      : `<p>${observedLabel}: ${formatAttributeValue(getObservedTargetValue(properties))}</p>`;
    const nameLine = isOriginalDataRenderMode()
      ? `<p>Name: ${formatAttributeValue(projectedName || properties.Name)}</p>`
      : "";
    const germplasmLine = isMultiGermplasmPredictionResult() && properties?.Name
      ? `<p>Selected germplasm: ${formatAttributeValue(properties.Name)}</p>`
      : "";
    const profileLine = isMultiProfilePredictionResult() && properties?.[predictionProfileLabelKey]
      ? `<p>Prediction profile: ${formatAttributeValue(getPredictionProfileDisplayLabel(properties[predictionProfileLabelKey]))}</p>`
      : "";
    const predictedLine = isOriginalDataRenderMode()
      ? ""
      : isSavedModelRenderMode()
        ? `<p>${predictedLabel}: ${formatAttributeValue(getPredictedTargetValue(properties))}</p>`
        : `<p>${trainingPredictedLabel}: ${formatAttributeValue(getPredictedTargetValue(properties))}</p>`;
    const predictionDifferenceLine = isOriginalDataRenderMode()
      ? ""
      : `<p>Prediction difference: ${formatYieldDifference(yieldDifference)}</p>`;
    const showCoordinates = !(activeDataViewTab === "original" || activeDataViewTab === "training" || activeDataViewTab === "prediction");
    const showCountry = !(activeDataViewTab === "original" || activeDataViewTab === "training" || activeDataViewTab === "prediction");
    const showRank = activeDataViewTab !== "original";
    tooltip.hidden = false;
    tooltip.innerHTML = `
      <strong>${escapeHtml(title)}</strong>
      ${grainYieldLine}
      ${nameLine}
      ${germplasmLine}
      ${profileLine}
      ${predictedLine}
      ${predictionDifferenceLine}
      ${showCoordinates && latitude !== null ? `<p>Latitude: ${formatCoordinate(latitude)}</p>` : ""}
      ${showCoordinates && longitude !== null ? `<p>Longitude: ${formatCoordinate(longitude)}</p>` : ""}
      ${showCountry && properties.Country ? `<p>Country: ${escapeHtml(properties.Country)}</p>` : ""}
      ${showRank && properties.Rank ? `<p>Rank: ${formatAttributeValue(properties.Rank)}</p>` : ""}
    `;

    positionTooltip(event);
  } catch (error) {
    console.error("Tooltip render error", error);
    tooltip.hidden = false;
    tooltip.innerHTML = `<strong>Record</strong><p>Tooltip data unavailable.</p>`;
    positionTooltip(event);
  }
};

const hideTooltip = () => {
  tooltip.hidden = true;
};

const setActiveSummaryTab = (tab) => {
  activeSummaryTab = tab;
  summaryTabCountriesButton.classList.toggle("active", tab === "countries");
  summaryTabStatsButton.classList.toggle("active", tab === "stats");
  if (summaryTabLogButton) {
    summaryTabLogButton.classList.toggle("active", tab === "log");
  }
  summaryPanelCountries.hidden = tab !== "countries";
  summaryPanelStats.hidden = tab !== "stats";
  if (summaryPanelLog) {
    summaryPanelLog.hidden = tab !== "log";
  }
};

const setActiveDetailsTab = (tab) => {
  activeDetailsTab = tab;
  tabGeoButton.classList.toggle("active", tab === "geo");
  tabAttributesButton.classList.toggle("active", tab === "attributes");
  tabGermplasmButton.classList.toggle("active", tab === "germplasm");
  panelGeo.hidden = tab !== "geo";
  panelAttributes.hidden = tab !== "attributes";
  panelGermplasm.hidden = tab !== "germplasm";
};

const updateDetailsTabLabels = () => {
  if (!tabGeoButton) {
    return;
  }
  if (activeDataViewTab === "training") {
    tabGeoButton.textContent = "Training";
    return;
  }
  tabGeoButton.textContent = isHighPotentialSitesPredictionMode()
    ? "Prediction"
    : "Geo-Information";
};

const syncAppConfig = async () => {
  try {
    const response = await fetch("/api/cimmyt-app-config", { method: "GET" });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.error ?? "The app version could not be loaded.");
    }
    const appVersion = String(payload.app_version ?? "").trim();
    if (!appVersion) {
      return;
    }
    if (buildBadge) {
      buildBadge.textContent = "M I C T L A N";
    }
    if (heroBuildInline) {
      heroBuildInline.textContent = `Apanohuayan ${appVersion}`;
    }
    preprocessValidationEnabled = payload.preprocess_validation_enabled !== false;
    if (payload.featurehero_settings && typeof payload.featurehero_settings === "object") {
      populateFeatureheroSettingsForm(payload.featurehero_settings);
    }
    applyPreprocessValidationVisibility();
  } catch (error) {
    console.error(error);
  }
};

const renderCountrySummary = (features = loadedFeatures) => {
  const counts = new Map();

  features.forEach((feature) => {
    const country = String(feature.properties.Country ?? "").trim();
    if (!country) {
      return;
    }
    counts.set(country, (counts.get(country) ?? 0) + 1);
  });

  const sortedCountries = Array.from(counts.entries()).sort((left, right) =>
    left[0].localeCompare(right[0]),
  );

  countrySummary.innerHTML = "";

  if (!sortedCountries.length) {
    const empty = document.createElement("p");
    empty.className = "country-empty";
    empty.textContent = "Load an Excel file to build the country summary.";
    countrySummary.append(empty);
    return;
  }

  sortedCountries.forEach(([country, count]) => {
    const item = document.createElement("div");
    item.className = "country-inline-item";
    item.innerHTML = `
      <span class="country-name">${country}</span>
      <span class="country-count">${formatNumber(count)} Geocoordinates</span>
    `;
    countrySummary.append(item);
  });
};

const resetDetails = () => {
  activeDetailsTab = "germplasm";
  setActiveDetailsTab("germplasm");
  setActiveSummaryTab("countries");
  detailsMeta.innerHTML = "";
  detailsList.innerHTML = "";
  germplasmList.innerHTML = "";
  detailsTitle.textContent = "Experiment Information";
  detailsSubtitle.textContent =
    "Load an Excel file first. Then you can explore the details of each record.";
  pageIndicator.textContent = "0 / 0";
  prevPageButton.disabled = true;
  nextPageButton.disabled = true;
  renderCountrySummary([]);
  renderSummaryLog(null);
  tabGermplasmButton.focus();
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
  const yieldDifference = getYieldDifference(selectedFeature.properties);
  const entryCode = selectedFeature.properties.EntryCode;
  const name = getProjectedSelectedGermplasmName(selectedFeature.properties.Name);

  detailsTitle.textContent =
    entryCode || name
      ? `${entryCode ?? "No EntryCode"} - ${name ?? "No Name"}`
      : selectedFeature.properties.idPK ?? `Fila ${selectedFeature.properties.row_number}`;
  detailsSubtitle.textContent =
    isDefaultBridgeSavedModelMode()
      ? `${selectedGermplasmNames.size} selected germplasm(s) projected across all Geocoordinates. Current Geocoordinate: ${name || "No Name"}`
      : selectedFeature.properties["Local check, Name of variety provided by farmer"] ??
        "Record loaded from the Excel file.";

  detailsMeta.innerHTML = "";
  const metaChips = [
    `Country: ${selectedFeature.properties.Country ?? "No data"}`,
    isSavedModelRenderMode()
      ? `${getObservedTargetColumnLabel()} Prediction Mean: ${getPredictedMeanLabel()}`
      : `${getObservedTargetColumnLabel()}: ${formatAttributeValue(getObservedTargetValue(selectedFeature.properties))}`,
  ];
  if (!isOriginalDataRenderMode()) {
    metaChips.push(
      `${getPredictedTargetColumnLabel()}: ${formatAttributeValue(getPredictedTargetValue(selectedFeature.properties))}`,
      `Prediction difference: ${formatYieldDifference(yieldDifference)}`,
    );
  }
  if (selectedFeature.properties.Rank) {
    metaChips.push(`Rank: ${formatAttributeValue(selectedFeature.properties.Rank)}`);
  }
  metaChips.push(
    `Latitude: ${formatCoordinate(latitude)}`,
    `Longitude: ${formatCoordinate(longitude)}`,
    `Geocoordinate ID: ${selectedFeature.properties.idPK ?? selectedFeature.properties.row_number}`,
  );
  metaChips.forEach((text) => {
    const chip = document.createElement("div");
    chip.className = "meta-chip";
    chip.textContent = text;
    detailsMeta.append(chip);
  });
  if (isCategoricalPredictionColorMode()) {
    const dominantCategory = String(selectedFeature.properties?.[predictionProfileLabelKey] ?? "").trim();
    const dominantGermplasm = String(selectedFeature.properties?.Name ?? "").trim();
    const activeCategory = isMultiGermplasmPredictionResult() ? dominantGermplasm : dominantCategory;
    const availableProfileSummaries = getAvailablePredictionProfileSummaries();
    if (activeCategory || availableProfileSummaries.length) {
      const singleVaryingHeader = getPredictionProfileSingleVaryingHeader();
      const profileChip = document.createElement("div");
      profileChip.className = "meta-chip meta-chip-profile";
      const title = document.createElement("span");
      title.className = "meta-chip-profile-title";
      title.textContent = isMultiGermplasmPredictionResult()
        ? "Selected germoplasms"
        : singleVaryingHeader
          ? `Prediction profiles: ${singleVaryingHeader}`
          : "Prediction profiles";
      profileChip.append(title);

      if (activeCategory) {
        const dominantColor = getPredictionProfileColor(activeCategory);
        const dominantDisplayLabel = getPredictionProfileDisplayLabel(activeCategory);
        const dominantBody = document.createElement("button");
        dominantBody.type = "button";
        dominantBody.className = "meta-chip-profile-body meta-chip-profile-body-button";
        dominantBody.title = `Show the best visible prediction for ${dominantDisplayLabel}.`;
        dominantBody.addEventListener("click", () => {
          const feature = getBestFeatureForProfileLabel(activeCategory);
          if (feature) {
            focusFeatureOnMap(feature, { zoomToFeature: true });
          }
        });
        const dominantSwatch = document.createElement("span");
        dominantSwatch.className = "meta-chip-color-swatch";
        dominantSwatch.style.background = dominantColor;
        dominantSwatch.style.boxShadow = `0 0 0 3px ${toMarkerColorAlpha(dominantColor, 0.18)}`;
        const dominantLabel = document.createElement("span");
        dominantLabel.className = "meta-chip-profile-label";
        dominantLabel.textContent = `Selected: ${dominantDisplayLabel}`;
        dominantBody.append(dominantSwatch, dominantLabel);
        profileChip.append(dominantBody);
      }

      if (availableProfileSummaries.length) {
        const profileList = document.createElement("div");
        profileList.className = "meta-chip-profile-list";
        availableProfileSummaries.forEach((summary) => {
          const label = String(summary?.label ?? "").trim();
          if (!label) {
            return;
          }
          const displayLabel = getPredictionProfileDisplayLabel(label);
          const color = getPredictionProfileColor(label);
          const profileOption = document.createElement("button");
          profileOption.type = "button";
          profileOption.className = "meta-chip-profile-option";
          if (label === activeCategory) {
            profileOption.classList.add("active");
          }
          const predictedMean = asFloat(summary?.predicted_mean);
          profileOption.title = Number.isFinite(predictedMean)
            ? `Show the best visible prediction for ${displayLabel} (predicted mean ${formatAttributeValue(predictedMean)}).`
            : `Show the best visible prediction for ${displayLabel}.`;
          profileOption.addEventListener("click", () => {
            const feature = getBestFeatureForProfileLabel(label);
            if (feature) {
              focusFeatureOnMap(feature, { zoomToFeature: true });
            }
          });

          const swatch = document.createElement("span");
          swatch.className = "meta-chip-color-swatch meta-chip-color-swatch-button";
          swatch.style.background = color;
          swatch.style.boxShadow = `0 0 0 3px ${toMarkerColorAlpha(color, 0.18)}`;
          const optionLabel = document.createElement("span");
          optionLabel.className = "meta-chip-profile-option-label";
          optionLabel.textContent = displayLabel;
          profileOption.append(swatch, optionLabel);
          profileList.append(profileOption);
        });
        profileChip.append(profileList);
      }

      const reference = document.createElement("span");
      reference.className = "meta-chip-profile-reference";
      reference.textContent = isMultiGermplasmPredictionResult()
        ? "Click a color to center the map on the best prediction for that germplasm."
        : "Click a color to center the map on the best prediction for that profile.";
      profileChip.append(reference);
      detailsMeta.append(profileChip);
    }
  }

  detailsList.innerHTML = "";
  if (!currentSlice.length) {
    const empty = document.createElement("article");
    empty.className = "attribute-card";
    empty.innerHTML = `
      <span class="attribute-name">Attributes</span>
      <span class="attribute-value">No non-geographic attributes are available for this record.</span>
    `;
    detailsList.append(empty);
  }
  currentSlice.forEach(([key, value]) => {
    const article = document.createElement("article");
    article.className = "attribute-card";
    article.innerHTML = `
      <span class="attribute-name">${key}</span>
      <span class="attribute-value">${formatAttributeValue(value)}</span>
    `;
    detailsList.append(article);
  });

  germplasmList.innerHTML = "";
  getCurrentOriginalGermplasmDetailKeys().forEach((key) => {
    const value =
      isDefaultBridgeSavedModelMode() &&
      (key === "Name" || key === "Local check, Name of variety provided by farmer")
        ? name
        : selectedFeature.properties[key];
    const article = document.createElement("article");
    article.className = "attribute-card";
    article.innerHTML = `
      <span class="attribute-name">${key}</span>
      <span class="attribute-value">${formatAttributeValue(value)}</span>
    `;
    germplasmList.append(article);
  });

  pageIndicator.textContent = `${currentPage + 1} / ${totalPages}`;
  prevPageButton.disabled = currentPage === 0;
  nextPageButton.disabled = currentPage >= totalPages - 1;
};

const validateFeatureCollection = (geojson) => {
  if (!geojson || geojson.type !== "FeatureCollection" || !Array.isArray(geojson.features)) {
    throw new Error("The pipeline did not return a valid GeoJSON feature collection.");
  }

  if (!geojson.features.length) {
    throw new Error("No valid Geocoordinates were returned by the processing pipeline.");
  }

  geojson.features.forEach((feature) => {
    const latitude = asFloat(feature?.geometry?.coordinates?.[1]);
    const longitude = asFloat(feature?.geometry?.coordinates?.[0]);
    if (latitude === null || longitude === null) {
      throw new Error("The processed data contains Geocoordinates without valid coordinates.");
    }
  });

  return geojson;
};

const resolvePipelineGeojson = async (payload) => {
  const directGeojson = payload?.geojson;
  let directGeojsonError = null;
  if (directGeojson) {
    try {
      return validateFeatureCollection(directGeojson);
    } catch (error) {
      directGeojsonError = error instanceof Error ? error : new Error(String(error));
    }
  }
  const downloadUrl = String(payload?.geojson_download_url ?? "").trim();
  if (!downloadUrl) {
    throw directGeojsonError ?? new Error("The pipeline did not return a valid GeoJSON feature collection.");
  }
  const response = await fetch(downloadUrl, { method: "GET" });
  const geojson = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error("The pipeline GeoJSON artifact could not be loaded.");
  }
  try {
    return validateFeatureCollection(geojson);
  } catch (error) {
    if (directGeojsonError) {
      throw directGeojsonError;
    }
    throw error;
  }
};

const processFileWithStatusTimeline = async (
  file,
  {
    selectedModelId = "",
    selectedGermplasmNames = [],
    selectedIdHeader = "",
    selectedGermplasmProjectionMode = "",
    projectionTemplateWorkbook = "",
    forecastPlantingDate = "",
    forecastHarvestingDate = "",
    pauseAfterPreprocess = false,
    climateScope = "point",
    regionalCountry = "",
    regionalBounds = null,
  } = {},
) => {
  const workflowMode = isPredictionWorkflowMode() ? "prediction" : "training";
  const firstStep = getInitialPipelineLoadingStep(file.name, workflowMode);
  await setLoadingState(firstStep.percent, firstStep.stage, firstStep.message);

  const startPayload = await startPipelineJob(file, {
    selectedModelId,
    selectedGermplasmNames,
    selectedIdHeader,
    selectedGermplasmProjectionMode,
    projectionTemplateWorkbook,
    forecastPlantingDate,
    forecastHarvestingDate,
    pauseAfterPreprocess,
    climateScope,
    regionalCountry,
    regionalBounds,
  });
  const statusUrl = startPayload?.status_url;
  if (!statusUrl) {
    throw new Error("The pipeline did not return a valid status URL.");
  }
  persistActivePipelineJob({
    jobId: startPayload?.job_id ?? "",
    statusUrl,
    sourceName: file.name,
    state: "running",
    workflowMode: isPredictionWorkflowMode() ? "prediction" : "training",
    predictionMode: isPredictionWorkflowMode(),
  });
  return pollPipelineStatus(statusUrl, {
    sourceName: file.name,
    workflowMode: isPredictionWorkflowMode() ? "prediction" : "training",
    predictionMode: isPredictionWorkflowMode(),
  });
};

const showPausedPreprocessValidation = async (payload, { updateOriginalData = true } = {}) => {
  if (updateOriginalData) {
    await renderPreprocessOriginalMapFromPayload(
      payload,
      payload?.source_name ?? "preprocess output",
    );
  }
  if (!preprocessValidationEnabled) {
    return;
  }
  pausedPreprocessPayload = payload;
  rememberPausedPreprocessPayload(payload);
  if (downloadPreprocessOutput && payload?.phase06_download_url) {
    downloadPreprocessOutput.href = payload.phase06_download_url;
  }
  if (continueAfterPreprocessButton) {
    continueAfterPreprocessButton.disabled = false;
  }
  if (preprocessValidationMessage) {
    preprocessValidationMessage.textContent =
      payload?.progress?.message ??
      "The preprocess output is ready. Download the phase06 workbook, validate it, and continue when approved.";
  }
  if (preprocessValidationPanel) {
    preprocessValidationPanel.hidden = false;
  }
  await setLoadingState(
    Number(payload?.progress?.percent ?? 52),
    payload?.progress?.stage ?? "Preprocess validation required",
    payload?.progress?.message ??
      "The preprocess phase06 workbook is ready for manual validation. Download it and continue when approved.",
  );
};

const createBoundingPolygon = (features) => {
  const longitudes = features.map((feature) => feature.geometry.coordinates[0]);
  const latitudes = features.map((feature) => feature.geometry.coordinates[1]);
  const minLon = d3.min(longitudes);
  const maxLon = d3.max(longitudes);
  const minLat = d3.min(latitudes);
  const maxLat = d3.max(latitudes);
  const padLon = Math.max((maxLon - minLon) * 0.12, 0.25);
  const padLat = Math.max((maxLat - minLat) * 0.14, 0.25);

  return [
    [minLon - padLon, minLat - padLat],
    [maxLon + padLon, minLat - padLat],
    [maxLon + padLon, maxLat + padLat],
    [minLon - padLon, maxLat + padLat],
    [minLon - padLon, minLat - padLat],
  ];
};

const computeTransformFromPolygon = (polygon) => {
  const projected = polygon.map((coordinates) => baseProjection(coordinates));
  const minX = d3.min(projected, ([x]) => x);
  const maxX = d3.max(projected, ([x]) => x);
  const minY = d3.min(projected, ([, y]) => y);
  const maxY = d3.max(projected, ([, y]) => y);
  const margin = 48;
  const scale = Math.min(
    (width - margin * 2) / (maxX - minX),
    (height - margin * 2) / (maxY - minY),
  );
  return d3.zoomIdentity
    .translate(width / 2 - scale * ((minX + maxX) / 2), height / 2 - scale * ((minY + maxY) / 2))
    .scale(scale);
};

const computeTransformForMarkers = (
  polygon,
  features,
  { baseMargin = 48, markerPadding = 0 } = {},
) => {
  const projected = polygon.map((coordinates) => baseProjection(coordinates));
  const minX = d3.min(projected, ([x]) => x);
  const maxX = d3.max(projected, ([x]) => x);
  const minY = d3.min(projected, ([, y]) => y);
  const maxY = d3.max(projected, ([, y]) => y);
  const largestOffset = d3.max(
    (features ?? []).map((feature) => {
      const offset = feature?.__displayOffset ?? { dx: 0, dy: 0 };
      return Math.max(Math.abs(offset.dx ?? 0), Math.abs(offset.dy ?? 0));
    }),
  ) ?? 0;
  const margin = baseMargin + largestOffset + markerPadding;
  const scale = Math.min(
    (width - margin * 2) / Math.max(maxX - minX, 1),
    (height - margin * 2) / Math.max(maxY - minY, 1),
  );
  return d3.zoomIdentity
    .translate(width / 2 - scale * ((minX + maxX) / 2), height / 2 - scale * ((minY + maxY) / 2))
    .scale(scale);
};

const projectPoint = (coordinates, transform = currentTransform) => {
  const [x, y] = baseProjection(coordinates);
  return [x * transform.k + transform.x, y * transform.k + transform.y];
};

const screenPointToCoordinates = (x, y, transform = currentTransform) => {
  const projectedX = (x - transform.x) / transform.k;
  const projectedY = (y - transform.y) / transform.k;
  const coordinates = baseProjection.invert([projectedX, projectedY]);
  if (!coordinates) {
    return null;
  }
  const [longitude, latitude] = coordinates;
  if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) {
    return null;
  }
  return [longitude, latitude];
};

const normalizeBoundsFromCoordinates = (start, end) => {
  if (!start || !end) {
    return null;
  }
  const [startLon, startLat] = start;
  const [endLon, endLat] = end;
  return {
    latitudeMin: Math.min(startLat, endLat),
    latitudeMax: Math.max(startLat, endLat),
    longitudeMin: Math.min(startLon, endLon),
    longitudeMax: Math.max(startLon, endLon),
  };
};

const buildOverlappingMarkerKey = (feature, { useProximityBuckets = false } = {}) => {
  const [longitude, latitude] = feature.geometry.coordinates;
  if (useProximityBuckets) {
    return [
      Math.round(Number(latitude) / AUTOMATIC_FLOW_PROXIMITY_BUCKET_DEGREES),
      Math.round(Number(longitude) / AUTOMATIC_FLOW_PROXIMITY_BUCKET_DEGREES),
    ].join("|");
  }
  return `${Number(latitude).toFixed(6)}|${Number(longitude).toFixed(6)}`;
};

const assignOverlappingMarkerOffsets = (features, { useProximityBuckets = false } = {}) => {
  const groups = new Map();

  features.forEach((feature) => {
    const key = buildOverlappingMarkerKey(feature, { useProximityBuckets });
    if (!groups.has(key)) {
      groups.set(key, []);
    }
    groups.get(key).push(feature);
  });

  groups.forEach((group) => {
    const sortedGroup = [...group].sort((left, right) => {
      const leftEntry = String(left.properties?.EntryCode ?? "");
      const rightEntry = String(right.properties?.EntryCode ?? "");
      const entryComparison = leftEntry.localeCompare(rightEntry);
      if (entryComparison !== 0) {
        return entryComparison;
      }
      const leftName = String(left.properties?.Name ?? "");
      const rightName = String(right.properties?.Name ?? "");
      return leftName.localeCompare(rightName);
    });

    if (sortedGroup.length === 1) {
      sortedGroup[0].__displayOffset = { dx: 0, dy: 0, stackSize: 1, stackIndex: 0 };
      return;
    }

    sortedGroup.forEach((feature, index) => {
      const ringIndex = Math.floor(index / 8);
      const positionInRing = index % 8;
      const pointsInRing = Math.min(8, sortedGroup.length - ringIndex * 8);
      const angle = (Math.PI * 2 * positionInRing) / pointsInRing - Math.PI / 2;
      const radius = OVERLAPPING_MARKER_BASE_RADIUS + ringIndex * OVERLAPPING_MARKER_RING_STEP;
      feature.__displayOffset = {
        dx: Math.cos(angle) * radius,
        dy: Math.sin(angle) * radius,
        stackSize: sortedGroup.length,
        stackIndex: index,
      };
    });
  });
};

const buildScreenPath = (transform) =>
  d3.geoPath(
    d3.geoTransform({
      point(lon, lat) {
        const [x, y] = projectPoint([lon, lat], transform);
        this.stream.point(x, y);
      },
    }),
  );

const markerTransform = (feature, transform = currentTransform) => {
  const [x, y] = projectPoint(feature.geometry.coordinates, transform);
  const offset = feature.__displayOffset ?? { dx: 0, dy: 0 };
  return `translate(${x + offset.dx},${y + offset.dy}) scale(1)`;
};

const wrapTileCoordinate = (value, max) => {
  const wrapped = value % max;
  return wrapped < 0 ? wrapped + max : wrapped;
};

const tileUrlFor = (z, x, y) =>
  tileUrlTemplate
    .replace("{z}", String(z))
    .replace("{x}", String(x))
    .replace("{y}", String(y));

const renderTiles = (transform) => {
  if (!tilesContainer) {
    return;
  }

  const zoomLevel = Math.max(
    minZoom,
    Math.min(maxZoom, Math.floor(Math.log2(transform.k))),
  );
  const levelScale = 2 ** zoomLevel;
  const tileScreenScale = transform.k / levelScale;
  const tilesPerAxis = 2 ** zoomLevel;

  const minTileX = Math.floor((-transform.x) / (tileSize * tileScreenScale));
  const maxTileX = Math.floor((width - transform.x) / (tileSize * tileScreenScale));
  const minTileY = Math.floor((-transform.y) / (tileSize * tileScreenScale));
  const maxTileY = Math.floor((height - transform.y) / (tileSize * tileScreenScale));

  const fragment = document.createDocumentFragment();

  for (let tileY = minTileY; tileY <= maxTileY; tileY += 1) {
    if (tileY < 0 || tileY >= tilesPerAxis) {
      continue;
    }

    for (let tileX = minTileX; tileX <= maxTileX; tileX += 1) {
      const image = document.createElement("img");
      image.className = "tile";
      image.alt = "";
      image.loading = "eager";
      image.decoding = "async";
      image.draggable = false;
      image.src = tileUrlFor(zoomLevel, wrapTileCoordinate(tileX, tilesPerAxis), tileY);
      image.style.width = `${tileSize * tileScreenScale}px`;
      image.style.height = `${tileSize * tileScreenScale}px`;
      image.style.left = `${tileX * tileSize * tileScreenScale + transform.x}px`;
      image.style.top = `${tileY * tileSize * tileScreenScale + transform.y}px`;
      fragment.append(image);
    }
  }

  tilesContainer.replaceChildren(fragment);
};

const renderBoundingBoxSelection = (transform, overlayRect) => {
  if (!overlayRect) {
    return;
  }
  const hasPredictionGridResult =
    activeDataViewTab === "prediction" &&
    datasetStore.prediction?.summary?.manual_bbox_grid &&
    typeof datasetStore.prediction.summary.manual_bbox_grid === "object";
  if (hasPredictionGridResult) {
    overlayRect.attr("display", "none");
    return;
  }
  const draft = mapBoundingBoxDraft;
  if (!draft) {
    overlayRect.attr("display", "none");
    return;
  }
  const northWest = projectPoint([draft.longitudeMin, draft.latitudeMax], transform);
  const southEast = projectPoint([draft.longitudeMax, draft.latitudeMin], transform);
  const x = Math.min(northWest[0], southEast[0]);
  const y = Math.min(northWest[1], southEast[1]);
  const rectWidth = Math.abs(southEast[0] - northWest[0]);
  const rectHeight = Math.abs(southEast[1] - northWest[1]);
  overlayRect
    .attr("display", rectWidth > 0 && rectHeight > 0 ? null : "none")
    .attr("x", x)
    .attr("y", y)
    .attr("width", rectWidth)
    .attr("height", rectHeight);
};

const buildManualGridPolygonFeature = (cell) => ({
  type: "Feature",
  geometry: {
    type: "Polygon",
    coordinates: [[
      [Number(cell.longitude_min), Number(cell.latitude_min)],
      [Number(cell.longitude_max), Number(cell.latitude_min)],
      [Number(cell.longitude_max), Number(cell.latitude_max)],
      [Number(cell.longitude_min), Number(cell.latitude_max)],
      [Number(cell.longitude_min), Number(cell.latitude_min)],
    ]],
  },
  properties: cell,
});

const buildManualGridScreenRectPath = (bounds, transform, paddingPx = 0) => {
  const northWest = projectPoint([bounds.longitudeMin, bounds.latitudeMax], transform);
  const southEast = projectPoint([bounds.longitudeMax, bounds.latitudeMin], transform);
  const x = Math.min(northWest[0], southEast[0]) - paddingPx;
  const y = Math.min(northWest[1], southEast[1]) - paddingPx;
  const widthValue = Math.abs(southEast[0] - northWest[0]) + paddingPx * 2;
  const heightValue = Math.abs(southEast[1] - northWest[1]) + paddingPx * 2;
  return `M${x},${y}H${x + widthValue}V${y + heightValue}H${x}Z`;
};

const normalizeManualGridCell = (cell) => ({
  ...cell,
  latitude_min: Number(cell.latitude_min),
  latitude_max: Number(cell.latitude_max),
  longitude_min: Number(cell.longitude_min),
  longitude_max: Number(cell.longitude_max),
  center_latitude: Number(cell.center_latitude),
  center_longitude: Number(cell.center_longitude),
});

const findManualGridCellIdForFeature = (feature, normalizedGridCells) => {
  const explicitGridCellId = String(feature?.properties?.["Forecast grid cell id"] ?? "").trim();
  if (explicitGridCellId) {
    return explicitGridCellId;
  }
  const longitude = asFloat(feature?.geometry?.coordinates?.[0]);
  const latitude = asFloat(feature?.geometry?.coordinates?.[1]);
  if (longitude === null || latitude === null) {
    return "";
  }
  const matchedCell = normalizedGridCells.find(
    (cell) =>
      Number.isFinite(cell.longitude_min) &&
      Number.isFinite(cell.longitude_max) &&
      Number.isFinite(cell.latitude_min) &&
      Number.isFinite(cell.latitude_max) &&
      longitude >= cell.longitude_min &&
      longitude <= cell.longitude_max &&
      latitude >= cell.latitude_min &&
      latitude <= cell.latitude_max,
  );
  return String(matchedCell?.grid_cell_id ?? "").trim();
};

const buildManualGridFeatureLookup = (gridCells) => {
  const predictionFeatures =
    activeDataViewTab === "prediction" ? datasetStore.prediction?.geojson?.features ?? [] : [];
  const normalizedGridCells = (gridCells ?? []).map(normalizeManualGridCell);
  const featureLookup = new Map();
  predictionFeatures.forEach((feature) => {
    const gridCellId = findManualGridCellIdForFeature(feature, normalizedGridCells);
    if (!gridCellId || featureLookup.has(gridCellId)) {
      return;
    }
    featureLookup.set(gridCellId, feature);
  });
  return featureLookup;
};

const getActiveManualGridPayload = () => {
  if (!(isPredictionWorkflowMode() && isRegionalManualMode() && activeDataViewTab === "prediction")) {
    return null;
  }
  const predictionGrid = datasetStore.prediction?.summary?.manual_bbox_grid;
  if (predictionGrid && typeof predictionGrid === "object") {
    return predictionGrid;
  }
  return regionalManualPreviewGrid && typeof regionalManualPreviewGrid === "object"
    ? regionalManualPreviewGrid
    : null;
};

const buildManualGridPredictedLookup = (gridCells) => {
  const predictionFeatures =
    activeDataViewTab === "prediction" ? datasetStore.prediction?.geojson?.features ?? [] : [];
  const normalizedGridCells = (gridCells ?? []).map(normalizeManualGridCell);
  const valuesByCell = new Map();
  predictionFeatures.forEach((feature) => {
    const gridCellId = findManualGridCellIdForFeature(feature, normalizedGridCells);
    const predictedValue = asFloat(getPredictedTargetValue(feature?.properties));
    if (!gridCellId || predictedValue === null) {
      return;
    }
    if (!valuesByCell.has(gridCellId)) {
      valuesByCell.set(gridCellId, []);
    }
    valuesByCell.get(gridCellId).push(predictedValue);
  });

  return new Map(
    Array.from(valuesByCell.entries()).map(([gridCellId, values]) => [
      gridCellId,
      d3.mean(values),
    ]),
  );
};

const buildManualGridWinningFeatureLookup = (gridCells) => {
  const predictionFeatures =
    activeDataViewTab === "prediction" ? datasetStore.prediction?.geojson?.features ?? [] : [];
  const normalizedGridCells = (gridCells ?? []).map(normalizeManualGridCell);
  const winners = new Map();
  predictionFeatures.forEach((feature) => {
    const gridCellId = findManualGridCellIdForFeature(feature, normalizedGridCells);
    const predictedValue = asFloat(getPredictedTargetValue(feature?.properties));
    if (!gridCellId || predictedValue === null) {
      return;
    }
    const current = winners.get(gridCellId);
    if (!current || predictedValue > current.predictedValue) {
      winners.set(gridCellId, { feature, predictedValue });
    }
  });
  return new Map(Array.from(winners.entries()).map(([gridCellId, payload]) => [gridCellId, payload.feature]));
};

const buildManualGridProfileFeatureLookup = (gridCells, profileLabel) => {
  const normalizedLabel = String(profileLabel ?? "").trim();
  if (!normalizedLabel) {
    return new Map();
  }
  const predictionFeatures =
    activeDataViewTab === "prediction" ? datasetStore.prediction?.geojson?.features ?? [] : [];
  const normalizedGridCells = (gridCells ?? []).map(normalizeManualGridCell);
  const winners = new Map();
  predictionFeatures.forEach((feature) => {
    const featureLabel = getPredictionCategoryLabelForFeature(feature);
    if (featureLabel !== normalizedLabel) {
      return;
    }
    const gridCellId = findManualGridCellIdForFeature(feature, normalizedGridCells);
    const predictedValue = asFloat(getPredictedTargetValue(feature?.properties));
    if (!gridCellId) {
      return;
    }
    const current = winners.get(gridCellId);
    if (predictedValue === null) {
      if (!current) {
        winners.set(gridCellId, { feature, predictedValue: Number.NEGATIVE_INFINITY });
      }
      return;
    }
    if (!current || predictedValue > current.predictedValue) {
      winners.set(gridCellId, { feature, predictedValue });
    }
  });
  return new Map(Array.from(winners.entries()).map(([gridCellId, payload]) => [gridCellId, payload.feature]));
};

const buildManualGridPredictedStats = (predictedLookup) => {
  const values = Array.from(predictedLookup.values()).filter((value) => Number.isFinite(value));
  if (!values.length) {
    return null;
  }
  const min = d3.min(values);
  const max = d3.max(values);
  if (!Number.isFinite(min) || !Number.isFinite(max)) {
    return null;
  }
  const step = max === min ? 0 : (max - min) / 4;
  return {
    min,
    max,
    q1Max: min + step,
    q2Max: min + step * 2,
    q3Max: min + step * 3,
  };
};

const getManualGridPredictedQuartileColor = (predictedValue, predictedStats) => {
  if (!Number.isFinite(predictedValue) || !predictedStats) {
    return "rgba(24, 69, 111, 0.18)";
  }
  if (predictedStats.max === predictedStats.min) {
    return "#245c9f";
  }
  if (predictedValue <= predictedStats.q1Max) {
    return "#8f1d1d";
  }
  if (predictedValue <= predictedStats.q2Max) {
    return "#d46a6a";
  }
  if (predictedValue <= predictedStats.q3Max) {
    return "#8eb8e5";
  }
  return "#245c9f";
};

const getManualGridPredictedGradientColor = (predictedValue, predictedStats) => {
  if (!Number.isFinite(predictedValue) || !predictedStats) {
    return "rgba(24, 69, 111, 0.18)";
  }
  if (predictedStats.max === predictedStats.min) {
    return "#245c9f";
  }
  const colorScale = d3
    .scaleLinear()
    .domain([
      predictedStats.min,
      predictedStats.q1Max,
      predictedStats.q2Max,
      predictedStats.q3Max,
      predictedStats.max,
    ])
    .range(["#8f1d1d", "#d46a6a", "#d46a6a", "#8eb8e5", "#245c9f"])
    .interpolate(d3.interpolateLab)
    .clamp(true);
  return colorScale(predictedValue);
};

const buildManualGridHeatSamples = (gridCells, predictedLookup) => {
  const normalizedGridCells = (gridCells ?? []).map(normalizeManualGridCell);
  const valuedCells = normalizedGridCells
    .map((cell) => ({
      ...cell,
      predictedValue: predictedLookup.get(String(cell.grid_cell_id ?? "")),
    }))
    .filter((cell) => Number.isFinite(cell.predictedValue));
  if (!valuedCells.length) {
    return [];
  }
  const samples = [];
  const subdivisionsPerCell = 10;
  valuedCells.forEach((cell) => {
    const lonStep = (cell.longitude_max - cell.longitude_min) / subdivisionsPerCell;
    const latStep = (cell.latitude_max - cell.latitude_min) / subdivisionsPerCell;
    for (let row = 0; row < subdivisionsPerCell; row += 1) {
      for (let column = 0; column < subdivisionsPerCell; column += 1) {
        const longitudeMin = cell.longitude_min + lonStep * column;
        const longitudeMax = column === subdivisionsPerCell - 1 ? cell.longitude_max : longitudeMin + lonStep;
        const latitudeMin = cell.latitude_min + latStep * row;
        const latitudeMax = row === subdivisionsPerCell - 1 ? cell.latitude_max : latitudeMin + latStep;
        const centerLongitude = (longitudeMin + longitudeMax) / 2;
        const centerLatitude = (latitudeMin + latitudeMax) / 2;
        let weightedDifference = 0;
        let totalWeight = 0;
        valuedCells.forEach((valuedCell) => {
          const distance =
            Math.hypot(
              centerLongitude - valuedCell.center_longitude,
              centerLatitude - valuedCell.center_latitude,
            ) || 0.000001;
          const weight = 1 / distance ** 2;
          weightedDifference += valuedCell.predictedValue * weight;
          totalWeight += weight;
        });
        samples.push({
          id: `${cell.grid_cell_id}:${row}:${column}`,
          longitudeMin,
          longitudeMax,
          latitudeMin,
          latitudeMax,
          predictedValue: totalWeight > 0 ? weightedDifference / totalWeight : cell.predictedValue,
        });
      }
    }
  });
  return samples;
};

const buildManualGridProfileHeatSamples = (gridCells, featureLookup) => {
  const normalizedGridCells = (gridCells ?? []).map(normalizeManualGridCell);
  return normalizedGridCells
    .map((cell) => ({
      id: String(cell.grid_cell_id ?? ""),
      longitudeMin: cell.longitude_min,
      longitudeMax: cell.longitude_max,
      latitudeMin: cell.latitude_min,
      latitudeMax: cell.latitude_max,
      profileLabel: getPredictionCategoryLabelForFeature(
        featureLookup.get(String(cell.grid_cell_id ?? "")),
      ),
    }))
    .filter((cell) => cell.profileLabel);
};

const MANUAL_GRID_SMOOTH_FILTER_ID = "manual-grid-smooth-filter";
const MANUAL_GRID_QUARTILE_SAMPLE_PADDING_PX = 2.25;
const MANUAL_GRID_CATEGORICAL_SAMPLE_PADDING_PX = 0;
const MANUAL_GRID_QUARTILE_HEAT_OPACITY = 0.46;

const isManualGridPredictionResult = () =>
  activeDataViewTab === "prediction" &&
  currentRenderedFlowMode === "saved_model" &&
  datasetStore.prediction?.summary?.climate_scope === "regional_manual";

const renderManualGridOverlay = (transform) => {
  if (!mapContext?.manualGridHeatLayer || !mapContext?.manualGridCellsLayer || !mapContext?.manualGridMarkersLayer) {
    return;
  }
  const gridPayload = getActiveManualGridPayload();
  const gridCells = Array.isArray(gridPayload?.cells) ? gridPayload.cells : [];
  if (!gridCells.length) {
    mapContext.manualGridHeatLayer.selectAll("path").remove();
    mapContext.manualGridCellsLayer.selectAll("path").remove();
    mapContext.manualGridMarkersLayer.selectAll("circle").remove();
    return;
  }

  const predictedLookup = buildManualGridPredictedLookup(gridCells);
  const predictedStats = buildManualGridPredictedStats(predictedLookup);
  const multiProfileMode = isCategoricalPredictionColorMode();
  const activeProfileLabel = getActivePredictionProfileLabel();
  const featureLookup = multiProfileMode
    ? (activeProfileLabel
        ? buildManualGridWinningFeatureLookup(gridCells, new Set([activeProfileLabel]))
        : buildManualGridWinningFeatureLookup(gridCells))
    : buildManualGridFeatureLookup(gridCells);
  const hasPredictionValues = (multiProfileMode ? featureLookup.size : predictedLookup.size) > 0 && activeDataViewTab === "prediction";
  const path = buildScreenPath(transform);
  const heatSamples = multiProfileMode
    ? buildManualGridProfileHeatSamples(gridCells, featureLookup)
    : hasPredictionValues
      ? buildManualGridHeatSamples(gridCells, predictedLookup)
      : [];

  mapContext.manualGridHeatLayer
    .selectAll("path")
    .data(heatSamples, (sample) => sample.id)
    .join("path")
    .attr(
      "d",
      (sample) => buildManualGridScreenRectPath(
        sample,
        transform,
        hasPredictionValues
          ? (multiProfileMode ? MANUAL_GRID_CATEGORICAL_SAMPLE_PADDING_PX : MANUAL_GRID_QUARTILE_SAMPLE_PADDING_PX)
          : 0,
      ),
    )
    .style("fill", (sample) => multiProfileMode
      ? toMarkerColorAlpha(getPredictionProfileColor(sample.profileLabel), 0.42)
      : toMarkerColorAlpha(getManualGridPredictedGradientColor(sample.predictedValue, predictedStats), 0.42))
    .style("opacity", (sample) => {
      if (!multiProfileMode) {
        return 1;
      }
      const highlightedLabel = getActivePredictionProfileLabel();
      if (!highlightedLabel) {
        return 1;
      }
      return String(sample.profileLabel ?? "").trim() === highlightedLabel ? 1 : 0.12;
    })
    .style("stroke", "none")
    .style("display", hasPredictionValues ? null : "none");

  mapContext.manualGridHeatLayer
    .attr("filter", hasPredictionValues ? `url(#${MANUAL_GRID_SMOOTH_FILTER_ID})` : null)
    .style("opacity", hasPredictionValues ? MANUAL_GRID_QUARTILE_HEAT_OPACITY : 1);

  mapContext.manualGridCellsLayer
    .selectAll("path")
    .data(gridCells, (cell) => String(cell.grid_cell_id ?? ""))
    .join("path")
    .attr("class", "manual-grid-cell")
    .attr("d", (cell) => path(buildManualGridPolygonFeature(cell)))
    .style("fill", "transparent")
    .style("fill-opacity", 1)
    .style("stroke", (cell) => {
      if (!hasPredictionValues) {
        return "rgba(24, 69, 111, 0.52)";
      }
      if (multiProfileMode) {
        return "transparent";
      }
      const predictedValue = predictedLookup.get(String(cell.grid_cell_id ?? ""));
      if (!Number.isFinite(predictedValue)) {
        return "rgba(24, 69, 111, 0.32)";
      }
      return toMarkerColorAlpha(getManualGridPredictedQuartileColor(predictedValue, predictedStats), 0.68);
    })
    .style("stroke-opacity", multiProfileMode ? 0 : hasPredictionValues ? 0 : 0.55)
    .style("stroke-width", multiProfileMode ? 0 : hasPredictionValues ? 0 : 1.1)
    .style("stroke-dasharray", hasPredictionValues ? null : "6 4")
    .style("pointer-events", hasPredictionValues ? "all" : "none")
    .style("cursor", hasPredictionValues ? "pointer" : "default")
    .on("mouseenter", (event, cell) => {
      if (!hasPredictionValues) {
        return;
      }
      const feature = featureLookup.get(String(cell.grid_cell_id ?? ""));
      if (!feature) {
        return;
      }
      showTooltip(event, feature);
    })
    .on("mousemove", (event, cell) => {
      if (!hasPredictionValues) {
        return;
      }
      const feature = featureLookup.get(String(cell.grid_cell_id ?? ""));
      if (!feature) {
        return;
      }
      showTooltip(event, feature);
    })
    .on("mouseleave", () => {
      if (hasPredictionValues) {
        hideTooltip();
      }
    })
    .on("click", (_, cell) => {
      if (!hasPredictionValues) {
        return;
      }
      const feature = featureLookup.get(String(cell.grid_cell_id ?? ""));
      if (!feature) {
        return;
      }
      selectedFeature = feature;
      currentPage = 0;
      renderDetails();
    });

  mapContext.manualGridMarkersLayer
    .selectAll("circle")
    .data(hasPredictionValues ? [] : gridCells, (cell) => String(cell.grid_cell_id ?? ""))
    .join("circle")
    .attr("class", "manual-grid-center")
    .attr("cx", (cell) => projectPoint([Number(cell.center_longitude), Number(cell.center_latitude)], transform)[0])
    .attr("cy", (cell) => projectPoint([Number(cell.center_longitude), Number(cell.center_latitude)], transform)[1])
    .attr("r", 3.8)
    .style("fill", "#4b9a73")
    .style("stroke", "rgba(255,255,255,0.9)")
    .style("stroke-width", 1.2)
    .style("opacity", 0.88);
};

const setupMapBase = async () => {
  const heatDefs = svg.append("defs");
  heatDefs
    .append("filter")
    .attr("id", MANUAL_GRID_SMOOTH_FILTER_ID)
    .attr("x", "-22%")
    .attr("y", "-22%")
    .attr("width", "144%")
    .attr("height", "144%")
    .append("feGaussianBlur")
    .attr("in", "SourceGraphic")
    .attr("stdDeviation", 2.9);

  const rootLayer = svg.append("g");
  const mapLayer = rootLayer.append("g");
  const labelsLayer = rootLayer.append("g");
  const selectionLayer = rootLayer.append("g").attr("class", "bbox-selection-layer");
  const manualGridHeatLayer = rootLayer.append("g").attr("class", "manual-grid-heat-layer");
  const manualGridCellsLayer = rootLayer.append("g").attr("class", "manual-grid-cells-layer");
  const manualGridMarkersLayer = rootLayer.append("g").attr("class", "manual-grid-markers-layer");
  const markersLayer = rootLayer.append("g");
  const bboxSelectionRect = selectionLayer
    .append("rect")
    .attr("class", "bbox-selection-rect")
    .attr("display", "none");
  const domainOutline = mapLayer.append("path").attr("class", "domain-outline");
  const graticulePath = mapLayer
    .append("path")
    .datum(d3.geoGraticule().step([10, 10]))
    .attr("class", "graticule");

  let world = { features: [] };
  try {
    const loadedWorld = await d3.json("./data/world.geojson");
    if (loadedWorld?.features) {
      world = loadedWorld;
    }
  } catch (error) {
    console.warn("World layer could not be loaded.", error);
  }

  const countryColor = d3
    .scaleOrdinal()
    .domain(world.features.map((feature) => feature.properties.name))
    .range(countryPalette);

  const countryPaths = mapLayer
    .selectAll("path.country")
    .data(world.features)
    .join("path")
    .attr("class", "country")
    .attr("fill", (feature) => countryColor(feature.properties.name));

  const countryBoundaries = mapLayer
    .append("path")
    .datum({ type: "FeatureCollection", features: world.features })
    .attr("class", "country-boundary");

  const countryLabels = labelsLayer
    .selectAll("text")
    .data(world.features)
    .join("text")
    .attr("class", "country-label")
    .text((feature) => feature.properties.name);

  const renderBase = (transform) => {
    currentTransform = transform;
    renderTiles(transform);
    const path = buildScreenPath(transform);
    countryPaths.attr("d", path);
    countryBoundaries.attr("d", path);
    graticulePath.attr("d", path);
    countryLabels
      .attr("x", (feature) => path.centroid(feature)[0])
      .attr("y", (feature) => path.centroid(feature)[1])
      .style("display", (feature) => {
        const [x, y] = path.centroid(feature);
        const area = path.area(feature);
        return Number.isFinite(x) &&
          Number.isFinite(y) &&
          x > 0 &&
          x < width &&
          y > 0 &&
          y < height &&
          area > 180
          ? "block"
          : "none";
      })
      .style("font-size", "11px");

    if (mapContext?.markerGroups) {
      mapContext.markerGroups.attr("transform", (feature) => markerTransform(feature, transform));
    }
    if (mapContext?.domainFeature) {
      domainOutline.datum(mapContext.domainFeature).attr("d", path);
    } else {
      domainOutline.attr("d", null);
    }
    renderBoundingBoxSelection(transform, bboxSelectionRect);
    renderManualGridOverlay(transform);
  };

  mapContext = {
    manualGridHeatLayer,
    manualGridCellsLayer,
    manualGridMarkersLayer,
    markersLayer,
    markerGroups: null,
    domainFeature: null,
    bboxSelectionRect,
    renderBase,
  };

  initialTransform = computeTransformFromPolygon([
    [-25, -38],
    [60, -38],
    [60, 38],
    [-25, 38],
    [-25, -38],
  ]);

  zoomBehavior = d3
    .zoom()
    .scaleExtent([2 ** minZoom, 2 ** maxZoom])
    .translateExtent([
      [-800, -800],
      [width + 800, height + 800],
    ])
    .on("zoom", (event) => {
      renderBase(event.transform);
    });

  svg.call(zoomBehavior);
  svg.call(zoomBehavior.transform, initialTransform);

  svg
    .on("pointerdown.bbox-selection", (event) => {
      if (!(mapBoundingBoxSelectionMode && isPredictionWorkflowMode() && isRegionalManualMode())) {
        return;
      }
      const [x, y] = d3.pointer(event, svg.node());
      const coordinates = screenPointToCoordinates(x, y);
      if (!coordinates) {
        return;
      }
      event.preventDefault();
      event.stopPropagation();
      mapBoundingBoxSelectionStart = coordinates;
      mapBoundingBoxDraft = normalizeBoundsFromCoordinates(coordinates, coordinates);
      if (mapContext) {
        mapContext.renderBase(currentTransform);
      }
    })
    .on("pointermove.bbox-selection", (event) => {
      if (!mapBoundingBoxSelectionStart) {
        return;
      }
      const [x, y] = d3.pointer(event, svg.node());
      const coordinates = screenPointToCoordinates(x, y);
      if (!coordinates) {
        return;
      }
      event.preventDefault();
      event.stopPropagation();
      mapBoundingBoxDraft = normalizeBoundsFromCoordinates(mapBoundingBoxSelectionStart, coordinates);
      if (mapContext) {
        mapContext.renderBase(currentTransform);
      }
    })
    .on("pointerup.bbox-selection", (event) => {
      if (!mapBoundingBoxSelectionStart) {
        return;
      }
      const [x, y] = d3.pointer(event, svg.node());
      const coordinates = screenPointToCoordinates(x, y) ?? mapBoundingBoxSelectionStart;
      event.preventDefault();
      event.stopPropagation();
      const bounds = normalizeBoundsFromCoordinates(mapBoundingBoxSelectionStart, coordinates);
      mapBoundingBoxSelectionStart = null;
      if (!bounds) {
        clearMapBoundingBoxSelection();
        return;
      }
      mapBoundingBoxDraft = bounds;
      setManualBoundsInputs(bounds);
      clearMapBoundingBoxSelection({ preserveDraft: true });
      renderManualRegionalPreview().catch((error) => {
        console.error(error);
      });
    });
};

const clearMarkers = () => {
  hideTooltip();
  selectedFeature = null;
  currentPage = 0;
  loadedFeatures = [];
  predictedYieldStats = null;
  activePredictionProfileHighlight = "";
  currentRenderedFlowMode = "automatic";
  setWorkflowInteractive(false);
  if (mapContext?.markersLayer) {
    mapContext.markersLayer.selectAll("*").remove();
  }
  if (mapContext?.manualGridHeatLayer) {
    mapContext.manualGridHeatLayer.selectAll("*").remove();
  }
  if (mapContext) {
    mapContext.markerGroups = null;
    mapContext.domainFeature = null;
    mapContext.renderBase(currentTransform);
  }
  resetDetails();
};

const registerDataset = (tab, geojson, sourceName, renderFlowMode, summary = null) => {
  datasetStore[tab] = {
    geojson,
    sourceName,
    renderFlowMode,
    summary,
  };
  if (tab === "top_germplasm") {
    topGermplasmPreviewStart = 0;
  }
  updateDataViewTabs();
};

const applyFeatureCollection = async (
  geojson,
  sourceName,
  { renderFlowMode = "automatic", showLoadingState = true } = {},
) => {
  if (!mapContext) {
    throw new Error("The map is still initializing. Please try the upload again.");
  }

  const points = geojson.features;
  assignOverlappingMarkerOffsets(points, {
    useProximityBuckets: renderFlowMode === "saved_model",
  });
  loadedFeatures = points;
  const longitudes = points.map((feature) => feature.geometry.coordinates[0]);
  const latitudes = points.map((feature) => feature.geometry.coordinates[1]);
  const predictedValues = points
    .map((feature) => asFloat(getPredictedTargetValue(feature.properties)))
    .filter((value) => value !== null);
  const absoluteErrors = points
    .map((feature) => {
      const actual = asFloat(getObservedTargetValue(feature?.properties));
      const predicted = asFloat(getPredictedTargetValue(feature?.properties));
      if (actual === null || predicted === null) {
        return null;
      }
      return Math.abs(actual - predicted);
    })
    .filter((value) => value !== null)
    .sort((left, right) => left - right);

  clearMarkers();
  loadedFeatures = points;
  currentRenderedFlowMode = renderFlowMode;
  setLegendState(renderFlowMode);
  if (showLoadingState) {
    await setLoadingState(70, "Building Geocoordinates", "Drawing points and enabling interactions.");
  }

  if (renderFlowMode === "saved_model" && predictedValues.length) {
    predictedYieldStats = {
      min: d3.min(predictedValues),
      mean: d3.mean(predictedValues),
      max: d3.max(predictedValues),
    };
  } else {
    predictedYieldStats = null;
  }
  if (renderFlowMode !== "saved_model" && absoluteErrors.length) {
    trainingErrorQuartiles = {
      q1: d3.quantileSorted(absoluteErrors, 0.25) ?? absoluteErrors[0],
      q2: d3.quantileSorted(absoluteErrors, 0.5) ?? absoluteErrors[absoluteErrors.length - 1],
      q3: d3.quantileSorted(absoluteErrors, 0.75) ?? absoluteErrors[absoluteErrors.length - 1],
    };
  } else {
    trainingErrorQuartiles = null;
  }
  updateTrainingMetricVisibility();

  mapContext.domainFeature = {
    type: "Feature",
    geometry: {
      type: "Polygon",
      coordinates: [createBoundingPolygon(points)],
    },
  };

  const showPointMarkers = !(
    renderFlowMode === "saved_model"
    && activeDataViewTab === "prediction"
    && datasetStore.prediction?.summary?.climate_scope === "regional_manual"
  );
  const markerGroups = mapContext.markersLayer
    .selectAll("g")
    .data(showPointMarkers ? points : [])
    .join("g")
    .attr("class", "point")
    .style("pointer-events", "all")
    .on("mouseenter", (event, feature) => showTooltip(event, feature))
    .on("mousemove", (event, feature) => showTooltip(event, feature))
    .on("mouseleave", hideTooltip)
    .on("click", (_, feature) => {
      focusFeatureOnMap(feature);
    });

  markerGroups
    .append("path")
    .attr("class", "marker-pin")
    .attr("d", markerPath)
    .style("fill", (feature) => getMarkerColor(feature))
    .style("pointer-events", "all");
  if (!(renderFlowMode === "saved_model" && activeDataViewTab === "prediction" && datasetStore.prediction?.summary?.climate_scope === "regional_manual")) {
    markerGroups.append("circle").attr("class", "marker-center").attr("r", 2.6).attr("cy", -2.5).style("pointer-events", "all");
  }
  mapContext.markerGroups = markerGroups;

  if (showLoadingState) {
    await setLoadingState(85, "Updating view", "Calculating initial zoom and record detail.");
  }
  const initialPolygon = createBoundingPolygon(points);
  initialTransform =
    renderFlowMode === "saved_model"
      ? computeTransformFromPolygon(initialPolygon)
      : computeTransformForMarkers(initialPolygon, points, {
          baseMargin: 64,
          markerPadding: 24,
        });
  svg.call(zoomBehavior.transform, initialTransform);

  if (isMultiGermplasmPredictionResult()) {
    const bestCategoryLabel = getBestPredictionCategoryLabelByMean();
    selectedFeature = getBestFeatureForProfileLabel(bestCategoryLabel) ?? points[0];
  } else {
    selectedFeature = points[0];
  }
  markerGroups.classed("active", (datum) => datum === selectedFeature);
  if (isCategoricalPredictionColorMode()) {
    setActivePredictionProfileHighlight(getPredictionCategoryLabelForFeature(selectedFeature));
  } else {
    setActivePredictionProfileHighlight("");
  }
  updateProfileHighlightState();
  setWorkflowInteractive(true);

  statsContainer.replaceChildren(
    createStat("Points", formatNumber(points.length)),
    createStat("Attributes", formatNumber(geojson.metadata.attribute_count)),
    createStat("Zoom", "Geocoordinates validated"),
    createStat("Min Latitude", formatCoordinate(d3.min(latitudes))),
    createStat("Max Latitude", formatCoordinate(d3.max(latitudes))),
    createStat("Min Longitude", formatCoordinate(d3.min(longitudes))),
    createStat("Max Longitude", formatCoordinate(d3.max(longitudes))),
  );

  setActiveSummaryTab("countries");
  setActiveDetailsTab("germplasm");
  renderCountrySummary(points);
  renderSummaryLog(getActiveDatasetSummary());
  renderDetails();
  renderColorHelp();
  tabGermplasmButton.focus();
  if (showLoadingState) {
    await setLoadingState(
      100,
      "Upload complete",
      `File processed successfully: ${sourceName}.`,
    );
  }
};

const showDatasetInView = async (tab, { force = false } = {}) => {
  const dataset = datasetStore[tab];
  if (!dataset) {
    activeDataViewTab = tab;
    updateDataViewTabs();
    clearMarkers();
    renderEmptyStats();
    setLegendState(tab === "prediction" ? "saved_model" : tab === "training" ? "automatic" : "original");
    renderColorHelp();
    return;
  }
  if (!force && activeDataViewTab === tab) {
    return;
  }
  activeDataViewTab = tab;
  updateDataViewTabs();
  await applyFeatureCollection(dataset.geojson, dataset.sourceName, {
    renderFlowMode: dataset.renderFlowMode,
    showLoadingState: false,
  });
};

const resetLoadedResults = () => {
  resetDatasetStore();
  clearMarkers();
  renderEmptyStats();
  setLegendState("automatic");
  renderColorHelp();
};

const buildPreprocessOriginalDataset = (payload, fallbackSourceName = "") => {
  const rawGeojson = payload?.preprocess_geojson;
  if (!rawGeojson || typeof rawGeojson !== "object") {
    return null;
  }
  const geojson = validateFeatureCollection(rawGeojson);
  return {
    geojson,
    sourceName:
      String(payload?.summary?.phase06_xlsx ?? "").trim() ||
      String(payload?.source_name ?? fallbackSourceName).trim() ||
      fallbackSourceName,
    summary: payload?.summary ?? null,
  };
};

const renderPreprocessOriginalMapFromPayload = async (payload, fallbackSourceName = "") => {
  const preprocessOriginalDataset = buildPreprocessOriginalDataset(payload, fallbackSourceName);
  if (!preprocessOriginalDataset) {
    return false;
  }
  registerDataset(
    "original",
    preprocessOriginalDataset.geojson,
    preprocessOriginalDataset.sourceName,
    "original",
    preprocessOriginalDataset.summary,
  );
  await showDatasetInView("original", { force: true });
  return true;
};

const handleFileUpload = async (event) => {
  const [file] = event.target.files ?? [];
  if (!file) {
    return;
  }
  if (selectionPropertiesFlowEnabled && !isPredictionWorkflowMode()) {
    try {
      await handleSelectionPropertiesUpload(file);
    } catch (error) {
      console.error(error);
      resetSelectionPropertiesState();
      renderSelectionPropertiesControls();
      await setLoadingState(
        100,
        "Upload error",
        error instanceof Error ? error.message : "The workbook columns could not be loaded.",
      );
      setSelectionPropertiesBadge("Upload error");
      setSelectionPropertiesStatus(
        error instanceof Error ? error.message : "The workbook columns could not be loaded.",
      );
    }
    return;
  }
  const selectedModel = isPredictionWorkflowMode() ? getSelectedSavedModel() : null;
  if (isPredictionWorkflowMode()) {
    if (!selectedModel) {
      if (fileInput) {
        fileInput.value = "";
      }
      window.alert("The workspace model is not ready yet in the High-Potential Sites tab.");
      return;
    }
    if (!selectedClimateScope) {
      if (fileInput) {
        fileInput.value = "";
      }
      window.alert("The climate scope is fixed to Manual bounding box climate grid for High-Potential Sites.");
      return;
    }
    if (selectedClimateScope === "regional_manual" && !hasCompleteManualBounds()) {
      if (fileInput) {
        fileInput.value = "";
      }
      window.alert("Complete latitude and longitude min/max for the Manual bounding box climate grid before uploading the workbook.");
      return;
    }
    try {
      pendingSavedModelFile = file;
      await clearDataset("prediction");
      resetPreprocessValidationState();
      if (predictionBridgeState?.isAvailable && selectedClimateScope === "point") {
        availableGermplasmNames = [...predictionBridgeState.germplasmNames];
        if (!selectedGermplasmNames.size) {
          selectedGermplasmNames = new Set(predictionBridgeState.selectedNames);
        }
        if (germplasmSelectionPanel) {
          germplasmSelectionPanel.hidden = false;
        }
        if (germplasmSelectionHelp) {
          germplasmSelectionHelp.textContent =
            `Rows were loaded from ${file.name}. The germplasm selection stays linked to the completed Training flow.`;
        }
        renderGermplasmSelectionList();
        await setLoadingState(
          0,
          "Ready to run",
          "Review the germplasm checklist, adjust the selection, and click Run.",
          false,
        );
        return;
      }
      await loadPredictionGermplasmList(file, { sourceLabel: file.name, mode: "uploaded" });
      return;
    } catch (error) {
      console.error(error);
      resetPendingGermplasmSelection();
      resetLoadedResults();
      await setLoadingState(
        100,
        "Upload error",
        error instanceof Error ? error.message : "The germplasm list could not be loaded.",
      );
      return;
    }
  }
  const forecastPlantingDate = forecastPlantingDateInput?.value?.trim() ?? "";
  const forecastHarvestingDate = forecastHarvestingDateInput?.value?.trim() ?? "";
  const effectiveClimateScope = getEffectiveClimateScope();
  const runtimeClimateScope = effectiveClimateScope === "default" ? "point" : effectiveClimateScope;
  const selectedGermplasmProjectionMode =
    predictionBridgeState?.isAvailable &&
    (selectedClimateScope === "default" || selectedClimateScope === "point")
      ? "all_markers"
      : "";
  const projectionTemplateWorkbook =
    predictionBridgeState?.isAvailable &&
    (selectedClimateScope === "default" || selectedClimateScope === "point")
      ? String(predictionBridgeState.templateWorkbookPath ?? "").trim()
      : "";
  const regionalCountry = regionalCountrySelect?.value?.trim() ?? "";
  const regionalBounds = {
    label: "Manual bounds",
    latitudeMin: parseRegionalBoundNumber(regionalBoundsLatitudeMinInput),
    latitudeMax: parseRegionalBoundNumber(regionalBoundsLatitudeMaxInput),
    longitudeMin: parseRegionalBoundNumber(regionalBoundsLongitudeMinInput),
    longitudeMax: parseRegionalBoundNumber(regionalBoundsLongitudeMaxInput),
  };
  if (selectedModel && effectiveClimateScope === "country_localities" && !regionalCountry) {
    window.alert("When you choose country-localities climate mode, you must select an African country.");
    return;
  }
  if (
    selectedModel &&
    effectiveClimateScope === "regional_manual" &&
    (
      regionalBounds.latitudeMin === null ||
      regionalBounds.latitudeMax === null ||
      regionalBounds.longitudeMin === null ||
      regionalBounds.longitudeMax === null
    )
  ) {
    window.alert("When you choose manual regional climate mode, you must complete latitude and longitude min/max.");
    return;
  }

  try {
    restoreLoadingPanelHome();
    resetLoadedResults();
    resetPreprocessValidationState();
    await setLoadingState(
      6,
      "Reading workbook",
      `Uploading ${file.name} to start cimmyt_app/preprocess. The Original Data tab will stay tied to the preprocess output, not the raw workbook.`,
    );
    await setLoadingState(
      10,
      "Uploading file",
      selectedModel && preprocessValidationEnabled
        ? `Sending ${file.name}, preparing the preprocess validation workbook, and reusing saved model ${selectedModel.model_id}.`
        : selectedModel
          ? `Sending ${file.name} and reusing saved model ${selectedModel.model_id}.`
        : `Sending ${file.name} to the local processing pipeline.`,
    );
    const payload = await processFileWithStatusTimeline(file, {
      selectedModelId: "",
      selectedGermplasmNames: [],
      forecastPlantingDate,
      forecastHarvestingDate,
      pauseAfterPreprocess: preprocessValidationEnabled,
      climateScope: effectiveClimateScope,
      regionalCountry: "",
      regionalBounds: null,
    });
    if (payload?.status === "paused") {
      await showPausedPreprocessValidation(payload);
      return;
    }
    await setLoadingState(
      94,
      "Preparing map output",
      "Building the final geospatial dataset and validating the processed Geocoordinates.",
    );
    const geojson = preparePredictionGeojsonForDisplay(
      await resolvePipelineGeojson(payload),
      payload.summary ?? null,
    );
    await setLoadingState(
      97,
      "Validating Geocoordinates",
      `${geojson.features.length} Geocoordinates with coordinates were returned by the pipeline.`,
    );
    const preprocessOriginalDataset = buildPreprocessOriginalDataset(payload, file.name);
    if (preprocessOriginalDataset) {
      registerDataset(
        "original",
        preprocessOriginalDataset.geojson,
        preprocessOriginalDataset.sourceName,
        "original",
        preprocessOriginalDataset.summary,
      );
    }
    registerDataset("training", geojson, payload.source_name ?? file.name, "automatic", payload.summary ?? null);
    updateDataViewTabs();
    activeDataViewTab = "original";
    updateDataViewTabs();
    if (preprocessOriginalDataset) {
      await showDatasetInView("original", { force: true });
    }
    await promptForGeneratedModelNameIfNeeded(payload.summary ?? null);
    primePredictionBridgeFromTraining(file, datasetStore.training?.summary ?? payload.summary ?? null);
    await setLoadingState(
      100,
      "Training complete",
      `Original Data now reflects the preprocess output with ${preprocessOriginalDataset?.geojson?.features?.length ?? geojson.features.length} mapped records. Open the Training tab to inspect the model-ready output.`,
      true,
    );
    await refreshSavedModels();
  } catch (error) {
    console.error(error);
    datasetStore.prediction = null;
    updateDataViewTabs();
    await setLoadingState(
      100,
      "Upload error",
      error instanceof Error ? error.message : "The file could not be processed.",
    );
  }
};

const handleContinueAfterPreprocess = async () => {
  if (legacyPipelineDisabled) {
    notifyLegacyFlowBlocked("Continue after preprocess");
    return;
  }
  if (!pausedPreprocessPayload?.continue_url) {
    return;
  }
  try {
    mountLoadingPanelInPrediction();
    activeDataViewTab = "prediction";
    updateDataViewTabs();
    if (continueAfterPreprocessButton) {
      continueAfterPreprocessButton.disabled = true;
    }
    await setLoadingState(
      54,
      "Resuming selected model flow",
      "Continuing from the validated preprocess phase06 workbook and running the selected saved model.",
    );
    const continuePayload = await continuePipelineJob(pausedPreprocessPayload.continue_url);
    const statusUrl = continuePayload?.status_url;
    if (!statusUrl) {
      throw new Error("The pipeline did not return a valid status URL when continuing.");
    }
    persistActivePipelineJob({
      jobId: continuePayload?.job_id ?? pausedPreprocessPayload?.job_id ?? "",
      statusUrl,
      sourceName: pausedPreprocessPayload?.source_name ?? "Validated preprocess output",
      state: "running",
      workflowMode: "prediction",
      predictionMode: true,
    });
    const payload = await pollPipelineStatus(statusUrl, {
      sourceName: pausedPreprocessPayload?.source_name ?? "validated preprocess output",
      lastPercent: 54,
      predictionMode: true,
    });
    if (payload?.status === "paused") {
      await showPausedPreprocessValidation(payload, { updateOriginalData: false });
      return;
    }
    if (preprocessValidationPanel) {
      preprocessValidationPanel.hidden = true;
    }
    clearActivePipelineJob();
    const geojson = filterPredictionGeojsonToSelectedNames(
      preparePredictionGeojsonForDisplay(
        await resolvePipelineGeojson(payload),
        payload.summary ?? null,
      ),
      Array.from(selectedGermplasmNames),
    );
    await setLoadingState(
      97,
      "Validating Geocoordinates",
      `${geojson.features.length} Geocoordinates with coordinates were returned by the pipeline.`,
    );
    registerDataset(
      "prediction",
      geojson,
      payload.source_name ?? "Validated preprocess output",
      "saved_model",
      payload.summary ?? null,
    );
    await showDatasetInView("prediction", { force: true });
    if (predictionBridgeState?.isAvailable && selectedClimateScope === "default") {
      if (germplasmSelectionPanel) {
        germplasmSelectionPanel.hidden = false;
      }
      renderGermplasmSelectionList();
    }
    triggerBrowserDownload(payload?.prediction_output_download_url);
    await setLoadingState(
      100,
      "High-Potential Sites complete",
      "The validated saved-model output is ready in the High-Potential Sites tab.",
      true,
    );
    scheduleLoadingPanelReset();
    await refreshSavedModels();
  } catch (error) {
    console.error(error);
    if (continueAfterPreprocessButton) {
      continueAfterPreprocessButton.disabled = false;
    }
    await setLoadingState(
      100,
      "Upload error",
      error instanceof Error ? error.message : "The pipeline could not continue after preprocess validation.",
    );
  }
};

const handleExecuteSelectedGermplasm = async () => {
  if (legacyPipelineDisabled) {
    notifyLegacyFlowBlocked("Selected germplasm execution");
    return;
  }
  if (selectedGermplasmRunInProgress) {
    return;
  }
  const file =
    predictionBridgeState?.isAvailable && selectedClimateScope === "default"
      ? predictionBridgeState.sourceFile ?? predictionBridgeState.file ?? pendingSavedModelFile
      : pendingSavedModelFile;
  if (!file) {
    window.alert("Select an Excel file first.");
    return;
  }

  const selectedModel = getSelectedSavedModel();
  const forecastPlantingDate = forecastPlantingDateInput?.value?.trim() ?? "";
  const forecastHarvestingDate = forecastHarvestingDateInput?.value?.trim() ?? "";
  const effectiveClimateScope = getEffectiveClimateScope();
  const runtimeClimateScope = effectiveClimateScope === "default" ? "point" : effectiveClimateScope;
  const selectedGermplasmProjectionMode =
    predictionBridgeState?.isAvailable &&
    (selectedClimateScope === "default" || selectedClimateScope === "point")
      ? "all_markers"
      : "";
  const projectionTemplateWorkbook =
    predictionBridgeState?.isAvailable &&
    (selectedClimateScope === "default" || selectedClimateScope === "point")
      ? String(predictionBridgeState.templateWorkbookPath ?? "").trim()
      : "";
  const regionalCountry = regionalCountrySelect?.value?.trim() ?? "";
  const regionalBounds = {
    label: "Manual bounds",
    latitudeMin: parseRegionalBoundNumber(regionalBoundsLatitudeMinInput),
    latitudeMax: parseRegionalBoundNumber(regionalBoundsLatitudeMaxInput),
    longitudeMin: parseRegionalBoundNumber(regionalBoundsLongitudeMinInput),
    longitudeMax: parseRegionalBoundNumber(regionalBoundsLongitudeMaxInput),
  };

  if (!selectedModel || !selectedSavedModelId) {
    window.alert("The workspace model is required before running High-Potential Sites.");
    return;
  }
  if (runtimeClimateScope === "country_localities" && !regionalCountry) {
    window.alert("When you choose country-localities climate mode, you must select an African country.");
    return;
  }
  if (
    runtimeClimateScope === "regional_manual" &&
    (
      regionalBounds.latitudeMin === null ||
      regionalBounds.latitudeMax === null ||
      regionalBounds.longitudeMin === null ||
      regionalBounds.longitudeMax === null
    )
  ) {
    window.alert("When you choose manual regional climate mode, you must complete latitude and longitude min/max.");
    return;
  }
  if (runtimeClimateScope === "regional_manual" && regionalManualPreviewGridCellCount === 0) {
    window.alert(
      "The selected manual bounding box did not generate any climate grid cells. Please expand the box before running the prediction.",
    );
    return;
  }

  selectedGermplasmRunInProgress = true;
  updateGermplasmSelectionCount();

  try {
    mountLoadingPanelInPrediction();
    activeDataViewTab = "prediction";
    updateDataViewTabs();
    await clearDataset("prediction");
    resetPreprocessValidationState();
    await setLoadingState(
      10,
      "Uploading file",
      selectedClimateScope === "default"
        ? `Sending ${file.name} with ${selectedGermplasmNames.size} selected germplasm name${selectedGermplasmNames.size === 1 ? "" : "s"}, reusing saved model ${selectedModel.model_id}, and recalculating the climate windows from the workbook dates.`
        : `Sending ${file.name} with ${selectedGermplasmNames.size} selected germplasm name${selectedGermplasmNames.size === 1 ? "" : "s"}, reusing saved model ${selectedModel.model_id}, and using the workbook planting and harvesting dates.`,
    );
    const payload = await processFileWithStatusTimeline(file, {
      selectedModelId: selectedSavedModelId,
      selectedGermplasmNames: Array.from(selectedGermplasmNames),
      selectedIdHeader: selectedPredictionIdField || clearSelectionIdSentinel,
      selectedGermplasmProjectionMode,
      projectionTemplateWorkbook,
      forecastPlantingDate,
      forecastHarvestingDate,
      pauseAfterPreprocess: preprocessValidationEnabled,
      climateScope: runtimeClimateScope,
      regionalCountry,
      regionalBounds: runtimeClimateScope === "regional_manual" ? regionalBounds : null,
    });
    if (payload?.status === "paused") {
      await showPausedPreprocessValidation(payload, { updateOriginalData: false });
      return;
    }
    await setLoadingState(
      94,
      "Preparing map output",
      "Building the final geospatial dataset and validating the processed Geocoordinates.",
    );
    const geojson = preparePredictionGeojsonForDisplay(
      await resolvePipelineGeojson(payload),
      payload.summary ?? null,
    );
    await setLoadingState(
      97,
      "Validating Geocoordinates",
      `${geojson.features.length} Geocoordinates with coordinates were returned by the pipeline.`,
    );
    registerDataset(
      "prediction",
      geojson,
      payload.source_name ?? file.name,
      "saved_model",
      payload.summary ?? null,
    );
    await showDatasetInView("prediction", { force: true });
    if (predictionBridgeState?.isAvailable && selectedClimateScope === "default") {
      if (germplasmSelectionPanel) {
        germplasmSelectionPanel.hidden = false;
      }
      renderGermplasmSelectionList();
    }
    triggerBrowserDownload(payload?.prediction_output_download_url);
    await setLoadingState(
      100,
      "High-Potential Sites complete",
      "The selected-model output is ready in the High-Potential Sites tab.",
      true,
    );
    scheduleLoadingPanelReset();
    await refreshSavedModels();
  } catch (error) {
    console.error(error);
    await clearDataset("prediction");
    await setLoadingState(
      100,
      "Upload error",
      error instanceof Error ? error.message : "The file could not be processed.",
    );
  } finally {
    selectedGermplasmRunInProgress = false;
    updateGermplasmSelectionCount();
  }
};

const resumePersistedPipelineJob = async () => {
  const activeJob = readActivePipelineJob();
  if (!activeJob?.statusUrl) {
    return;
  }
  try {
    if (activeJob?.workflowMode === "prediction" || activeJob?.predictionMode) {
      mountLoadingPanelInPrediction();
      activeDataViewTab = "prediction";
      updateDataViewTabs();
      await clearDataset("prediction");
    } else {
      restoreLoadingPanelHome();
      resetLoadedResults();
    }
    await setLoadingState(
      Number(activeJob?.lastPercent ?? 12),
      activeJob?.state === "paused" ? "Recovering paused preprocess validation" : "Reconnecting to pipeline",
      activeJob?.state === "paused"
        ? "Restoring the preprocess validation step from the last active job."
        : `Reconnecting to the active pipeline job for ${activeJob.sourceName ?? "the uploaded workbook"}.`,
    );
    const payload = await pollPipelineStatus(activeJob.statusUrl, {
      sourceName: activeJob.sourceName ?? "the uploaded workbook",
      lastPercent: Number(activeJob?.lastPercent ?? 12),
      predictionMode: Boolean(activeJob?.workflowMode === "prediction" || activeJob?.predictionMode),
    });
    if (payload?.status === "paused") {
      await showPausedPreprocessValidation(payload, {
        updateOriginalData: !(activeJob?.workflowMode === "prediction" || activeJob?.predictionMode),
      });
      return;
    }
    const geojson = preparePredictionGeojsonForDisplay(
      await resolvePipelineGeojson(payload),
      payload.summary ?? null,
    );
    await setLoadingState(
      97,
      "Validating Geocoordinates",
      `${geojson.features.length} Geocoordinates with coordinates were returned by the pipeline.`,
    );
    const resumedTab =
      activeJob?.state === "paused" || activeJob?.pausedPayload ? "prediction" : "training";
    registerDataset(
      resumedTab,
      geojson,
      payload.source_name ?? activeJob.sourceName ?? "Recovered pipeline job",
      activeJob?.state === "paused" || activeJob?.pausedPayload ? "saved_model" : "automatic",
      payload.summary ?? null,
    );
    await showDatasetInView(resumedTab, { force: true });
    if (
      resumedTab === "prediction" &&
      predictionBridgeState?.isAvailable &&
      selectedClimateScope === "default"
    ) {
      if (germplasmSelectionPanel) {
        germplasmSelectionPanel.hidden = false;
      }
      renderGermplasmSelectionList();
    }
    await refreshSavedModels();
  } catch (error) {
    console.error(error);
    clearActivePipelineJob();
    await setLoadingState(
      100,
      "Upload error",
      error instanceof Error ? error.message : "The pipeline connection could not be restored.",
    );
  }
};

if (savedModelSelect) {
  savedModelSelect.addEventListener("change", (event) => {
    selectedSavedModelId = event.target.value ?? "";
    if (
      predictionBridgeState?.isAvailable &&
      selectedSavedModelId &&
      selectedSavedModelId !== predictionBridgeState.modelId
    ) {
      predictionBridgeState = null;
      if (selectedClimateScope === "default") {
        selectedClimateScope = "";
      }
    }
    resetPreprocessValidationState();
    updateSelectedModelHelp();
    renderSavedModels(savedModelsCache);
    updateFileUploadAvailability();
  });
}

if (climateScopeSelect) {
  climateScopeSelect.addEventListener("change", (event) => {
    selectedClimateScope = event.target.value ?? "";
    if (!isRegionalManualMode()) {
      clearMapBoundingBoxSelection();
    }
    if (isPredictionWorkflowMode()) {
      activeDataViewTab = "prediction";
      updateDataViewTabs();
      clearDataset("prediction").catch((error) => {
        console.error(error);
      });
    }
    updateClimateScopePanel();
    if (isRegionalManualMode()) {
      renderManualRegionalPreview().catch((error) => {
        console.error(error);
      });
    }
    if (isPredictionWorkflowMode() && selectedClimateScope === "point") {
      pendingSavedModelFile = null;
      if (fileInput) {
        fileInput.value = "";
      }
      updateFileUploadAvailability();
      promptPredictionPointWorkbookSelection();
    }
  });
}

if (predictionPointUploadButton) {
  predictionPointUploadButton.addEventListener("click", () => {
    promptPredictionPointWorkbookSelection();
  });
}

[forecastPlantingDateInput, forecastHarvestingDateInput].forEach((input) => {
  if (!input) {
    return;
  }
  input.addEventListener("change", () => {
    updateFileUploadAvailability();
    window.requestAnimationFrame(() => {
      input.blur();
    });
  });
});

if (regionalCountrySelect) {
  regionalCountrySelect.addEventListener("change", () => {
    refreshRegionalCountryPreviewSample().catch((error) => {
      console.error(error);
    });
  });
}

if (germplasmSelectAllButton) {
  germplasmSelectAllButton.addEventListener("click", () => {
    selectedGermplasmNames = new Set(
      predictionGermplasmSourceMode === "original"
        ? (availableGermplasmNames.length ? [availableGermplasmNames[0]] : [])
        : availableGermplasmNames,
    );
    if (predictionBridgeState?.isAvailable) {
      predictionBridgeState.selectedNames = Array.from(selectedGermplasmNames);
    }
    renderGermplasmSelectionList();
  });
}

if (germplasmClearAllButton) {
  germplasmClearAllButton.addEventListener("click", () => {
    selectedGermplasmNames = new Set();
    if (predictionBridgeState?.isAvailable) {
      predictionBridgeState.selectedNames = [];
    }
    renderGermplasmSelectionList();
  });
}

if (executeGermplasmSelectionButton) {
  executeGermplasmSelectionButton.addEventListener("click", () => {
    handleExecuteSelectedGermplasm().catch((error) => {
      console.error(error);
    });
  });
}

if (predictionIdColumnSelect) {
  predictionIdColumnSelect.addEventListener("change", updatePredictionIdModalAcceptState);
}

if (germplasmSelectionIdSelect) {
  germplasmSelectionIdSelect.addEventListener("change", () => {
    const selectedHeader = String(germplasmSelectionIdSelect.value ?? "").trim();
    applyPredictionIdFieldSelection(selectedHeader).catch((error) => {
      console.error(error);
      setLoadingState(
        100,
        "Id field error",
        error instanceof Error ? error.message : "The selected Id field could not be loaded.",
        true,
      ).catch(console.error);
    });
  });
}

if (predictionIdModalClose) {
  predictionIdModalClose.addEventListener("click", () => {
    closePredictionIdModal();
  });
}

if (predictionIdModalBackdrop) {
  predictionIdModalBackdrop.addEventListener("click", () => {
    closePredictionIdModal();
  });
}

if (predictionIdModalCancel) {
  predictionIdModalCancel.addEventListener("click", () => {
    closePredictionIdModal();
  });
}

if (predictionIdModalAccept) {
  predictionIdModalAccept.addEventListener("click", () => {
    applyPredictionIdFieldSelection().catch((error) => {
      console.error(error);
      setLoadingState(
        100,
        "Id field error",
        error instanceof Error ? error.message : "The selected Id field could not be loaded.",
        true,
      ).catch(console.error);
    });
  });
}

[
  regionalBoundsLatitudeMinInput,
  regionalBoundsLatitudeMaxInput,
  regionalBoundsLongitudeMinInput,
  regionalBoundsLongitudeMaxInput,
].forEach((input) => {
  if (!input) {
    return;
  }
  input.addEventListener("input", () => {
    updateFileUploadAvailability();
    renderManualRegionalPreview().catch((error) => {
      console.error(error);
    });
  });
});

if (predictionControlsClearButton) {
  predictionControlsClearButton.addEventListener("click", () => {
    resetPredictionControls();
  });
}

if (regionalBoundsDrawMapButton) {
  regionalBoundsDrawMapButton.addEventListener("click", () => {
    if (mapBoundingBoxSelectionMode) {
      clearMapBoundingBoxSelection();
      return;
    }
    beginMapBoundingBoxSelection();
  });
}

if (regionalBoundsClearMapButton) {
  regionalBoundsClearMapButton.addEventListener("click", async () => {
    const shouldClearPredictionMap =
      datasetStore.prediction?.summary?.climate_scope === "regional_manual";
    clearMapBoundingBoxSelection({ clearInputs: true });
    if (shouldClearPredictionMap) {
      await clearDataset("prediction");
    }
    renderManualRegionalPreview().catch((error) => {
      console.error(error);
    });
  });
}

if (continueAfterPreprocessButton) {
  continueAfterPreprocessButton.addEventListener("click", () => {
    handleContinueAfterPreprocess().catch((error) => {
      console.error(error);
    });
  });
}

modelList.addEventListener("click", (event) => {
  const button = event.target.closest("[data-model-action]");
  if (!button) {
    return;
  }
  const action = button.dataset.modelAction ?? "";
  const modelId = button.dataset.modelId ?? "";
  if (action === "load-workspace") {
    loadSavedWorkspace(modelId).catch((error) => {
      console.error(error);
      setSelectionPropertiesBadge("Workspace error");
      setSelectionPropertiesStatus(error instanceof Error ? error.message : "The saved workspace could not be loaded.");
      setLoadingState(100, "Workspace error", error instanceof Error ? error.message : "The saved workspace could not be loaded.", true).catch(console.error);
    });
    return;
  }
  if (action === "details") {
    openWorkspaceSettingsModal(modelId).catch((error) => {
      console.error(error);
    });
    return;
  }
  if (action === "summary") {
    openModelModal(modelId);
  }
});

modelScrollPrev.addEventListener("click", () => {
  scrollModelCards(-1);
});

modelScrollNext.addEventListener("click", () => {
  scrollModelCards(1);
});

modelScroller.addEventListener("scroll", updateModelScrollerControls);

modelModalClose.addEventListener("click", closeModelModal);
modelModalBackdrop.addEventListener("click", closeModelModal);
if (settingsButton) {
  settingsButton.addEventListener("click", openSettingsModal);
}
if (newWorkspaceButton) {
  newWorkspaceButton.addEventListener("click", () => {
    startNewWorkspace().catch((error) => {
      console.error(error);
      setLoadingState(100, "Reset failed", error instanceof Error ? error.message : "The workspace could not be reset.");
    });
  });
}
if (refreshAppButton) {
  refreshAppButton.addEventListener("click", () => {
    window.location.reload();
  });
}
if (cancelAllButton) {
  cancelAllButton.addEventListener("click", () => {
    cancelAllProcesses().catch((error) => {
      console.error(error);
      setLoadingState(100, "Cancel failed", error instanceof Error ? error.message : "The running processes could not be cancelled.");
    });
  });
}
if (settingsModalClose) {
  settingsModalClose.addEventListener("click", closeSettingsModal);
}
if (settingsModalBackdrop) {
  settingsModalBackdrop.addEventListener("click", closeSettingsModal);
}
if (settingsModalCancel) {
  settingsModalCancel.addEventListener("click", closeSettingsModal);
}
if (settingsModalSave) {
  settingsModalSave.addEventListener("click", () => {
    saveFeatureheroSettings().catch((error) => {
      console.error(error);
      setSettingsStatus(error instanceof Error ? error.message : "The settings could not be saved.");
    });
  });
}
if (modelNameModalClose) {
  modelNameModalClose.addEventListener("click", deferModelNameDialog);
}
if (modelNameModalBackdrop) {
  modelNameModalBackdrop.addEventListener("click", deferModelNameDialog);
}
if (modelNameModalLater) {
  modelNameModalLater.addEventListener("click", deferModelNameDialog);
}
if (modelNameModalSave) {
  modelNameModalSave.addEventListener("click", saveModelNameFromDialog);
}
if (modelNameInput) {
  modelNameInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      saveModelNameFromDialog();
    }
  });
}
modelDeleteButton.addEventListener("click", () => {
  if (activeModalModelId) {
    deleteModel(activeModalModelId).catch((error) => {
      console.error(error);
    });
  }
});

window.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && modelModal && !modelModal.hidden) {
    closeModelModal();
    return;
  }
  if (event.key === "Escape" && settingsModal && !settingsModal.hidden) {
    closeSettingsModal();
    return;
  }
  if (event.key === "Escape" && predictionIdModal && !predictionIdModal.hidden) {
    closePredictionIdModal();
    return;
  }
  if (event.key === "Escape" && modelNameModal && !modelNameModal.hidden) {
    deferModelNameDialog();
  }
});

prevPageButton.addEventListener("click", () => {
  if (!workflowInteractive) {
    return;
  }
  if (!selectedFeature || currentPage === 0) {
    return;
  }
  currentPage -= 1;
  renderDetails();
});

nextPageButton.addEventListener("click", () => {
  if (!workflowInteractive) {
    return;
  }
  if (!selectedFeature) {
    return;
  }
  currentPage += 1;
  renderDetails();
});

summaryTabCountriesButton.addEventListener("click", () => {
  if (!workflowInteractive) {
    return;
  }
  setActiveSummaryTab("countries");
});

summaryTabStatsButton.addEventListener("click", () => {
  if (!workflowInteractive) {
    return;
  }
  setActiveSummaryTab("stats");
});

if (summaryTabLogButton) {
  summaryTabLogButton.addEventListener("click", () => {
    if (!workflowInteractive) {
      return;
    }
    setActiveSummaryTab("log");
  });
}

tabGeoButton.addEventListener("click", () => {
  if (!workflowInteractive) {
    return;
  }
  setActiveDetailsTab("geo");
});

tabGermplasmButton.addEventListener("click", () => {
  if (!workflowInteractive) {
    return;
  }
  setActiveDetailsTab("germplasm");
});

tabAttributesButton.addEventListener("click", () => {
  if (!workflowInteractive) {
    return;
  }
  setActiveDetailsTab("attributes");
});

if (dataViewTabOriginalButton) {
  dataViewTabOriginalButton.addEventListener("click", () => {
    showDatasetInView("original").catch((error) => {
      console.error(error);
    });
  });
}

if (dataViewTabTrainingButton) {
  dataViewTabTrainingButton.addEventListener("click", () => {
    if (legacyPipelineDisabled && !datasetStore.training) {
      notifyLegacyFlowBlocked("Training tab");
      return;
    }
    selectedWorkflowMode = "training";
    restoreLoadingPanelHome();
    updateForecastDatePanel();
    showDatasetInView("training").catch((error) => {
      console.error(error);
    });
  });
}

if (TOP_GERMPLASM_ENABLED && dataViewTabTopGermplasmButton) {
  dataViewTabTopGermplasmButton.addEventListener("click", () => {
    restoreLoadingPanelHome();
    updateForecastDatePanel();
    showDatasetInView("top_germplasm").catch((error) => {
      console.error(error);
    });
  });
}

if (topGermplasmPreviewSlider) {
  topGermplasmPreviewSlider.addEventListener("input", () => {
    topGermplasmPreviewStart = Number(topGermplasmPreviewSlider.value || 0);
    renderTopGermplasmPreview();
  });
}

if (predictionPointOriginalButton) {
  predictionPointOriginalButton.addEventListener("click", () => {
    const bridgeSourceFile = predictionBridgeState?.sourceFile ?? predictionBridgeState?.file ?? null;
    if (!predictionBridgeState?.isAvailable || !bridgeSourceFile) {
      window.alert("Load a workspace with Training first to explore the original germplasm list.");
      return;
    }
    loadPredictionGermplasmList(bridgeSourceFile, {
      sourceLabel: predictionBridgeState?.sourceName?.trim() || bridgeSourceFile.name,
      mode: "original",
    }).catch((error) => {
      console.error(error);
      resetPendingGermplasmSelection();
      resetLoadedResults();
      setLoadingState(
        100,
        "Upload error",
        error instanceof Error ? error.message : "The germplasm list could not be loaded.",
      ).catch(console.error);
    });
  });
}

if (dataViewTabPredictionButton) {
  dataViewTabPredictionButton.addEventListener("click", () => {
    if (legacyPipelineDisabled && !datasetStore.prediction) {
      notifyLegacyFlowBlocked("High-Potential Sites tab");
      return;
    }
    selectedWorkflowMode = "prediction";
    const activeJob = readActivePipelineJob();
    if ((activeJob?.workflowMode === "prediction" || activeJob?.predictionMode || pausedPreprocessPayload) && !loadingPanel.hidden) {
      mountLoadingPanelInPrediction();
    } else {
      restoreLoadingPanelHome();
      loadingPanel.hidden = true;
      if (predictionLoadingSlot) {
        predictionLoadingSlot.hidden = true;
      }
    }
    updateForecastDatePanel();
    hydratePredictionBridge()
      .then(() => showDatasetInView("prediction"))
      .catch((error) => {
        console.error(error);
      });
  });
}

fileInput.addEventListener("change", handleFileUpload);

if (selectionPropertiesUploadTrigger) {
  selectionPropertiesUploadTrigger.addEventListener("click", () => {
    if (selectionPropertiesState.workspaceReadonlyLoaded || !fileInput || fileInput.disabled) {
      return;
    }
    try {
      if (typeof fileInput.showPicker === "function") {
        fileInput.showPicker();
        return;
      }
    } catch (error) {
      console.error(error);
    }
    fileInput.click();
  });
}

if (selectionStepNextButton) {
  selectionStepNextButton.addEventListener("click", () => {
    if (!isSelectionPropertiesConfigured()) {
      return;
    }
    focusSelectionStep("select-columns");
  });
}

if (selectionSummaryNextButton) {
  selectionSummaryNextButton.addEventListener("click", () => {
    if (!isSelectionSummaryReady()) {
      return;
    }
    focusSelectionStep("summary");
  });
}

if (selectionPropertiesRestore) {
  selectionPropertiesRestore.addEventListener("click", () => {
    selectionPropertiesState.collapsed = false;
    renderSelectionWorkbench();
    focusSelectionStep(selectionPropertiesState.workspaceReadonlyLoaded ? "initial" : selectionPropertiesState.summaryReady ? "summary" : "initial");
  });
}

if (selectionPropertiesHide) {
  selectionPropertiesHide.addEventListener("click", () => {
    selectionPropertiesState.collapsed = true;
    renderSelectionWorkbench();
    updateSelectionPropertiesCollapseState();
  });
}

selectionStepItems.forEach((item) => {
  if (!item) {
    return;
  }
  const handleStepNavigation = () => {
    const stepKey = item.dataset.stepKey ?? "";
    if (stepKey === "initial") {
      focusSelectionStep("initial");
      return;
    }
    if (stepKey === "select-columns" && isSelectionPropertiesConfigured()) {
      focusSelectionStep("select-columns");
      return;
    }
    if (stepKey === "summary" && isSelectionSummaryReady()) {
      focusSelectionStep("summary");
    }
  };
  item.addEventListener("click", handleStepNavigation);
  item.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") {
      return;
    }
    event.preventDefault();
    handleStepNavigation();
  });
});

[
  selectionTargetVariableSelect,
  selectionLongitudeColumnSelect,
  selectionLatitudeColumnSelect,
  selectionPlantingDateColumnSelect,
  selectionHarvestingDateColumnSelect,
  selectionSoilTextureColumnSelect,
  selectionSoilDepthColumnSelect,
].forEach((element) => {
  if (!element) {
    return;
  }
  element.addEventListener("change", () => {
    syncSelectionPropertiesSelection().catch((error) => {
      console.error(error);
      setSelectionPropertiesBadge("Preview error");
      setSelectionPropertiesStatus(
        error instanceof Error ? error.message : "The workbook preview could not be generated.",
      );
    });
  });
});

if (selectionWorkspaceNameInput) {
  selectionWorkspaceNameInput.addEventListener("input", () => {
    selectionPropertiesState.workspaceName = selectionWorkspaceNameInput.value ?? "";
  });
}

[
  [selectionCategoricSearch, "categoric"],
  [selectionQuantitativeSearch, "cuantitative"],
  [selectionExcludedSearch, "excluded"],
].forEach(([element, key]) => {
  if (!element) {
    return;
  }
  element.addEventListener("input", () => {
    selectionPropertiesState.search[key] = element.value ?? "";
    renderSelectionPropertiesControls();
  });
});

const startNewWorkspace = async () => {
  window.sessionStorage.setItem(newWorkspaceReloadFlagKey, "1");
  window.location.reload();
};

const init = async () => {
  forceOpenStepperAfterReload = window.sessionStorage.getItem(newWorkspaceReloadFlagKey) === "1";
  if (forceOpenStepperAfterReload) {
    window.sessionStorage.removeItem(newWorkspaceReloadFlagKey);
  }
  closeModelModal();
  closeSettingsModal();
  resetDatasetStore();
  renderEmptyStats();
  resetDetails();
  setSelectionActiveStep("initial");
  renderSelectionPropertiesControls();
  setSelectionPropertiesBadge("Waiting for file");
  setSelectionPropertiesStatus("Upload a workbook to begin the selecctionProperties flow.");
  resetPreprocessValidationState();
  renderSavedModels([]);
  syncSelectedModelControl();
  updateClimateScopePanel();
  setWorkflowInteractive(false);
  setLegendState("automatic");
  await syncAppConfig();
  updateForecastDatePanel();
  updateFileUploadAvailability();
  applyPreprocessValidationVisibility();
  await setLoadingState(
    0,
    "Waiting for file",
    selectionPropertiesFlowEnabled
      ? "Upload any .xlsx file to start the selecctionProperties flow."
      : "Upload a file to start processing.",
    false,
  );
  if (modelPanel) {
    modelPanel.classList.toggle("model-panel-disabled", legacyPipelineDisabled);
    modelPanel.setAttribute(
      "title",
      legacyPipelineDisabled
        ? "Training and prediction are temporarily disabled while selecctionProperties is being integrated."
        : "",
    );
  }
  await refreshSavedModels();
  await refreshRegionalCountryBounds();
  await renderManualRegionalPreview();
  await setupMapBase();
  if (!legacyPipelineDisabled) {
    await resumePersistedPipelineJob();
  }
};

init().catch((error) => {
  console.error(error);
  statsContainer.replaceChildren(createStat("Error", "The map could not be initialized"));
});

export const SELECCTION_PROPERTIES_FLOW_ID = "selecctionProperties";

export const selectionPropertiesSteps = [
  "Initial Settings",
  "Select Columns",
  "Summary",
];

const latitudeTokens = ["latitude", "lat"];
const longitudeTokens = ["longitude", "long", "lng", "lon"];
const identifierTokens = ["id", "pk", "code", "name", "germplasm", "entry", "variety", "rank", "plot", "site", "farm"];
const quantitativeTokens = [
  "yield",
  "number",
  "count",
  "percentage",
  "percent",
  "total",
  "avg",
  "average",
  "height",
  "depth",
  "area",
  "stand",
  "moisture",
  "week",
  "mm",
  "cm",
  "age",
  "precision",
  "altitude",
  "temperature",
  "t/ha",
];
const dgHeaderPattern = /^DG\d+$/i;

const includesAnyToken = (value, tokens) => {
  const normalized = String(value ?? "").trim().toLowerCase();
  return tokens.some((token) => normalized.includes(token));
};

const normalizeHeaders = (headers = []) =>
  headers.map((header) => String(header ?? "").trim()).filter(Boolean);

export const isDGColumn = (value = "") => dgHeaderPattern.test(String(value ?? "").trim());

export const guessCoordinateColumn = (headers, axis) => {
  const tokens = axis === "latitude" ? latitudeTokens : longitudeTokens;
  return normalizeHeaders(headers).find((header) => includesAnyToken(header, tokens)) ?? "";
};

export const buildSelectableColumnOptions = (headers, excludedColumns = []) => {
  const normalizedHeaders = normalizeHeaders(headers);
  const blocked = new Set(
    excludedColumns.map((column) => String(column ?? "").trim()).filter(Boolean),
  );
  return normalizedHeaders.filter((header) => !blocked.has(String(header ?? "").trim()));
};

export const buildAvailableSelectionColumns = ({
  headers = [],
  targetColumn = "",
  latitudeColumn = "",
  longitudeColumn = "",
} = {}) =>
  buildSelectableColumnOptions(headers, [targetColumn, latitudeColumn, longitudeColumn]);

export const classifySelectionPropertiesColumns = ({
  headers = [],
  targetColumn = "",
  latitudeColumn = "",
  longitudeColumn = "",
  identifierColumns = [],
} = {}) => {
  const available = buildAvailableSelectionColumns({
    headers,
    targetColumn,
    latitudeColumn,
    longitudeColumn,
  });
  const normalizedIdentifierColumns = normalizeHeaders(identifierColumns).filter((header) => available.includes(header));
  const quantitativeColumns = available.filter(
    (header) => !normalizedIdentifierColumns.includes(header) && includesAnyToken(header, quantitativeTokens),
  );
  const categoricalColumns = available.filter(
    (header) => !normalizedIdentifierColumns.includes(header) && !quantitativeColumns.includes(header),
  );
  return {
    identifierColumns: normalizedIdentifierColumns,
    categoricalColumns,
    quantitativeColumns,
    excludedColumns: [],
  };
};

export const buildSelectionPropertiesSummary = ({
  sourceName = "",
  rowCount = 0,
  featureCount = 0,
  targetColumn = "",
  latitudeColumn = "",
  longitudeColumn = "",
  identifierColumns = [],
  categoricalColumns = [],
  quantitativeColumns = [],
  excludedColumns = [],
}) => ({
  workflow: SELECCTION_PROPERTIES_FLOW_ID,
  source_name: sourceName,
  row_count: rowCount,
  mapped_feature_count: featureCount,
  target_variable: targetColumn,
  latitude_column: latitudeColumn,
  longitude_column: longitudeColumn,
  identifier_columns: identifierColumns,
  categorical_columns: categoricalColumns,
  quantitative_columns: quantitativeColumns,
  excluded_columns: excludedColumns,
  preprocess_disabled: true,
  training_disabled: true,
  prediction_disabled: true,
});

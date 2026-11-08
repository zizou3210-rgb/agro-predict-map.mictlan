export const summarizePredictionValues = (values) => {
  const sorted = values.filter(Number.isFinite).sort((a, b) => a - b);
  if (!sorted.length) {
    return { mean: null, min: null, max: null, median: null, q1: null, q3: null };
  }
  const quantile = (p) => {
    const position = (sorted.length - 1) * p;
    const lower = Math.floor(position);
    const upper = Math.ceil(position);
    return sorted[lower] + (sorted[upper] - sorted[lower]) * (position - lower);
  };
  return {
    mean: sorted.reduce((sum, value) => sum + value, 0) / sorted.length,
    min: sorted[0],
    max: sorted[sorted.length - 1],
    median: quantile(0.5),
    q1: quantile(0.25),
    q3: quantile(0.75),
  };
};

export const buildPredictionStatistics = (candidates, winners, cellAreaKm2 = 25) => {
  const groups = new Map(candidates.map(candidate => [candidate.label, {
    ...candidate, cells: 0, values: [],
  }]));
  const allValues = [];
  for (const winner of winners) {
    if (!groups.has(winner.label)) {
      groups.set(winner.label, { ...winner, cells: 0, values: [] });
    }
    const group = groups.get(winner.label);
    group.cells += 1;
    if (Number.isFinite(winner.value)) {
      group.values.push(winner.value);
      allValues.push(winner.value);
    }
  }
  const totalCells = winners.length;
  return {
    rows: Array.from(groups.values(), ({ values, ...group }) => ({
      ...group,
      percentage: totalCells ? group.cells / totalCells * 100 : 0,
      areaKm2: group.cells * cellAreaKm2,
      statistics: summarizePredictionValues(values),
    })),
    total: {
      cells: totalCells,
      percentage: totalCells ? 100 : 0,
      areaKm2: totalCells * cellAreaKm2,
      statistics: summarizePredictionValues(allValues),
    },
  };
};

// Keep table and CSV columns in the same order; source column names stay unchanged.
export const predictionStatisticsColumns = (criterion) => [
  "Genotype", criterion ? `Value ${criterion}` : "Criterion", "Color", "Cells won",
  "Percentage", "km²", "Mean", "Minimum", "Maximum", "Q1", "Median", "Q3",
];

export const predictionStatisticsCsv = (result, criterion) => {
  const stats = row => ["mean", "min", "max", "q1", "median", "q3"]
    .map(key => row.statistics[key]);
  const counts = row => [row.cells, row.percentage, row.areaKm2];
  const records = [predictionStatisticsColumns(criterion),
    ...result.rows.map(row => [row.name, row.criterionValue, row.colorName,
      ...counts(row), ...stats(row)]),
    ["Total", "", "", ...counts(result.total), ...stats(result.total)],
  ];
  const escape = value => `"${String(value ?? "").replaceAll('"', '""')}"`;
  // UTF-8 BOM preserves km² and source names when opened in Excel.
  return "\uFEFF" + records.map(row => row.map(escape).join(",")).join("\r\n") + "\r\n";
};

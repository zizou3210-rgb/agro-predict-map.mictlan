const assert = require('node:assert/strict');
const fs = require('node:fs');

(async () => {
  const source = fs.readFileSync('src/predictionStatistics.js', 'utf8');
  const { summarizePredictionValues, buildPredictionStatistics, predictionStatisticsColumns, predictionStatisticsCsv } = await import(
    `data:text/javascript;base64,${Buffer.from(source).toString('base64')}`
  );
  assert.deepEqual(summarizePredictionValues([4, 1, 3, 2]), {
    mean: 2.5, min: 1, max: 4, median: 2.5, q1: 1.75, q3: 3.25,
  });
  assert.deepEqual(summarizePredictionValues([0]), {
    mean: 0, min: 0, max: 0, median: 0, q1: 0, q3: 0,
  });
  assert.deepEqual(summarizePredictionValues([null, NaN, Infinity]), {
    mean: null, min: null, max: null, median: null, q1: null, q3: null,
  });
  const candidates = [
    { label:'A - 0', name:'A', criterionValue:'0', color:'#2e7d32' },
    { label:'B - 4', name:'B', criterionValue:'4', color:'#1565c0' },
    { label:'C - 0', name:'C', criterionValue:'0', color:'#7b1fa2' },
  ];
  const winners = [
    { ...candidates[0], value:4 }, { ...candidates[0], value:1 },
    { ...candidates[0], value:3 }, { ...candidates[1], value:2 },
  ];
  const result = buildPredictionStatistics(candidates, winners);
  assert.deepEqual(result.rows.map(row => [row.cells, row.percentage, row.areaKm2]),
    [[3,75,75], [1,25,25], [0,0,0]]);
  assert.equal(result.rows[0].criterionValue, '0');
  assert.equal(result.rows[0].statistics.mean, 8/3);
  assert.equal(result.rows[2].statistics.mean, null);
  assert.equal(result.total.cells, 4);
  assert.equal(result.total.areaKm2, 100);
  assert.equal(result.total.percentage, 100);
  assert.equal(result.total.statistics.mean, 2.5);
  assert.equal(result.total.statistics.median, 2.5);
  // The total is the mean of all winning cells, not the mean of row means.
  const unequal = buildPredictionStatistics(candidates,
    [{...candidates[0],value:0}, {...candidates[0],value:0}, {...candidates[1],value:9}]);
  assert.equal(unequal.total.statistics.mean, 3);
  // A filtered competition replaces the winners and retains zero-win rows.
  const filtered = buildPredictionStatistics(candidates,
    winners.map(winner => ({ ...candidates[1], value:winner.value })));
  assert.equal(filtered.rows[0].cells, 0);
  assert.equal(filtered.rows[1].cells, 4);
  assert.equal(filtered.rows[1].percentage, 100);
  assert.equal(filtered.total.cells, 4);
  const empty = buildPredictionStatistics(candidates, []);
  assert.equal(empty.total.areaKm2, 0);
  assert.equal(empty.total.percentage, 0);
  assert.equal(empty.total.statistics.mean, null);
  assert.deepEqual(predictionStatisticsColumns('Farm'), [
    'Genotype', 'Value Farm', 'Color', 'Cells won', 'Percentage', 'km²',
    'Mean', 'Minimum', 'Maximum', 'Q1', 'Median', 'Q3',
  ]);
  assert.equal(predictionStatisticsColumns('source_header')[1], 'Value source_header');
  const csvResult = buildPredictionStatistics([
    {label:'A', name:'A, "quoted"', criterionValue:'Farm\n1', colorName:'Green'},
    {label:'B', name:'B', criterionValue:'0', colorName:'Purple'},
  ], [{label:'A', value:0}]);
  const csv = predictionStatisticsCsv(csvResult, 'Farm');
  assert.ok(csv.startsWith('\uFEFF"Genotype","Value Farm","Color"'));
  assert.ok(csv.includes('"A, ""quoted"""')); // CSV quoting and source newlines survive.
  assert.ok(csv.includes('"Farm\n1","Green","1","100","25","0","0","0","0","0","0"'));
  assert.ok(csv.includes('"B","0","Purple","0","0","0","","","","","",""'));
  assert.ok(csv.endsWith('"Total","","","1","100","25","0","0","0","0","0","0"\r\n'));
  console.log('Prediction statistics: winners, zero categories, percentages, areas, quartiles and filtered totals passed');
})().catch(error => { console.error(error); process.exitCode = 1; });

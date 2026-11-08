const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

(async () => {
  const root = path.resolve(__dirname, '..');
  const fixture = JSON.parse(fs.readFileSync(path.join(__dirname, 'fixtures/prediction_statistics_real_run.json')));
  const source = fs.readFileSync(path.join(root, 'src/main.js'), 'utf8');
  const extract = name => {
    const start = source.indexOf(`const ${name} =`);
    assert.ok(start >= 0);
    return source.slice(start, source.indexOf('\n};', start) + 3);
  };
  const compete = new Function('normalizePredictionCategoryLabel',
    `${extract('buildManualGridWinningFeatureLookupFromEntries')}; return buildManualGridWinningFeatureLookupFromEntries;`)(value => value.trim());
  const moduleSource = fs.readFileSync(path.join(root, 'src/predictionStatistics.js'), 'utf8');
  const {buildPredictionStatistics, predictionStatisticsCsv, predictionStatisticsColumns} = await import(
    `data:text/javascript;base64,${Buffer.from(moduleSource).toString('base64')}`);
  const palette = [['#2e7d32','Green'],['#d35400','Orange'],['#7b1fa2','Purple'],
    ['#1565c0','Blue'],['#c62828','Red'],['#6d4c41','Brown'],
    ['#fbc02d','Yellow'],['#00838f','Turquoise'],['#ad1457','Pink']];
  const candidates = fixture.profiles.map(profile => {
    const prediction = fixture.predictions.find(row => `${row[1]} - ${row[2]}` === profile.label);
    const [color, colorName] = palette[profile.palette_index];
    return {label:profile.label,name:prediction[1],criterionValue:prediction[2],color,colorName};
  });
  const byLabel = new Map(candidates.map(candidate => [candidate.label,candidate]));
  const entries = fixture.predictions.map(row => ({
    gridCellId:row[0],featureLabel:`${row[1]} - ${row[2]}`,predictedValue:row[3],feature:row,
  }));
  const close = (actual, expected, label) => {
    if (expected === null) assert.equal(actual, null, label);
    else assert.ok(Math.abs(actual - expected) < 1e-10, `${label}: ${actual} != ${expected}`);
  };
  const verifyRow = (actual, expected) => {
    for (const key of ['cells','percentage','areaKm2']) close(actual[key],expected[key],key);
    for (const key of ['mean','min','max','q1','median','q3']) close(actual.statistics[key],expected.statistics[key],key);
  };
  const verifySelection = (labels, expected) => {
    const winners = [...compete(entries, labels).values()];
    if (!labels) assert.deepEqual(winners, fixture.map_winners, 'Every winning cell must match the real map artifact');
    const result = buildPredictionStatistics(candidates,winners.map(row => ({...byLabel.get(`${row[1]} - ${row[2]}`),value:row[3]})));
    assert.equal(result.rows.length,9, 'Include participants with zero wins');
    for (const row of result.rows) verifyRow(row,expected.rows[row.label]);
    verifyRow(result.total,expected.total);
    assert.equal(result.rows.reduce((sum,row) => sum+row.cells,0),result.total.cells);
    // Validate the downloadable table as well as the values supplied to the UI.
    const csvRows = predictionStatisticsCsv(result,fixture.criterion).replace(/^\uFEFF/,'').trimEnd()
      .split('\r\n').map(line => line.slice(1,-1).split('","'));
    assert.equal(csvRows.length,11);
    assert.deepEqual(csvRows[0].slice(-3),['Q1','Median','Q3']);
    result.rows.forEach((row,i) => {
      const csv = csvRows[i+1];
      assert.deepEqual(csv.slice(0,3),[row.name,row.criterionValue,row.colorName]);
      const values = [row.cells,row.percentage,row.areaKm2,...['mean','min','max','q1','median','q3'].map(key => row.statistics[key])];
      assert.deepEqual(csv.slice(3),values.map(value => String(value ?? '')));
    });
    assert.equal(csvRows.at(-1)[0],'Total');
    assert.equal(Number(csvRows.at(-1)[3]),expected.total.cells);
    assert.equal(Number(csvRows.at(-1)[5]),expected.total.areaKm2);
    return result;
  };
  assert.equal(fixture.predictions.length,2349);
  const all = verifySelection(null,fixture.expected);
  // Render the actual table with real prediction features, not a parallel template.
  const features = fixture.predictions.map(row => ({properties:{
    'Forecast grid cell id':row[0],Name:row[1],Farm:row[2],[fixture.target]:row[3],
  }}));
  const labelFor = feature => `${feature.properties.Name} - ${feature.properties.Farm}`;
  let clickHandler;
  const container = {innerHTML:'',querySelector(selector) {
    if (selector === 'table') return {offsetHeight:0,parentElement:{}};
    return {addEventListener(event,handler) {clickHandler=handler;}};
  }};
  const context = {
    predictionStatisticsContainer:container,
    isManualGridPredictionResult:()=>true,
    datasetStore:{prediction:{summary:{},rawGeojson:{features}}},
    getPredictionSelectedIdHeader:()=>fixture.criterion,
    getPredictedTargetColumnLabel:()=>fixture.target,
    getPredictionProfileColorMap:()=>new Map(candidates.map(row=>[row.label,row.color])),
    getPredictionDistinctGermplasmNames:()=>[...new Set(candidates.map(row=>row.name))],
    getPredictionSelectedIdValueForProperties:properties=>properties?.Farm ?? '',
    getPredictionCategoryLabelForFeature:labelFor,
    getPredictionNameAndIdLabelForFeature:labelFor,
    hasManualGridCompetitionFeatures:()=>true,
    getPredictedTargetValue:properties=>properties[fixture.target],
    asFloat:Number,buildPredictionStatistics,predictionStatisticsCsv,
    getPredictionProfileColorName:color=>palette.find(entry=>entry[0]===color)?.[1] ?? color,
    predictionStatisticsColumns,
    escapeHtml:value=>String(value).replaceAll('&','&amp;').replaceAll('<','&lt;'),
    ResizeObserver:class {observe() {} disconnect() {}},
  };
  const render = new Function('context', `
    const {${Object.keys(context).join(',')}} = context;
    let predictionStatisticsRenderCache=null, predictionStatisticsResizeObserver=null;
    ${extract('renderPredictionStatistics')}
    return renderPredictionStatistics;
  `)(context);
  const winnerFeatures = compete(features.map(feature=>({feature,
    gridCellId:feature.properties['Forecast grid cell id'],featureLabel:labelFor(feature),
    predictedValue:feature.properties[fixture.target],
  })));
  render(winnerFeatures);
  const renderedRows = container.innerHTML.match(/<tbody>([\s\S]*?)<\/tbody>/)[1].match(/<tr>[\s\S]*?<\/tr>/g);
  const number = (value,decimals=6)=>Number.isFinite(value)
    ? value.toLocaleString('en-US',{maximumFractionDigits:decimals}):'—';
  renderedRows.forEach((markup,index)=>{
    const row = all.rows.slice().sort((a,b)=>a.label.localeCompare(b.label,undefined,{numeric:true,sensitivity:'base'}))[index];
    const cells = [...markup.matchAll(/<(?:th|td)\b[^>]*>([\s\S]*?)<\/(?:th|td)>/g)]
      .map(match=>match[1].replace(/<[^>]*>/g,''));
    assert.deepEqual(cells,[row.name,row.criterionValue,row.colorName,number(row.cells,0),
      `${number(row.percentage,2)}%`,number(row.areaKm2,0),
      ...['mean','min','max','q1','median','q3'].map(key=>number(row.statistics[key]))]);
  });
  const footer = container.innerHTML.match(/<tfoot>([\s\S]*?)<\/tfoot>/)[1];
  const footerCells = [...footer.matchAll(/<(?:th|td)\b[^>]*>([\s\S]*?)<\/(?:th|td)>/g)]
    .map(match=>match[1].replace(/<[^>]*>/g,''));
  assert.deepEqual(footerCells,['Total','','',number(all.total.cells,0),
    `${number(all.total.percentage,2)}%`,number(all.total.areaKm2,0),
    ...['mean','min','max','q1','median','q3'].map(key=>number(all.total.statistics[key]))]);
  assert.equal(renderedRows.length,9);
  assert.equal(typeof clickHandler,'function');

  assert.deepEqual(all.rows.map(row => row.cells),[130,0,0,59,72,0,0,0,0]);
  const filtered = verifySelection(new Set(fixture.filtered_labels),fixture.filtered_expected);
  assert.equal(filtered.rows.at(-1).cells,261, 'A previously losing profile wins after filtering');
  console.log(`Real prediction statistics (${fixture.run_id}): 2349 predictions, 261 map cells, all row/total statistics, CSV and filtered competition passed`);
})().catch(error => {console.error(error);process.exitCode=1;});

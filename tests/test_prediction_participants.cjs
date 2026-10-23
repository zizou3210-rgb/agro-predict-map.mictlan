const assert = require('node:assert/strict');
const fs = require('node:fs');
const source = fs.readFileSync('src/main.js', 'utf8');
const extract = (name) => {
  const start = source.indexOf(`const ${name} =`);
  assert.ok(start >= 0);
  return source.slice(start, source.indexOf('\n};', start) + 3);
};
const names = ['CIM-RT-EAPP1-E -013', 'CIM-RT-EAPP1-E -015', 'CIM-RT-EAPP2-L-008'];
const winners = names.slice(0, 2).map(Name => ({ properties: { Name } }));
const datasetStore = { prediction: { summary: { selected_germplasm_names: names }, geojson: { features: winners } } };
const helpers = new Function('datasetStore', 'loadedFeatures', `
  const activeDataViewTab = 'prediction';
  const currentRenderedFlowMode = 'saved_model';
  const getPredictionSelectedIdHeader = () => '';
  const isCategoricalPredictionColorMode = () => isMultiGermplasmPredictionResult();
  const multiProfilePalette = ['red', 'blue', 'green'];
  ${extract('getPredictionDistinctGermplasmNames')}
  const isMultiGermplasmPredictionResult = () => getPredictionDistinctGermplasmNames().length > 1;
  ${extract('getAvailablePredictionProfileSummaries')}
  ${extract('getPredictionProfileColorMap')}
  return { names: getPredictionDistinctGermplasmNames, profiles: getAvailablePredictionProfileSummaries, colors: getPredictionProfileColorMap };
`)(datasetStore, winners);
assert.deepEqual(helpers.names(), names);
assert.deepEqual(helpers.profiles().map(profile => profile.label), names);
assert.equal(helpers.colors().get(names[2]), 'green');
// Filtering visible winners must not remove participants from the run legend.
winners.splice(1);
assert.deepEqual(helpers.profiles().map(profile => profile.label), names);
datasetStore.prediction.summary.manual_grid_prediction_names = names.slice(0, 2);
assert.deepEqual(helpers.names(), names);
// Older summaries without a recorded selection still use feature names.
datasetStore.prediction.summary = {};
assert.deepEqual(helpers.names(), [names[0]]);
console.log('Prediction legend retains participants with zero winning cells');

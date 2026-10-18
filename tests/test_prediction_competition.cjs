const assert = require('node:assert/strict');
const fs = require('node:fs');
const source = fs.readFileSync('src/main.js', 'utf8');
const extract = name => {
  const start = source.indexOf(`const ${name} =`);
  assert.ok(start >= 0);
  return source.slice(start, source.indexOf('\n};', start) + 3);
};
const createInteraction = new Function('state', `
  let predictionProfileInteractionInProgress = false;
  const activeDataViewTab = 'prediction';
  const isCategoricalPredictionColorMode = () => true;
  const isManualGridPredictionResult = () => true;
  const hasManualGridCompetitionFeatures = () => state.hasRaw;
  const predictionProfileSelectionTouched = true;
  const getCheckedPredictionProfileLabels = () => new Set(state.labels);
  const buildManualGridOverlaySelectionKey = labels => [...labels].sort().join('|');
  const ensureManualGridProfileOverlayForLabels = labels => state.fetch([...labels]);
  let activeManualGridServerOverlayKey = '';
  const currentTransform = {};
  const renderManualGridOverlay = () => state.rendered.push([...state.labels]);
  ${extract('runPredictionProfileInteractionWithLoading')}
  return runPredictionProfileInteractionWithLoading;
`);

(async () => {
  const purple = {properties: {'Forecast grid cell id':'1', GLS:0, 'Grain Yield predicted':3.214527}};
  const blue = {properties: {'Forecast grid cell id':'1', GLS:4, 'Grain Yield predicted':3.214527}};
  const detailsState = {selected:purple, hidden:0, renders:0};
  const syncSelected = new Function('state', `
    let selectedFeature = state.selected;
    let currentPage = 3;
    const hideTooltip = () => {state.hidden += 1;};
    const renderDetails = () => {state.renders += 1; state.details = selectedFeature;};
    ${extract('syncManualGridSelectedFeature')}
    return lookup => {syncManualGridSelectedFeature(lookup); return {selectedFeature,currentPage};};
  `)(detailsState);
  assert.equal(syncSelected(new Map([['1',blue]])).selectedFeature, blue);
  assert.equal(detailsState.details.properties.GLS, 4);
  assert.equal(detailsState.details.properties['Grain Yield predicted'], 3.214527);
  assert.equal(detailsState.hidden, 1);
  syncSelected(new Map([['1',blue]]));
  assert.equal(detailsState.renders, 1);
  assert.equal(syncSelected(new Map()).selectedFeature, null);
  assert.equal(detailsState.details, null);

  // Map setup can populate the cache before saved-model color mode is active.
  const cacheState = { categorical: false, id: '' };
  const getCache = new Function('state', `
    let manualGridOverlayComputationCache = null;
    const datasetStore = {prediction: {geojson: {features: [{properties:{Name:'C', 'Grain Yield predicted':3, 'Forecast grid cell id':'1'}}]}, summary:{}}};
    const isCategoricalPredictionColorMode = () => state.categorical;
    const getPredictionSelectedIdHeader = () => state.id;
    const getPredictionCategoryLabelForFeature = f => state.categorical ? f.properties.Name : '';
    const normalizePredictionCategoryLabel = value => value.trim();
    const normalizeManualGridCell = x => x;
    const getManualGridBackendOverlayBase = () => null;
    const getManualGridInterpolatedSurface = () => null;
    const getPredictionDistinctGermplasmNames = () => ['A','C'];
    const getPredictedTargetValue = p => p['Grain Yield predicted'];
    const asFloat = Number;
    const d3 = {mean: values => values.reduce((a,b)=>a+b,0)/values.length};
    const buildManualGridDirectHeatSamples = () => [];
    const buildManualGridPredictedStats = () => ({});
    ${extract('getManualGridOverlayComputationState')}
    const cells = [{grid_cell_id:'1'}];
    return () => getManualGridOverlayComputationState(cells);
  `)(cacheState);
  const initialCache = getCache();
  assert.equal(initialCache.featureEntries[0].featureLabel, '');
  cacheState.categorical = true;
  const competitionCache = getCache();
  assert.notEqual(competitionCache, initialCache);
  assert.equal(competitionCache.featureEntries[0].featureLabel, 'C');
  assert.equal(getCache(), competitionCache);
  cacheState.id = 'Farm';
  assert.notEqual(getCache(), competitionCache);

  const state = { hasRaw: true, labels: ['A'], rendered: [], fetch() { throw new Error('Local competition must not request the server'); } };
  const run = createInteraction(state);
  await run(() => { state.labels = ['C']; });
  assert.deepEqual(state.rendered.at(-1), ['C']);

  // Rapid clicks during a delayed backend request must retain the latest set.
  let release;
  const requests = [];
  state.hasRaw = false;
  state.fetch = labels => {
    requests.push(labels);
    return requests.length === 1 ? new Promise(resolve => { release = resolve; }) : Promise.resolve({});
  };
  const pending = run(() => { state.labels = ['A']; });
  await Promise.resolve();
  await run(() => { state.labels = ['B', 'C']; });
  assert.deepEqual(state.labels, ['B', 'C']);
  release({});
  await pending;
  assert.deepEqual(requests, [['A'], ['B', 'C']]);
  assert.deepEqual(state.rendered.at(-1), ['B', 'C']);

  const compete = new Function('normalizePredictionCategoryLabel', `${extract('buildManualGridWinningFeatureLookupFromEntries')}; return buildManualGridWinningFeatureLookupFromEntries;`)(value => value.trim());
  const entries = [
    { gridCellId: '1', featureLabel: 'A', predictedValue: 5, feature: 'A1' },
    { gridCellId: '1', featureLabel: 'B', predictedValue: 4, feature: 'B1' },
    { gridCellId: '1', featureLabel: 'C', predictedValue: 3, feature: 'C1' },
    { gridCellId: '2', featureLabel: 'A', predictedValue: 4, feature: 'A2' },
    { gridCellId: '2', featureLabel: 'B', predictedValue: 5, feature: 'B2' },
    { gridCellId: '2', featureLabel: 'C', predictedValue: 3, feature: 'C2' },
  ];
  assert.deepEqual([...compete(entries).values()], ['A1', 'B2']);
  assert.deepEqual([...compete(entries, new Set(['C'])).values()], ['C1', 'C2']);
  assert.deepEqual([...compete(entries, new Set(['B', 'C'])).values()], ['B1', 'B2']);
  console.log('Local competition and rapid checkbox changes passed');
})().catch(error => { console.error(error); process.exitCode = 1; });

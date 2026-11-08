const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
(async () => {
  const root = path.resolve(__dirname,'..');
  const source = fs.readFileSync(path.join(root,'src/main.js'),'utf8');
  const paletteSource = fs.readFileSync(path.join(root,'src/predictionColors.js'),'utf8');
  const {getPredictionProfilePaletteColor,getPredictionProfileColorName,multiProfilePalette} =
    await import(`data:text/javascript;base64,${Buffer.from(paletteSource).toString('base64')}`);
  const extract = name => {
    const start = source.indexOf(`const ${name} =`);
    assert.ok(start >= 0,name);
    return source.slice(start,source.indexOf('\n};',start)+3);
  };
  const colors = Array.from({length:1000},(_,index)=>getPredictionProfilePaletteColor(index));
  assert.equal(new Set(colors).size,1000, 'Never cycle back to an assigned color');
  assert.deepEqual(colors.slice(0,multiProfilePalette.length),multiProfilePalette);
  assert.notEqual(colors[0],colors[10]);
  colors.forEach(color=>{
    assert.match(color,/^#[0-9a-f]{6}$/);
    assert.ok(getPredictionProfileColorName(color));
  });
  const label = feature => `${feature.properties.Name} - ${feature.properties.Farm}`;
  const features = Array.from({length:25},(_,index)=>({properties:{Name:'Genotype',Farm:String(index+1)}}));
  const prediction = {
    rawGeojson:{features},geojson:{features:features.slice(0,2)},
    summary:{profile_summaries:features.map(feature=>({label:label(feature)}))},
  };
  const state = {selected:[],loaded:features.slice(0,2)};
  const helpers = new Function('state','prediction','getPredictionProfilePaletteColor',`
    const datasetStore={prediction};
    let loadedFeatures=state.loaded;
    const isCategoricalPredictionColorMode=()=>true;
    const getPredictionSelectedIdHeader=()=>'Farm';
    const getSelectedPredictionNameIdLabels=()=>state.selected;
    const getPredictionCategoryLabelForFeature=feature=>feature.properties.Name+' - '+feature.properties.Farm;
    const normalizePredictionCategoryLabel=value=>value.trim();
    const isOriginalDataRenderMode=()=>false;
    const isSavedModelRenderMode=()=>true;
    ${extract('mergePredictionCategoryLabels')}
    ${extract('getPredictionProfileColorMap')}
    ${extract('getPredictionProfileColor')}
    ${extract('getMarkerColor')}
    ${extract('toMarkerColorAlpha')}
    return {map:getPredictionProfileColorMap,marker:getMarkerColor,color:getPredictionProfileColor,
      alpha:toMarkerColorAlpha,load:features=>{loadedFeatures=features;}};
  `)(state,prediction,getPredictionProfilePaletteColor);
  const initial = helpers.map();
  assert.equal(initial.size,25, 'Include zero-win participants from raw predictions');
  assert.equal(new Set(initial.values()).size,25);
  features.forEach(feature=>{
    const color=initial.get(label(feature));
    assert.equal(helpers.marker(feature),color,'Circle uses the participant color');
    assert.equal(helpers.color(label(feature)),color,'Map uses the same participant color');
    assert.match(helpers.alpha(color,0.42),/^rgba\(/,'Map can apply opacity to every palette color');
  });
  const statisticsSource = fs.readFileSync(path.join(root,'src/predictionStatistics.js'),'utf8');
  const statistics = await import(`data:text/javascript;base64,${Buffer.from(statisticsSource).toString('base64')}`);
  const container = {innerHTML:'',querySelector(selector) {
    return selector==='table' ? {offsetHeight:0,parentElement:{}} : {addEventListener() {}};
  }};
  const context = {
    predictionStatisticsContainer:container,isManualGridPredictionResult:()=>true,
    datasetStore:{prediction},getPredictionSelectedIdHeader:()=>'Farm',
    getPredictedTargetColumnLabel:()=>'Yield',getPredictionProfileColorMap:helpers.map,
    getPredictionDistinctGermplasmNames:()=>['Genotype'],
    getPredictionSelectedIdValueForProperties:props=>props.Farm,
    getPredictionCategoryLabelForFeature:label,getPredictionNameAndIdLabelForFeature:label,
    hasManualGridCompetitionFeatures:()=>true,getPredictedTargetValue:props=>Number(props.Farm),
    getPredictionProfileColorName,asFloat:Number,escapeHtml:String,
    buildPredictionStatistics:statistics.buildPredictionStatistics,
    predictionStatisticsColumns:statistics.predictionStatisticsColumns,
    predictionStatisticsCsv:statistics.predictionStatisticsCsv,
    ResizeObserver:class {observe() {} disconnect() {}},
  };
  const render = new Function('context',`
    const {${Object.keys(context).join(',')}}=context;
    let predictionStatisticsRenderCache=null,predictionStatisticsResizeObserver=null;
    ${extract('renderPredictionStatistics')}
    return renderPredictionStatistics;
  `)(context);
  render(new Map(features.map((feature,index)=>[String(index),feature])));
  const rows=container.innerHTML.match(/<tbody>([\s\S]*?)<\/tbody>/)[1].match(/<tr>[\s\S]*?<\/tr>/g);
  assert.equal(rows.length,25);
  features.forEach((feature,index)=>{
    const color=helpers.marker(feature);
    assert.ok(rows[index].includes(`background:${color}`),'Table swatch must match circle and map');
    assert.ok(rows[index].includes(getPredictionProfileColorName(color)),'Table color name must match swatch');
  });
  helpers.load([features.at(-1)]);
  prediction.geojson={features:[features.at(-1)]};
  assert.deepEqual([...helpers.map()],[...initial], 'Filtering winners cannot change participant colors');
  // Older results without raw predictions still retain every summary participant.
  prediction.rawGeojson=null;
  assert.deepEqual([...helpers.map()],[...initial]);
  state.selected=['Genotype - 26'];
  assert.equal(helpers.map().size,26);
  assert.equal(new Set(helpers.map().values()).size,26);
  console.log('Prediction colors: 1000 unique colors, 25 participants, stable filtering and matching map/circle colors passed');
})().catch(error=>{console.error(error);process.exitCode=1;});

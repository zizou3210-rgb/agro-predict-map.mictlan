const assert = require('node:assert/strict');
const fs = require('node:fs');
const source = fs.readFileSync('src/main.js', 'utf8');
const start = source.indexOf('const renderPipelineProgress =');
const end = source.indexOf('\n};', start) + 3;
const details = { textContent: '' };
const activity = { parentElement: {}, children: [], replaceChildren(...children) { this.children = children; } };
const document = {
  getElementById(id) { return id === 'loading-work-details' ? details : activity; },
  createElement() { return { textContent: '' }; },
};
const percent = { textContent: '' };
const render = new Function('document', 'loadingPanel', 'loadingPercent', 'loadingBarFill', 'formatLoadingPercentLabel', `let pipelineActivityIdentity = ''; ${source.slice(start, end)}; return renderPipelineProgress;`)(document, {}, percent, { parentElement: {} }, value => `${value}%`);
const history = Array.from({ length: 45 }, (_, index) => ({ stage: `Farm process ${index}`, started_at: '2026-10-06T12:00:00Z', ended_at: '2026-10-06T12:00:01Z', status: 'finished', details: { stage_percent: 100 } }));
render({ percent: 99, stage: 'Saving Farm file', details: { stage_completed: 100, stage_total: 100, stage_unit: 'rows', stage_percent: 99 }, activity: history });
assert.equal(activity.children.length, 45);
assert.ok(activity.children.every(item => item.textContent.includes('100%') && item.textContent.endsWith('finished')));
assert.ok(details.textContent.includes('Stage: 99%'));
assert.equal(percent.textContent, 'Total 99%');
render({ percent: 99, stage: 'Reading Farm file', details: { stage_completed: 0, stage_total: 1, stage_unit: 'steps', stage_percent: 0 }, activity: [...history, { stage: 'Reading Farm file', started_at: '2026-10-06T12:00:02Z', status: 'running', details: { stage_percent: 0 } }] });
assert.equal(activity.children.length, 46);
assert.ok(activity.children.at(-1).textContent.includes('0%'));
assert.ok(activity.children.at(-1).textContent.endsWith('running'));
console.log('Farm UI activity and stage percentage checks passed');
render({ percent: 100, stage: 'Upload error', details: {}, activity: [{ stage: 'Saving workbook', started_at: '2026-10-06T12:00:02Z', ended_at: '2026-10-06T12:00:03Z', status: 'error', details: { stage_percent: 98 } }] });
assert.ok(activity.children[0].textContent.includes('98%'));
assert.ok(activity.children[0].textContent.endsWith('error'));
assert.ok(!activity.children[0].textContent.includes('finished'));

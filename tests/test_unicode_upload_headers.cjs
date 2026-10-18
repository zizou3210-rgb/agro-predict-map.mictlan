const assert = require('node:assert/strict');
const fs = require('node:fs');
const source = fs.readFileSync('src/main.js', 'utf8');
const start = source.indexOf('const encodeUploadHeaders =');
const end = source.indexOf('const startPipelineJob =', start);
let captured;
const encode = new Function('fetch', source.slice(start, end) + '; return { encodeUploadHeaders, fetchUpload };')((url, options) => { captured = {url, options}; return Promise.resolve({ok: true}); });
const raw = {'Content-Type': 'application/octet-stream', 'X-File-Name': 'maíz – 🌽 東京 100%.xlsx', 'X-Target-Column': 'Rendimiento ≥ 5', 'X-Selected-Germplasm-Names': JSON.stringify(['α–β', 'maíz🌽'])};
assert.throws(() => new Headers(raw), TypeError);
const safe = encode.encodeUploadHeaders(raw);
assert.doesNotThrow(() => new Headers(safe));
for (const [key, value] of Object.entries(raw)) {
  assert.equal(key.startsWith('X-') ? decodeURIComponent(safe[key]) : safe[key], value);
}
const body = {name: raw['X-File-Name']};
encode.fetchUpload('/upload', {method:'POST', headers:raw, body});
assert.equal(captured.options.body, body);
assert.equal(captured.options.headers['X-Upload-Header-Encoding'], 'uri-component-v1');
for (const route of ['start', 'germplasm-options', 'original-data', 'selecction-properties', 'selecction-properties/summary', 'selecction-properties/preview']) {
  assert.ok(source.includes(`fetchUpload("/api/process-xlsx/${route}",`));
}
console.log('Unicode upload headers and upload routes passed');

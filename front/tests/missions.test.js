import test from 'node:test';
import assert from 'node:assert/strict';
import { buildSync } from 'esbuild';
import { createRequire } from 'node:module';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

const require = createRequire(import.meta.url);
const output = buildSync({ entryPoints: ['src/MissionCreateForm.jsx'], bundle: true, write: false, platform: 'node', format: 'cjs', external: ['react'] }).outputFiles[0].text;
const component = { exports: {} };
new Function('require', 'module', 'exports', output)(require, component, component.exports);

test('mission form requires spacecraft and blocks submission while options load', () => {
  const html = renderToStaticMarkup(React.createElement(component.exports.default, { request: async () => {}, onClose: () => {}, onSaved: () => {} }));
  assert.match(html, /<select[^>]*name="spacecraft_id"[^>]*required=""/);
  assert.match(html, /<option value="" disabled="" selected="">Select a spacecraft/);
  assert.match(html, /<button disabled="">Save/);
  assert.match(html, /<input(?=[^>]*name="crew_size")(?=[^>]*type="number")(?=[^>]*required="")[^>]*>/);
  assert.match(html, /Search astronauts by name/);
  assert.match(html, /0 astronauts selected/);
  assert.doesNotMatch(html, /No spacecraft<\/option>|Sem nave/);
});

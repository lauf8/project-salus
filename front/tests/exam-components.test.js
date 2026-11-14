import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { buildSync } from 'esbuild';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

const require = createRequire(import.meta.url);
function component(path) {
  const output = buildSync({ entryPoints: [path], bundle: true, write: false, platform: 'node', format: 'cjs', external: ['react', 'react-dom/server'] }).outputFiles[0].text;
  const module = { exports: {} }; new Function('require', 'module', 'exports', output)(require, module, module.exports); return module.exports;
}
const { default: Catalog } = component('src/ExamCatalog.jsx');
const { default: ResultForm, StructuredResult } = component('src/ExamResultForm.jsx');
const definition = { name: 'Hemograma', revision: 1, fields: [{ code: 'hemoglobin', label: 'Hemoglobina', type: 'number', unit: 'g/dL', required: true, options: [] }, { code: 'fasting', label: "Fasting", type: 'boolean', required: false, options: [] }] };

test('catalog creation action requires authorized medical permission', () => {
  const readOnly = renderToStaticMarkup(React.createElement(Catalog, { types: [], canManage: false }));
  const medical = renderToStaticMarkup(React.createElement(Catalog, { types: [], canManage: true }));
  assert.doesNotMatch(readOnly, /Add exam/);
  assert.match(medical, /Add exam/);
});

test('result form uses assigned fields, units, references and collection metadata', () => {
  const html = renderToStaticMarkup(React.createElement(ResultForm, { exam: { definition_snapshot: definition }, initial: {} }));
  assert.match(html, /Hemoglobina \(g\/dL\) \*/);
  assert.match(html, /<input[^>]*required=""[^>]*name="value:hemoglobin"/);
  assert.match(html, /name="reference:hemoglobin"/);
  assert.match(html, /name="collected_at"/);
  assert.match(html, /name="laboratory"/);
  assert.match(html, /name="summary" required=""/);
});

test('history renders frozen labels, zero and false, plus laboratory reference', () => {
  const html = renderToStaticMarkup(React.createElement(StructuredResult, { result: { exam_snapshot: definition, structured_values: { hemoglobin: 0, fasting: false }, reference_ranges: { hemoglobin: 'Referência original' }, laboratory: 'Laboratório original' } }));
  assert.match(html, /0 g\/dL/); assert.match(html, />No</); assert.match(html, /Referência original/); assert.match(html, /Laboratório original/); assert.match(html, /Version 1/);
});

test('legacy result correction uses its original schema', () => {
  const html = renderToStaticMarkup(React.createElement(ResultForm, { exam: { definition_snapshot: definition }, initial: { id: 1, exam_snapshot: null, summary: 'Resultado antigo' } }));
  assert.doesNotMatch(html, /name="value:hemoglobin"/);
  assert.match(html, /Resultado antigo/);
});

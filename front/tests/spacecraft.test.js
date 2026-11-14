import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { buildSync } from 'esbuild';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

const require = createRequire(import.meta.url);
function load(path) {
  const output = buildSync({ entryPoints: [path], bundle: true, write: false, platform: 'node', format: 'cjs', external: ['react'] }).outputFiles[0].text;
  const module = { exports: {} };
  new Function('require', 'module', 'exports', output)(require, module, module.exports);
  return module.exports;
}
const { spacecraftPayload, modulePayload, validatePayload, fieldErrors } = load('src/spacecraft/forms.ts');
const { default: Form } = load('src/spacecraft/SpacecraftForm.tsx');
const data = values => { const result = new FormData(); Object.entries(values).forEach(([key, value]) => result.set(key, String(value))); return result; };
const material = { component: 'pressure_shell', material: 'Alloy', location: 'Primary structure', specification: '7075-T6', contact_environment: 'cabin_air' };
const initial = { id: 1, spacecraft_id: 2, name: 'Cabin', code: 'crew-cabin', technical_specifications: { dimensions_m: { length: 4.5, diameter: 3.2 }, dry_mass_kg: 2800, materials: [material], thermal_insulation: 'Multilayer', shielding: 'Debris' } };
const existingData = () => data({ name: 'Cabin', code: 'crew-cabin', length: 4.5, diameter: 3.2, dry_mass_kg: 2800, thermal_insulation: 'Multilayer', shielding: 'Debris' });

test('unchanged partial specification is omitted from PATCH and optional fields can be cleared', () => {
  const payload = modulePayload(existingData(), [material], initial);
  assert.equal(Object.hasOwn(payload, 'technical_specifications'), false);
  assert.equal(payload.manufactured_year, null);
  assert.equal(payload.pressurized_volume_m3, null);
  assert.equal(payload.is_pressurized, null);
  assert.equal(payload.is_habitable, null);
});

test('editing specification sends all existing dimensions, mass and material metadata', () => {
  const form = existingData(); form.set('shielding', 'Revised shielding');
  const payload = modulePayload(form, [material], initial);
  assert.equal(payload.technical_specifications.dimensions_m.length, 4.5);
  assert.equal(payload.technical_specifications.dimensions_m.diameter, 3.2);
  assert.equal(payload.technical_specifications.dry_mass_kg, 2800);
  assert.deepEqual(payload.technical_specifications.materials[0], material);
  assert.equal(payload.technical_specifications.thermal_insulation, 'Multilayer');
  assert.equal(payload.technical_specifications.shielding, 'Revised shielding');
});

test('removing all specification fields clears the complete specification', () => {
  const payload = modulePayload(data({ name: 'Cabin', code: 'crew-cabin' }), [], initial);
  assert.equal(payload.technical_specifications, null);
});

test('three-state fields preserve false and true and encode unknown as null', () => {
  for (const [value, expected] of [['true', true], ['false', false], ['unknown', null]]) {
    const payload = modulePayload(data({ name: 'Cabin', code: 'crew-cabin', is_pressurized: value, is_habitable: value }), []);
    assert.equal(payload.is_pressurized, expected);
    assert.equal(payload.is_habitable, expected);
  }
});

test('forms reject blank names, invalid years, non-HTTP URLs and invalid materials', () => {
  const errors = validatePayload(spacecraftPayload(data({ name: ' ', manufactured_year: 32768, technical_reference_url: 'ftp://example.com' })));
  assert.ok(errors.name); assert.ok(errors.manufactured_year); assert.ok(errors.technical_reference_url);
  const moduleErrors = validatePayload(modulePayload(data({ name: 'Cabin', code: ' ', length: 0, dry_mass_kg: -1, pressurized_volume_m3: -3 }), [{ component: ' ', material: ' ' }]));
  for (const key of ['code', 'length', 'dry_mass_kg', 'pressurized_volume_m3', 'materials.0.component', 'materials.0.material']) assert.ok(moduleErrors[key], key);
  assert.deepEqual(fieldErrors({ status: 422, detail: [{ loc: ['body', 'technical_specifications', 'materials', 0, 'material'], msg: 'Required' }] }, true), { 'materials.0.material': 'Required' });
  assert.deepEqual(fieldErrors({ status: 409, message: 'Duplicate code' }, true), { code: 'Duplicate code' });
});

test('editing renders saved material metadata, tri-state values and technical fields', () => {
  const html = renderToStaticMarkup(React.createElement(Form, { request: () => {}, spacecraftId: 2, initial: { ...initial, is_pressurized: false, is_habitable: true }, onClose: () => {}, onSaved: () => {} }));
  for (const value of ['pressure_shell', '7075-T6', 'cabin_air', '2800', '4.5', 'Multilayer', 'Debris']) assert.ok(html.includes(value));
  assert.match(html, /value="false" selected=""/);
  assert.match(html, /value="true" selected=""/);
  assert.match(html, /Unknown/);
});


test('maximum crew capacity accepts positive integers and supports explicit clearing', () => {
  const payload = spacecraftPayload(data({ name: 'Explorer', maximum_crew_capacity: 6 }));
  assert.equal(payload.maximum_crew_capacity, 6);
  assert.equal(validatePayload(payload).maximum_crew_capacity, undefined);
  assert.equal(spacecraftPayload(data({ name: 'Explorer', maximum_crew_capacity: '' })).maximum_crew_capacity, null);
  for (const value of [0, -1, 6.5, 2147483648]) assert.ok(validatePayload(spacecraftPayload(data({ name: 'Explorer', maximum_crew_capacity: value }))).maximum_crew_capacity);
});

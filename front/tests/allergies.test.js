import test from 'node:test';
import assert from 'node:assert/strict';
import { allergyStatus } from '../src/allergies.js';

test('open screening remains pending with or without registered allergies', () => {
  assert.equal(allergyStatus({ allergy_screening_completed: false, active_ingredients: [] }), "Screening pending");
  assert.equal(allergyStatus({ allergy_screening_completed: false, active_ingredients: [{ id: 1, name: 'Allergen' }] }), "Screening pending");
});

test('completed screening distinguishes registered allergies from no known allergies', () => {
  assert.equal(allergyStatus({ allergy_screening_completed: true, active_ingredients: [] }), "No known allergies");
  assert.equal(allergyStatus({ allergy_screening_completed: true, active_ingredients: [{ id: 1, name: 'Allergen' }] }), "Allergies recorded");
});

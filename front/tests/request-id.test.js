import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequestId } from '../src/services/request-id.js';

const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

test('uses native UUID generation when available', () => {
  const expected = '9adfe784-6897-4259-8866-74d5668ed913';
  assert.equal(createRequestId({ randomUUID: () => expected }), expected);
});

test('supports HTTP browsers that expose getRandomValues without randomUUID', () => {
  const provider = { getRandomValues: bytes => globalThis.crypto.getRandomValues(bytes) };
  assert.equal(provider.randomUUID, undefined);
  const first = createRequestId(provider);
  const second = createRequestId(provider);
  assert.match(first, uuid);
  assert.match(second, uuid);
  assert.notEqual(first, second);
});

test('missing browser crypto does not crash measurement forms', () => {
  assert.equal(createRequestId(null), null);
  assert.equal(createRequestId({}), null);
});

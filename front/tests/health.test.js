import test from "node:test";
import assert from "node:assert/strict";
import {
  indicators,
  formatValue,
  buildChartData,
} from "../src/health-indicators.js";

test("todos os indicadores têm identificador e hotspot próprios", () => {
  assert.equal(indicators.length, 12);
  assert.equal(new Set(indicators.map((item) => item.id)).size, 12);
  assert.equal(
    new Set(indicators.map((item) => item.point.join(","))).size,
    12,
  );
});
test("ausência de dados e escalas são exibidas sem classificações clínicas", () => {
  for (const indicator of indicators)
    assert.equal(formatValue(null, indicator), "No data");
  assert.equal(
    formatValue(
      { value: 450 },
      indicators.find((item) => item.id === "sleep_duration"),
    ),
    "7h 30min",
  );
  assert.equal(
    formatValue(
      { systolic: 120, diastolic: 80 },
      indicators.find((item) => item.id === "blood_pressure"),
    ),
    "120/80",
  );
  assert.equal(
    formatValue(
      { category: "pain" },
      indicators.find((item) => item.id === "consciousness"),
    ),
    "Responds to pain",
  );
  assert.equal(
    formatValue(
      { value: 4 },
      indicators.find((item) => item.id === "sleep_quality"),
    ),
    "4 · Good",
  );
});
test("gráfico mantém pontos brutos e lacunas sem interpolar ou agregar observações", () => {
  const start = Date.parse("2026-01-01T00:00:00Z"),
    hour = 3600000;
  const rows = [
    { id: 3, value: 75, collected_at: "2026-01-01T03:10:00Z" },
    { id: 1, value: 70, collected_at: "2026-01-01T00:10:00Z" },
    { id: 2, value: 72, collected_at: "2026-01-01T00:20:00Z" },
  ];
  const points = buildChartData(rows, start, start + 4 * hour, hour);
  assert.deepEqual(
    points.filter((point) => point.id).map((point) => point.id),
    [1, 2, 3],
  );
  assert.deepEqual(
    points.filter((point) => !point.id).map((point) => point.time),
    [start + hour, start + 2 * hour, start + 4 * hour],
  );
  assert.equal(points.filter((point) => point.value === null).length, 3);
});

test("glicemia usa mg/dL e mantém valores numéricos no histórico", () => {
  const indicator = indicators.find((item) => item.id === "blood_glucose");
  assert.equal(indicator.unit, "mg/dL");
  assert.ok(indicator.min > 0);
  assert.equal(formatValue({ value: 95 }, indicator), "95");
  assert.equal(formatValue(null, indicator), "No data");
});

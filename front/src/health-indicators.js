export const indicators = [
  {
    id: "blood_glucose",
    name: "Blood glucose (blood sugar)",
    region: "Blood",
    unit: "mg/dL",
    point: [270, 275],
    min: 0.1,
  },
  {
    id: "consciousness",
    name: "Level of consciousness",
    region: "Head",
    point: [147, 48],
    category: {
      alert: "Alert",
      voice: "Responds to voice",
      pain: "Responds to pain",
      unresponsive: "Unresponsive",
    },
  },
  {
    id: "mood",
    name: "Mood",
    unit: "1–5",
    region: "Head",
    point: [173, 56],
    min: 1,
    max: 5,
    labels: ["Very poor", "Poor", "Neutral", "Good", "Very good"],
  },
  {
    id: "attention",
    name: "Changes in attention",
    region: "Head",
    point: [158, 78],
    category: { better: "Better", usual: "Usual", worse: "Worse" },
  },
  {
    id: "heart_rate",
    name: "Heart rate",
    region: "Heart",
    unit: "bpm",
    point: [170, 164],
    min: 0.1,
  },
  {
    id: "respiratory_rate",
    name: "Respiratory rate",
    region: "Lungs",
    unit: "breaths/min",
    point: [134, 152],
    min: 0.1,
  },
  {
    id: "blood_pressure",
    name: "Blood pressure",
    region: "Wrist",
    unit: "mmHg",
    point: [79, 264],
  },
  {
    id: "oxygen_saturation",
    name: "Oxygen saturation",
    region: "Finger",
    unit: "%",
    point: [75, 282],
    min: 0,
    max: 100,
  },
  {
    id: "body_temperature",
    name: "Body temperature",
    region: "Armpit",
    unit: "°C",
    point: [111, 177],
    min: 0.1,
  },
  {
    id: "sleep_duration",
    name: "Sleep duration",
    region: "Sleep and recovery",
    unit: "min",
    point: [270, 318],
    min: 0,
  },
  {
    id: "sleep_quality",
    name: "Sleep quality",
    unit: "1–5",
    region: "Sleep and recovery",
    point: [270, 360],
    min: 1,
    max: 5,
    labels: ["Very poor", "Poor", "Fair", "Good", "Very good"],
  },
  {
    id: "fatigue",
    name: "Fatigue",
    unit: "0–10",
    region: "Sleep and recovery",
    point: [270, 402],
    min: 0,
    max: 10,
  },
];
export const sources = {
  self_report: "Self-report",
  manual_measurement: "Manual measurement",
  device: "Device",
};
export const formatDate = (value) =>
  value
    ? new Date(value).toLocaleString("en-US", {
        dateStyle: "short",
        timeStyle: "short",
      })
    : "No data";
export function formatValue(observation, indicator) {
  if (!observation) return "No data";
  if (indicator.category)
    return indicator.category[observation.category] || observation.category;
  if (indicator.id === "blood_pressure")
    return `${observation.systolic}/${observation.diastolic}`;
  if (indicator.id === "sleep_duration")
    return `${Math.floor(observation.value / 60)}h ${observation.value % 60}min`;
  if (indicator.labels)
    return `${observation.value} · ${indicator.labels[observation.value - 1]}`;
  return Number(observation.value).toLocaleString("en-US");
}
export function buildChartData(rows, start, end, bucketSize) {
  const occupied = new Set(
    rows.map((row) =>
      Math.floor((Date.parse(row.collected_at) - start) / bucketSize),
    ),
  );
  const points = rows.map((row) => ({
    ...row,
    time: Date.parse(row.collected_at),
  }));
  for (let time = start; time <= end; time += bucketSize) {
    if (!occupied.has(Math.floor((time - start) / bucketSize)))
      points.push({ time, value: null, systolic: null, diastolic: null });
  }
  return points.sort((a, b) => a.time - b.time || (a.id || 0) - (b.id || 0));
}

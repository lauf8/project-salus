import BodyMap from "./HumanBodyMap";
import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  indicators,
  sources,
  formatDate,
  formatValue,
  buildChartData,
} from "./health-indicators";
import { HeartPulse, Thermometer, Activity, Wind, Moon, BedDouble, Brain, ScanEye, Droplets } from "lucide-react";
import "./health.css";
import { createRequestId } from "./services/request-id";
import { measurementFields, measurementContext } from "./measurement-fields";
import AllergySection from "./AllergySection";
import HealthAlerts from "./HealthAlerts";
import AlertSettings from "./AlertSettings";
import { highestAlert, measurementStatusLabels, observationContext, severityLabels, symptomLabels } from "./health-alerts";

const vitalIds = ["heart_rate", "body_temperature", "blood_pressure", "respiratory_rate"];
const displayIndicators = [...vitalIds.map((id) => indicators.find((item) => item.id === id)), ...indicators.filter((item) => !vitalIds.includes(item.id))];
const indicatorIcons = { heart_rate: HeartPulse, body_temperature: Thermometer, blood_pressure: Activity, respiratory_rate: Wind, sleep_quality: Moon, sleep_duration: BedDouble, attention: Brain, consciousness: ScanEye, blood_glucose: Droplets, oxygen_saturation: Droplets };
function IndicatorIcon({ item, latest }) {
  const Icon = indicatorIcons[item.id];
  const emoji = item.id === "mood"
    ? (latest ? ["😞", "🙁", "😐", "🙂", "😄"][latest.value - 1] : "😶")
    : latest ? (latest.value <= 3 ? "🙂" : latest.value <= 6 ? "😓" : "😩") : "😶";
  return <span className={`indicator-icon indicator-icon-${item.id}`} aria-hidden="true">{Icon ? <Icon size={23} strokeWidth={1.7} /> : emoji}</span>;
}

const localNow = () =>
  new Date(Date.now() - new Date().getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 16);
const periodOptions = [
  { days: 1, label: "24 hours", bucket: 3600000 },
  { days: 7, label: "7 days", bucket: 21600000 },
  { days: 30, label: "30 days", bucket: 86400000 },
];

export { default as BodyMap } from "./HumanBodyMap";

function BodyConnections({ containerRef, selected }) {
  const [paths, setPaths] = useState([]);
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const update = () => {
      const bounds = container.getBoundingClientRect();
      setPaths(
        indicators.flatMap((item) => {
          const point = container.querySelector(
            `.body-hotspot[data-indicator="${item.id}"]`,
          );
          const card = container.querySelector(
            `.health-card[data-indicator="${item.id}"]`,
          );
          if (!point || !card) return [];
          const origin = point.getBoundingClientRect(),
            target = card.getBoundingClientRect();
          const x = origin.x + origin.width / 2 - bounds.x,
            y = origin.y + origin.height / 2 - bounds.y;
          const endX =
            (target.right < origin.x ? target.right : target.left) - bounds.x;
          const endY = target.y + target.height / 2 - bounds.y;
          const elbow = (x + endX) / 2;
          return [{ id: item.id, d: `M${x} ${y}H${elbow}V${endY}H${endX}` }];
        }),
      );
    };
    const observer = new ResizeObserver(update);
    observer.observe(container);
    for (const card of container.querySelectorAll(".health-card"))
      observer.observe(card);
    container.addEventListener("body-map-change", update);
    update();
    return () => {
      observer.disconnect();
      container.removeEventListener("body-map-change", update);
    };
  }, [containerRef]);
  return (
    <svg className="body-connections" aria-hidden="true">
      {paths.map((path) => (
        <path
          key={path.id}
          d={path.d}
          fill="none"
          stroke={path.id === selected ? "#0b3d91" : "#b4c7e2"}
          strokeWidth={path.id === selected ? 2 : 1}
          strokeDasharray={path.id === selected ? undefined : "3 4"}
        />
      ))}
    </svg>
  );
}

function ObservationForm({
  indicator,
  missionId,
  summary,
  request,
  path,
  onSaved,
  onClose,
}) {
  const [requestId] = useState(createRequestId);
  const fields = measurementFields(indicator.id);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [session, setSession] = useState(false);
  async function submit(event) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const body = {
      indicator: indicator.id,
      client_request_id: requestId,
      unit: indicator.unit || null,
      ...measurementContext(indicator.id, data),
      collected_at: new Date(data.get("collected_at")).toISOString(),
      mission_id: missionId ? Number(missionId) : null,
      source: data.get("source"),
      note: data.get("note") || null,
      is_preflight_reference: data.get("is_preflight_reference") === "on",
    };
    if (indicator.category) body.category = data.get("category");
    else if (indicator.id === "blood_pressure") {
      body.systolic = Number(data.get("systolic"));
      body.diastolic = Number(data.get("diastolic"));
    } else if (indicator.id === "sleep_duration" && session) {
      body.sleep_started_at = new Date(
        data.get("sleep_started_at"),
      ).toISOString();
      body.sleep_ended_at = new Date(data.get("sleep_ended_at")).toISOString();
    } else if (indicator.id === "sleep_duration") {
      body.value =
        Number(data.get("sleep_hours")) * 60 +
        Number(data.get("sleep_minutes"));
    } else body.value = Number(data.get("value"));
    setBusy(true);
    setError("");
    try {
      await request(path + "/observations", { method: "POST", body });
      onSaved();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }
  const scale = indicator.labels || indicator.id === "fatigue";
  return (
    <div
      className="overlay"
      onKeyDown={(event) => {
        if (event.key === "Escape" && !busy) onClose();
        if (event.key === "Tab") {
          const controls = event.currentTarget.querySelectorAll(
            "button:not(:disabled),input:not(:disabled),select:not(:disabled),textarea:not(:disabled)",
          );
          const first = controls[0],
            last = controls[controls.length - 1];
          if (event.shiftKey && document.activeElement === first) {
            event.preventDefault();
            last.focus();
          } else if (!event.shiftKey && document.activeElement === last) {
            event.preventDefault();
            first.focus();
          }
        }
      }}
    >
      <section
        className="modal health-form"
        role="dialog"
        aria-modal="true"
        aria-labelledby="observation-title"
      >
        <header>
          <h2 id="observation-title">
            Record {indicator.name.toLowerCase()}
          </h2>
          <button
            className="icon"
            type="button"
            disabled={busy}
            onClick={onClose}
            aria-label="Close"
          >
            ×
          </button>
        </header>
        <form onSubmit={submit}>
          <label>
            Collection time
            <input
              name="collected_at"
              type="datetime-local"
              required
              defaultValue={localNow()}
              max={localNow()}
              autoFocus
            />
          </label>
          {indicator.id === "sleep_duration" && (
            <label className="checkfield">
              <input
                type="checkbox"
                checked={session}
                onChange={(event) => setSession(event.target.checked)}
              />
              Enter sleep start and end times
            </label>
          )}
          {indicator.category ? (
            <label>
              {indicator.id === "attention"
                ? "Compared with your individual baseline"
                : "AVPU assessment"}
              <select name="category">
                {Object.entries(indicator.category).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
          ) : indicator.id === "blood_pressure" ? (
            <div className="health-form-pair">
              <label>
                Systolic (mmHg)
                <input
                  name="systolic"
                  type="number"
                  min="1"
                  step="any"
                  required
                />
              </label>
              <label>
                Diastolic (mmHg)
                <input
                  name="diastolic"
                  type="number"
                  min="1"
                  step="any"
                  required
                />
              </label>
            </div>
          ) : indicator.id === "sleep_duration" && session ? (
            <>
              <label>
                Sleep start
                <input
                  name="sleep_started_at"
                  type="datetime-local"
                  required
                  max={localNow()}
                />
              </label>
              <label>
                Sleep end
                <input
                  name="sleep_ended_at"
                  type="datetime-local"
                  required
                  max={localNow()}
                />
              </label>
              <small>The system will calculate the duration in minutes.</small>
            </>
          ) : indicator.id === "sleep_duration" ? (
            <div className="health-form-pair">
              <label>
                Hours of sleep
                <input
                  name="sleep_hours"
                  type="number"
                  min="0"
                  step="1"
                  required
                />
              </label>
              <label>
                Additional minutes
                <input
                  name="sleep_minutes"
                  type="number"
                  min="0"
                  max="59"
                  step="1"
                  defaultValue="0"
                  required
                />
              </label>
            </div>
          ) : scale ? (
            <label>
              {indicator.name}
              <select name="value">
                {Array.from(
                  { length: indicator.max - indicator.min + 1 },
                  (_, index) => index + indicator.min,
                ).map((value) => (
                  <option key={value} value={value}>
                    {value}
                    {indicator.labels
                      ? ` · ${indicator.labels[value - 1]}`
                      : value === 0
                        ? " · No fatigue"
                        : value === 10
                          ? " · Maximum fatigue"
                          : ""}
                  </option>
                ))}
              </select>
              {indicator.id === "fatigue" && (
                <small>0: no fatigue · 10: maximum fatigue</small>
              )}
            </label>
          ) : (
            <label>
              Value ({indicator.unit})
              <input
                name="value"
                type="number"
                min={indicator.min}
                max={indicator.max}
                step={indicator.id === "sleep_duration" ? "1" : "any"}
                required
              />
            </label>
          )}
          {fields.activity && <fieldset><legend>Activity at collection</legend>
            <label>Activity at collection<select name="activity" defaultValue="unknown"><option value="unknown">Unknown</option><option value="rest">At rest</option><option value="exercise">During exercise</option></select></label>
          </fieldset>}
          {fields.oxygen && <fieldset><legend>Respiratory context</legend><label>Supplemental oxygen use<select name="supplemental_oxygen" defaultValue="unknown"><option value="unknown">Unknown</option><option value="false">No</option><option value="true">Yes</option></select></label>
          </fieldset>}
          {fields.quality && <fieldset><legend>Reading quality</legend><label>Measurement quality<select name="signal_quality" defaultValue="unknown"><option value="unknown">Not provided</option><option value="good">Good</option><option value="poor">Insufficient / poor signal</option></select></label></fieldset>}
          {fields.meal && <fieldset><legend>Blood glucose context</legend><label>Meal context<select name="glucose_context" defaultValue="unknown"><option value="unknown">Unknown</option><option value="fasting">Fasting</option><option value="after_meal">After a meal</option></select></label></fieldset>}
          {fields.symptoms && <fieldset><legend>Symptoms associated with the measurement</legend><label>Symptom record status<select name="symptoms_status" defaultValue="unknown"><option value="unknown">Unknown / not recorded</option><option value="absent">Warning symptoms absent</option><option value="present">Symptoms present (select below)</option></select></label>{Object.entries(symptomLabels).map(([value, label]) => <label className="checkfield" key={value}><input type="checkbox" name="symptoms" value={value}/>{label}</label>)}</fieldset>}
          {fields.confusion && <fieldset><legend>Consciousness assessment</legend><label>New-onset confusion<select name="acute_confusion" defaultValue="unknown"><option value="unknown">Unknown / not assessed</option><option value="false">No</option><option value="true">Yes</option></select></label></fieldset>}
          <label>
            Source
            <select
              name="source"
              defaultValue={
                indicator.id === "consciousness"
                  ? "manual_measurement"
                  : indicator.category ||
                      scale ||
                      indicator.id === "sleep_duration"
                    ? "self_report"
                    : "manual_measurement"
              }
            >
              {indicator.id !== "consciousness" && (
                <option value="self_report">Self-report</option>
              )}
              <option value="manual_measurement">Manual measurement</option>
            </select>
          </label>
          <label>
            Note (optional)
            <textarea name="note" maxLength={4000} rows={3} />
          </label>
          {summary.can_set_reference && missionId && (
            <label className="checkfield">
              <input name="is_preflight_reference" type="checkbox" />
              Use as individual pre-mission baseline
            </label>
          )}
          {error && (
            <div className="error" role="alert">
              {error}
            </div>
          )}
          <footer>
            <button
              className="secondary"
              type="button"
              disabled={busy}
              onClick={onClose}
            >
              Cancel
            </button>
            <button disabled={busy}>
              {busy ? "Saving…" : "Save measurement"}
            </button>
          </footer>
        </form>
      </section>
    </div>
  );
}

function Delta({ value, indicator }) {
  if (!value) return <>No comparison available</>;
  if (indicator.id === "sleep_duration")
    return (
      <>
        {value.value > 0 ? "+" : value.value < 0 ? "−" : ""}
        {formatValue({ value: Math.abs(value.value) }, indicator)}
      </>
    );
  const format = (number) =>
    `${number > 0 ? "+" : ""}${number.toLocaleString("en-US")}`;
  return (
    <>
      {indicator.id === "blood_pressure"
        ? `${format(value.systolic)} / ${format(value.diastolic)}`
        : format(value.value)}{" "}
      {indicator.labels || indicator.id === "fatigue"
        ? "points"
        : indicator.unit || "points"}
    </>
  );
}

export default function HealthDashboard({
  request,
  user,
  missions,
  users,
  context,
  initialSelection,
  lockSelection = false,
}) {
  const layoutRef = useRef(null);
  const [alerts, setAlerts] = useState([]), [alertsLoading, setAlertsLoading] = useState(false), [alertsError, setAlertsError] = useState("");
  const [missionId, setMissionId] = useState(initialSelection?.missionId || ""),
    [astronautId, setAstronautId] = useState(
      initialSelection?.astronautId || (context?.is_astronaut ? String(user.id) : ""),
    );
  const [summary, setSummary] = useState(null),
    [summaryError, setSummaryError] = useState(""),
    [summaryLoading, setSummaryLoading] = useState(true);
  const [selected, setSelected] = useState(initialSelection?.indicator || "heart_rate"),
    [period, setPeriod] = useState(7),
    [rows, setRows] = useState([]),
    [historyError, setHistoryError] = useState(""),
    [historyLoading, setHistoryLoading] = useState(true),
    [revision, setRevision] = useState(0),
    [form, setForm] = useState(false);
  const path = `/v1/health/astronauts/${astronautId}`,
    indicator = indicators.find((item) => item.id === selected);
  const range = useMemo(() => {
    const end = Date.now();
    return { start: end - period * 86400000, end };
  }, [period, revision, selected, astronautId, missionId]);
  const entry = summary?.indicators.find((item) => item.indicator === selected);

  useEffect(() => {
    const controller = new AbortController();
    setSummary(null);
    setSummaryLoading(true);
    setSummaryError("");
    if (!astronautId) {
      setSummaryLoading(false);
      return () => controller.abort();
    }
    request(`${path}/summary${missionId ? `?mission_id=${missionId}` : ""}`, {
      signal: controller.signal,
    })
      .then((data) => {
        if (!controller.signal.aborted) setSummary(data);
      })
      .catch((err) => {
        if (!controller.signal.aborted) setSummaryError(err.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setSummaryLoading(false);
      });
    return () => controller.abort();
  }, [path, missionId, request, revision]);
  useEffect(() => {
    const controller = new AbortController();
    setRows([]);
    setHistoryLoading(true);
    setHistoryError("");
    if (!astronautId) {
      setHistoryLoading(false);
      return () => controller.abort();
    }
    async function load() {
      let all = [];
      for (let page = 1; ; page++) {
        const query = new URLSearchParams({
          indicator: selected,
          start: new Date(range.start).toISOString(),
          end: new Date(range.end).toISOString(),
          page: String(page),
          per_page: "100",
          ...(missionId ? { mission_id: missionId } : {}),
        });
        const response = await request(`${path}/history?${query}`, {
          signal: controller.signal,
        });
        all.push(...response.data);
        if (!response.pagination.has_next) break;
      }
      if (!controller.signal.aborted) setRows(all);
    }
    load()
      .catch((err) => {
        if (!controller.signal.aborted) setHistoryError(err.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setHistoryLoading(false);
      });
    return () => controller.abort();
  }, [path, missionId, selected, range, request]);
  useEffect(() => {
    const controller = new AbortController();
    setAlerts([]); setAlertsError(""); setAlertsLoading(Boolean(astronautId));
    if (!astronautId) return () => controller.abort();
    async function loadAlerts() {
      const rows = [];
      for (let page = 1; ; page++) {
        const query = new URLSearchParams({ status: "active", page: String(page), per_page: "100", ...(missionId ? { mission_id: missionId } : {}) });
        const data = await request(`${path}/alerts?${query}`, { signal: controller.signal });
        rows.push(...data.data);
        if (!data.pagination.has_next) break;
      }
      if (!controller.signal.aborted) setAlerts(rows);
    }
    loadAlerts().catch(err => { if (!controller.signal.aborted) setAlertsError(err.message); }).finally(() => { if (!controller.signal.aborted) setAlertsLoading(false); });
    return () => controller.abort();
  }, [request, path, astronautId, missionId, revision]);
  useEffect(() => {
    if (initialSelection && !alertsLoading && !summaryLoading) document.getElementById(`health-indicator-${initialSelection.indicator}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [initialSelection, alertsLoading, summaryLoading]);
  const chartData = useMemo(
    () =>
      buildChartData(
        rows,
        range.start,
        range.end,
        periodOptions.find((item) => item.days === period).bucket,
      ),
    [rows, range, period],
  );
  const canRecord =
    summary?.can_record &&
    (selected !== "consciousness" || summary.can_record_consciousness);
  const selectIndicator = (id) => {
    setSelected(id);
    setForm(false);
  };
  const candidates = (context?.supervised_astronauts || []).filter(
    (candidate) => String(candidate.mission_id) === missionId,
  );
  const renderIndicatorCard = (item) => {
            const indicatorSummary = summary?.indicators.find(record => record.indicator === item.id);
            const latest = indicatorSummary?.latest;
            const activeAlert = highestAlert(alerts, item.id);
            return (
              <article
                key={item.id}
                id={`health-indicator-${item.id}`}
                data-indicator={item.id}
                className={`health-card ${selected === item.id ? "selected" : ""} ${activeAlert ? `has-alert alert-${activeAlert.severity}` : ""}`}
              >
                <button type="button" className="health-card-main" aria-pressed={selected === item.id} aria-controls="indicator-detail" onClick={() => selectIndicator(item.id)}>
                <IndicatorIcon item={item} latest={summaryLoading || summaryError ? null : latest} />
                <span>{item.name}</span>
                {activeAlert && <span className="health-card-alert">⚠ {(activeAlert.awaiting_medical_review ? "Medical review pending" : severityLabels[activeAlert.severity])} · {activeAlert.status === "acknowledged" ? "Acknowledged" : "Active"}</span>}
                {!summaryLoading && !summaryError && ["stale", "insufficient_quality"].includes(indicatorSummary?.measurement_status) && <small>{measurementStatusLabels[indicatorSummary.measurement_status]}</small>}
                <strong>
                  {summaryLoading
                    ? "Loading…"
                    : summaryError
                      ? "Unavailable"
                      : formatValue(latest, item)}
                  {latest && item.unit && item.id !== "sleep_duration" && (
                    <small> {item.unit}</small>
                  )}
                </strong>
                <time dateTime={latest?.collected_at}>
                  {summaryLoading ? "" : formatDate(latest?.collected_at)}
                </time>
                <small>{item.id === "mood" ? "Latest recorded mood" : item.id === "fatigue" ? "Latest recorded fatigue · 0–10" : item.region}</small>
                </button>
                {astronautId && <HealthAlerts compact indicatorId={item.id} showEmptyHistory={selected === item.id} key={`${astronautId}-${missionId}-${item.id}`} request={request} astronautId={astronautId} missionId={missionId} alerts={alerts.filter(alert => alert.indicator === item.id)} loading={selected === item.id && alertsLoading} error={selected === item.id ? alertsError : ""} onRefresh={() => setRevision(value => value + 1)} onIndicator={id => { selectIndicator(id); document.getElementById("indicator-detail")?.scrollIntoView({ behavior: "smooth" }); }} onMeasure={id => { selectIndicator(id); setForm(true); }} canMeasureConsciousness={summary?.can_record_consciousness}/>}
              </article>
            );
  };
  return (
    <section className="health-dashboard">
      <div className="page-heading">
        <div>
          <h1>Health monitoring</h1>
          <p>
            {astronautId === String(user.id)
              ? "My indicators"
              : users.find((candidate) => String(candidate.id) === astronautId)
                  ?.name}
          </p>
        </div>
        <button
          className="secondary"
          onClick={() => setRevision((value) => value + 1)}
        >
          Refresh
        </button>
      </div>
      <div className="health-context">
        <label>
          Mission
          <select
            aria-label="Mission"
            disabled={lockSelection}
            value={missionId}
            onChange={(event) => {
              setMissionId(event.target.value);
              setAstronautId(context?.is_astronaut ? String(user.id) : "");
              setForm(false);
            }}
          >
            <option value="">
              {context?.is_astronaut
                ? "All my measurements"
                : "Select a mission"}
            </option>
            {missions.map((mission) => (
              <option key={mission.id} value={mission.id}>
                {mission.name}
              </option>
            ))}
          </select>
        </label>
        {(user.is_physician || user.is_nurse) && missionId && (
          <label>
            Astronaut
            <select
              aria-label="Astronaut"
              disabled={lockSelection}
              value={astronautId}
              onChange={(event) => {
                setAstronautId(event.target.value);
                setForm(false);
              }}
            >
              <option value="">Select an astronaut</option>
              {context?.is_astronaut && (
                <option value={user.id}>My indicators</option>
              )}
              {candidates.map((candidate) => (
                <option key={candidate.id} value={candidate.id}>
                  {candidate.name}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>
      {!astronautId && (
        <p role="status">
          Select a mission and an astronaut to view or record measurements.
        </p>
      )}
      {summaryLoading && <p role="status">Loading indicators…</p>}
      {summaryError && (
        <div className="error" role="alert">
          {summaryError}
          <button
            className="link"
            onClick={() => setRevision((value) => value + 1)}
          >
            Try again
          </button>
        </div>
      )}
      <AlertSettings key={missionId} request={request} missionId={missionId} onSaved={() => setRevision(value => value + 1)}/>

      {astronautId && <AllergySection key={`${astronautId}-${missionId}`} request={request} crewMemberId={astronautId} missionId={missionId} />}
      <div className="health-body-layout" ref={layoutRef}>
        <BodyConnections containerRef={layoutRef} selected={selected} />
        <div className="health-card-list health-vital-cards" role="group" aria-label="Vital signs">
          {displayIndicators.filter(item => vitalIds.includes(item.id)).map(renderIndicatorCard)}
        </div>
        <div className="health-body">
          <BodyMap selected={selected} onSelect={selectIndicator} />
        </div>
        <div className="health-card-list health-other-cards" role="group" aria-label="Other health indicators">
          {displayIndicators.filter(item => !vitalIds.includes(item.id)).map(renderIndicatorCard)}
        </div>
      </div>
      <section
        className="panel health-detail"
        id="indicator-detail"
        aria-labelledby="indicator-heading"
      >
        <div className="section-heading">
          <div>
            <h2 id="indicator-heading">{indicator.name}</h2>
            <p>
              {entry?.latest
                ? `${formatValue(entry.latest, indicator)} ${indicator.id === "sleep_duration" ? "" : indicator.unit || ""} · ${formatDate(entry.latest.collected_at)} · ${sources[entry.latest.source]}`
                : "No data"}
            </p>
          </div>
          {canRecord && (
            <button onClick={() => setForm(true)}>Record measurement</button>
          )}
        </div>
        {selected === "fatigue" && (
          <p>Scale from 0 (no fatigue) to 10 (maximum fatigue).</p>
        )}
        {selected === "consciousness" && !summary?.can_record_consciousness && (
          <p>
            The AVPU assessment must be recorded by another authorized flight surgeon.
          </p>
        )}
        {entry?.latest && <details className="measurement-context"><summary>Collection context · {measurementStatusLabels[entry.measurement_status]}</summary><p>{observationContext(entry.latest)}</p>{entry.evaluation_notes?.map(note => <p key={note}>{note}</p>)}</details>}
        <div className="health-comparisons">
          <div>
            <small>Pre-mission baseline</small>
            <strong>
              {formatValue(entry?.preflight_reference, indicator)}
            </strong>
            {entry?.preflight_reference && (
              <small>
                {formatDate(entry.preflight_reference.collected_at)} ·{" "}
                {sources[entry.preflight_reference.source]}
              </small>
            )}
          </div>
          {!indicator.category && (
            <>
              <div>
                <small>Change from previous reading</small>
                <strong>
                  <Delta value={entry?.previous_delta} indicator={indicator} />
                </strong>
                <small>
                  {entry?.previous && formatDate(entry.previous.collected_at)}
                </small>
              </div>
              <div>
                <small>Change from baseline</small>
                <strong>
                  <Delta value={entry?.reference_delta} indicator={indicator} />
                </strong>
              </div>
            </>
          )}
        </div>
        {entry?.trend && (
          <p className="health-trend">
            {
              {
                increasing: "Increase",
                decreasing: "Decrease",
                stable: "No change",
                mixed: "Changes in different directions",
              }[entry.trend]
            }{" "}
            compared with the previous reading.
          </p>
        )}
        <div
          className="health-period"
          role="group"
          aria-label="History period"
        >
          {periodOptions.map((option) => (
            <button
              key={option.days}
              className={period === option.days ? "" : "secondary"}
              aria-pressed={period === option.days}
              onClick={() => setPeriod(option.days)}
            >
              {option.label}
            </button>
          ))}
        </div>
        {historyLoading ? (
          <p role="status">Loading history…</p>
        ) : historyError ? (
          <div className="error" role="alert">
            {historyError}
            <button
              className="link"
              onClick={() => setRevision((value) => value + 1)}
            >
              Try again
            </button>
          </div>
        ) : !rows.length ? (
          <div className="empty">No data for this period</div>
        ) : (
          <>
            {!indicator.category && (
              <>
                <div
                  className="health-chart"
                  role="img"
                  aria-label={`Trend for ${indicator.name}. Values and dates are available in the table below.`}
                >
                  <ResponsiveContainer width="100%" height={280}>
                    <LineChart
                      data={chartData}
                      margin={{ top: 15, right: 20, bottom: 10, left: 5 }}
                      accessibilityLayer
                    >
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis
                        dataKey="time"
                        type="number"
                        domain={[range.start, range.end]}
                        scale="time"
                        tickFormatter={(value) =>
                          new Date(value).toLocaleDateString("en-US", {
                            day: "2-digit",
                            month: "2-digit",
                            ...(period === 1 ? { hour: "2-digit" } : {}),
                          })
                        }
                      />
                      <YAxis
                        width={65}
                        tickFormatter={(value) =>
                          selected === "sleep_duration"
                            ? formatValue(
                                { value: Math.round(value) },
                                indicator,
                              )
                            : value
                        }
                      />
                      <Tooltip
                        labelFormatter={(value) => formatDate(value)}
                        formatter={(value, name) => [
                          selected === "sleep_duration"
                            ? `${Math.floor(value / 60)}h ${value % 60}min`
                            : `${value} ${indicator.unit || "points"}`,
                          name,
                        ]}
                      />
                      <Legend />
                      {(selected === "blood_pressure"
                        ? ["systolic", "diastolic"]
                        : ["value"]
                      ).map((key, index) => (
                        <Line
                          key={key}
                          type="linear"
                          dataKey={key}
                          name={
                            key === "systolic"
                              ? "Systolic"
                              : key === "diastolic"
                                ? "Diastolic"
                                : indicator.name
                          }
                          stroke={index ? "#fc3d21" : "#0b3d91"}
                          dot={{ r: 4 }}
                          connectNulls={false}
                          isAnimationActive={false}
                        />
                      ))}
                    </LineChart>
                  </ResponsiveContainer>
                </div>
                <small>
                  Intervals without records appear as gaps (
                  {period === 1 ? "1 hour" : period === 7 ? "6 hours" : "1 day"}
                  ), without estimating values.
                </small>
              </>
            )}
            {indicator.category ? (
              <ol className="health-timeline">
                {rows.map((row) => (
                  <li key={row.id}>
                    <time dateTime={row.collected_at}>
                      {formatDate(row.collected_at)}
                    </time>
                    <strong>{formatValue(row, indicator)}</strong><small>{observationContext(row)}</small><small>{measurementStatusLabels[row.evaluation_status]}</small>{row.evaluation_notes?.map(note => <small key={note}>{note}</small>)}
                    <span>
                      {sources[row.source]} · Recorded by:{" "}
                      {users.find(
                        (person) => person.id === row.recorded_by_user_id,
                      )?.name || `User ${row.recorded_by_user_id}`}
                    </span>
                    <small>
                      Recorded at {formatDate(row.recorded_at)}
                      {row.is_preflight_reference
                        ? " · Pre-mission baseline"
                        : ""}
                    </small>
                    {row.note && <p>{row.note}</p>}
                  </li>
                ))}
              </ol>
            ) : (
              <div className="table-wrap">
                <table>
                  <caption className="health-table-caption">
                    Measurements for this period
                  </caption>
                  <thead>
                    <tr>
                      <th>COLLECTED AT</th>
                      <th>VALUE</th>
                      <th>CONTEXT AND ASSESSMENT</th>
                      <th>SOURCE</th>
                      <th>NOTE</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row) => (
                      <tr key={row.id}>
                        <td>
                          <time dateTime={row.collected_at}>
                            {formatDate(row.collected_at)}
                          </time>
                          <small>
                            Recorded at {formatDate(row.recorded_at)}
                          </small>
                        </td>
                        <td>
                          {formatValue(row, indicator)}{" "}
                          {indicator.id === "sleep_duration"
                            ? ""
                            : indicator.unit}
                        </td>
                        <td><small>{observationContext(row)}</small><small>{measurementStatusLabels[row.evaluation_status]}</small>{row.evaluation_notes?.map(note => <small key={note}>{note}</small>)}{row.original_values && <small>Original: {row.original_values.value ?? `${row.original_values.systolic}/${row.original_values.diastolic}`} {row.original_values.unit}</small>}</td>
                        <td>
                          {sources[row.source]}
                          <small>
                            Recorded by:{" "}
                            {users.find(
                              (person) => person.id === row.recorded_by_user_id,
                            )?.name || `User ${row.recorded_by_user_id}`}
                          </small>
                          {row.is_preflight_reference && (
                            <small>Pre-mission baseline</small>
                          )}
                        </td>
                        <td>{row.note || "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </section>
      {form && summary && (
        <ObservationForm
          key={`${astronautId}-${missionId}-${selected}`}
          indicator={indicator}
          missionId={missionId}
          summary={summary}
          request={request}
          path={path}
          onClose={() => setForm(false)}
          onSaved={() => {
            setForm(false);
            setRevision((value) => value + 1);
          }}
        />
      )}
    </section>
  );
}

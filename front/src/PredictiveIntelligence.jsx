import React, {useCallback, useEffect, useMemo, useState} from 'react';
import {Bar, BarChart, CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis} from 'recharts';
import {Activity, BookOpen, RefreshCw, ShieldAlert} from 'lucide-react';
import {canRecordOutcome, chartPoints, domainLabels, evidenceLabels, feedbackOptions, indicatorName, indicatorRows, kindLabels, label, levelLabels, probabilityText, scoreText, signalSummary, sortPredictions, statusLabels, supplyRows, urgencyLabels} from './predictive';
import './predictive.css';

const date = value => value ? new Date(value).toLocaleString('en-US', {dateStyle: 'short', timeStyle: 'short'}) : 'Not analyzed';
const number = value => value == null ? '—' : Number(value).toLocaleString('en-US', {maximumFractionDigits: 2});
const tabs = [['dashboard', 'Dashboard'], ['astronaut', 'Astronaut'], ['mission', 'Mission'], ['spacecraft', 'Spacecraft'], ['models', 'Models']];

function KindBadge({kind}) {
  return <span className={`predictive-kind ${kind}`}>{kindLabels[kind] || label(kind)}</span>;
}

function LevelBadge({level}) {
  return <span className={`predictive-level ${level}`}>{levelLabels[level] || label(level)}</span>;
}

function Notice({text}) {
  return text ? <p className="predictive-notice"><ShieldAlert size={16}/>{text}</p> : null;
}

function Factors({prediction}) {
  if (!prediction.factors?.length) return null;
  return <div className="table-wrap"><table className="predictive-table"><thead><tr><th>Factor</th><th>Direction</th><th>Observed</th><th>Baseline</th><th>Deviation</th></tr></thead><tbody>
    {prediction.factors.map((factor, index) => <tr key={index}>
      <td>{factor.indicator ? indicatorName(factor.indicator) : label(factor.category || factor.food_name || factor.context || factor.feature || 'Context')}</td>
      <td>{label(factor.direction || (factor.value === true ? 'present' : ''))}</td>
      <td>{number(factor.mean_7d ?? factor.latest_value ?? factor.mean_daily_kcal ?? factor.current_balance ?? factor.occurrences ?? factor.affected_astronauts ?? factor.value)} {factor.unit || ''}</td>
      <td>{number(factor.baseline_mean ?? factor.plan_target_kcal ?? factor.analyzed_astronauts)}{factor.baseline_source && <small> · {label(factor.baseline_source)}</small>}</td>
      <td>{factor.z_score != null ? `z ${number(factor.z_score)}` : factor.robust_z != null ? `robust z ${number(factor.robust_z)}` : '—'}{factor.relative_contribution != null && <small> · {Math.round(factor.relative_contribution * 100)}% of signal</small>}</td>
    </tr>)}
  </tbody></table></div>;
}

function PredictionCard({prediction}) {
  const probability = probabilityText(prediction);
  return <article className={`predictive-card ${prediction.prediction_kind}`}>
    <header><div><KindBadge kind={prediction.prediction_kind}/><small>{domainLabels[prediction.domain] || label(prediction.domain)}</small></div><LevelBadge level={prediction.risk_level}/></header>
    <h3>{prediction.title}</h3>
    <dl className="predictive-facts">
      <div><dt>Horizon</dt><dd>{prediction.horizon_hours ? `${prediction.horizon_hours} h` : 'Not applicable'}</dd></div>
      <div><dt>{probability ? 'Probability' : 'Score'}</dt><dd>{probability || scoreText(prediction)}</dd></div>
      <div><dt>Uncertainty</dt><dd>{label(prediction.uncertainty?.level || 'unknown')}</dd></div>
    </dl>
    {prediction.score_meaning && <p><small>{prediction.score_meaning}</small></p>}
    <Factors prediction={prediction}/>
    {prediction.prediction_kind === 'insufficient_data' && <p className="predictive-missing">Missing: {(prediction.data_quality?.missing_sources || prediction.data_quality?.missing_or_without_baseline || [prediction.data_quality?.reason]).filter(Boolean).map(indicatorName).join(', ') || 'Recent data'}</p>}
    {prediction.uncertainty?.note && <p><small>{prediction.uncertainty.note}</small></p>}
    {prediction.evidence?.clinical_alert_precedence && <p className="predictive-notice"><ShieldAlert size={16}/>{prediction.evidence.clinical_alert_precedence}</p>}
    {prediction.evidence?.excluded_actions?.length > 0 && <details><summary>Excluded actions ({prediction.evidence.excluded_actions.length})</summary><ul>{prediction.evidence.excluded_actions.map(row => <li key={row.action_code}>{label(row.action_code)} · {label(row.reason)}: {row.details.join(' ')}</li>)}</ul></details>}
  </article>;
}

function Predictions({run, emptyText}) {
  if (!run) return <div className="empty"><h3>{emptyText}</h3></div>;
  const rows = sortPredictions(run.predictions);
  const summary = signalSummary(run.predictions);
  return <section>
    <p>Analysis {date(run.as_of)} · {label(run.trigger)} · engine {run.engine_version} · rules {run.model_versions?.rules}{run.model_versions?.models?.length ? ` · models ${run.model_versions.models.join(', ')}` : ''}</p>
    <p>{summary.signals} signal(s) · {summary.insufficient} area(s) with insufficient information</p>
    <div className="predictive-grid">{rows.map(prediction => <PredictionCard key={prediction.id} prediction={prediction}/>)}</div>
  </section>;
}

function Sources({recommendation}) {
  const explanation = recommendation.explanation || {};
  return <details><summary><BookOpen size={14}/> {evidenceLabels[explanation.state] || label(explanation.state || 'pending')}</summary>
    {explanation.summary && <p>{explanation.summary}{explanation.generated && <small> · Explanation generated by Ollama from the cited passages and validated against them.</small>}</p>}
    {recommendation.sources?.length > 0 ? <ul className="predictive-sources">{recommendation.sources.map(source => <li key={source.id}><strong>{source.title}</strong> · {source.page ? `page ${source.page}` : source.section} · {source.revision}{source.source_url?.startsWith('https://') && <> · <a href={source.source_url} target="_blank" rel="noreferrer">Source</a></>}<blockquote>{source.excerpt}</blockquote></li>)}</ul>
      : <p>No retrieved passage. Catalog references: {(explanation.catalog_references || recommendation.action.source_references || []).map(ref => ref.title).join('; ') || 'none'}.</p>}
  </details>;
}

function FeedbackForm({recommendation, request, onSaved}) {
  const options = feedbackOptions(recommendation);
  const [error, setError] = useState(''), [busy, setBusy] = useState(false), [decision, setDecision] = useState(options[0] || '');
  if (!options.length) return null;
  return <form className="predictive-form" onSubmit={async event => {event.preventDefault();const data = new FormData(event.currentTarget);setBusy(true);setError('');try {onSaved(await request(`/v1/recommendations/${recommendation.id}/feedback`, {method: 'POST', body: {decision, justification: data.get('justification'), executed_action: data.get('executed_action') || null}}));} catch (failure) {setError(failure.message);} finally {setBusy(false);}}}>
    <label>Decision<select value={decision} onChange={event => setDecision(event.target.value)}>{options.map(option => <option key={option} value={option}>{statusLabels[option]}</option>)}</select></label>
    <label>Justification<textarea name="justification" required minLength={3} maxLength={2000}/></label>
    {decision === 'executed' && <label>Action executed<textarea name="executed_action" required maxLength={2000}/></label>}
    {error && <p className="error" role="alert">{error}</p>}
    <button disabled={busy}>Save decision</button>
  </form>;
}

function OutcomeForm({recommendation, request, onSaved}) {
  const [error, setError] = useState(''), [busy, setBusy] = useState(false);
  if (!canRecordOutcome(recommendation)) return null;
  return <details><summary>Record observed result</summary><form className="predictive-form" onSubmit={async event => {event.preventDefault();const form = event.currentTarget;const data = new FormData(form);const value = name => data.get(name) === '' ? null : Number(data.get(name));setBusy(true);setError('');try {onSaved(await request(`/v1/recommendations/${recommendation.id}/outcomes`, {method: 'POST', body: {indicator: data.get('indicator'), value_before: value('value_before'), value_after: value('value_after'), observation_window_hours: Number(data.get('observation_window_hours')), result: data.get('result'), notes: data.get('notes') || null}}));form.reset();} catch (failure) {setError(failure.message);} finally {setBusy(false);}}}>
    <label>Indicator followed<input name="indicator" required maxLength={100}/></label>
    <label>Value before<input name="value_before" type="number" step="any"/></label>
    <label>Value after<input name="value_after" type="number" step="any"/></label>
    <label>Observation window (hours)<input name="observation_window_hours" type="number" min="1" required defaultValue="72"/></label>
    <label>Documented result<select name="result">{['improved', 'unchanged', 'worsened', 'inconclusive'].map(option => <option key={option} value={option}>{label(option)}</option>)}</select></label>
    <label>Notes<textarea name="notes" maxLength={4000}/></label>
    {error && <p className="error" role="alert">{error}</p>}
    <button disabled={busy}>Save result</button>
  </form></details>;
}

function RecommendationCard({initial, request}) {
  const [recommendation, setRecommendation] = useState(initial), [busy, setBusy] = useState(false), [error, setError] = useState('');
  useEffect(() => setRecommendation(initial), [initial]);
  return <article className={`predictive-recommendation ${recommendation.status}`}>
    <header><div><strong>{recommendation.action.name}</strong><small>{label(recommendation.action.action_category)} · responsible: {recommendation.action.responsible_roles.map(label).join(', ')}</small></div><span className={`predictive-status ${recommendation.status}`}>{statusLabels[recommendation.status]}</span></header>
    <p>{recommendation.action.description}</p>
    <p><small>{recommendation.rationale}</small></p>
    <p><small>Urgency: {urgencyLabels[recommendation.urgency] || label(recommendation.urgency)} · rank score {number(recommendation.rank_score)} · catalog v{recommendation.action.version} · priority {recommendation.priority}</small></p>
    <Sources recommendation={recommendation}/>
    <button className="secondary" disabled={busy} onClick={async () => {setBusy(true);setError('');try {setRecommendation(await request(`/v1/recommendations/${recommendation.id}/evidence`, {method: 'POST'}));} catch (failure) {setError(failure.message);} finally {setBusy(false);}}}><RefreshCw size={14}/>Retrieve evidence</button>
    {error && <p className="error" role="alert">{error}</p>}
    {recommendation.feedback?.length > 0 && <ul className="predictive-history">{recommendation.feedback.map(row => <li key={row.id}>{date(row.created_at)} · {statusLabels[row.decision]} · {row.justification}{row.executed_action && ` · executed: ${row.executed_action}`}</li>)}</ul>}
    {recommendation.outcomes?.length > 0 && <ul className="predictive-history">{recommendation.outcomes.map(row => <li key={row.id}>{date(row.evaluated_at)} · {indicatorName(row.indicator)}: {number(row.value_before)} → {number(row.value_after)} in {row.observation_window_hours} h · {label(row.result)}</li>)}</ul>}
    <FeedbackForm recommendation={recommendation} request={request} onSaved={setRecommendation}/>
    <OutcomeForm recommendation={recommendation} request={request} onSaved={setRecommendation}/>
  </article>;
}

function Recommendations({rows = [], title = 'Preventive recommendations', request}) {
  return <section className="panel predictive-panel"><h2>{title}</h2><p>Suggestions come from an approved, versioned catalog. A responsible team member decides; nothing is executed automatically.</p>
    {rows.length ? rows.map(row => <RecommendationCard key={row.id} initial={row} request={request}/>) : <p>No recommendations for the current analysis.</p>}
  </section>;
}

function History({rows = []}) {
  if (!rows.length) return null;
  return <section className="panel predictive-panel"><h2>Prediction history</h2><div className="table-wrap"><table className="predictive-table"><thead><tr><th>Analysis</th><th>Trigger</th><th>Status</th><th>Signals</th><th>Kinds</th></tr></thead><tbody>
    {rows.map(row => <tr key={row.id}><td>{date(row.as_of)}</td><td>{label(row.trigger)}</td><td>{label(row.status)}{row.error && <small> · {row.error}</small>}</td><td>{row.signals}</td><td>{Object.entries(row.kinds).map(([kind, count]) => `${kindLabels[kind]}: ${count}`).join(' · ')}</td></tr>)}
  </tbody></table></div></section>;
}

function useLoader(request, path) {
  const [data, setData] = useState(null), [error, setError] = useState(''), [loading, setLoading] = useState(false);
  const load = useCallback(async () => {if (!path) return;setLoading(true);setError('');try {setData(await request(path));} catch (failure) {setData(null);setError(failure.message);} finally {setLoading(false);}}, [request, path]);
  useEffect(() => {setData(null);load();}, [load]);
  return {data, setData, error, setError, loading, load};
}

function Dashboard({request, onAstronaut, onMission}) {
  const {data, error, loading} = useLoader(request, '/v1/predictions/dashboard');
  if (error) return <p className="error" role="alert">{error}</p>;
  if (!data) return loading ? <p role="status">Loading predictive dashboard…</p> : null;
  return <>
    <div className="stats predictive-stats">
      <div><span>Monitored astronauts</span><strong>{data.monitored_astronauts}</strong><small>{data.visible_astronauts} visible to your profile</small></div>
      <div><span>Monitored missions</span><strong>{data.monitored_missions}</strong><small>{data.missions.length} accessible</small></div>
      <div><span>Risks identified</span><strong>{Object.values(data.risk_levels).reduce((a, b) => a + b, 0)}</strong><small>{Object.entries(data.risk_levels).map(([level, count]) => `${levelLabels[level]} ${count}`).join(' · ') || 'No active signals'}</small></div>
      <div><span>Pending recommendations</span><strong>{data.pending_recommendations}</strong><small>{data.failed_runs} failed analyses awaiting retry</small></div>
    </div>
    <Notice text={data.notice}/>
    <section className="panel predictive-panel"><h2>Signals by type</h2><div className="predictive-chips">{Object.entries(data.prediction_kinds).map(([kind, count]) => <span key={kind}><KindBadge kind={kind}/> {count}</span>)}{Object.entries(data.domains).map(([domain, count]) => <span key={domain} className="predictive-chip">{domainLabels[domain] || label(domain)} · {count}</span>)}</div>
      {data.run_history.length > 0 && <div className="predictive-chart" aria-label="Analyses per day"><ResponsiveContainer width="100%" height={180}><BarChart data={data.run_history}><CartesianGrid strokeDasharray="3 3"/><XAxis dataKey="date"/><YAxis allowDecimals={false}/><Tooltip/><Bar dataKey="runs" name="Analyses" fill="#0b3d91" isAnimationActive={false}/></BarChart></ResponsiveContainer></div>}
    </section>
    <section className="panel predictive-panel"><h2>Astronauts (health trends)</h2><div className="table-wrap"><table className="predictive-table"><thead><tr><th>Astronaut</th><th>Mission</th><th>Last analysis</th><th>Signals</th><th>Insufficient areas</th><th/></tr></thead><tbody>
      {data.astronauts.map(row => <tr key={`${row.mission_id}-${row.astronaut_id}`}><td>{row.name}</td><td>{row.mission_name}</td><td>{date(row.analyzed_at)}</td><td>{row.signals}{row.risk_types.length > 0 && <small> · {row.risk_types.map(label).join(', ')}</small>}</td><td>{row.insufficient}</td><td><button className="link" onClick={() => onAstronaut(row)}>Open</button></td></tr>)}
    </tbody></table></div>{!data.astronauts.length && <p>No astronaut predictive data is visible to your profile.</p>}</section>
    <section className="panel predictive-panel"><h2>Missions (operational risks)</h2><div className="table-wrap"><table className="predictive-table"><thead><tr><th>Mission</th><th>Status</th><th>Last analysis</th><th>Signals</th><th>Highest level</th><th/></tr></thead><tbody>
      {data.missions.map(row => <tr key={row.mission_id}><td>{row.name}</td><td>{label(row.status)}</td><td>{date(row.analyzed_at)}</td><td>{row.signals}{row.risk_types.length > 0 && <small> · {row.risk_types.map(label).join(', ')}</small>}</td><td>{row.highest_level ? <LevelBadge level={row.highest_level}/> : '—'}</td><td><button className="link" onClick={() => onMission(row.mission_id)}>Open</button></td></tr>)}
    </tbody></table></div></section>
    <Recommendations rows={data.top_recommendations} title="Highest-ranked pending recommendations" request={request}/>
  </>;
}

function IndicatorChart({points, indicator, values}) {
  const data = useMemo(() => chartPoints(points, values?.baseline_mean ?? null), [points, values]);
  if (!data.length) return <p>No recorded values in the last 30 days.</p>;
  return <div className="predictive-chart" aria-label={`${indicatorName(indicator)} over 30 days`}><ResponsiveContainer width="100%" height={240}><LineChart data={data}><CartesianGrid strokeDasharray="3 3"/><XAxis dataKey="label"/><YAxis domain={['auto', 'auto']}/><Tooltip/>
    <Line dataKey="value" name={indicatorName(indicator)} stroke="#0b3d91" dot isAnimationActive={false}/>
    {values?.baseline_mean != null && <ReferenceLine y={values.baseline_mean} stroke="#b45309" strokeDasharray="6 4" label={{value: 'Individual baseline', position: 'insideBottomLeft', fill: '#b45309', fontSize: 11}}/>}
  </LineChart></ResponsiveContainer></div>;
}

function AstronautView({request, astronauts, selection, onSelect}) {
  const key = selection ? `${selection.mission_id}:${selection.astronaut_id}` : '';
  const path = selection ? `/v1/predictions/astronauts/${selection.astronaut_id}?mission_id=${selection.mission_id}` : null;
  const {data, setData, error, setError, loading} = useLoader(request, path);
  const [indicator, setIndicator] = useState(''), [busy, setBusy] = useState(false);
  const rows = indicatorRows(data?.indicators, data?.data_quality);
  const active = indicator && data?.timeline?.[indicator] ? indicator : rows.find(row => data?.timeline?.[row.key])?.key || '';
  return <>
    <div className="predictive-toolbar"><label>Astronaut<select value={key} onChange={event => onSelect(astronauts.find(row => `${row.mission_id}:${row.astronaut_id}` === event.target.value) || null)}><option value="">Select an astronaut</option>{astronauts.map(row => <option key={`${row.mission_id}:${row.astronaut_id}`} value={`${row.mission_id}:${row.astronaut_id}`}>{row.name} · {row.mission_name}</option>)}</select></label>
      {selection && <button disabled={busy} onClick={async () => {setBusy(true);setError('');try {setData(await request(`/v1/predictions/astronauts/${selection.astronaut_id}/analyze?mission_id=${selection.mission_id}`, {method: 'POST'}));} catch (failure) {setError(failure.message);} finally {setBusy(false);}}}><Activity size={16}/>Run analysis</button>}</div>
    {error && <p className="error" role="alert">{error}</p>}
    {!selection && <div className="empty"><h3>Select an astronaut visible to your profile</h3></div>}
    {loading && <p role="status">Loading astronaut predictions…</p>}
    {data && <>
      <Notice text={data.notice}/>
      <p>Visible areas: {data.visible_domains.map(domain => domainLabels[domain] || domain).join(', ')}</p>
      <section className="panel predictive-panel"><h2>Potential problems</h2><Predictions run={data.latest} emptyText="No analysis yet. Run an analysis or wait for the scheduled worker."/></section>
      <section className="panel predictive-panel"><h2>Current indicators and individual baseline</h2>
        {rows.length ? <div className="table-wrap"><table className="predictive-table"><thead><tr><th>Indicator</th><th>Latest</th><th>7-day mean</th><th>Baseline</th><th>Deviation (z)</th><th>Trend / day</th><th>Data quality</th></tr></thead><tbody>
          {rows.map(row => <tr key={row.key} className={row.key === active ? 'selected' : ''} onClick={() => setIndicator(row.key)}><td><button className="link" onClick={() => setIndicator(row.key)}>{row.name}</button></td><td>{number(row.latest)} {row.unit}</td><td>{number(row.mean7d)}</td><td>{number(row.baseline)}{row.baselineSource && <small> · {label(row.baselineSource)}</small>}</td><td>{number(row.z)}</td><td>{number(row.slope)}</td><td>{label(row.quality)}</td></tr>)}
        </tbody></table></div> : <p>No feature snapshot yet.</p>}
        {active && <><h3>{indicatorName(active)} · last 30 days</h3><IndicatorChart points={data.timeline[active]} indicator={active} values={data.indicators[active]}/></>}
      </section>
      <Recommendations rows={data.recommendations} request={request}/>
      <History rows={data.history}/>
    </>}
  </>;
}

function MissionView({request, missions, missionId, onSelect}) {
  const {data, setData, error, setError, loading} = useLoader(request, missionId ? `/v1/predictions/missions/${missionId}` : null);
  const [busy, setBusy] = useState(false);
  const supplies = supplyRows(data?.context);
  return <>
    <div className="predictive-toolbar"><label>Mission<select value={missionId || ''} onChange={event => onSelect(event.target.value ? Number(event.target.value) : null)}><option value="">Select a mission</option>{missions.map(row => <option key={row.id} value={row.id}>{row.name}</option>)}</select></label>
      {data?.can_analyze && <button disabled={busy} onClick={async () => {setBusy(true);setError('');try {setData(await request(`/v1/predictions/missions/${missionId}/analyze`, {method: 'POST'}));} catch (failure) {setError(failure.message);} finally {setBusy(false);}}}><Activity size={16}/>Run mission analysis</button>}</div>
    {error && <p className="error" role="alert">{error}</p>}
    {!missionId && <div className="empty"><h3>Select a mission</h3></div>}
    {loading && <p role="status">Loading mission predictions…</p>}
    {data && <>
      <Notice text={data.notice}/>
      <section className="panel predictive-panel"><h2>Operational risks and preventive alerts</h2><Predictions run={data.latest} emptyText="No mission analysis yet."/></section>
      {data.context && <>
        <section className="panel predictive-panel"><h2>Supply status</h2>{supplies.length ? <div className="table-wrap"><table className="predictive-table"><thead><tr><th>Food</th><th>State</th><th>Balance</th><th>Daily rate</th><th>Days of stock</th><th>Estimated depletion</th><th>Safety margin</th></tr></thead><tbody>
          {supplies.map(row => <tr key={row.food_product_id}><td>{row.food_name}</td><td>{label(row.state)}</td><td>{number(row.current_balance)}</td><td>{number(row.daily_rate)}</td><td>{number(row.days_of_stock)}{row.days_of_stock_range && <small> · range {row.days_of_stock_range.join('–')}</small>}</td><td>{row.depletion}</td><td>{row.margin}</td></tr>)}
        </tbody></table></div> : <p>No food projection is available yet. Record a versioned food plan in the mission Risks tab.</p>}</section>
        <section className="panel predictive-panel"><h2>Collective health trends</h2><p>{data.context.astronauts_analyzed} of {data.context.astronauts} astronauts analyzed. Pending crew recommendations: {data.crew_pending_recommendations.count}.</p><p>Elapsed {data.context.duration.elapsed_days ?? '—'} days{data.context.duration.planned_days ? ` of ${data.context.duration.planned_days} planned` : ''}.</p></section>
        <section className="panel predictive-panel"><h2>Incident history</h2>{[...data.context.occurrences, ...data.context.similar_mission_occurrences].length ? <ul>{data.context.occurrences.map(row => <li key={`m-${row.category}`}>This mission · {label(row.category)}: {row.recorded} recorded, {row.confirmed} confirmed</li>)}{data.context.similar_mission_occurrences.map(row => <li key={`s-${row.category}`}>Same spacecraft, previous missions · {label(row.category)}: {row.confirmed} confirmed</li>)}</ul> : <p>No recorded occurrences.</p>}</section>
      </>}
      <Recommendations rows={data.recommendations} title="Prioritized mission recommendations" request={request}/>
      <History rows={data.history}/>
    </>}
  </>;
}

function SpacecraftView({request, spacecraft}) {
  const [selected, setSelected] = useState('');
  const {data, error, loading} = useLoader(request, selected ? `/v1/predictions/spacecraft/${selected}` : null);
  return <>
    <div className="predictive-toolbar"><label>Spacecraft<select value={selected} onChange={event => setSelected(event.target.value)}><option value="">Select a spacecraft</option>{spacecraft.map(row => <option key={row.id} value={row.id}>{row.name}</option>)}</select></label></div>
    {error && <p className="error" role="alert">{error}</p>}
    {loading && <p role="status">Loading spacecraft analysis…</p>}
    {data && <>
      <section className="panel predictive-panel"><h2>Technical risk</h2><Predictions run={data.latest} emptyText="No spacecraft analysis yet. The scheduled worker analyzes spacecraft assigned to active missions."/></section>
      {data.context && <section className="panel predictive-panel"><h2>Usage history</h2><p>{data.context.usage.missions} mission(s) · {data.context.usage.completed_missions} completed · {number(data.context.usage.usage_days)} days in use · {data.context.modules.length} module(s)</p></section>}
      <History rows={data.history}/>
    </>}
  </>;
}

function Models({request, isAdmin}) {
  const {data, setData, error, setError} = useLoader(request, '/v1/prediction-models');
  async function transition(model, target) {
    setError('');
    try {await request(`/v1/prediction-models/${model.id}/${target}`, {method: 'POST'});setData(await request('/v1/prediction-models'));} catch (failure) {setError(failure.message);}
  }
  return <section className="panel predictive-panel"><h2>Prediction models</h2><p>Supervised models are trained offline with <code>python -m scripts.train_prediction_models</code>, compared with simple baselines on a temporal hold-out and never activated automatically. Rule-based detection runs without a trained model.</p>
    {error && <p className="error" role="alert">{error}</p>}
    {data && !data.length && <p>No trained model is registered. Probabilities are not shown until a validated, calibrated model is approved and activated.</p>}
    {data?.length > 0 && <div className="table-wrap"><table className="predictive-table"><thead><tr><th>Model</th><th>Outcome</th><th>Status</th><th>Validation</th>{isAdmin && <th>Actions</th>}</tr></thead><tbody>
      {data.map(model => {const metrics = model.validation_metrics?.metrics || {};return <tr key={model.id}><td>{model.name}<small> · {model.version}</small></td><td>{label(model.predicted_outcome)} · {model.horizon_hours} h</td><td>{label(model.status)}{model.metadata?.monitoring?.state && <small> · monitoring: {label(model.metadata.monitoring.state)}</small>}</td>
        <td>{model.validation_metrics?.passed ? `PR-AUC ${number(metrics.pr_auc)} · Brier ${number(metrics.brier)} · recall ${number(metrics.recall)}` : `Not deployable: ${(model.validation_metrics?.reasons || []).join('; ')}`}</td>
        {isAdmin && <td className="predictive-actions">{model.status === 'candidate' && <button onClick={() => transition(model, 'approve')}>Approve</button>}{['approved', 'retired'].includes(model.status) && model.validation_metrics?.passed && <button onClick={() => transition(model, 'activate')}>{model.status === 'retired' ? 'Roll back to this version' : 'Activate'}</button>}{model.status === 'active' && <button className="secondary" onClick={() => transition(model, 'retire')}>Retire</button>}</td>}</tr>;})}
    </tbody></table></div>}
  </section>;
}

export default function PredictiveIntelligence({request, missions, spacecraft, user}) {
  const [tab, setTab] = useState('dashboard'), [astronauts, setAstronauts] = useState([]), [astronaut, setAstronaut] = useState(null), [missionId, setMissionId] = useState(null);
  useEffect(() => {request('/v1/predictions/dashboard').then(result => setAstronauts(result.astronauts)).catch(() => setAstronauts([]));}, [request]);
  return <div className="predictive">
    <div className="page-heading"><div><h1>Predictive Intelligence</h1><p>Rule-based detection, statistical anomalies and validated models over existing health, mission and spacecraft records.</p></div></div>
    <div className="tabs predictive-tabs" role="tablist">{tabs.map(([id, title]) => <button key={id} role="tab" aria-selected={tab === id} className={tab === id ? 'selected' : ''} onClick={() => setTab(id)}>{title}</button>)}</div>
    {tab === 'dashboard' && <Dashboard request={request} onAstronaut={row => {setAstronaut(row);setTab('astronaut');}} onMission={id => {setMissionId(id);setTab('mission');}}/>}
    {tab === 'astronaut' && <AstronautView request={request} astronauts={astronauts} selection={astronaut} onSelect={setAstronaut}/>}
    {tab === 'mission' && <MissionView request={request} missions={missions} missionId={missionId} onSelect={setMissionId}/>}
    {tab === 'spacecraft' && <SpacecraftView request={request} spacecraft={spacecraft}/>}
    {tab === 'models' && <Models request={request} isAdmin={Boolean(user?.is_global_admin)}/>}
  </div>;
}

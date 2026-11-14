import React, { useEffect, useState } from 'react';

export default function AlertSettings({ request, missionId, onSaved }) {
  const [settings, setSettings] = useState(null), [error, setError] = useState(''), [loading, setLoading] = useState(false), [editing, setEditing] = useState(false), [busy, setBusy] = useState(false), [revision, setRevision] = useState(0);
  const path = `/v1/health/missions/${missionId}/alert-settings`;
  useEffect(() => {
    if (!missionId) return;
    const controller = new AbortController();
    setSettings(null); setError(''); setLoading(true); setEditing(false);
    request(path, { signal: controller.signal }).then(data => { if (!controller.signal.aborted) setSettings(data); }).catch(err => { if (!controller.signal.aborted) setError(err.message); }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [request, path, missionId, revision]);
  if (!missionId) return null;
  return <section className="alert-settings" aria-label="Mission alert profile">{loading && <p role="status">Loading alert profile…</p>}{error && <div className="error" role="alert">{error}<button className="link" onClick={() => setRevision(value => value + 1)}>Update settings</button></div>}{settings && <details className="monitoring-settings-details"><summary>Mission monitoring profile</summary><p>Simulation profile · {settings.rule_version} · Time zone: {settings.timezone} · Emergency channel: {settings.emergency_channel || "Not configured"}</p>{settings.can_edit && <button className="secondary" onClick={() => setEditing(true)}>Configure mission profile</button>}</details>}
    {editing && settings && <div className="overlay"><section className="modal" role="dialog" aria-modal="true" aria-label="Configure alert profile"><header><h2>Configure alert profile</h2><button className="icon" aria-label="Close" disabled={busy} onClick={() => setEditing(false)}>×</button></header><form onSubmit={async event => {
      event.preventDefault(); const data = new FormData(event.currentTarget);
      const high = {};
      for (const context of ['fasting', 'after_meal', 'unknown']) {
        const thresholds = {};
        for (const severity of ['attention', 'urgent', 'critical']) {
          const value = data.get(`${context}_${severity}`);
          if (value !== '') thresholds[severity] = Number(value);
        }
        if (Object.keys(thresholds).length) high[context] = thresholds;
      }
      setBusy(true); setError('');
      try { const result = await request(path, { method: 'PUT', body: { expected_revision: settings.revision, profile_id: settings.profile_id, timezone: data.get('timezone'), emergency_channel: data.get('emergency_channel') || null, oxygen_thresholds: { normal_min: Number(data.get('normal_min')), attention_min: Number(data.get('attention_min')), urgent_min: Number(data.get('urgent_min')) }, high_glucose_thresholds: high, approval_note: data.get('approval_note') } }); setSettings(result); setEditing(false); onSaved(); }
      catch (err) { setError(err.message); } finally { setBusy(false); }
    }}><fieldset disabled={busy}><label>Mission time zone (IANA)<input autoFocus name="timezone" required defaultValue={settings.timezone} placeholder="America/Bahia"/></label><label>Mission emergency channel<input name="emergency_channel" maxLength={500} defaultValue={settings.emergency_channel || ''}/></label><fieldset><legend>SpO₂ targets approved by the medical team (%)</legend><p>Critical below the critical threshold; urgent up to the urgent threshold; caution up to the caution threshold.</p><label>Caution threshold<input type="number" name="normal_min" min="0" max="100" step="any" required defaultValue={settings.oxygen_thresholds.normal_min}/></label><label>Urgent threshold<input type="number" name="attention_min" min="0" max="100" step="any" required defaultValue={settings.oxygen_thresholds.attention_min}/></label><label>Critical threshold<input type="number" name="urgent_min" min="0" max="100" step="any" required defaultValue={settings.oxygen_thresholds.urgent_min}/></label></fieldset><fieldset><legend>High blood glucose (mg/dL)</legend><p>Inclusive thresholds (≥). Leave blank to skip a rule for this context.</p>{[['fasting', "Fasting"], ['after_meal', "After a meal"], ['unknown', "Unknown context"]].map(([context, label]) => <fieldset key={context}><legend>{label}</legend>{[['attention', "Caution"], ['urgent', "Urgent"], ['critical', "Critical"]].map(([severity, text]) => <label key={severity}>{text}<input type="number" name={`${context}_${severity}`} min="70" step="any" defaultValue={settings.high_glucose_thresholds[context]?.[severity] ?? ''}/></label>)}</fieldset>)}</fieldset><label>Medical approval record<textarea name="approval_note" required maxLength={4000}/></label></fieldset>{error && <div className="error" role="alert">{error}</div>}<footer><button type="button" className="secondary" disabled={busy} onClick={() => setEditing(false)}>Cancel</button><button disabled={busy}>{busy ? "Saving…" : "Save new version"}</button></footer></form></section></div>}
  </section>;
}

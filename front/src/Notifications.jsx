import React, { useCallback, useEffect, useState } from 'react';
import { Bell, CheckCheck, RefreshCw } from 'lucide-react';
import { formatDate, indicators } from './health-indicators';
import { alertStatusLabels } from './health-alerts';
import './notifications.css';


export default function Notifications({ request, onOpenRecord, onChange }) {
  const [status, setStatus] = useState('pending'), [page, setPage] = useState(1), [pageSize, setPageSize] = useState(10), [result, setResult] = useState(null), [loading, setLoading] = useState(true), [error, setError] = useState(''), [busy, setBusy] = useState(null), [revision, setRevision] = useState(0);
  const refresh = useCallback(() => setRevision(value => value + 1), []);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError('');
    request(`/v1/notifications?${new URLSearchParams({ status, page: String(page), per_page: String(pageSize) })}`, { signal: controller.signal }).then(data => { if (!controller.signal.aborted) { setResult(data); if (!data.data.length && page > 1 && data.pagination.total_pages < page) setPage(Math.max(1, data.pagination.total_pages)); } }).catch(err => { if (!controller.signal.aborted) setError(err.message); }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [request, status, page, pageSize, revision]);
  useEffect(() => {
    const timer = setInterval(() => { if (!document.hidden) refresh(); }, 30000);
    return () => clearInterval(timer);
  }, [refresh]);
  async function read(notification, openRecord = false) {
    setBusy(notification.id); setError('');
    try { if (!notification.read_at) await request(`/v1/notifications/${notification.id}/read`, { method: 'POST' }); onChange(); if (openRecord) onOpenRecord(notification); else refresh(); }
    catch (err) { setError(err.message); } finally { setBusy(null); }
  }
  return <section aria-label="Clinical notifications"><div className="page-heading"><div><h1>Notifications</h1><p>Critical alerts for the crew members under your care on this mission.</p></div><button className="secondary" onClick={refresh} disabled={loading}><RefreshCw size={16}/>Refresh</button></div><div className="notification-toolbar"><div className="tabs" role="group" aria-label="Notification filter">{[['pending', "Unread"], ['all', "All"]].map(([value, label]) => <button key={value} className={status === value ? 'selected' : ''} aria-pressed={status === value} onClick={() => { setStatus(value); setPage(1); setResult(null); }}>{label}</button>)}</div><button className="secondary" disabled={busy !== null || loading || !result?.data.length} onClick={async () => { setBusy('all'); setError(''); try { await request('/v1/notifications/read-all', { method: 'POST' }); setPage(1); refresh(); onChange(); } catch (err) { setError(err.message); } finally { setBusy(null); } }}><CheckCheck size={16}/>Mark all as read</button></div><p className="muted notification-explanation">Only critical alerts generate notifications. Marking a notification as read does not acknowledge or resolve the alert in the medical record.</p>
    {loading && <p role="status">Loading notifications…</p>}{error && <div className="error" role="alert">{error}<button className="link" onClick={refresh}>Try again</button></div>}
    {result && !error && <><div className="notification-list" aria-busy={loading}>{result.data.map(notification => <article key={notification.id} className={`panel notification-item ${notification.read_at ? 'notification-read' : 'notification-unread'} ${notification.alert_status === 'resolved' ? 'notification-resolved' : ''}`}><header><div><strong><Bell size={17}/>{notification.title}</strong><span>{notification.read_at ? "Read" : "Unread"} · {alertStatusLabels[notification.alert_status]}</span></div><time dateTime={notification.created_at}>{formatDate(notification.created_at)}</time></header><p>{notification.message}</p><p className="notification-context">{notification.mission_name} · {indicators.find(item => item.id === notification.indicator)?.name} · Collected: {formatDate(notification.collected_at)}</p>{notification.verification_required && notification.alert_status !== 'resolved' && <small>Check the measurement confirmation in the medical record.</small>}<div className="actions"><button disabled={busy !== null || loading} onClick={() => read(notification, true)}>Open medical record</button>{!notification.read_at && <button className="secondary" disabled={busy !== null || loading} onClick={() => read(notification)}>Mark as read</button>}</div></article>)}</div>{!loading && !result.data.length && <div className="empty">{status === 'pending' ? "No unread notifications." : "No notifications recorded."}</div>}<nav className="pagination notification-pagination" aria-label="Notification pagination"><label>Items per page<select aria-label="Notifications per page" value={pageSize} disabled={loading} onChange={event => { setPageSize(Number(event.target.value)); setPage(1); }}>{[5, 10, 20, 50].map(size => <option key={size} value={size}>{size}</option>)}</select></label><span>Page {page} of {Math.max(1, result.pagination.total_pages)} · {result.pagination.total} records</span><button className="secondary" disabled={loading || !result.pagination.has_previous} onClick={() => setPage(value => value - 1)}>Previous</button><button className="secondary" disabled={loading || !result.pagination.has_next} onClick={() => setPage(value => value + 1)}>Next</button></nav></>}
  </section>;
}

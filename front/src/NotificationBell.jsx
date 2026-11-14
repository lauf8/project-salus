import React, { useEffect, useState } from 'react';
import { Bell } from 'lucide-react';
import './notifications.css';

export function NotificationBell({ request, enabled, revision, onOpen }) {
  const [count, setCount] = useState(0), [unavailable, setUnavailable] = useState(false);
  useEffect(() => {
    if (!enabled) { setCount(0); return; }
    let controller;
    let disposed = false;
    const update = async () => {
      controller?.abort();
      controller = new AbortController();
      const signal = controller.signal;
      try { const data = await request('/v1/notifications/summary', { signal }); if (!disposed && !signal.aborted) { setCount(data.pending_count); setUnavailable(false); } }
      catch { if (!disposed && !signal.aborted) setUnavailable(true); }
    };
    update();
    const timer = setInterval(() => { if (!document.hidden) update(); }, 30000);
    window.addEventListener('focus', update);
    return () => { disposed = true; clearInterval(timer); window.removeEventListener('focus', update); controller?.abort(); };
  }, [request, enabled, revision]);
  if (!enabled) return null;
  return <button type="button" className="notification-bell" onClick={onOpen} aria-label={unavailable ? "Open notifications · count unavailable" : `Notifications: ${count} unread`} title={unavailable ? "Count temporarily unavailable" : "Clinical notifications"}><Bell size={20}/>{count > 0 && <span className="notification-count">{count > 99 ? '99+' : count}</span>}</button>;
}


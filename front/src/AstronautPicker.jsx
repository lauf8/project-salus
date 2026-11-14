import React, { useEffect, useState } from 'react';

export default function AstronautPicker({ request, excludedIds = [], disabled = false, onAdd }) {
  const [search, setSearch] = useState(''), [results, setResults] = useState([]), [page, setPage] = useState(1), [hasNext, setHasNext] = useState(false);
  const [loading, setLoading] = useState(false), [busy, setBusy] = useState(false), [error, setError] = useState('');
  useEffect(() => {
    if (!search.trim() || disabled) { setResults([]); return; }
    let active = true;
    setLoading(true); setError('');
    const timer = setTimeout(async () => {
      try {
        const data = await request(`/v1/users/?${new URLSearchParams({ search: search.trim(), is_astronaut: 'true', page: String(page), per_page: '10' })}`);
        if (active) { setResults(data.data); setHasNext(data.pagination.has_next); }
      } catch (err) { if (active) { setError(err.message); setResults([]); } }
      finally { if (active) setLoading(false); }
    }, 250);
    return () => { active = false; clearTimeout(timer); };
  }, [search, page, request, disabled]);
  const available = results.filter(user => user.is_astronaut && !excludedIds.includes(user.id));
  return <section className="panel" aria-label="Add astronauts"><label>Search astronauts by name<input type="search" value={search} disabled={disabled || busy} onChange={event => { setSearch(event.target.value); setResults([]); setPage(1); }} placeholder="Type an astronaut's name"/></label>{disabled && <p role="status">Set a valid planned crew size with a free seat to add another astronaut.</p>}{loading && search.trim() && !disabled && <p role="status">Searching…</p>}{!loading && search.trim() && !disabled && !available.length && <p>No matching astronauts available.</p>}{!disabled && available.map(user => <div className="section-heading" key={user.id}><span><strong>{user.name}</strong><small>{user.email}</small></span><button type="button" disabled={busy || loading} onClick={async () => { setBusy(true); setError(''); try { await onAdd(user); setResults(rows => rows.filter(row => row.id !== user.id)); } catch (err) { setError(err.message); } finally { setBusy(false); } }}>Add <span className="sr-only">{user.name}</span></button></div>)}{search.trim() && !disabled && <div className="pagination"><button type="button" className="secondary" disabled={page === 1 || loading || busy} onClick={() => setPage(value => value - 1)}>Previous</button><button type="button" className="secondary" disabled={!hasNext || loading || busy} onClick={() => setPage(value => value + 1)}>Next</button></div>}{error && <div className="error" role="alert">{error}</div>}</section>;
}

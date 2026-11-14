import React, { useEffect, useState } from 'react';

export default function IngredientPicker({ request, selected, onChange, disabled = false }) {
  const [search, setSearch] = useState(''), [page, setPage] = useState(1), [result, setResult] = useState(null), [error, setError] = useState(''), [loading, setLoading] = useState(false), [revision, setRevision] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError(''); setResult(null);
    request(`/v1/active-ingredients?${new URLSearchParams({ search, page, per_page: 10 })}`, { signal: controller.signal })
      .then(data => { if (!controller.signal.aborted) setResult(data); })
      .catch(err => { if (!controller.signal.aborted) setError(err.message); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [request, search, page, revision]);
  return <fieldset disabled={disabled}><legend>Active ingredients</legend>
    <ul>{selected.map(item => <li key={item.id}>{item.name} <button type="button" className="link" aria-label={`Remove ${item.name}`} onClick={() => onChange(selected.filter(row => row.id !== item.id))}>Remove</button></li>)}</ul>
    {!selected.length && <p>No active ingredients selected.</p>}
    <label>Search active ingredients<input value={search} onChange={event => { setSearch(event.target.value); setPage(1); }} /></label>
    {loading && <p role="status">Searching active ingredients…</p>}
    {error && <div className="error" role="alert">{error}<button type="button" className="link" onClick={() => setRevision(value => value + 1)}>Try again</button></div>}
    {result && <><div className="ingredient-options">{result.data.map(item => <label className="checkfield" key={item.id}><input type="checkbox" checked={selected.some(row => row.id === item.id)} onChange={event => onChange(event.target.checked ? [...selected, item] : selected.filter(row => row.id !== item.id))}/>{item.name}</label>)}</div>{!result.data.length && <p>No active ingredients found.</p>}<div className="pagination"><button type="button" className="secondary" disabled={!result.pagination.has_previous} onClick={() => setPage(value => value - 1)}>Previous</button><span>Page {page}</span><button type="button" className="secondary" disabled={!result.pagination.has_next} onClick={() => setPage(value => value + 1)}>Next</button></div></>}
  </fieldset>;
}


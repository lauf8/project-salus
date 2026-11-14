export async function api(path, { token, body, ...options } = {}) {
  let response;
  try { response = await fetch(`/api${path}`, {...options, headers:{...(body !== undefined ? {'Content-Type':'application/json'} : {}), 'X-Public-Profile':globalThis.localStorage?.getItem('orbital-profile')||'is_global_admin', ...(globalThis.localStorage?.getItem('orbital-public-user') ? {'X-Public-User':globalThis.localStorage?.getItem('orbital-public-user')} : {}), ...options.headers}, ...(body !== undefined ? {body:JSON.stringify(body)} : {})}); }
  catch { throw new Error("Unable to connect to the API. Check that the backend is running."); }
  if (response.status === 204) return null;
  const data = await response.json().catch(()=>null);
  if (!response.ok) {
    const messages = {401:"Unable to load the selected public user.",403:"You do not have permission to perform this action.",404:"Resource does not exist or is inaccessible.",409:"The operation conflicts with the rules or history of this resource."};
    const detail = data?.detail;
    const message = Array.isArray(detail) ? detail.map(e=>`${e.loc?.filter(v=>v!=='body').join('.')}: ${e.msg}`).join('\n') : typeof detail === 'string' ? detail : messages[response.status] || "Unable to complete the request.";
    const error = new Error(message); error.status=response.status; error.detail=detail; throw error;
  }
  return data;
}
export async function allPages(path, token) {
  const rows=[];
  for(let page=1;;page++) { const result=await api(`${path}?page=${page}&per_page=100`,{token}); rows.push(...result.data); if(!result.pagination.has_next) return rows; }
}
export function identity(token) { try { return JSON.parse(atob(token.split('.')[1].replace(/-/g,'+').replace(/_/g,'/'))); } catch { return {}; } }

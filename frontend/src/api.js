const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api/v1'

export async function planTrip(origin, destination, { signal } = {}) {
  let response
  try {
    response = await fetch(`${API_BASE_URL}/trips/plan/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ origin, destination }),
      signal,
    })
  } catch (error) {
    if (error.name === 'AbortError') throw error
    throw new Error('Cannot reach the trip planner API. Is the backend running?', {
      cause: error,
    })
  }

  const body = await response.json().catch(() => null)

  if (!response.ok) {
    throw new Error(errorMessage(body) ?? `Request failed (${response.status}).`)
  }
  return body
}

function errorMessage(body) {
  if (!body) return null
  if (body.detail) return body.detail
  // DRF validation errors: { field: ["message"], non_field_errors: [...] }
  const first = Object.values(body).flat()[0]
  return typeof first === 'string' ? first : null
}

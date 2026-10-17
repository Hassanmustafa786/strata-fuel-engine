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

  // Every response is { status, message, data }.
  if (!response.ok || !body?.status) {
    throw new Error(errorMessage(body) ?? `Request failed (${response.status}).`)
  }
  return body.data
}

function errorMessage(body) {
  const detail = body?.data?.detail
  // The specific reason, e.g. "'Toronto, ON' is not in the USA."
  if (typeof detail === 'string') return detail
  // Validation errors: { field: ["message"], non_field_errors: [...] }
  if (detail && typeof detail === 'object') {
    const first = Object.values(detail).flat()[0]
    if (typeof first === 'string') return first
  }
  return body?.message ?? null
}

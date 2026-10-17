import { Fuel, Info, TriangleAlert } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { planTrip } from './api'
import FuelStopList from './components/FuelStopList'
import RouteMap from './components/RouteMap'
import TripPlannerForm from './components/TripPlannerForm'
import TripSummary from './components/TripSummary'

export default function App() {
  const [initial] = useState(tripFromUrl)
  const hasInitialTrip = Boolean(initial.origin && initial.destination)
  const [plan, setPlan] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(hasInitialTrip)
  const [selectedStop, setSelectedStop] = useState(null)
  const pending = useRef(null)

  function handlePlan(origin, destination) {
    setLoading(true)
    setError(null)
    setSelectedStop(null)
    runPlan(origin, destination)
  }

  // Only sets state after the request settles, so it is safe in effects.
  async function runPlan(origin, destination) {
    // Keep the trip in the URL so it can be shared or reloaded.
    window.history.replaceState(null, '', `?${new URLSearchParams({ origin, destination })}`)
    pending.current?.abort()
    const controller = new AbortController()
    pending.current = controller

    try {
      setPlan(await planTrip(origin, destination, { signal: controller.signal }))
    } catch (err) {
      if (err.name !== 'AbortError') {
        setPlan(null)
        setError(err.message)
      }
    } finally {
      if (pending.current === controller) setLoading(false)
    }
  }

  // Plan the trip from the URL once, on first load.
  useEffect(() => {
    if (hasInitialTrip) runPlan(initial.origin, initial.destination)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div className="app">
      <aside className="panel">
        <header className="brand">
          <Fuel size={22} aria-hidden />
          <div>
            <h1>Fuel Route Planner</h1>
            <p>Cheapest fuel stops for a 500-mile range, 10 mpg vehicle.</p>
          </div>
        </header>

        <TripPlannerForm initial={initial} loading={loading} onSubmit={handlePlan} />

        {error && (
          <p className="error" role="alert">
            <TriangleAlert size={16} aria-hidden /> {error}
          </p>
        )}

        {plan && (
          <>
            <TripSummary plan={plan} />
            <FuelStopList
              stops={plan.fuel_plan.stops}
              selected={selectedStop}
              onSelect={setSelectedStop}
            />
            <p className="fine-print assumptions">
              <Info size={14} aria-hidden /> {plan.assumptions.start_fuel}{' '}
              {plan.assumptions.refuelling} Prices come from the supplied dataset.
            </p>
          </>
        )}

        {!plan && !error && !loading && (
          <p className="empty">
            Enter a start and finish anywhere in the USA. You can also paste coordinates like
            “41.88, -87.63”.
          </p>
        )}
      </aside>

      <main className="map-wrap">
        <RouteMap plan={plan} selectedStop={selectedStop} onSelectStop={setSelectedStop} />
      </main>
    </div>
  )
}

function tripFromUrl() {
  const params = new URLSearchParams(window.location.search)
  return {
    origin: params.get('origin') ?? '',
    destination: params.get('destination') ?? '',
  }
}

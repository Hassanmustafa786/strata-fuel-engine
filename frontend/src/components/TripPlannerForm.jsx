import { ArrowUpDown, Flag, LoaderCircle, MapPin, Navigation } from 'lucide-react'
import { useState } from 'react'

const EXAMPLES = [
  ['New York, NY', 'Los Angeles, CA'],
  ['Chicago, IL', 'Denver, CO'],
  ['Miami, FL', 'Seattle, WA'],
  ['Dallas, TX', 'Atlanta, GA'],
]

export default function TripPlannerForm({ initial, loading, onSubmit }) {
  const [origin, setOrigin] = useState(initial.origin)
  const [destination, setDestination] = useState(initial.destination)

  const canSubmit = origin.trim() && destination.trim() && !loading

  function submit(event) {
    event.preventDefault()
    if (canSubmit) onSubmit(origin.trim(), destination.trim())
  }

  function runExample([from, to]) {
    setOrigin(from)
    setDestination(to)
    onSubmit(from, to)
  }

  return (
    <form className="planner-form" onSubmit={submit}>
      <div className="field-stack">
        <label className="field">
          <MapPin size={16} className="field-icon start" aria-hidden />
          <span className="visually-hidden">Start</span>
          <input
            value={origin}
            onChange={(e) => setOrigin(e.target.value)}
            placeholder="Start, e.g. Chicago, IL"
            autoComplete="off"
          />
        </label>
        <label className="field">
          <Flag size={16} className="field-icon finish" aria-hidden />
          <span className="visually-hidden">Finish</span>
          <input
            value={destination}
            onChange={(e) => setDestination(e.target.value)}
            placeholder="Finish, e.g. Denver, CO"
            autoComplete="off"
          />
        </label>
        <button
          type="button"
          className="swap"
          title="Swap start and finish"
          onClick={() => {
            setOrigin(destination)
            setDestination(origin)
          }}
        >
          <ArrowUpDown size={16} />
        </button>
      </div>

      <button type="submit" className="primary" disabled={!canSubmit}>
        {loading ? (
          <LoaderCircle size={18} className="spin" />
        ) : (
          <Navigation size={18} />
        )}
        {loading ? 'Planning route…' : 'Plan route'}
      </button>

      <div className="examples">
        <span>Try:</span>
        {EXAMPLES.map((pair) => (
          <button
            key={pair.join()}
            type="button"
            className="chip"
            disabled={loading}
            onClick={() => runExample(pair)}
          >
            {pair[0].split(',')[0]} → {pair[1].split(',')[0]}
          </button>
        ))}
      </div>
    </form>
  )
}

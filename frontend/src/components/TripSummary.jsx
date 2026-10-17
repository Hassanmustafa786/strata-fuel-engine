import { CircleDollarSign, Clock, Droplet, Fuel, Route, TriangleAlert } from 'lucide-react'
import { formatDuration, formatMoney, formatNumber } from '../format'

export default function TripSummary({ plan }) {
  const { route, fuel_plan: fuel, vehicle, meta } = plan
  const calls = meta.external_calls

  return (
    <section className="summary" aria-label="Trip summary">
      <div className="total">
        <CircleDollarSign size={22} aria-hidden />
        <div>
          <div className="total-label">Total fuel cost</div>
          <div className="total-value">{formatMoney(fuel.total_cost)}</div>
        </div>
      </div>

      <dl className="stats">
        <Stat icon={Route} label="Distance" value={`${formatNumber(route.distance_miles)} mi`} />
        <Stat icon={Clock} label="Drive time" value={formatDuration(route.duration_seconds)} />
        <Stat icon={Droplet} label="Fuel" value={`${formatNumber(fuel.total_gallons)} gal`} />
        <Stat icon={Fuel} label="Fuel stops" value={fuel.stops.length} />
      </dl>

      {!fuel.feasible && (
        <p className="warning">
          <TriangleAlert size={16} aria-hidden /> {fuel.message}
        </p>
      )}

      <p className="fine-print">
        {vehicle.max_range_miles} mi range · {vehicle.mpg} mpg · {vehicle.tank_gallons} gal tank.
        Answered in {meta.elapsed_ms} ms with {calls.geocoding} geocoding and{' '}
        {calls.routing} routing {calls.geocoding + calls.routing === 1 ? 'call' : 'calls'}
        {calls.geocoding + calls.routing === 0 && ' (cached)'}.
      </p>
    </section>
  )
}

function Stat({ icon: Icon, label, value }) {
  return (
    <div className="stat">
      <dt>
        <Icon size={14} aria-hidden /> {label}
      </dt>
      <dd>{value}</dd>
    </div>
  )
}

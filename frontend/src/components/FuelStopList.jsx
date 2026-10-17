import { formatMoney, formatNumber, formatPrice } from '../format'

export default function FuelStopList({ stops, selected, onSelect }) {
  if (!stops.length) return null

  return (
    <section aria-label="Fuel stops">
      <h2 className="section-title">Fuel stops</h2>
      <ol className="stop-list">
        {stops.map((stop) => {
          const { station } = stop
          return (
            <li key={stop.order}>
              <button
                type="button"
                className={`stop ${selected === stop.order ? 'selected' : ''}`}
                onClick={() => onSelect(stop.order)}
              >
                <span className="stop-badge">{stop.order}</span>
                <span className="stop-body">
                  <span className="stop-name">{station.name}</span>
                  <span className="stop-place">
                    {station.city}, {station.state} ·{' '}
                    {stop.type === 'origin'
                      ? `start, ${formatNumber(stop.distance_from_origin_miles)} mi from origin`
                      : `mile ${formatNumber(stop.route_mile)}`}
                  </span>
                  <span className="stop-fuel">
                    {formatNumber(stop.gallons)} gal × {formatPrice(station.price_per_gallon)}
                  </span>
                </span>
                <span className="stop-cost">{formatMoney(stop.cost)}</span>
              </button>
            </li>
          )
        })}
      </ol>
    </section>
  )
}

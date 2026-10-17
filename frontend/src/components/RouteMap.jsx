import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { useEffect, useMemo, useRef } from 'react'
import {
  CircleMarker,
  MapContainer,
  Marker,
  Polyline,
  Popup,
  TileLayer,
  Tooltip,
  useMap,
} from 'react-leaflet'
import { formatMoney, formatNumber, formatPrice } from '../format'

const US_CENTER = [39.5, -98.35]

// Div icons avoid Leaflet's default marker images, which bundlers break.
const pin = (className, label) =>
  L.divIcon({
    className: '',
    html: `<div class="map-pin ${className}">${label}</div>`,
    iconSize: [28, 28],
    iconAnchor: [14, 14],
    popupAnchor: [0, -14],
  })

export default function RouteMap({ plan, selectedStop, onSelectStop }) {
  const line = useMemo(
    () => plan?.route.geometry.coordinates.map(([lon, lat]) => [lat, lon]) ?? [],
    [plan],
  )

  return (
    <MapContainer center={US_CENTER} zoom={4} className="map" scrollWheelZoom>
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors · Routing <a href="https://project-osrm.org/">OSRM</a>'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />

      {plan && (
        <>
          <FitBounds line={line} />
          <Polyline positions={line} pathOptions={{ color: '#0f766e', weight: 5, opacity: 0.85 }} />

          {plan.corridor_stations.map((s) => (
            <CircleMarker
              key={s.id}
              center={[s.latitude, s.longitude]}
              radius={3}
              pathOptions={{ color: '#94a3b8', weight: 1, fillOpacity: 0.6 }}
            >
              <Tooltip>
                {s.name} · {formatPrice(s.price_per_gallon)}
              </Tooltip>
            </CircleMarker>
          ))}

          <Marker position={[plan.origin.latitude, plan.origin.longitude]} icon={pin('start', 'A')}>
            <Popup>{plan.origin.label}</Popup>
          </Marker>
          <Marker
            position={[plan.destination.latitude, plan.destination.longitude]}
            icon={pin('finish', 'B')}
          >
            <Popup>{plan.destination.label}</Popup>
          </Marker>

          {plan.fuel_plan.stops.map((stop) => (
            <StopMarker
              key={stop.order}
              stop={stop}
              selected={selectedStop === stop.order}
              onSelect={onSelectStop}
            />
          ))}
        </>
      )}
    </MapContainer>
  )
}

function StopMarker({ stop, selected, onSelect }) {
  const ref = useRef(null)
  const map = useMap()
  const { station } = stop
  const position = [station.latitude, station.longitude]

  useEffect(() => {
    if (selected && ref.current) {
      map.flyTo(position, Math.max(map.getZoom(), 9), { duration: 0.6 })
      ref.current.openPopup()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected])

  return (
    <Marker
      ref={ref}
      position={position}
      icon={pin('stop', stop.order)}
      zIndexOffset={1000}
      eventHandlers={{ click: () => onSelect(stop.order) }}
    >
      <Popup>
        <strong>
          {stop.order}. {station.name}
        </strong>
        <br />
        {station.address}, {station.city}, {station.state}
        <br />
        {formatPrice(station.price_per_gallon)}/gal · route mile {formatNumber(stop.route_mile)}
        <br />
        Buy {formatNumber(stop.gallons)} gal = <strong>{formatMoney(stop.cost)}</strong>
        {station.location_precision === 'city' && (
          <>
            <br />
            <em>Shown at the city centre</em>
          </>
        )}
      </Popup>
    </Marker>
  )
}

function FitBounds({ line }) {
  const map = useMap()
  useEffect(() => {
    if (!line.length) return
    // The container may have been resized by layout since Leaflet measured it.
    map.invalidateSize()
    map.fitBounds(line, { padding: [40, 40] })
  }, [line, map])
  return null
}

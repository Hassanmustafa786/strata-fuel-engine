# Fuel Route Planner UI

React + Vite + React Leaflet. Calls `POST /api/v1/trips/plan/` once per trip and draws
the route, the fuel stops and the stations considered along the route.

```bash
npm install
npm run dev      # http://localhost:5173, proxies /api to http://127.0.0.1:8000
npm run build
```

Trips can be linked directly: `http://localhost:5173/?origin=Chicago,IL&destination=Denver,CO`.

To call a backend elsewhere, set `VITE_API_BASE_URL` (see `.env.example`).

# K8s Manager Frontend

The frontend is a React/Vite operations console for the K8s Manager API. It
supports cluster selection, namespace creation, application deployment, live
pod status, resource editing, and destructive-action confirmation.

## Development

```bash
npm ci
npm run dev
```

The Vite server proxies `/api` to `http://127.0.0.1:8000`. Start Django
separately from the repository root.

## Validation

```bash
npm run lint
npm run build
```

The production build is emitted to `dist/` and served by the Nginx image.

## Structure

```text
src/
  components/       Shared status, alert, toast, and confirmation UI
  lib/              API response and status helpers
  App.jsx           Application workspace and API workflow orchestration
  App.css           Dashboard layout and responsive visual system
  index.css         Global browser and typography defaults
```

In production, Nginx serves the frontend and proxies `/api/` and `/metrics`
to the internal Django `backend` service.

## UX conventions

- Blue actions create or save resources.
- Green, amber, and red statuses represent healthy, transitional, and failed
  states.
- Destructive actions use an explicit confirmation dialog.
- Application details use a responsive detail panel.
- The interface supports keyboard focus states and reduced-motion preferences.

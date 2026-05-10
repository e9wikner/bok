# BokAi Frontend

Next.js frontend for the BokAi bookkeeping system.

## Development

```bash
npm install
npm run dev
```

Open `http://localhost:3000`.

For local development against a backend on another origin:

```bash
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev
```

When `NEXT_PUBLIC_API_URL` is empty, the frontend calls relative `/api` and
`/health` URLs. In Docker this is proxied by `next.config.mjs` to
`BACKEND_URL`, normally `http://api:8000`.

## Production Build

```bash
npm run lint
npm run build
npm run start
```

The Docker image uses `output: "standalone"` and runs `node server.js`.

## Security Notes

- Do not expose a static API key through `NEXT_PUBLIC_*` variables.
- Browser users authenticate through `/api/v1/auth/login` and store a JWT in
  local storage.
- For LAN deployment, prefer the same-origin `/api` rewrite so the browser only
  needs to reach the frontend origin.

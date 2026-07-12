# breadcrumbs — Frontend

Next.js (App Router) + TypeScript UI for the breadcrumbs
**AI Incident Investigation Workspace**.

## Requirements

- Node.js 18.18+ (Node 20+ recommended)

## Local setup

From the `frontend/` directory:

```bash
# 1. Install dependencies
npm install

# 2. Configure environment (backend URL + Supabase)
cp .env.example .env.local   # then fill in the Supabase values below

# 3. Run the development server
npm run dev
```

The app runs at http://localhost:3000.

The homepage renders the **AI Incident Investigation Workspace** landing page,
an auth panel (sign up / log in / log out), and a health-check card that calls
the backend `GET /health`. When signed in, it calls the protected
`GET /auth/me` endpoint with the Supabase access token as a Bearer header and
shows your provisioned organization.

## Authentication (Supabase)

### Required manual input

Add to **`frontend/.env.local`** (see [`.env.example`](.env.example)), from
**Supabase dashboard → Project Settings → API**:

- `NEXT_PUBLIC_SUPABASE_URL` — the **Project URL**
- `NEXT_PUBLIC_SUPABASE_ANON_KEY` — the **anon / publishable** public key

These are public client keys and are safe to ship to the browser. Restart
`npm run dev` after changing env values.

> **Tip for local testing:** In the Supabase dashboard under
> **Authentication → Providers → Email**, you can disable "Confirm email" so new
> signups can log in immediately without an email round-trip.

## Configuration

| Variable                        | Default                 | Description                        |
| ------------------------------- | ----------------------- | ---------------------------------- |
| `NEXT_PUBLIC_API_BASE_URL`      | `http://localhost:8000` | Base URL of the backend API.       |
| `NEXT_PUBLIC_SUPABASE_URL`      | _(required)_            | Supabase project URL.              |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | _(required)_            | Supabase anon/publishable key.     |

## Scripts

- `npm run dev` — start the dev server
- `npm run build` — production build
- `npm run start` — run the production build
- `npm run lint` — lint the project

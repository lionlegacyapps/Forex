# Deploying to Vercel

## Overview

| Layer | Hosting | Notes |
|---|---|---|
| Frontend (React) | Vercel CDN | Auto-deployed on push |
| Backend (Express) | Vercel Serverless | `/api/*` routes |
| Database | Neon (free PostgreSQL) | Persistent, serverless-compatible |

---

## Step 1 — Create a free Neon database

1. Go to [neon.tech](https://neon.tech) → **Sign Up free**
2. Create a new project: name it `truck-dispatch`
3. Copy the **Connection string** — it looks like:
   ```
   postgresql://user:password@ep-xxx.us-east-2.aws.neon.tech/neondb?sslmode=require
   ```
4. Keep this tab open — you'll paste it into Vercel next

---

## Step 2 — Deploy to Vercel

### Option A: Via Vercel Dashboard (Recommended)

1. Go to [vercel.com](https://vercel.com) → **Sign Up** with GitHub
2. Click **Add New Project** → Import `lionlegacyapps/Forex`
3. Select the **`claude/truck-dispatch-ai-app-5h2IQ`** branch (or merge to main first)
4. Vercel auto-detects the `vercel.json` — click **Deploy**

### Option B: Via Vercel CLI

```bash
npm install -g vercel
vercel login
vercel --prod
```

---

## Step 3 — Add Environment Variables in Vercel

In your Vercel project → **Settings** → **Environment Variables**, add:

### Required
| Variable | Value |
|---|---|
| `DATABASE_URL` | Your Neon connection string from Step 1 |
| `JWT_SECRET` | Any long random string (e.g. `openssl rand -base64 32`) |
| `JWT_REFRESH_SECRET` | Another long random string |

### Optional (enables real features)
| Variable | Feature |
|---|---|
| `DEEPSEEK_API_KEY` | Real AI responses (get free key at platform.deepseek.com) |
| `VITE_MAPBOX_TOKEN` | Live map with truck markers (mapbox.com) |
| `TELNYX_API_KEY` | Real SMS to drivers |
| `SAMSARA_API_KEY` | Real ELD tracking |
| `MOTIVE_API_KEY` | Real ELD tracking |

---

## Step 4 — Run Database Migration + Seed

After first deploy, open the Vercel dashboard terminal or run locally with the Neon DATABASE_URL:

```bash
# Set the production DATABASE_URL
export DATABASE_URL="postgresql://user:pass@ep-xxx.neon.tech/neondb?sslmode=require"

cd server

# Push schema to Neon
npx prisma db push

# Seed demo data
npm run seed
```

Or use the Vercel CLI:
```bash
vercel env pull .env.production.local
DATABASE_URL=$(grep DATABASE_URL .env.production.local | cut -d= -f2) npx prisma db push
```

---

## Step 5 — Done!

Your app will be live at `https://your-project.vercel.app`

Login with:
- **admin@dispatch.com** / `dispatch123`
- **dispatcher@alphalogistics.com** / `dispatch123`
- **dispatcher@swiftlocal.com** / `dispatch123`

---

## Updating the App

Every push to the deployed branch automatically redeploys on Vercel.

```bash
git add . && git commit -m "update" && git push
```

---

## Troubleshooting

**"Cannot find module" errors on Vercel**
- Make sure `DATABASE_URL` is set in Vercel environment variables
- Check the Vercel build logs for the specific module

**Database connection errors**
- Verify the Neon connection string includes `?sslmode=require`
- Neon free tier pauses after 5 minutes of inactivity — first request may be slow

**API returns 500**
- Check Vercel Function logs in the dashboard
- Make sure `JWT_SECRET` is set

**Map not showing**
- Add `VITE_MAPBOX_TOKEN` to Vercel env vars — the placeholder SVG map shows without it

# Putting NILA on the internet

End state: a real website at `https://nila.pages.dev` (or whatever name you
pick) that anyone can open, redeployed automatically every time you push to
GitHub, with community reports shared between everyone who visits.

Cost: free. Cloudflare's free tier covers this comfortably: unlimited static
requests, 100,000 function calls a day, 5 GB of database. No credit card.

Everything below happens in your browser. No terminal.

---

## What is actually running

| Part | What it is | Where it runs |
|---|---|---|
| `web/public/index.html` | the whole app, one file | the visitor's browser |
| `web/public/vendor/maplibre/` | the 3D engine, fetched only if someone opens 3D | the visitor's browser |
| `web/functions/api/reports.js` | the reports API | Cloudflare's servers |
| D1 database | where reports are stored | Cloudflare's servers |

The `vendor/maplibre/` folder has to go up with everything else. Without it the
map still works in full, but the **3D view** button reports that it cannot load.

Cloudflare Pages serves the HTML. Anything under `functions/` automatically
becomes an API route, so `functions/api/reports.js` answers `/api/reports`.
There is no server to configure.

---

## Step 1. Get the code on GitHub

If the repo already exists, skip to step 2.

Otherwise: github.com, **New repository**, name it `nila`, make it **Public**,
do not add a README (this project has one), **Create repository**. Then on the
empty repo page click **uploading an existing file** and drag the whole project
folder in. Commit.

## Step 2. Create a Cloudflare account

<https://dash.cloudflare.com/sign-up>. Email and a password, free, no card.
Verify the email they send you.

## Step 3. Connect the repo to Pages

In the Cloudflare dashboard:

1. **Workers & Pages** in the left sidebar
2. **Create application** → **Pages** → **Connect to Git**
3. Sign in with GitHub, then **Install & Authorize**. When it asks which
   repositories Cloudflare may see, picking just `nila` is fine.
4. Select the `nila` repo → **Begin setup**

Now the build settings. This is the part where a wrong value costs you twenty
minutes, so take it slowly:

| Field | Value |
|---|---|
| Project name | `nila` (this becomes your URL) |
| Production branch | `main` |
| Framework preset | **None** |
| Build command | **leave completely empty** |
| Build output directory | `public` |
| Root directory (advanced) | `web` |

Root directory `web` is what makes Cloudflare look inside the `web/` folder,
where both `public/` and `functions/` live. Without it, it looks at the repo
root and finds neither.

**Save and Deploy.** About a minute later you get a URL like
`https://nila.pages.dev`. Open it. The map should be there.

If `nila` is taken (project names are shared across all of Cloudflare), it will
say so and you pick another: `nila-nepal`, `nila-atlas`, anything. Nothing
inside the app depends on the name.

At this point the site is live but reports are not saved yet, because there is
no database behind it. The app notices and quietly falls back to storing
reports in the visitor's own browser.

## Step 4. Create the reports database

Still in the dashboard:

1. **Storage & Databases** → **D1 SQL Database** → **Create database**
2. Name it `nila-reports` → **Create**
3. Open it, go to the **Console** tab
4. Open `web/schema.sql` from the project, copy the whole thing, paste it into
   the console, run it

That creates the `reports` table and its indexes. The console should report
success with no rows returned, which is what you want.

## Step 5. Wire the database to the site

1. **Workers & Pages** → your `nila` project → **Settings**
2. Find **Bindings** (it may be under Functions on older dashboards) →
   **Add binding** → **D1 database**
3. Variable name: `DB` — exactly that, capital D capital B. The code looks for
   `env.DB` and nothing else.
4. D1 database: `nila-reports`
5. Save

Bindings only take effect on a new deployment. Go to **Deployments**, find the
latest one, and use **Retry deployment** (or push any commit to GitHub).

## Step 6. Check it

Open your URL. Click **Report**, submit something, then open the site on your
phone. If the report is there too, it came from the database rather than from
your browser, and you are done.

---

## Updating it later

Change `page_template.html`, run `python build_page.py`, commit and push.
Cloudflare rebuilds and redeploys on its own within a minute or two. There is
nothing to run and nothing to upload.

Never edit `web/public/index.html` directly. `build_page.py` regenerates it
from the template and the data files, so your edits would be overwritten on the
next build.

---

## Using the command line instead

If you would rather deploy from a terminal, `web/wrangler.toml.cli` is a ready
wrangler config. Rename it to `wrangler.toml`, fill in the `database_id` that
`npx wrangler d1 create nila-reports` prints, then:

```
cd web
npm install
npx wrangler login
npx wrangler d1 execute nila-reports --remote --file=./schema.sql
npx wrangler pages deploy public
```

One warning: once a `wrangler.toml` exists in the repo, Cloudflare treats it as
the source of truth and the dashboard bindings page goes read-only. Pick one
approach or the other, not both. That is why the file ships with a `.cli`
suffix.

---

## A custom domain, if you want one

Buy a domain (Cloudflare Registrar sells at close to cost, usually about $10 a
year). Then: **Workers & Pages** → your project → **Custom domains** → **Set up
a custom domain**. HTTPS is handled for you.

`nila.pages.dev` works perfectly well and costs nothing, so this is optional.

---

## Before you share it widely

**Keep the disclaimers.** The app says in several places that it is a
prototype, that the lake data is approximate, that the weights are not
validated by a glaciologist, and that community reports are unverified. That
matters more once it is public. A stranger in Nepal finding a page that looks
like a flood warning system could act on it. Please do not remove that framing,
and make it more prominent if you promote the site.

**Moderation.** Reports publish immediately unless they trip the spam
heuristics, and the only way to remove one is a database query. From the D1
console:

```sql
UPDATE reports SET status = 'hidden' WHERE id = 'the-report-id';
```

The better version is an admin endpoint behind a secret, added as another file
under `web/functions/api/`.

**The data.** The lake inventory is compiled from published literature and is
approximate. If you ever get access to the real ICIMOD inventory, importing it
is the single biggest upgrade available.

---

## If something goes wrong

**Build fails with "output directory not found"** — Build output directory
should be `public` and Root directory should be `web`. Check both in Settings →
Builds & deployments.

**Site loads but the Report button says no server** — either the D1 binding is
missing, or it was added but the site has not been redeployed since. Retry the
deployment.

**Reports save but vanish on another device** — the binding variable name is
probably not exactly `DB`.

**Map is blank grey** — tile images could not load, usually a network or
ad-blocker issue. The Nepal outline and all the markers still work, because the
map does not depend on the tiles.

**Pushed to GitHub but nothing redeployed** — check you pushed to `main`, and
that Cloudflare's GitHub app still has access to the repo under your GitHub
settings → Applications.

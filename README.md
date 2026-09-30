# Nomad Outdoors event board

The group's website on Cloudflare (free plan), with a D1 database.

- `nomadoutdoors.org` is the shop window: who we are, trip types, recent trips, the kit partner pitch and "The garage" (links to OBS Icons UAE and OBScure Parts).
- `nomadoutdoors.org/board` is the members' event board with sign-ups. It is hidden from search engines.

## Current setup (live since 29 Sept 2026)

- Hosted as a Cloudflare **Pages** project called `nomad-outdoors`, deployed by uploading a zip containing `_worker.js` (the same file as `worker.js`, renamed).
- Production settings: D1 binding named `DB` pointing at the `nomad-outdoors` database, and a secret named `ORGANISER_CODE` (with an S and an underscore).
- Custom domains: `nomadoutdoors.org` and `www.nomadoutdoors.org`.
- Settings only take effect on the next deployment, so upload the zip again after changing them.
- Still to do: set up Email Routing for hello@nomadoutdoors.org.

The dashboard steps below describe the original Worker route. The Pages route above is what's actually in use.

## What's in the folder

- `worker.js` is the whole site in one file (page, icons and the sign-up logic). This is the file you paste into Cloudflare.
- `src/` holds the editable source. `build.py` turns it into `worker.js`.
- `wrangler.toml` is only needed if you ever deploy from the command line instead of the dashboard.
- `icon-preview.png` shows the home-screen icon.

## Set it up in the Cloudflare dashboard (about 15 minutes)

Cloudflare moves its menus around from time to time, so the labels below may differ slightly.

1. **Create the Worker.** Go to Workers & Pages, choose Create, then Create Worker (the Hello World starter). Name it `nomad-outdoors` and deploy.
2. **Paste the site in.** Open the new Worker, choose Edit code, select everything in the editor, paste the contents of `worker.js` and press Deploy.
3. **Create the database.** Go to Storage & Databases, then D1, and create a database called `nomad-outdoors`. The tables are created automatically on first use.
4. **Connect the database.** Back in the Worker, go to Settings, then Bindings, and add a D1 database binding. The variable name must be exactly `DB`. Select the `nomad-outdoors` database.
5. **Set the organiser code.** In Settings, go to Variables and Secrets and add a secret called `ORGANISER_CODE`. Choose something you're happy to share with the organisers.
6. **Add the domain.** In Settings, go to Domains & Routes, add a Custom domain and enter your domain (or a subdomain such as `events.yourdomain.com`). The domain needs to be on the same Cloudflare account.
7. **Test it.** Open the site, use Organiser login at the bottom of the page, post a test event, then sign up to it from a different phone. Delete the test event when you're done.

## How people use it

- **Members** tap the link in WhatsApp, open an event and tap "I'm in". They give their name, mobile number, vehicle, how many people and what they're bringing. The phone remembers them after that.
- **Numbers** are only shown to organisers, never on the public page.
- **"I can't make it"** removes them. If they signed up on another phone, "Enter your number" at the bottom of the page links this phone to their sign-ups.
- **Add to Home Screen** (Safari share menu on iPhone, browser menu on Android) gives them a Nomad icon that opens like an app.

## Organisers

- Log in once per phone with the organiser code. The phone remembers it.
- Post, edit and delete events. Picking a type fills in a starter kit list.
- On each event, "Copy for WhatsApp" gives a ready-made announcement with the link. "Copy list with numbers" gives the roll call for the day.
- To change the code, update the `ORGANISER_CODE` secret. Everyone will need to log in again.

## Making changes later

Edit the files in `src/`, run `python3 build.py`, and paste the new `worker.js` into the Worker editor as in step 2. Events and sign-ups live in the database, so they aren't affected.

## Good to know

- Anyone with the link can see who's going, but not their numbers. Keep the link in the group.
- Sign-ups are trust-based. Someone who knows another member's number could cancel for them. That's fine for a friendly group and easy to tighten later if needed.
- The free Workers and D1 allowances are far beyond what a group of 50 will use.
- A photo gallery can be added later using Cloudflare R2 storage alongside the same Worker.

## Route library (added 30 Sept 2026)

- Original GPX exports from Gaia GPS live in `content/gpx/`.
- `python3 tools/import_gpx.py [new files.gpx]` processes every track: stats, simplified map line, elevation profile, a tidy GPX download, `dist/data/routes/index.json` and `dist/sitemap.xml`.
- Privacy: waypoints are never copied, the first and last 500 m of every track are trimmed, and any stop longer than two hours (a camp) is cut out with the area around it.
- Titles, notes, vehicle, type, featured and hidden flags are edited in `content/routes/meta.json`. New routes get a working title; the importer never overwrites your edits.
- Then run `python3 build.py`, commit and push. Cloudflare publishes automatically.
- Pages: `/routes` (library) and `/routes/<slug>` (map, stats, elevation, GPX download).

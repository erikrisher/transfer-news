# Transfer News Page

A webpage that shows the latest soccer transfer news every day, on its own,
for free. It pulls headlines from public news feeds (BBC, Sky Sports, The
Guardian, Google News), keeps only transfer stories, and sorts them into tiers:

- **Manchester United** — red neon-glow border (top priority)
- **Premier League** — white neon-glow border
- **Other top-5 leagues & general transfers** — plain border

Once it's on GitHub, it updates itself twice a day. **It does not use Claude or
any paid service** — if you cancel any subscription, this keeps working.

---

## What each file does (you don't need to edit these)

- `fetch_news.py` — grabs the news and builds the page. Pure Python, no installs.
- `index.html` — the actual webpage people see. Rebuilt automatically each day.
- `.github/workflows/update.yml` — the daily timer that runs the script.
- `README.md` — this file.

---

## One-time setup (about 10 minutes, no command line needed)

### Step 1 — Create the repository on GitHub
1. Go to https://github.com/new
2. **Repository name:** `transfer-news` (or anything you like)
3. Set it to **Public** (required for free GitHub Pages).
4. Leave everything else as-is and click **Create repository**.

### Step 2 — Upload these files
1. On the new repo page, click the link **"uploading an existing file"**.
2. Open this folder on your Desktop, select **all** the files, and drag them
   into the browser upload box.
   - Important: it must include the hidden `.github` folder. If dragging skips
     it, drag the `.github` folder in as a second step. (On Mac, press
     `Cmd+Shift+.` in Finder to reveal hidden folders.)
3. Click **Commit changes** at the bottom.

### Step 3 — Let the timer write to your repo
1. In your repo, go to **Settings → Actions → General**.
2. Scroll to **Workflow permissions**.
3. Select **Read and write permissions**, then **Save**.

### Step 4 — Turn on the webpage (GitHub Pages)
1. Go to **Settings → Pages**.
2. Under **Source**, choose **Deploy from a branch**.
3. Branch: **main**, folder: **/ (root)**. Click **Save**.
4. Wait ~1 minute, then refresh. Your public link appears at the top, like:
   `https://YOUR-USERNAME.github.io/transfer-news/`
5. **That link is your page.** Bookmark it.

### Step 5 — Fill it with news right now (optional)
The page updates on its own at 6am and 4pm UTC, but to see it immediately:
1. Go to the **Actions** tab.
2. Click **"Update transfer news"** on the left.
3. Click **Run workflow → Run workflow**.
4. Wait ~1 minute, then reload your page link.

Done. From now on it refreshes twice a day automatically.

---

## Make it feel like an app (optional)
- **iPhone:** open your page link in Safari → tap the Share button → **Add to
  Home Screen**. Now it's an icon you tap like any app.
- **Android:** open in Chrome → menu (⋮) → **Add to Home screen**.
- **Laptop:** just bookmark it, or set it as your browser's start page.

---

## Good to know
- Scheduled runs sometimes start a few minutes late — that's normal for GitHub's
  free tier, not a bug.
- GitHub pauses scheduled jobs only after 60 days of **zero** activity. Since
  this commits an update daily, it stays awake on its own.
- If one news source is temporarily down, the script just skips it and uses the
  others — the page never ends up empty.

## Want to tweak it later?
Everything is in `fetch_news.py`:
- Change which teams count as "top priority" — edit the `MAN_UTD` list.
- Add or remove news sources — edit the `FEEDS` list at the top.
- Change how often it runs — edit the `cron:` lines in
  `.github/workflows/update.yml`.

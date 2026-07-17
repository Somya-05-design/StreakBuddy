# GitHub Streak Guard

Snapchat-style "your streak is about to end" push notifications, but for
your GitHub contribution graph.

Runs entirely on GitHub Actions (free) — nothing to host, nothing to keep
running on your machine.

## How it works

- 3 times a day, a GitHub Actions workflow checks whether today's UTC
  contribution day already has a commit/contribution.
- If it does, the run exits silently — no notification spam.
- If it doesn't, it sends you a push notification via [ntfy.sh](https://ntfy.sh),
  with wording that gets more urgent the later in the day it is.
- The day boundary is 00:00 UTC = 5:30 AM IST — this matches how GitHub
  actually calculates your contribution graph, not local midnight.
- Nothing is stored anywhere. Streak length is recalculated fresh from
  GitHub's own data every single run.

Schedule (converted to UTC for the workflow file):

| Stage  | IST time | UTC time  | Tone |
|--------|----------|-----------|------|
| soft   | 6:00 PM  | 12:30 UTC | gentle nudge |
| urgent | 10:30 PM | 17:00 UTC | more direct |
| final  | 1:30 AM  | 20:00 UTC | last chance, shows hours left |

## Setup (5-10 minutes)

### 1. Get a phone notification channel (ntfy.sh)
1. Install the **ntfy** app: [iOS](https://apps.apple.com/app/ntfy/id1625396347) / [Android](https://play.google.com/store/apps/details?id=io.heckel.ntfy)
2. In the app, tap **Subscribe to topic**.
3. Pick a random, hard-to-guess topic name — e.g. `StreakBuddy-x7f2k9`
   (anyone who knows this name can send you notifications, so don't use
   something obvious).
4. That's it — no account needed.

### 2. Create a repo for this tool
You can use this exact folder as a new GitHub repo (public or private,
doesn't matter — it never has to be your "main" repo).

```bash
cd streak-guard
git init
git add .
git commit -m "streak guard"
git branch -M main
git remote add origin https://github.com/<your-username>/streak-guard.git
git push -u origin main
```

### 3. Set the repo variable
In your new repo: **Settings → Secrets and variables → Actions → Variables tab → New repository variable**
- Name: `GH_USERNAME`
- Value: your GitHub username

Note: GitHub does not allow custom variable/secret names starting with
the `GITHUB_` prefix (it's reserved for GitHub's own built-ins), which
is why this project uses `GH_USERNAME` instead of `GITHUB_USERNAME`
everywhere — in the repo variable, the workflow file, and the script.

### 4. Set the repo secret
Same page, **Secrets tab → New repository secret**
- Name: `NTFY_TOPIC`
- Value: the topic name you picked in step 1 (e.g. `StreakBuddy-x7f2k9`)

You do **not** need to create a personal access token — GitHub Actions
automatically provides `secrets.GITHUB_TOKEN` on every run (that's a
built-in, not something you create), and reading public contribution
data doesn't need any special scopes. The workflow maps this built-in
token to an internal env var called `GH_TOKEN` before handing it to the
script.

### 5. Test it immediately
Go to the **Actions** tab → **GitHub Streak Guard** workflow → **Run workflow**
button → pick a stage (`soft`/`urgent`/`final`) → Run.

The very first lines of the log will show:
```
DEBUG: GH_USERNAME='yourname' (len=8)
DEBUG: GH_TOKEN set: True
DEBUG: NTFY_TOPIC='yourtopic' (len=9)
DEBUG: CHECK_STAGE='soft'
```
If any of these are empty, the log will print a `FATAL:` line telling
you exactly which repo variable/secret to check.

If you haven't committed today, you should get a push notification on
your phone within a few seconds after the debug lines. If you have
committed today, the log will say "Already committed today... Staying
quiet."

### 6. Let it run
That's it. From tomorrow onward it runs automatically 3x a day with zero
further action from you.

## Known limitations (accepted by design)

- GitHub Actions scheduled crons aren't millisecond-precise — GitHub
  reserves the right to delay them slightly under load. Expect
  "approximately" the times above, not exact.
- ntfy.sh topics are public by obscurity (no auth) — keep your topic
  name private, don't commit it into the repo itself (it's a secret,
  not a variable, for this reason).
- Counts *any* public contribution type (commits, PRs, reviews, issues)
  across all your public repos — same definition as your GitHub profile's
  green graph.

## Names used in this project (for reference)

| Type | Name | Set where | Read by script as |
|---|---|---|---|
| Repo Variable | `GH_USERNAME` | Settings → Variables | `GH_USERNAME` |
| Repo Secret | `NTFY_TOPIC` | Settings → Secrets | `NTFY_TOPIC` |
| Built-in (no setup) | `secrets.GITHUB_TOKEN` | provided automatically | `GH_TOKEN` |

## Files

```
streak-guard/
├── .github/workflows/streak-check.yml   # the 3x/day scheduler
├── scripts/check_streak.py               # the actual check + notify logic
└── README.md                             # this file
```

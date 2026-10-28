# Shared demo: Firebase Hosting → Cloud Run

Participants open one link (`https://<project>.web.app`), enter a passcode, and test on their own time.
Hosting serves only `deploy/hosting/robots.txt` and forwards everything else to the Cloud Run service
`meal-demo`, which runs `demo/server.py` in a container built from `Dockerfile`.

## What goes out (check before every deploy)

`gcloud meta list-files-for-upload .` must list exactly the 24 files the server needs (Dockerfile,
`meal/*.py` (incl. `energy.py`), `eval/__init__.py`, `eval/pricing.py`, `data/*.json`, `data_wm/*.json`, `demo/server.py`,
`demo/index.html`, `demo/shell.html`, `deploy/requirements-demo.txt`). No cases, runs, user-study data, docs or `.git`. The Dockerfile copies
the same list explicitly.

## Account and project — personal only

The demo lives in project `cs621-meal-demo`, owned by zhouhanwei421@gmail.com. The CLI defaults on this
machine may point at a former employer's account and project; never rely on them. Every command below names
the account and project explicitly.

Before every deploy: `gcloud meta list-files-for-upload . | wc -l` must print **24** (19 until 24 Oct, then
`data_wm/*.json` and `meal/energy.py` for weight management; 24 from 28 Oct with `demo/shell.html`). Any other number:
stop and find out why.

## Protections

| | Where | Default |
| --- | --- | --- |
| Passcode on every API call | `DEMO_PASSCODE` (Secret Manager) | required |
| Spend per run (agent stops) | `DEMO_SESSION_CAP` | US$0.05 |
| Spend in total (new runs refused) | `DEMO_TOTAL_CAP`, counter in Firestore `meta/spend` | US$2.00 |
| Runs at once | `DEMO_MAX_LIVE` | 3 |
| One instance (sessions live in memory) | `--max-instances 1` | |
| Anthropic key | Secret Manager, never in code or chat | |
| Hard ceiling | A **separate API key** in a Console workspace with its own spend limit | recommended |

## One-time setup (owner, in a terminal)

```bash
gcloud auth login zhouhanwei421@gmail.com
firebase login:use zhouhanwei421@gmail.com          # or: firebase login:add
# Console: create project <PROJECT>, link billing (Blaze), create Firestore (Native, asia-southeast1)
gcloud services enable run.googleapis.com cloudbuild.googleapis.com secretmanager.googleapis.com \
  artifactregistry.googleapis.com firestore.googleapis.com --project <PROJECT> --account zhouhanwei421@gmail.com
printf '%s' "$ANTHROPIC_API_KEY" | gcloud secrets create anthropic-key --data-file=- --project <PROJECT> --account zhouhanwei421@gmail.com
printf '%s' '<passcode>' | gcloud secrets create demo-passcode --data-file=- --project <PROJECT> --account zhouhanwei421@gmail.com
```

## Deploy

```bash
gcloud run deploy meal-demo --source . --region asia-southeast1 \
  --project <PROJECT> --account zhouhanwei421@gmail.com \
  --allow-unauthenticated --max-instances 1 --no-cpu-throttling --memory 512Mi --timeout 300 \
  --set-secrets ANTHROPIC_API_KEY=anthropic-key:latest,DEMO_PASSCODE=demo-passcode:latest \
  --set-env-vars DEMO_SESSION_CAP=0.05,DEMO_TOTAL_CAP=2,DEMO_MAX_LIVE=3 \
  --set-build-env-vars CODE_REV=$(git rev-parse --short HEAD)
firebase deploy --only hosting --project <PROJECT>
```

Note: Cloud Build reads `CODE_REV` only as a build arg; if `--set-build-env-vars` does not reach the
Dockerfile `ARG`, sessions record `code: unknown` — then pass `--set-env-vars CODE_REV=...` instead.

## After the study

```bash
.venv/bin/pip install google-cloud-firestore && gcloud auth application-default login
.venv/bin/python scripts/export_sessions.py <PROJECT>
.venv/bin/python scripts/study_summary.py
gcloud run services delete meal-demo --region asia-southeast1 --project <PROJECT> --account zhouhanwei421@gmail.com
```
Delete the service (or set `--max-instances 0`) when the study ends, and rotate the demo API key.

## Deployed (2026-10-24)

- Link: https://cs621-meal-demo.web.app (Hosting → Cloud Run `meal-demo`, asia-southeast1, revision
  `meal-demo-00001`, code `14f6389`).
- Checked live: every /api call and every source path is 401 without the passcode; Hosting serves one
  file (robots.txt); fixed planner and one Haiku run completed with the passcode (US$0.0044).
- Two check sessions in Firestore start with `ZZTEST_`: exclude them from the study.
- The first deploy uploaded 20 files instead of 19 (this README, written after the check; Cloud Build source
  bucket only, not in the image). `.gcloudignore` now excludes it.
- 2026-10-24: revision `meal-demo-00003`, code `9d1de84` (agent with request_input, intent ids, status query).
  Live check: Haiku run with the passcode declared "no egg", ordered S$27.20 with `intent_id`, no violations
  (US$0.0046). Upload list was 19 files before deploying.
- 2026-10-24: revisions `00004`–`00005`, code `371b732`: question sheet, presenter controls (`?presenter=1`). Live checks: inject needs the passcode; sell-out reached the fixed planner (no re-plan, no order); blank budget with fixed rules stops with a plain reason. Upload list 19 files each time.
- 2026-10-24: revision `00006`, code `be97bdc` (weight management: Alex/Bea/Chloe, data_wm). Upload list 23 files. Live: personas served, Chloe stopped for needs_professional_review with no plan or order (US$0.0004).
- 2026-10-24: revision `00007`, code `fd2bf87` (wm prompt fix: the calculator decides scope). Upload list 23 files; 401 without the passcode.

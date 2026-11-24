# Phase 1 — Repository inspection and environment audit

Performed 2026-11-24 on the development machine (Windows 11, Git Bash).

## Repository

| Item | Finding |
|---|---|
| URL | https://github.com/Hari160606/AgriResolve-AI (public) |
| Default branch | `main`, no other branches |
| Commits | 1 — `5b10d7c` "Initial commit" (2026-11-23), author `Hariharan R <hariharanramakrishnan08@gmail.com>`, committed through the GitHub web UI, signature verified by GitHub |
| Files at audit time | `README.md` only (content: the project name) |
| Issues / PRs | none visible on the repository page |
| Local workspace | empty folder, not a git repository |

Conclusion: greenfield. There was no code or history to review.

## Identity (checked separately, as required)

| Check | Value |
|---|---|
| `git config --global user.name` | `Hari160606` |
| `git config --global user.email` | `hariharanramakrishnan08@gmail.com` |
| Authenticated GitHub account (credential helper username only) | `Hari160606` |
| GitHub-resolved author of the existing commit | `Hari160606` |

**No mismatch.** Notes:
- the existing commit's author *name* ("Hariharan R") differs from the git config name; the email is
  what GitHub matches, so authorship still links to the right account;
- `gh` CLI is not installed, so `gh auth status` was unavailable and the Git Credential Manager
  (`manager`, v2.9.1) was queried instead — only the `username=` field was read, never the token;
- no identity settings were changed.

## Environment readiness

| Component | Status | Notes |
|---|---|---|
| Python | ✅ 3.13.0 | `python` on PATH is the Microsoft Store stub; use `py -3.13` or the full path |
| pip | ✅ 24.2 | |
| Virtualenv | ✅ created at `.venv` | `.venv\Scripts\python` |
| streamlit / pandas / numpy / plotly / scikit-learn / SQLAlchemy / psycopg2 | ✅ installed in `.venv` | versions pinned in `requirements.txt` |
| pytest | ✅ | 19 tests |
| PostgreSQL | ⚠️ server 18.1 running on 127.0.0.1:5432, service `postgresql-x64-18` | **password not supplied**, so the schema has not been loaded |
| Ollama | ✅ 0.40.17, model `llama3` | used by the AI assistant |
| Google Earth Engine | ❌ | no `earthengine-api`, no credentials, no `GEE_PROJECT_ID` |
| Google APIs | ❌ | no keys in `.env` |
| Git / VS Code | ✅ git 2.56.0, VS Code 1.146.0 (`code` on PATH) | |

## Files created for the scaffold

`.gitignore`, `.env.example`, `requirements.txt`, `src/config/*.yaml`, the folder tree from master
instruction A4 (each data folder keeps a `.gitkeep`).

## Open questions carried forward

1. PostgreSQL password / role for `agriresolve_app` — needed before `db/load.py` can run.
2. Google Cloud project for Earth Engine: existing project id, or should registration be walked through?
3. Branch strategy: one branch per phase (suggested `phase-01-repo-audit`, …) or commit straight to `main`?
4. Licence for the repository (phase 15).

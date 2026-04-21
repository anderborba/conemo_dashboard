# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

CONEMO is a Streamlit dashboard that monitors a mental health intervention study. It tracks participants enrolled at UBS (primary care units), their session progress across therapeutic journeys (depression/PHQ-9, anxiety/GAD-7), clinical scores, and patient feedback. Data comes from Google BigQuery (Firestore export) or a local PARQUET cache.

## Running the dashboard

```bash
# Install dependencies
pip install -r requirements.txt

# Run the dashboard
streamlit run Code/PY/dashboard_conemo.py

# Or the dated version (Fase C1 deliverable, currently staged):
streamlit run Code/PY/dashboard_conemo_20_04_2026_v1.py
```

The dashboard runs on `http://localhost:8501` by default. Streamlit config is in `.streamlit/config.toml`.

## Data modes

**Local cache mode (default for development):** The dashboard reads from `Data/PARQUET/` files. This directory is **not tracked in git** — it must be copied manually to the local clone before running.

**BigQuery mode:** Activated when Google credentials are available. On Streamlit Cloud, credentials come from `st.secrets["gcp_service_account"]`. Locally, the fallback path is `/home/aborba/Documentos/chave_conemo/conemo-412202-6e149ab3485a.json`. The `🔄` button in the sidebar clears Streamlit's `@st.cache_data` and re-queries BigQuery.

## Code architecture

The dashboard is a single-file Streamlit app. Its structure:

1. **BigQuery client** — `_get_bq_client()` with `@st.cache_resource`; tries `st.secrets` first, falls back to local key file.
2. **Data loaders** — `load_users_sessions()`, `load_journeys()`, `load_patience()` with `@st.cache_data`. Each runs a SQL query against `conemo-412202.firestore_export.*_raw_latest` tables.
3. **Data enrichment** — `parse_user()` inside `load_users_sessions()` unpacks nested JSON from Firestore into flat columns (`ubs_name`, `ubs_city`, `phq_score`, `gad_score`, age, etc.). `build_desc_df()` does the same for baseline questionnaire variables.
4. **Sidebar navigation** — `st.sidebar.radio` drives page selection; six pages rendered with `if/elif` blocks.
5. **Clinical helpers** — `phq_severity()`, `gad_severity()`, `age_group()`, `_phq_gravity()`, `_igi_gravity()` translate raw scores to clinical labels.
6. **Display helpers** — `_freq_table()` and `_stats_table()` render paired table+chart columns for the Análise Descritiva page.

Key data invariant: `ubs_city` is normalized to Title Case and `ubs_name` stays uppercase (both filtered to remove invalid entries like `"N/A"`, `""`, `"FAKE ORGANIZATION"`).

## BigQuery schema (Firestore export)

| Table | Key fields used |
|---|---|
| `users_raw_latest` | `document_id` (user_id), `DATA` (JSON with org, forms, baseline, scores) |
| `sessions_raw_latest` | `DATA` (JSON), `path_params.userId` |
| `journeys_raw_latest` | `DATA` (JSON), `path_params.userId`, `enabled='true'` filter |
| `patient_feedback_raw_latest` | `DATA` (JSON with patientId, feedbackType, source) |

## Workflow and governance

This project follows a formal phase-based workflow. **New phases require explicit approval from the project coordinator before any implementation.** The canonical documents are in `Docs/`:

- `Docs/Plano-implementacao-dashboard.md` — canonical implementation plan (V.2.0.0)
- `Docs/fase-dashboard-executiva-1.md` — execution log for Fase C1 (completed, merged via PR #1)

Branches are required for all technical work; direct commits to `main` are not allowed by discipline. The `🔄` button must remain visible in the dashboard per a binding coordination decision.

Current state: Fase C1 (P0/P1/P2) is merged into `main`. Next phase awaits formal prioritization.

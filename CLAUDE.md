# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

CONEMO is a Streamlit dashboard that monitors a mental health intervention study. It tracks participants enrolled at UBS (primary care units), their session progress across therapeutic journeys (depression/PHQ-9, anxiety/GAD-7), clinical scores, and patient feedback. Data comes from Google BigQuery (Firestore export) or a local PARQUET cache.

## Running the dashboard

```bash
# Install dependencies
pip install -r requirements.txt

# Run the dashboard (current Fase C1 deliverable)
streamlit run Code/PY/dashboard_conemo_20_04_2026_v1.py
```

The dashboard runs on `http://localhost:8501` by default. Streamlit config is in `.streamlit/config.toml`.

**Dev Container / Codespaces:** `.devcontainer/devcontainer.json` is configured to auto-start the dashboard on attach via `postAttachCommand` and forward port 8501.

## Data modes

**Local cache mode (default for development):** The dashboard reads from `Data/PARQUET/` files. The entire `Data/` directory is gitignored — it must be copied manually to the local clone before running.

**BigQuery mode:** Activated when Google credentials are available. On Streamlit Cloud, credentials come from `st.secrets["gcp_service_account"]`. Locally, the fallback path is `/home/aborba/Documentos/chave_conemo/conemo-412202-6e149ab3485a.json`. The `🔄` button in the sidebar calls `clear_all_caches()` and `st.rerun()`, which clears all `@st.cache_data` and re-queries BigQuery.

## Code architecture

The dashboard is a single file (`Code/PY/dashboard_conemo_20_04_2026_v1.py`, ~1500 lines). Its structure:

1. **BigQuery client** — `_get_bq_client()` with `@st.cache_resource`; tries `st.secrets` first, falls back to local key file.
2. **SQL queries** — four module-level string constants: `_QUERY_USERS_SESSIONS`, `_QUERY_JOURNEYS`, `_QUERY_PATIENCE`, `_QUERY_LAST_UPDATE`.
3. **Data loaders** — `load_users_sessions()`, `load_journeys()`, `load_patience()`, `load_last_update()` with `@st.cache_data`. `clear_all_caches()` must call `.clear()` on all four plus `build_desc_df`.
4. **Data enrichment** — `parse_user()` inside `load_users_sessions()` unpacks nested JSON from Firestore into flat columns (`ubs_name`, `ubs_city`, `phq_score`, `gad_score`, age, etc.). `build_desc_df()` (also `@st.cache_data`) does the same for the full baseline questionnaire variables (PHQ/GAD/IGI/SRAP, sociodemographic, quality-of-life, etc.).
5. **Journey enrichment** — after loading, `df_journeys` is left-joined with `df_users_unique` to attach UBS/score columns.
6. **Sidebar navigation** — `st.sidebar.radio` drives page selection; six pages rendered with `if/elif` blocks: `🏠 Visão Geral`, `🏥 Por UBS`, `🗺️ Jornadas`, `💬 Feedback de Pacientes`, `👤 Por Participante`, `📊 Análise Descritiva`.
7. **Clinical helpers** — two overlapping sets exist: `phq_severity()` / `gad_severity()` (used in the participant detail page) and `_phq_gravity()` / `_gad_gravity()` / `_igi_gravity()` (used in Análise Descritiva). Both classify the same scales but return slightly different label strings — do not merge without checking callers.
8. **Display helpers** — `_freq_table()` and `_stats_table()` render paired table+chart columns for the Análise Descritiva page.

Key data invariant: both `ubs_city` and `ubs_name` are normalized to **uppercase** (`str.upper().str.strip()`), and filtered to remove invalid entries like `"N/A"`, `""`, `"X"`, `"FAKE ORGANIZATION"`, `"FAKE CITY"`.

## BigQuery schema (Firestore export)

| Table | Key fields used |
|---|---|
| `users_raw_latest` | `document_id` (user_id), `DATA` (JSON with org, forms, baseline, scores) |
| `sessions_raw_latest` | `DATA` (JSON), `path_params.userId` |
| `journeys_raw_latest` | `DATA` (JSON), `path_params.userId`, `enabled='true'` filter |
| `patient_feedback_raw_latest` | `DATA` (JSON with patientId, feedbackType, source) |

All tables are in project `conemo-412202`, dataset `firestore_export`.

## Workflow and governance

This project follows a formal phase-based workflow. **New phases require explicit approval from the project coordinator before any implementation.** The canonical documents are in `Docs/`:

- `Docs/Plano-implementacao-dashboard.md` — canonical implementation plan (V.2.0.0)
- `Docs/fase-dashboard-executiva-1.md` — execution log for Fase C1 (completed, merged via PR #1)

Branches are required for all technical work; direct commits to `main` are not allowed by discipline. The `🔄` button must remain visible in the dashboard per a binding coordination decision.

Current state: Fase C1 (P0/P1/P2) is merged into `main`. Next phase awaits formal prioritization.

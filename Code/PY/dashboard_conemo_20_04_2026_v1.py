import os
import json
from datetime import datetime

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from google.cloud import bigquery
from google.oauth2 import service_account

# ---------------------------------------------------------------------------
# Configuração da página
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="CONEMO Dashboard",
    page_icon="🏥",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Cliente BigQuery — Streamlit Cloud (st.secrets) ou desenvolvimento local
# ---------------------------------------------------------------------------
@st.cache_resource
def _get_bq_client() -> bigquery.Client:
    try:
        if "gcp_service_account" in st.secrets:
            creds = service_account.Credentials.from_service_account_info(
                st.secrets["gcp_service_account"],
                scopes=["https://www.googleapis.com/auth/cloud-platform"],
            )
            return bigquery.Client(credentials=creds, project=creds.project_id)
    except Exception:
        pass
    # Fallback para desenvolvimento local com arquivo de chave
    os.environ.setdefault(
        "GOOGLE_APPLICATION_CREDENTIALS",
        "/home/aborba/Documentos/chave_conemo/conemo-412202-6e149ab3485a.json",
    )
    return bigquery.Client()

# ---------------------------------------------------------------------------
# Queries BigQuery
# ---------------------------------------------------------------------------
_QUERY_USERS_SESSIONS = """
SELECT
  u.document_id                                       AS user_id,
  u.DATA                                              AS json_data_user,
  JSON_VALUE(u.DATA, '$.email')                       AS email,
  TIMESTAMP_SECONDS(
    CAST(JSON_VALUE(u.DATA, '$.forms[0].date._seconds') AS INT64)
  )                                                   AS firstFormTs,
  JSON_VALUE(s.DATA, '$.sessionNumber')               AS sessionNumber,
  JSON_VALUE(s.DATA, '$.isCompleted')                 AS isCompleted,
  JSON_VALUE(s.DATA, '$.completedDate')               AS completedDate
FROM
  `conemo-412202.firestore_export.users_raw_latest` u
LEFT JOIN
  `conemo-412202.firestore_export.sessions_raw_latest` s
  ON JSON_VALUE(s.path_params, '$.userId') = u.document_id
"""

_QUERY_JOURNEYS = """
SELECT
  document_id,
  JSON_VALUE(path_params, '$.userId')             AS user_id,
  JSON_VALUE(DATA, '$.type')                      AS journey_type,
  JSON_VALUE(DATA, '$.enabled')                   AS enabled,
  SAFE_CAST(JSON_VALUE(DATA, '$.lastSession') AS INT64) AS lastSession,
  SAFE_CAST(JSON_VALUE(DATA, '$.lastAccess._seconds') AS INT64) AS lastAccessSeconds
FROM
  `conemo-412202.firestore_export.journeys_raw_latest`
WHERE
  JSON_VALUE(DATA, '$.enabled') = 'true'
"""

_QUERY_PATIENCE = """
SELECT
  document_id,
  JSON_VALUE(DATA, '$.patientId')                 AS patientId,
  JSON_VALUE(DATA, '$.patientWhatsAppId')         AS patientWhatsAppId,
  SAFE_CAST(JSON_VALUE(DATA, '$.createdAt._seconds') AS INT64) AS createdAtSeconds,
  JSON_VALUE(DATA, '$.feedbackType')              AS feedbackType,
  JSON_EXTRACT(DATA, '$.data')                    AS feedback_data,
  JSON_VALUE(DATA, '$.source')                    AS source,
  JSON_VALUE(DATA, '$.sessionId')                 AS sessionId
FROM
  `conemo-412202.firestore_export.patient_feedback_raw_latest`
"""

# ---------------------------------------------------------------------------
# Funções de carregamento direto do BigQuery
# ---------------------------------------------------------------------------
@st.cache_data
def load_users_sessions() -> pd.DataFrame:
    df = _get_bq_client().query(_QUERY_USERS_SESSIONS).to_dataframe()

    df["sessionNumber"] = pd.to_numeric(df["sessionNumber"], errors="coerce")
    df["isCompleted"] = (
        df["isCompleted"].astype(str).str.lower().str.strip()
        .map({"true": True, "false": False})
    )

    def parse_user(json_str):
        try:
            data = json.loads(json_str)
            org = data.get("organization", {})
            forms = data.get("forms", [])
            phq, gad = None, None
            if forms:
                for s in forms[0].get("scores", []):
                    if s.get("type") == "PHQ":
                        phq = s.get("score")
                    if s.get("type") == "GAD":
                        gad = s.get("score")

            birth_seconds = None
            bd = data.get("birthDate")
            if isinstance(bd, dict):
                birth_seconds = bd.get("_seconds")
            age = None
            if birth_seconds:
                birth = datetime.fromtimestamp(birth_seconds)
                today = datetime.now()
                age = today.year - birth.year - (
                    (today.month, today.day) < (birth.month, birth.day)
                )

            return pd.Series({
                "ubs_name": org.get("name", "N/A"),
                "ubs_city": org.get("city", "N/A"),
                "phq_score": phq,
                "gad_score": gad,
                "gender": data.get("gender", "N/A"),
                "age": age,
                "user_name": data.get("name", "N/A"),
                "education": data.get("education", "N/A"),
                "occupation": data.get("occupation", "N/A"),
            })
        except Exception:
            return pd.Series({
                "ubs_name": "N/A", "ubs_city": "N/A",
                "phq_score": None, "gad_score": None,
                "gender": "N/A", "age": None, "user_name": "N/A",
                "education": "N/A", "occupation": "N/A",
            })

    extracted = df["json_data_user"].apply(parse_user)
    df = pd.concat([df, extracted], axis=1)

    df["ubs_name"] = df["ubs_name"].str.upper().str.strip()
    df["ubs_city"] = df["ubs_city"].str.upper().str.strip()
    df = df[~df["ubs_city"].isin(["FAKE CITY", "N/A", ""])]
    df = df[~df["ubs_name"].isin(["N/A", "", "X", "FAKE ORGANIZATION"])]

    return df


@st.cache_data
def load_journeys() -> pd.DataFrame:
    df = _get_bq_client().query(_QUERY_JOURNEYS).to_dataframe()
    df["lastAccessDate"] = pd.to_datetime(
        df["lastAccessSeconds"], unit="s", errors="coerce"
    )
    return df


@st.cache_data
def load_patience() -> pd.DataFrame:
    df = _get_bq_client().query(_QUERY_PATIENCE).to_dataframe()
    df["createdAt"] = pd.to_datetime(
        df["createdAtSeconds"], unit="s", errors="coerce"
    )
    return df


def clear_all_caches():
    load_users_sessions.clear()
    load_journeys.clear()
    load_patience.clear()
    build_desc_df.clear()


@st.cache_data
def build_desc_df(_df: pd.DataFrame) -> pd.DataFrame:
    def parse_extended(json_str):
        try:
            data = json.loads(json_str)

            # ── Scores de forms[0].scores (PHQ, GAD, IGI) ──────────────────
            forms = data.get("forms", [])
            scores = {}
            if forms:
                for s in forms[0].get("scores", []):
                    scores[s.get("type", "")] = s.get("score")

            # ── Variáveis do questionário baseline ─────────────────────────
            # Estrutura: data["baseline"][0]["answers"] = [{variable, value}]
            bl_answers = {}
            bl = data.get("baseline")
            if isinstance(bl, list) and bl:
                for item in bl[0].get("answers", []):
                    var = item.get("variable")
                    val = item.get("value")
                    if var:
                        bl_answers[var] = val

            return pd.Series({
                # Sociodemográfico
                "sexgr":    data.get("gender"),
                "race":     bl_answers.get("race"),
                "hl4":      bl_answers.get("hl4"),
                "pmarry":   bl_answers.get("pmarry"),
                "se1":      bl_answers.get("se1"),
                "se17":     data.get("occupation"),
                "income1":  bl_answers.get("income1"),
                # Clínico — scores
                "phq":   scores.get("PHQ"),
                "gad":   scores.get("GAD"),
                "igi":   scores.get("IGI"),
                "srapt": scores.get("SRAP") or scores.get("SRAPT"),
                "level": data.get("level") or scores.get("LEVEL"),
                "SC4":   data.get("SC4"),
                # Suporte social
                "ss1": bl_answers.get("ss1"),
                # Histórico de tratamento
                "ms1":       bl_answers.get("ms1"),
                "psychtr":   bl_answers.get("psychtr"),
                "ms4":       bl_answers.get("ms4"),
                "psychhosp": bl_answers.get("psychhosp"),
                "erpsych":   bl_answers.get("erpsych"),
                "caps":      bl_answers.get("caps"),
                "adpsych":   bl_answers.get("adpsych"),
                "conspsych": bl_answers.get("conspsych"),
                # Álcool
                "audit1": bl_answers.get("audit1"),
                "audit2": bl_answers.get("audit2"),
                "audit3": bl_answers.get("audit3"),
                # Tabaco
                "tabacco3": bl_answers.get("tabacco3"),
                # Ativação comportamental
                **{f"ca{i}": bl_answers.get(f"ca{i}") for i in range(1, 10)},
                # Qualidade de vida (EQ-5D)
                "eqdmob":    bl_answers.get("eqdmob"),
                "eqdcare":   bl_answers.get("eqdcare"),
                "eqdactivi": bl_answers.get("eqdactivi"),
                "eqdpain":   bl_answers.get("eqdpain"),
                "eqddep":    bl_answers.get("eqddep"),
            })
        except Exception:
            return pd.Series({})

    users = _df.drop_duplicates(subset="user_id").copy()
    extended = users["json_data_user"].apply(parse_extended)
    return pd.concat([
        users[["user_id", "age", "ubs_name", "ubs_city"]].reset_index(drop=True),
        extended.reset_index(drop=True),
    ], axis=1)


# ---------------------------------------------------------------------------
# Carrega os dados
# ---------------------------------------------------------------------------
df = load_users_sessions()
df_journeys = load_journeys()
df_patience = load_patience()

df_desc = build_desc_df(df)

# Enriquece journeys com info de UBS do df de usuarios
df_users_unique = df.drop_duplicates(subset="user_id")[
    ["user_id", "ubs_name", "ubs_city", "phq_score", "gad_score", "gender", "age"]
]
df_journeys = df_journeys.merge(df_users_unique, on="user_id", how="left")

# ---------------------------------------------------------------------------
# Sidebar — navegação
# ---------------------------------------------------------------------------
st.sidebar.title("🏥 CONEMO")
st.sidebar.markdown("---")
page = st.sidebar.radio(
    "Navegação",
    [
        "🏠 Visão Geral",
        "🏥 Por UBS",
        "🗺️ Jornadas",
        "💬 Feedback de Pacientes",
        "👤 Por Participante",
        "📊 Análise Descritiva",
    ],
)
st.sidebar.markdown("---")
if st.sidebar.button("🔄 Atualizar dados do BigQuery"):
    clear_all_caches()
    st.rerun()

# ---------------------------------------------------------------------------
# Helpers — análise descritiva
# ---------------------------------------------------------------------------
def _freq_table(series: pd.Series, label: str):
    s = series.dropna().astype(str)
    s = s[s.str.strip().str.lower().isin(["", "nan", "none", "n/a"]) == False]
    if s.empty:
        st.info(f"Dados não disponíveis: **{label}**")
        return
    counts = s.value_counts()
    total = counts.sum()
    tbl = pd.DataFrame({label: counts.index, "n": counts.values})
    tbl["%"] = (tbl["n"] / total * 100).round(1)
    tbl["n (%)"] = tbl["n"].astype(str) + " (" + tbl["%"].astype(str) + "%)"
    col_t, col_g = st.columns([1, 1])
    col_t.dataframe(tbl[[label, "n (%)"]].reset_index(drop=True), hide_index=True)
    fig = px.bar(
        tbl, x="n", y=label, orientation="h",
        color="n", color_continuous_scale="Blues",
        labels={"n": "n", label: label},
    )
    fig.update_layout(
        showlegend=False, coloraxis_showscale=False,
        height=max(220, len(tbl) * 40), margin=dict(l=0, r=0, t=20, b=0)
    )
    col_g.plotly_chart(fig, width='stretch')


def _stats_row(series: pd.Series, label: str) -> dict | None:
    s = pd.to_numeric(series, errors="coerce").dropna()
    if s.empty:
        return None
    return {
        "Variável": label,
        "n": len(s),
        "Média": round(s.mean(), 2),
        "DP": round(s.std(), 2),
        "Mediana": round(s.median(), 2),
        "IQR": f"{round(s.quantile(0.25), 1)}–{round(s.quantile(0.75), 1)}",
        "Min": round(s.min(), 1),
        "Max": round(s.max(), 1),
    }


def _stats_table(series: pd.Series, label: str):
    row = _stats_row(series, label)
    if row is None:
        st.info(f"Dados não disponíveis: **{label}**")
        return
    col_t, col_g = st.columns([1, 1])
    col_t.dataframe(pd.DataFrame([row]), hide_index=True)
    s = pd.to_numeric(series, errors="coerce").dropna()
    fig = px.histogram(
        s, nbins=15,
        labels={"value": label, "count": "n"},
        color_discrete_sequence=["#636EFA"],
    )
    fig.update_layout(showlegend=False, height=250, xaxis_title=label, yaxis_title="n")
    col_g.plotly_chart(fig, width='stretch')


def _phq_gravity(score):
    try:
        s = float(score)
    except (TypeError, ValueError):
        return "N/D"
    if s <= 4:   return "Sem depressão (0–4)"
    if s <= 9:   return "Leve (5–9)"
    if s <= 14:  return "Moderada (10–14)"
    if s <= 19:  return "Mod. grave (15–19)"
    return "Grave (20–27)"


def _gad_gravity(score):
    try:
        s = float(score)
    except (TypeError, ValueError):
        return "N/D"
    if s <= 4:   return "Mínima (0–4)"
    if s <= 9:   return "Leve (5–9)"
    if s <= 14:  return "Moderada (10–14)"
    return "Grave (15–21)"


def _igi_gravity(score):
    try:
        s = float(score)
    except (TypeError, ValueError):
        return "N/D"
    if s <= 7:   return "Sem insônia (0–7)"
    if s <= 14:  return "Subclínica (8–14)"
    if s <= 21:  return "Moderada (15–21)"
    return "Grave (22–28)"


# ---------------------------------------------------------------------------
# Helpers de classificação clínica
# ---------------------------------------------------------------------------
def phq_severity(score):
    if score is None:
        return "N/D"
    score = float(score)
    if score <= 4:
        return "Sem depressão"
    if score <= 9:
        return "Leve"
    if score <= 14:
        return "Moderada"
    if score <= 19:
        return "Moderadamente grave"
    return "Grave"


def gad_severity(score):
    if score is None:
        return "N/D"
    score = float(score)
    if score <= 4:
        return "Mínima"
    if score <= 9:
        return "Leve"
    if score <= 14:
        return "Moderada"
    return "Grave"


def severity_color(label):
    return {
        "Sem depressão": "green", "Mínima": "green",
        "Leve": "orange", "Moderada": "orange",
        "Moderadamente grave": "red", "Grave": "red",
        "N/D": "gray",
    }.get(label, "gray")


def age_group(age):
    if pd.isna(age):
        return "Não informado"
    age = int(age)
    if age < 18:
        return "< 18"
    if age <= 29:
        return "18–29"
    if age <= 39:
        return "30–39"
    if age <= 49:
        return "40–49"
    if age <= 59:
        return "50–59"
    if age <= 69:
        return "60–69"
    if age <= 79:
        return "70–79"
    return "80+"


# ---------------------------------------------------------------------------
# Página 1 — Visão Geral (Gestão do Projeto)
# ---------------------------------------------------------------------------
if page == "🏠 Visão Geral":
    st.title("Visão Geral — Gestão do Projeto")

    df_users = df.drop_duplicates(subset="user_id")

    total_users = df_users["user_id"].nunique()
    total_sessions = len(df)
    sessions_done = int(df["isCompleted"].sum())
    completion_rate = sessions_done / total_sessions * 100 if total_sessions > 0 else 0
    total_journeys = df_journeys["user_id"].nunique()
    total_feedback = len(df_patience)

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Participantes", total_users)
    m2.metric("Total de Sessões", total_sessions)
    m3.metric("Sessões Concluídas", sessions_done)
    m4.metric("Taxa de Conclusão", f"{completion_rate:.1f}%")
    m5.metric("Feedbacks Recebidos", total_feedback)

    st.markdown("---")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Recrutamento — Novos Participantes por Mês")
        if "firstFormTs" in df_users.columns and df_users["firstFormTs"].notna().any():
            df_recruit = df_users.copy()
            df_recruit["firstFormTs"] = pd.to_datetime(
                df_recruit["firstFormTs"], errors="coerce"
            )
            df_recruit = df_recruit.dropna(subset=["firstFormTs"])
            df_recruit["mes"] = df_recruit["firstFormTs"].dt.to_period("M").astype(str)
            recruit_count = (
                df_recruit.groupby("mes")["user_id"].nunique().reset_index(name="Novos Participantes")
            )
            fig_recruit = px.bar(
                recruit_count,
                x="mes",
                y="Novos Participantes",
                labels={"mes": "Mês"},
                color="Novos Participantes",
                color_continuous_scale="Blues",
            )
            fig_recruit.update_layout(
                showlegend=False, coloraxis_showscale=False, height=350,
                xaxis_title="Mês", yaxis_title="Novos participantes"
            )
            st.plotly_chart(fig_recruit, width='stretch')
        else:
            st.info("Data de primeiro formulário não disponível para recrutamento temporal.")

    with col2:
        st.subheader("Taxa de Conclusão de Sessões por UBS")
        comp_ubs = (
            df.groupby("ubs_name")["isCompleted"]
            .apply(lambda x: x.mean() * 100 if x.count() > 0 else 0.0)
            .reset_index(name="Taxa (%)")
            .rename(columns={"ubs_name": "UBS"})
        )
        fig_comp = px.bar(
            comp_ubs.sort_values("Taxa (%)"),
            x="Taxa (%)", y="UBS", orientation="h",
            color="Taxa (%)", color_continuous_scale="Greens",
        )
        fig_comp.update_layout(
            showlegend=False, coloraxis_showscale=False, height=350
        )
        st.plotly_chart(fig_comp, width='stretch')

    st.markdown("---")
    st.subheader("Resumo por Município")

    resumo_mun = (
        df_users.groupby("ubs_city")
        .agg(
            Participantes=("user_id", "nunique"),
            UBS_count=("ubs_name", "nunique"),
            PHQ9_media=("phq_score", "mean"),
            GAD7_media=("gad_score", "mean"),
        )
        .reset_index()
        .rename(columns={"ubs_city": "Município", "UBS_count": "UBSs"})
    )
    resumo_mun["PHQ-9 Média"] = resumo_mun["PHQ9_media"].round(1)
    resumo_mun["GAD-7 Média"] = resumo_mun["GAD7_media"].round(1)
    resumo_mun = resumo_mun[
        ["Município", "Participantes", "UBSs", "PHQ-9 Média", "GAD-7 Média"]
    ].sort_values("Participantes", ascending=False)
    st.dataframe(resumo_mun, width='stretch', hide_index=True)
    st.download_button(
        "⬇️ CSV", resumo_mun.to_csv(index=False).encode("utf-8"),
        "resumo_municipios.csv", "text/csv", key="dl_mun"
    )

# ---------------------------------------------------------------------------
# Página 2 — Por UBS
# ---------------------------------------------------------------------------
elif page == "🏥 Por UBS":
    st.title("Estatísticas por UBS")

    col_f1, col_f2 = st.columns(2)
    all_cities = sorted(df["ubs_city"].dropna().unique())
    sel_cities = col_f1.multiselect("Cidade", all_cities, default=all_cities)

    df_city = df[df["ubs_city"].isin(sel_cities)] if sel_cities else df
    all_ubs = sorted(df_city["ubs_name"].dropna().unique())
    sel_ubs = col_f2.multiselect("UBS", all_ubs, default=all_ubs)

    dff = df_city[df_city["ubs_name"].isin(sel_ubs)] if sel_ubs else df_city
    df_users = dff.drop_duplicates(subset="user_id")

    total_users = df_users["user_id"].nunique()
    mean_phq = df_users["phq_score"].mean()
    mean_gad = df_users["gad_score"].mean()
    sessions_total = len(dff)
    sessions_done = dff["isCompleted"].sum()
    completion_rate = sessions_done / sessions_total * 100 if sessions_total > 0 else 0

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Participantes", total_users)
    m2.metric("Média PHQ-9 (Depressão)", f"{mean_phq:.1f}" if pd.notna(mean_phq) else "N/D")
    m3.metric("Média GAD-7 (Ansiedade)", f"{mean_gad:.1f}" if pd.notna(mean_gad) else "N/D")
    m4.metric("Conclusão de Sessões", f"{completion_rate:.1f}%")

    st.markdown("---")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Participantes por UBS")
        ubs_count = (
            df_users["ubs_name"].value_counts().reset_index()
        )
        ubs_count.columns = ["UBS", "Participantes"]
        fig = px.bar(
            ubs_count.sort_values("Participantes"),
            x="Participantes", y="UBS", orientation="h",
            color="Participantes", color_continuous_scale="Blues",
        )
        fig.update_layout(showlegend=False, coloraxis_showscale=False, height=400)
        st.plotly_chart(fig, width='stretch')
        st.download_button(
            "⬇️ CSV", ubs_count.to_csv(index=False).encode("utf-8"),
            "participantes_por_ubs.csv", "text/csv", key="dl_ubs_count"
        )

    with col2:
        st.subheader("Média PHQ-9 e GAD-7 por UBS")
        scores_ubs = (
            df_users.groupby("ubs_name")[["phq_score", "gad_score"]]
            .mean().reset_index()
            .rename(columns={"ubs_name": "UBS", "phq_score": "PHQ-9", "gad_score": "GAD-7"})
        )
        scores_melt = scores_ubs.melt(id_vars="UBS", var_name="Escala", value_name="Média")
        fig2 = px.bar(
            scores_melt, x="Média", y="UBS", color="Escala",
            orientation="h", barmode="group",
            color_discrete_map={"PHQ-9": "#EF553B", "GAD-7": "#636EFA"},
        )
        fig2.update_layout(height=400)
        st.plotly_chart(fig2, width='stretch')
        st.download_button(
            "⬇️ CSV", scores_ubs.to_csv(index=False).encode("utf-8"),
            "scores_phq_gad_por_ubs.csv", "text/csv", key="dl_scores_ubs"
        )

    col3, col4, col5 = st.columns(3)

    with col3:
        st.subheader("Taxa de Conclusão por UBS")
        comp_ubs = (
            dff.groupby("ubs_name")["isCompleted"]
            .apply(lambda x: x.mean() * 100 if x.count() > 0 else 0.0)
            .reset_index(name="Taxa (%)")
            .rename(columns={"ubs_name": "UBS"})
        )
        fig3 = px.bar(
            comp_ubs.sort_values("Taxa (%)"),
            x="Taxa (%)", y="UBS", orientation="h",
            color="Taxa (%)", color_continuous_scale="Greens",
        )
        fig3.update_layout(showlegend=False, coloraxis_showscale=False, height=350)
        st.plotly_chart(fig3, width='stretch')
        st.download_button(
            "⬇️ CSV", comp_ubs.to_csv(index=False).encode("utf-8"),
            "taxa_conclusao_por_ubs.csv", "text/csv", key="dl_comp_ubs"
        )

    with col4:
        st.subheader("Distribuição de Gênero")
        gender_map = {"F": "Feminino", "M": "Masculino"}
        gender_counts = (
            df_users["gender"].map(gender_map).fillna("Não informado")
            .value_counts().reset_index()
        )
        gender_counts.columns = ["Gênero", "Contagem"]
        fig4 = px.pie(
            gender_counts, names="Gênero", values="Contagem",
            hole=0.4, color_discrete_sequence=px.colors.qualitative.Set2,
        )
        fig4.update_layout(height=350)
        st.plotly_chart(fig4, width='stretch')
        st.download_button(
            "⬇️ CSV", gender_counts.to_csv(index=False).encode("utf-8"),
            "distribuicao_genero.csv", "text/csv", key="dl_gender"
        )

    with col5:
        st.subheader("Distribuição por Faixa Etária")
        age_order = ["< 18", "18–29", "30–39", "40–49", "50–59", "60–69", "70–79", "80+", "Não informado"]
        age_data = (
            df_users["age"].apply(age_group)
            .value_counts().reindex(age_order, fill_value=0)
            .reset_index()
        )
        age_data.columns = ["Faixa Etária", "N"]
        fig5 = px.bar(
            age_data, x="Faixa Etária", y="N",
            color="N", color_continuous_scale="Purples",
            labels={"N": "Participantes"},
        )
        fig5.update_layout(showlegend=False, coloraxis_showscale=False, height=350)
        st.plotly_chart(fig5, width='stretch')
        st.download_button(
            "⬇️ CSV", age_data.to_csv(index=False).encode("utf-8"),
            "distribuicao_faixa_etaria.csv", "text/csv", key="dl_ages"
        )

    st.markdown("---")
    st.subheader("Resumo por UBS")
    comp_lookup = comp_ubs.set_index("UBS")["Taxa (%)"].to_dict()
    resumo = (
        df_users.groupby("ubs_name")
        .agg(
            Participantes=("user_id", "nunique"),
            PHQ9_media=("phq_score", "mean"),
            GAD7_media=("gad_score", "mean"),
        )
        .reset_index().rename(columns={"ubs_name": "UBS"})
    )
    resumo["Conclusão (%)"] = resumo["UBS"].map(comp_lookup).round(1)
    resumo["PHQ-9 Média"] = resumo["PHQ9_media"].round(1)
    resumo["GAD-7 Média"] = resumo["GAD7_media"].round(1)
    resumo = resumo[
        ["UBS", "Participantes", "PHQ-9 Média", "GAD-7 Média", "Conclusão (%)"]
    ].sort_values("Participantes", ascending=False)
    st.dataframe(resumo, width='stretch', hide_index=True)
    st.download_button(
        "⬇️ CSV", resumo.to_csv(index=False).encode("utf-8"),
        "resumo_por_ubs.csv", "text/csv", key="dl_resumo"
    )

# ---------------------------------------------------------------------------
# Página 3 — Jornadas
# ---------------------------------------------------------------------------
elif page == "🗺️ Jornadas":
    st.title("Jornadas — Adesão e Engajamento")

    if df_journeys.empty:
        st.warning("Nenhum dado de jornadas disponível.")
        st.stop()

    col_f1, col_f2 = st.columns(2)
    all_cities_j = sorted(df_journeys["ubs_city"].dropna().unique())
    sel_cities_j = col_f1.multiselect(
        "Cidade", all_cities_j, default=all_cities_j, key="jf_city"
    )
    dfj = df_journeys[df_journeys["ubs_city"].isin(sel_cities_j)] if sel_cities_j else df_journeys

    all_types = sorted(dfj["journey_type"].dropna().unique())
    sel_types = col_f2.multiselect(
        "Tipo de Jornada", all_types, default=all_types, key="jf_type"
    )
    dfj = dfj[dfj["journey_type"].isin(sel_types)] if sel_types else dfj

    total_journeys = len(dfj)
    users_with_journey = dfj["user_id"].nunique()
    mean_last_session = dfj["lastSession"].mean()

    m1, m2, m3 = st.columns(3)
    m1.metric("Jornadas Ativas", total_journeys)
    m2.metric("Participantes com Jornada", users_with_journey)
    m3.metric(
        "Última Sessão Média",
        f"{mean_last_session:.1f}" if pd.notna(mean_last_session) else "N/D"
    )

    st.markdown("---")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Jornadas por Tipo")
        type_counts = (
            dfj["journey_type"].value_counts().reset_index()
        )
        type_counts.columns = ["Tipo", "Jornadas"]
        fig_type = px.pie(
            type_counts, names="Tipo", values="Jornadas",
            hole=0.4,
            color_discrete_map={"PHQ": "#EF553B", "GAD": "#636EFA"},
        )
        fig_type.update_layout(height=350)
        st.plotly_chart(fig_type, width='stretch')
        st.download_button(
            "⬇️ CSV", type_counts.to_csv(index=False).encode("utf-8"),
            "jornadas_por_tipo.csv", "text/csv", key="dl_jtype"
        )

    with col2:
        st.subheader("Distribuição de Última Sessão Completada")
        sess_data = dfj["lastSession"].dropna()
        if not sess_data.empty:
            fig_sess = px.histogram(
                sess_data, nbins=15,
                labels={"value": "Última Sessão", "count": "Frequência"},
                color_discrete_sequence=["#19D3F3"],
            )
            fig_sess.update_layout(
                showlegend=False, height=350,
                xaxis_title="Número da última sessão",
                yaxis_title="Frequência"
            )
            st.plotly_chart(fig_sess, width='stretch')
        else:
            st.info("Dados de última sessão não disponíveis.")

    st.markdown("---")

    col3, col4 = st.columns(2)

    with col3:
        st.subheader("Jornadas por UBS")
        if "ubs_name" in dfj.columns:
            ubs_j = (
                dfj.groupby("ubs_name")["document_id"]
                .count().reset_index(name="Jornadas")
                .rename(columns={"ubs_name": "UBS"})
                .sort_values("Jornadas")
            )
            fig_ubs_j = px.bar(
                ubs_j, x="Jornadas", y="UBS", orientation="h",
                color="Jornadas", color_continuous_scale="Teal",
            )
            fig_ubs_j.update_layout(showlegend=False, coloraxis_showscale=False, height=350)
            st.plotly_chart(fig_ubs_j, width='stretch')
            st.download_button(
                "⬇️ CSV", ubs_j.to_csv(index=False).encode("utf-8"),
                "jornadas_por_ubs.csv", "text/csv", key="dl_jubs"
            )

    with col4:
        st.subheader("Último Acesso — Dias desde o Acesso")
        if dfj["lastAccessDate"].notna().any():
            today = pd.Timestamp.now(tz="UTC").tz_localize(None)
            dfj_copy = dfj.copy()
            dfj_copy["lastAccessDate"] = dfj_copy["lastAccessDate"].dt.tz_localize(None)
            dfj_copy["dias_sem_acesso"] = (today - dfj_copy["lastAccessDate"]).dt.days
            access_data = dfj_copy["dias_sem_acesso"].dropna()
            fig_access = px.histogram(
                access_data, nbins=20,
                labels={"value": "Dias sem acesso", "count": "Frequência"},
                color_discrete_sequence=["#FFA15A"],
            )
            fig_access.update_layout(
                showlegend=False, height=350,
                xaxis_title="Dias desde o último acesso",
                yaxis_title="Frequência"
            )
            st.plotly_chart(fig_access, width='stretch')
        else:
            st.info("Dados de último acesso não disponíveis.")

    st.markdown("---")
    st.subheader("Tabela de Jornadas")
    tbl_j = dfj[
        ["user_id", "journey_type", "lastSession", "lastAccessDate", "ubs_name", "ubs_city"]
    ].rename(columns={
        "user_id": "Participante", "journey_type": "Tipo",
        "lastSession": "Última Sessão", "lastAccessDate": "Último Acesso",
        "ubs_name": "UBS", "ubs_city": "Cidade"
    }).sort_values("Último Acesso", ascending=False)
    with st.expander("Ver tabela completa de jornadas"):
        st.dataframe(tbl_j, width='stretch', hide_index=True)
        st.download_button(
            "⬇️ CSV", tbl_j.to_csv(index=False).encode("utf-8"),
            "jornadas_detalhes.csv", "text/csv", key="dl_jdetails"
        )

# ---------------------------------------------------------------------------
# Página 4 — Feedback de Pacientes (Patience)
# ---------------------------------------------------------------------------
elif page == "💬 Feedback de Pacientes":
    st.title("Feedback de Pacientes (Patience)")

    if df_patience.empty:
        st.warning("Nenhum dado de feedback disponível.")
        st.stop()

    total_feedback = len(df_patience)
    n_patients = df_patience["patientId"].nunique()
    n_types = df_patience["feedbackType"].nunique()
    n_sources = df_patience["source"].nunique()

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total de Feedbacks", total_feedback)
    m2.metric("Pacientes com Feedback", n_patients)
    m3.metric("Tipos de Feedback", n_types)
    m4.metric("Fontes", n_sources)

    st.markdown("---")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Feedbacks por Tipo")
        type_counts = (
            df_patience["feedbackType"].value_counts().reset_index()
        )
        type_counts.columns = ["Tipo de Feedback", "Quantidade"]
        fig_ft = px.bar(
            type_counts.sort_values("Quantidade"),
            x="Quantidade", y="Tipo de Feedback", orientation="h",
            color="Quantidade", color_continuous_scale="Blues",
        )
        fig_ft.update_layout(showlegend=False, coloraxis_showscale=False, height=350)
        st.plotly_chart(fig_ft, width='stretch')
        st.download_button(
            "⬇️ CSV", type_counts.to_csv(index=False).encode("utf-8"),
            "feedback_por_tipo.csv", "text/csv", key="dl_ftype"
        )

    with col2:
        st.subheader("Feedbacks por Fonte (Source)")
        source_counts = (
            df_patience["source"].fillna("N/D").value_counts().reset_index()
        )
        source_counts.columns = ["Fonte", "Quantidade"]
        fig_src = px.pie(
            source_counts, names="Fonte", values="Quantidade",
            hole=0.4, color_discrete_sequence=px.colors.qualitative.Pastel,
        )
        fig_src.update_layout(height=350)
        st.plotly_chart(fig_src, width='stretch')
        st.download_button(
            "⬇️ CSV", source_counts.to_csv(index=False).encode("utf-8"),
            "feedback_por_fonte.csv", "text/csv", key="dl_fsource"
        )

    st.markdown("---")

    st.subheader("Volume de Feedbacks ao Longo do Tempo")
    df_p_time = df_patience.dropna(subset=["createdAt"]).copy()
    if not df_p_time.empty:
        df_p_time["mes"] = df_p_time["createdAt"].dt.to_period("M").astype(str)
        feedback_time = (
            df_p_time.groupby(["mes", "feedbackType"])
            .size().reset_index(name="Quantidade")
        )
        fig_time = px.bar(
            feedback_time, x="mes", y="Quantidade", color="feedbackType",
            labels={"mes": "Mês", "feedbackType": "Tipo"},
            barmode="stack",
        )
        fig_time.update_layout(height=350, xaxis_title="Mês", yaxis_title="Feedbacks")
        st.plotly_chart(fig_time, width='stretch')

    st.markdown("---")
    st.subheader("Feedbacks Recentes")
    tbl_feedback = df_patience[
        ["patientId", "feedbackType", "source", "sessionId", "createdAt"]
    ].rename(columns={
        "patientId": "Paciente", "feedbackType": "Tipo",
        "source": "Fonte", "sessionId": "Sessão", "createdAt": "Data"
    }).sort_values("Data", ascending=False).head(50)
    with st.expander("Ver últimos 50 feedbacks"):
        st.dataframe(tbl_feedback, width='stretch', hide_index=True)
        st.download_button(
            "⬇️ CSV", tbl_feedback.to_csv(index=False).encode("utf-8"),
            "feedbacks_recentes.csv", "text/csv", key="dl_freq"
        )

# ---------------------------------------------------------------------------
# Página 5 — Por Participante
# ---------------------------------------------------------------------------
elif page == "👤 Por Participante":
    st.title("Estatísticas por Participante")

    user_ids = sorted(df["user_id"].dropna().unique())
    selected_id = st.selectbox("Selecione o ID do participante", user_ids)

    df_user = df[df["user_id"] == selected_id]
    if df_user.empty:
        st.warning("Participante não encontrado.")
        st.stop()

    row = df_user.iloc[0]

    # --- Perfil ---
    st.markdown("---")
    st.subheader("Perfil")

    gender_label = {"F": "Feminino", "M": "Masculino"}.get(str(row.get("gender", "")), "Não informado")
    age_str = f"{int(row['age'])} anos" if pd.notna(row.get("age")) else "N/D"
    email_raw = str(row.get("email", "N/D"))
    if "@" in email_raw:
        local, domain = email_raw.split("@", 1)
        email_masked = local[:3] + "***@" + domain
    else:
        email_masked = email_raw

    p1, p2, p3, p4, p5 = st.columns(5)
    p1.metric("UBS", row.get("ubs_name", "N/D"))
    p2.metric("Cidade", row.get("ubs_city", "N/D"))
    p3.metric("Gênero", gender_label)
    p4.metric("Idade", age_str)
    p5.metric("E-mail", email_masked)

    # --- Scores de saúde mental ---
    st.markdown("---")
    st.subheader("Scores de Saúde Mental (Baseline)")

    phq = row.get("phq_score")
    gad = row.get("gad_score")
    phq_label = phq_severity(phq)
    gad_label = gad_severity(gad)

    sc1, sc2 = st.columns(2)

    with sc1:
        phq_val = float(phq) if phq is not None else 0
        fig_phq = go.Figure(go.Indicator(
            mode="gauge+number",
            value=phq_val,
            title={"text": f"PHQ-9 — {phq_label}"},
            gauge={
                "axis": {"range": [0, 27]},
                "bar": {"color": "#EF553B"},
                "steps": [
                    {"range": [0, 4], "color": "#d4edda"},
                    {"range": [4, 9], "color": "#fff3cd"},
                    {"range": [9, 14], "color": "#ffd8b1"},
                    {"range": [14, 19], "color": "#f8d7da"},
                    {"range": [19, 27], "color": "#c0392b"},
                ],
                "threshold": {"line": {"color": "black", "width": 3}, "value": phq_val},
            },
        ))
        fig_phq.update_layout(height=280)
        st.plotly_chart(fig_phq, width='stretch')
        st.markdown(
            f"<p style='text-align:center; color:{severity_color(phq_label)}; font-weight:bold'>"
            f"Depressão: {phq_label} (score {phq_val:.0f}/27)</p>",
            unsafe_allow_html=True,
        )

    with sc2:
        gad_val = float(gad) if gad is not None else 0
        fig_gad = go.Figure(go.Indicator(
            mode="gauge+number",
            value=gad_val,
            title={"text": f"GAD-7 — {gad_label}"},
            gauge={
                "axis": {"range": [0, 21]},
                "bar": {"color": "#636EFA"},
                "steps": [
                    {"range": [0, 4], "color": "#d4edda"},
                    {"range": [4, 9], "color": "#fff3cd"},
                    {"range": [9, 14], "color": "#f8d7da"},
                    {"range": [14, 21], "color": "#c0392b"},
                ],
                "threshold": {"line": {"color": "black", "width": 3}, "value": gad_val},
            },
        ))
        fig_gad.update_layout(height=280)
        st.plotly_chart(fig_gad, width='stretch')
        st.markdown(
            f"<p style='text-align:center; color:{severity_color(gad_label)}; font-weight:bold'>"
            f"Ansiedade: {gad_label} (score {gad_val:.0f}/21)</p>",
            unsafe_allow_html=True,
        )

    # --- Progresso das sessões ---
    st.markdown("---")
    st.subheader("Progresso das Sessões")

    sessions = (
        df_user.drop_duplicates(subset="sessionNumber")
        .sort_values("sessionNumber")[["sessionNumber", "isCompleted", "completedDate"]]
        .copy()
    )
    total_sess = len(sessions)
    done_sess = int(sessions["isCompleted"].sum())

    s1, s2, s3 = st.columns(3)
    s1.metric("Total de sessões", total_sess)
    s2.metric("Concluídas", done_sess)
    s3.metric("Taxa de conclusão", f"{done_sess/total_sess*100:.0f}%" if total_sess > 0 else "N/D")

    sessions["Status"] = sessions["isCompleted"].map(
        {True: "Concluída", False: "Não concluída", None: "N/D"}
    ).fillna("N/D")
    sessions = sessions.dropna(subset=["sessionNumber"])
    sessions["Sessão"] = "Sessão " + sessions["sessionNumber"].astype(int).astype(str)

    fig_sess = px.bar(
        sessions, x="Sessão", y=[1] * len(sessions),
        color="Status",
        color_discrete_map={"Concluída": "#2ecc71", "Não concluída": "#e74c3c", "N/D": "#bdc3c7"},
        labels={"y": ""}, height=220,
    )
    fig_sess.update_yaxes(visible=False)
    fig_sess.update_layout(showlegend=True, bargap=0.1)
    st.plotly_chart(fig_sess, width='stretch')

    with st.expander("Ver tabela de sessões"):
        tbl_sessions = sessions[["Sessão", "Status", "completedDate"]].rename(
            columns={"completedDate": "Data de conclusão"}
        )
        st.dataframe(tbl_sessions, width='stretch', hide_index=True)
        st.download_button(
            "⬇️ CSV", tbl_sessions.to_csv(index=False).encode("utf-8"),
            f"sessoes_{selected_id}.csv", "text/csv", key="dl_sessions"
        )

    # --- Jornadas do participante ---
    st.markdown("---")
    st.subheader("Jornadas")

    user_journeys = df_journeys[df_journeys["user_id"] == selected_id]
    if user_journeys.empty:
        st.info("Nenhuma jornada ativa para este participante.")
    else:
        j1, j2 = st.columns(2)
        j1.metric("Jornadas ativas", len(user_journeys))
        j2.metric(
            "Tipos",
            ", ".join(user_journeys["journey_type"].dropna().unique().tolist()) or "N/D"
        )
        tbl_j = user_journeys[
            ["journey_type", "lastSession", "lastAccessDate"]
        ].rename(columns={
            "journey_type": "Tipo", "lastSession": "Última Sessão",
            "lastAccessDate": "Último Acesso"
        })
        st.dataframe(tbl_j, width='stretch', hide_index=True)

    # --- Feedbacks do participante ---
    st.markdown("---")
    st.subheader("Feedbacks Recebidos (Patience)")

    user_feedback = df_patience[df_patience["patientId"] == selected_id]
    if user_feedback.empty:
        st.info("Nenhum feedback registrado para este participante.")
    else:
        fb1, fb2 = st.columns(2)
        fb1.metric("Total de feedbacks", len(user_feedback))
        fb2.metric(
            "Tipos",
            ", ".join(user_feedback["feedbackType"].dropna().unique().tolist()) or "N/D"
        )
        tbl_fb = user_feedback[
            ["feedbackType", "source", "sessionId", "createdAt"]
        ].rename(columns={
            "feedbackType": "Tipo", "source": "Fonte",
            "sessionId": "Sessão", "createdAt": "Data"
        }).sort_values("Data", ascending=False)
        with st.expander("Ver feedbacks"):
            st.dataframe(tbl_fb, width='stretch', hide_index=True)
            st.download_button(
                "⬇️ CSV", tbl_fb.to_csv(index=False).encode("utf-8"),
                f"feedback_{selected_id}.csv", "text/csv", key="dl_pfb"
            )

# ---------------------------------------------------------------------------
# Página 6 — Análise Descritiva
# ---------------------------------------------------------------------------
elif page == "📊 Análise Descritiva":
    st.title("Análise Descritiva — Baseline")
    st.caption(
        f"Total de participantes na análise: **{df_desc['user_id'].nunique()}** "
        f"| Dados extraídos do formulário de baseline"
    )
    st.markdown("---")

    tabs = st.tabs([
        "1. Sociodemográfico",
        "2. Variáveis Clínicas",
        "3. Suporte Social",
        "4. Histórico de Tratamento",
        "5. Uso de Álcool",
        "6. Uso de Tabaco",
        "7. Ativação Comportamental",
        "8. Qualidade de Vida",
    ])

    # ── Tab 1: Características sociodemográficas ────────────────────────────
    with tabs[0]:
        st.subheader("Tabela 1 — Caracterização da Amostra")

        # Sexo
        st.markdown("**Sexo (sexgr)**")
        gender_map = {"F": "Feminino", "M": "Masculino"}
        sexgr = df_desc["sexgr"].map(lambda x: gender_map.get(str(x), x) if pd.notna(x) else None)
        _freq_table(sexgr, "Sexo")

        st.markdown("---")

        # Idade
        st.markdown("**Idade (PS2)**")
        _stats_table(df_desc["age"], "Idade (anos)")

        st.markdown("---")

        # Raça/cor
        st.markdown("**Raça/cor (race/race6)**")
        _freq_table(df_desc["race"], "Raça/cor")

        st.markdown("---")

        # Escolaridade
        st.markdown("**Escolaridade (hl4)**")
        _freq_table(df_desc["hl4"], "Escolaridade")

        st.markdown("---")

        # Situação conjugal
        st.markdown("**Situação conjugal (pmarry)**")
        _freq_table(df_desc["pmarry"], "Situação conjugal")

        st.markdown("---")

        # Atividade principal
        st.markdown("**Atividade principal (se1)**")
        _freq_table(df_desc["se1"], "Atividade principal")

        st.markdown("---")

        # Ocupação detalhada
        st.markdown("**Ocupação detalhada (se17)**")
        _freq_table(df_desc["se17"], "Ocupação detalhada")

        st.markdown("---")

        # Renda familiar
        st.markdown("**Renda familiar (income1)**")
        _freq_table(df_desc["income1"], "Renda familiar")

        st.markdown("---")

        # UBS
        st.markdown("**UBS (ip3)**")
        _freq_table(df_desc["ubs_name"], "UBS")

    # ── Tab 2: Variáveis clínicas ────────────────────────────────────────────
    with tabs[1]:
        st.subheader("Tabela 2 — Sintomas de Saúde Mental")

        st.markdown("**Depressão — PHQ (phq)**")
        _stats_table(df_desc["phq"], "PHQ")

        st.markdown("---")

        st.markdown("**Ansiedade — GAD (gad)**")
        _stats_table(df_desc["gad"], "GAD")

        st.markdown("---")

        st.markdown("**Insônia — IGI (igi)**")
        _stats_table(df_desc["igi"], "IGI")

        st.markdown("---")

        st.markdown("**S-RAP item — SC4**")
        _freq_table(df_desc["SC4"], "SC4")

        st.markdown("---")

        st.markdown("**S-RAP total (srapt)**")
        _stats_table(df_desc["srapt"], "S-RAP total")

        st.markdown("---")

        st.markdown("**S-RAP nível (level)**")
        _freq_table(df_desc["level"], "S-RAP nível")

        st.markdown("---")

        st.subheader("Distribuição por Gravidade")

        grav_col1, grav_col2, grav_col3 = st.columns(3)

        with grav_col1:
            st.markdown("**PHQ — Distribuição por gravidade**")
            phq_grav = df_desc["phq"].apply(_phq_gravity)
            grav_counts_phq = phq_grav[phq_grav != "N/D"].value_counts().reset_index()
            grav_counts_phq.columns = ["Gravidade", "n"]
            if not grav_counts_phq.empty:
                grav_counts_phq["%"] = (grav_counts_phq["n"] / grav_counts_phq["n"].sum() * 100).round(1)
                grav_counts_phq["n (%)"] = grav_counts_phq["n"].astype(str) + " (" + grav_counts_phq["%"].astype(str) + "%)"
                st.dataframe(grav_counts_phq[["Gravidade", "n (%)"]], hide_index=True)
                fig_phq_g = px.pie(grav_counts_phq, names="Gravidade", values="n",
                                   color_discrete_sequence=px.colors.sequential.RdBu)
                fig_phq_g.update_layout(height=280)
                st.plotly_chart(fig_phq_g, width='stretch')
            else:
                st.info("Dados PHQ não disponíveis.")

        with grav_col2:
            st.markdown("**GAD — Distribuição por gravidade**")
            gad_grav = df_desc["gad"].apply(_gad_gravity)
            grav_counts_gad = gad_grav[gad_grav != "N/D"].value_counts().reset_index()
            grav_counts_gad.columns = ["Gravidade", "n"]
            if not grav_counts_gad.empty:
                grav_counts_gad["%"] = (grav_counts_gad["n"] / grav_counts_gad["n"].sum() * 100).round(1)
                grav_counts_gad["n (%)"] = grav_counts_gad["n"].astype(str) + " (" + grav_counts_gad["%"].astype(str) + "%)"
                st.dataframe(grav_counts_gad[["Gravidade", "n (%)"]], hide_index=True)
                fig_gad_g = px.pie(grav_counts_gad, names="Gravidade", values="n",
                                   color_discrete_sequence=px.colors.sequential.Blues)
                fig_gad_g.update_layout(height=280)
                st.plotly_chart(fig_gad_g, width='stretch')
            else:
                st.info("Dados GAD não disponíveis.")

        with grav_col3:
            st.markdown("**IGI — Distribuição por gravidade**")
            igi_grav = df_desc["igi"].apply(_igi_gravity)
            grav_counts_igi = igi_grav[igi_grav != "N/D"].value_counts().reset_index()
            grav_counts_igi.columns = ["Gravidade", "n"]
            if not grav_counts_igi.empty:
                grav_counts_igi["%"] = (grav_counts_igi["n"] / grav_counts_igi["n"].sum() * 100).round(1)
                grav_counts_igi["n (%)"] = grav_counts_igi["n"].astype(str) + " (" + grav_counts_igi["%"].astype(str) + "%)"
                st.dataframe(grav_counts_igi[["Gravidade", "n (%)"]], hide_index=True)
                fig_igi_g = px.pie(grav_counts_igi, names="Gravidade", values="n",
                                   color_discrete_sequence=px.colors.sequential.Greens)
                fig_igi_g.update_layout(height=280)
                st.plotly_chart(fig_igi_g, width='stretch')
            else:
                st.info("Dados IGI não disponíveis.")

    # ── Tab 3: Suporte social ────────────────────────────────────────────────
    with tabs[2]:
        st.subheader("Tabela 3 — Suporte Social")

        ss1_raw = df_desc["ss1"]
        ss1_valid = ss1_raw.dropna()

        if ss1_valid.empty:
            st.info("Dados de suporte social (ss1) não disponíveis.")
        else:
            ss1_mapped = ss1_raw.map(
                lambda x: "Sim" if str(x).strip() in ("1", "1.0", "True", "true")
                else ("Não" if str(x).strip() in ("0", "0.0", "False", "false") else None)
            )

            n_total = ss1_mapped.notna().sum()
            n_sim   = (ss1_mapped == "Sim").sum()
            n_nao   = (ss1_mapped == "Não").sum()

            m1, m2, m3 = st.columns(3)
            m1.metric("Total respondentes", int(n_total))
            m2.metric("Com suporte social", f"{n_sim} ({n_sim/n_total*100:.1f}%)" if n_total else "N/D")
            m3.metric("Sem suporte social", f"{n_nao} ({n_nao/n_total*100:.1f}%)" if n_total else "N/D")

            st.markdown("---")
            _freq_table(ss1_mapped, "Suporte social (ss1)")

    # ── Tab 4: Histórico de tratamento em saúde mental ───────────────────────
    with tabs[3]:
        st.subheader("Tabela 4 — Uso de Serviços de Saúde Mental")

        st.markdown("**Tratamento psicológico/psiquiátrico vida (ms1)**")
        _freq_table(df_desc["ms1"], "Tratamento vida (ms1)")

        st.markdown("---")

        st.markdown("**Tratamento atual (psychtr)**")
        _freq_table(df_desc["psychtr"], "Tratamento atual")

        st.markdown("---")

        st.markdown("**Uso de medicação (ms4)**")
        _freq_table(df_desc["ms4"], "Uso de medicação")

        st.markdown("---")

        st.markdown("**Hospitalização vida (psychhosp)**")
        row_hosp = _stats_row(df_desc["psychhosp"], "Hospitalização vida")
        if row_hosp:
            st.dataframe(pd.DataFrame([row_hosp]), hide_index=True)
        _freq_table(df_desc["psychhosp"], "Hospitalização vida (n %)")

        st.markdown("---")

        st.markdown("**Emergência psiquiátrica — últimos 3 meses (erpsych)**")
        _freq_table(df_desc["erpsych"], "Emergência psiquiátrica")

        st.markdown("---")

        st.markdown("**Ambulatório psiquiátrico / CAPS — últimos 3 meses (caps)**")
        _freq_table(df_desc["caps"], "CAPS")

        st.markdown("---")

        st.markdown("**Serviço álcool e drogas / CAPSad — últimos 3 meses (adpsych)**")
        _freq_table(df_desc["adpsych"], "CAPSad")

        st.markdown("---")

        st.markdown("**Hospitalização em saúde mental — últimos 3 meses (conspsych)**")
        _freq_table(df_desc["conspsych"], "Hospitalização SM (3 meses)")

    # ── Tab 5: Uso de álcool ─────────────────────────────────────────────────
    with tabs[4]:
        st.subheader("Tabela 5 — Uso de Álcool (AUDIT-C)")

        st.markdown("**Frequência de consumo (audit1)**")
        _freq_table(df_desc["audit1"], "Frequência (audit1)")

        st.markdown("---")

        st.markdown("**Doses por ocasião (audit2)**")
        _freq_table(df_desc["audit2"], "Doses (audit2)")

        st.markdown("---")

        st.markdown("**Consumo em binge (audit3)**")
        _freq_table(df_desc["audit3"], "Binge (audit3)")

    # ── Tab 6: Uso de tabaco ─────────────────────────────────────────────────
    with tabs[5]:
        st.subheader("Tabela 6 — Tabagismo")

        st.markdown("**Fuma atualmente / Cigarros por dia (tabacco3)**")
        _freq_table(df_desc["tabacco3"], "Tabagismo (tabacco3)")
        st.markdown("---")
        _stats_table(pd.to_numeric(df_desc["tabacco3"], errors="coerce"), "Cigarros/dia (tabacco3)")

    # ── Tab 7: Ativação comportamental ──────────────────────────────────────
    with tabs[6]:
        st.subheader("Tabela 7 — Behavioral Activation (ca1–ca9)")

        ca_rows = []
        for i in range(1, 10):
            row = _stats_row(df_desc[f"ca{i}"], f"ca{i}")
            if row:
                ca_rows.append(row)

        if ca_rows:
            st.dataframe(pd.DataFrame(ca_rows), hide_index=True)
            st.markdown("---")
            # Box plot dos itens disponíveis
            ca_cols = [f"ca{i}" for i in range(1, 10) if f"ca{i}" in df_desc.columns]
            ca_melt = df_desc[ca_cols].apply(pd.to_numeric, errors="coerce").melt(
                var_name="Item", value_name="Score"
            ).dropna()
            if not ca_melt.empty:
                fig_ca = px.box(
                    ca_melt, x="Item", y="Score",
                    color="Item",
                    color_discrete_sequence=px.colors.qualitative.Pastel,
                    labels={"Score": "Score", "Item": "Item CA"},
                )
                fig_ca.update_layout(showlegend=False, height=380)
                st.plotly_chart(fig_ca, width='stretch')
        else:
            st.info("Dados de ativação comportamental (ca1–ca9) não disponíveis.")

    # ── Tab 8: Qualidade de vida ─────────────────────────────────────────────
    with tabs[7]:
        st.subheader("Tabela 8 — Qualidade de Vida (EQ-5D)")

        eq5d_vars = {
            "eqdmob":    "Mobilidade",
            "eqdcare":   "Autocuidado",
            "eqdactivi": "Atividades habituais",
            "eqdpain":   "Dor",
            "eqddep":    "Ansiedade/depressão",
        }

        for col, label in eq5d_vars.items():
            st.markdown(f"**{label} ({col})**")
            _freq_table(df_desc[col], label)
            st.markdown("---")

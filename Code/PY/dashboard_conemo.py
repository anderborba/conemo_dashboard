import os
import json
from datetime import datetime

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# ---------------------------------------------------------------------------
# Configuração da página
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="CONEMO Dashboard",
    page_icon="🏥",
    layout="wide",
)

PARQUET_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "../../Data/PARQUET/conemo_dados_consolidados_raw_04_03_2026.parquet",
)

# ---------------------------------------------------------------------------
# P0.1 — Timestamp da última atualização do cache (arquivo Parquet local)
#
# O dashboard opera em modo cache/local. A função abaixo obtém a data e hora
# da última modificação do arquivo Parquet que serve de base para os dados
# exibidos. Esse timestamp é exibido na sidebar para indicar a atualidade
# das informações visualizadas.
# ---------------------------------------------------------------------------
def get_cache_timestamp() -> str:
    """Retorna o timestamp de última modificação do arquivo Parquet de cache.

    Se o arquivo não existir ou ocorrer erro na leitura, retorna uma mensagem
    informativa em vez de propagar a exceção.
    """
    try:
        mtime = os.path.getmtime(PARQUET_PATH)
        return datetime.fromtimestamp(mtime).strftime("%d/%m/%Y %H:%M:%S")
    except FileNotFoundError:
        return "Arquivo de cache não encontrado"
    except Exception:
        return "Não disponível"


# ---------------------------------------------------------------------------
# Carregamento e pré-processamento dos dados
# ---------------------------------------------------------------------------
@st.cache_data
def load_data() -> pd.DataFrame:
    df = pd.read_parquet(PARQUET_PATH)

    # Normaliza tipos
    df["sessionNumber"] = pd.to_numeric(df["sessionNumber"], errors="coerce")
    df["isCompleted"] = df["isCompleted"].map(
        {"true": True, "false": False, True: True, False: False}
    )

    # Extrai campos do JSON do usuário
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

            return pd.Series(
                {
                    "ubs_name": org.get("name", "N/A"),
                    "ubs_city": org.get("city", "N/A"),
                    "phq_score": phq,
                    "gad_score": gad,
                    "gender": data.get("gender", "N/A"),
                    "age": age,
                    "user_name": data.get("name", "N/A"),
                }
            )
        except Exception:
            return pd.Series(
                {
                    "ubs_name": "N/A",
                    "ubs_city": "N/A",
                    "phq_score": None,
                    "gad_score": None,
                    "gender": "N/A",
                    "age": None,
                    "user_name": "N/A",
                }
            )

    extracted = df["json_data_user"].apply(parse_user)
    df = pd.concat([df, extracted], axis=1)

    # Normaliza caixa em ubs_name (maiúsculas — padrão estabelecido em P0)
    df["ubs_name"] = df["ubs_name"].str.upper().str.strip()

    # ---------------------------------------------------------------------------
    # P1.2 — Normalização de caixa em ubs_city
    #
    # Regra adotada: strip → Title Case.
    # Unifica variantes equivalentes por diferença de caixa ou espaços excedentes,
    # como "são paulo", "SÃO PAULO" e "São Paulo", que passam a ser representadas
    # uniformemente como "São Paulo".
    # ubs_name permanece em maiúsculas (padrão P0), preservando a coerência entre
    # os dois filtros: cidade pré-filtra UBS, UBS permanece como pivô operacional.
    # ---------------------------------------------------------------------------
    df["ubs_city"] = df["ubs_city"].str.strip().str.title()

    # ---------------------------------------------------------------------------
    # P1.1 — Remoção de cidades inválidas ou vazias
    #
    # Remove linhas em que ubs_city é:
    #   - NaN ou None (dado ausente na fonte)
    #   - string vazia após strip (whitespace-only na fonte)
    #   - placeholder de dado ausente: "N/A"
    #   - dado de teste: "Fake City"
    #
    # Esses valores apareciam como opção em branco ou inválida no multiselect.
    # A condição é explícita e auditável; não mascara outros problemas de dados:
    # se uma cidade legítima ficasse fora do dashboard, seria identificável aqui.
    # ---------------------------------------------------------------------------
    _CIDADES_INVALIDAS = {"Fake City", "N/A", ""}
    df = df[
        df["ubs_city"].notna()
        & (~df["ubs_city"].isin(_CIDADES_INVALIDAS))
    ]

    return df


df = load_data()

# ---------------------------------------------------------------------------
# Sidebar — navegação, timestamp e botão de atualização
#
# P0.2: a navegação principal é orientada a UBS/gestão. A visão individual
#       por participante não compõe a navegação principal do MVP visual
#       (decisão vinculante — Plano-implementacao-dashboard.md §8, item 8).
#       Sua lógica permanece no código e é acessível via seção própria
#       dentro da página de UBS.
# P0.3: o botão 🔄 é mantido visível na sidebar. A operação está
#       temporariamente condicionada à credencial Google/BigQuery; no estado
#       atual o dashboard opera em modo cache/local. A presença do botão
#       não é bloqueadora da execução (decisão vinculante de coordenação).
# ---------------------------------------------------------------------------
st.sidebar.title("🏥 CONEMO")
st.sidebar.markdown("---")

# P0.1 — Timestamp da última atualização do cache
st.sidebar.markdown("**📅 Dados atualizados em:**")
st.sidebar.info(get_cache_timestamp())
st.sidebar.markdown("*Modo: cache local*")

st.sidebar.markdown("---")

# P0.3 — Botão de atualização (operação condicionada à credencial BigQuery;
#         mantido visível conforme decisão vinculante da coordenação)
if st.sidebar.button("🔄 Atualizar dados"):
    st.cache_data.clear()
    st.rerun()

st.sidebar.markdown("---")

# P0.2 — Navegação principal orientada a UBS/gestão
page = st.sidebar.radio(
    "Navegação",
    ["📊 Estatísticas por UBS"],
)

# ---------------------------------------------------------------------------
# P2 — Label discreto de versão MVP
#
# Exibido no rodapé da sidebar como caption (texto pequeno e mudo do
# Streamlit). Não interfere na navegação, no timestamp nem no botão 🔄.
# Indica ao usuário que o dashboard está em versão MVP operacional.
# ---------------------------------------------------------------------------
st.sidebar.markdown("---")
st.sidebar.caption("Dashboard CONEMO — Versão MVP")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def phq_severity(score):
    if score is None:
        return "N/D"
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
    if score <= 4:
        return "Mínima"
    if score <= 9:
        return "Leve"
    if score <= 14:
        return "Moderada"
    return "Grave"


def severity_color(label):
    colors = {
        "Sem depressão": "green",
        "Mínima": "green",
        "Leve": "orange",
        "Moderada": "orange",
        "Moderadamente grave": "red",
        "Grave": "red",
        "N/D": "gray",
    }
    return colors.get(label, "gray")


# ---------------------------------------------------------------------------
# Página 1 — Estatísticas por UBS
# ---------------------------------------------------------------------------
if page == "📊 Estatísticas por UBS":
    st.title("Estatísticas por UBS")

    # --- Filtros ---
    col_f1, col_f2 = st.columns(2)
    all_cities = sorted(df["ubs_city"].dropna().unique())
    sel_cities = col_f1.multiselect("Cidade", all_cities, default=all_cities)

    df_city = df[df["ubs_city"].isin(sel_cities)] if sel_cities else df
    all_ubs = sorted(df_city["ubs_name"].dropna().unique())
    sel_ubs = col_f2.multiselect("UBS", all_ubs, default=all_ubs)

    dff = df_city[df_city["ubs_name"].isin(sel_ubs)] if sel_ubs else df_city

    # DataFrame de participantes únicos (um por user_id)
    df_users = dff.drop_duplicates(subset="user_id")

    # --- Métricas ---
    total_users = df_users["user_id"].nunique()
    mean_phq = df_users["phq_score"].mean()
    mean_gad = df_users["gad_score"].mean()
    sessions_total = len(dff)
    sessions_done = dff["isCompleted"].sum()
    completion_rate = (sessions_done / sessions_total * 100) if sessions_total > 0 else 0

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Participantes", total_users)
    m2.metric("Média PHQ-9 (Depressão)", f"{mean_phq:.1f}" if pd.notna(mean_phq) else "N/D")
    m3.metric("Média GAD-7 (Ansiedade)", f"{mean_gad:.1f}" if pd.notna(mean_gad) else "N/D")
    m4.metric("Conclusão de Sessões", f"{completion_rate:.1f}%")

    st.markdown("---")

    # --- Gráficos: linha 1 ---
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Participantes por UBS")
        ubs_count = (
            df_users["ubs_name"].value_counts().reset_index()
        )
        ubs_count.columns = ["UBS", "Participantes"]
        fig = px.bar(
            ubs_count.sort_values("Participantes"),
            x="Participantes",
            y="UBS",
            orientation="h",
            color="Participantes",
            color_continuous_scale="Blues",
        )
        fig.update_layout(showlegend=False, coloraxis_showscale=False, height=400)
        st.plotly_chart(fig, width='stretch')

    with col2:
        st.subheader("Média PHQ-9 e GAD-7 por UBS")
        scores_ubs = (
            df_users.groupby("ubs_name")[["phq_score", "gad_score"]]
            .mean()
            .reset_index()
            .rename(columns={"ubs_name": "UBS", "phq_score": "PHQ-9", "gad_score": "GAD-7"})
        )
        scores_melt = scores_ubs.melt(id_vars="UBS", var_name="Escala", value_name="Média")
        fig2 = px.bar(
            scores_melt,
            x="Média",
            y="UBS",
            color="Escala",
            orientation="h",
            barmode="group",
            color_discrete_map={"PHQ-9": "#EF553B", "GAD-7": "#636EFA"},
        )
        fig2.update_layout(height=400)
        st.plotly_chart(fig2, width='stretch')

    # --- Gráficos: linha 2 ---
    col3, col4, col5 = st.columns(3)

    with col3:
        st.subheader("Taxa de Conclusão por UBS")
        comp_ubs = (
            dff.groupby("ubs_name")["isCompleted"]
            .apply(lambda x: x.mean() * 100 if x.count() > 0 else 0.0)
            .reset_index(name="Taxa (%)")
        )
        comp_ubs = comp_ubs.rename(columns={"ubs_name": "UBS"})
        fig3 = px.bar(
            comp_ubs.sort_values("Taxa (%)"),
            x="Taxa (%)",
            y="UBS",
            orientation="h",
            color="Taxa (%)",
            color_continuous_scale="Greens",
        )
        fig3.update_layout(showlegend=False, coloraxis_showscale=False, height=350)
        st.plotly_chart(fig3, width='stretch')

    with col4:
        st.subheader("Distribuição de Gênero")
        gender_map = {"F": "Feminino", "M": "Masculino"}
        gender_counts = (
            df_users["gender"]
            .map(gender_map)
            .fillna("Não informado")
            .value_counts()
            .reset_index()
        )
        gender_counts.columns = ["Gênero", "Contagem"]
        fig4 = px.pie(
            gender_counts,
            names="Gênero",
            values="Contagem",
            hole=0.4,
            color_discrete_sequence=px.colors.qualitative.Set2,
        )
        fig4.update_layout(height=350)
        st.plotly_chart(fig4, width='stretch')

    with col5:
        st.subheader("Distribuição de Idades")
        ages = df_users["age"].dropna()
        fig5 = px.histogram(
            ages,
            nbins=20,
            labels={"value": "Idade", "count": "Frequência"},
            color_discrete_sequence=["#AB63FA"],
        )
        fig5.update_layout(showlegend=False, height=350, xaxis_title="Idade", yaxis_title="Frequência")
        st.plotly_chart(fig5, width='stretch')

    # --- Tabela resumo ---
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
        .reset_index()
        .rename(columns={"ubs_name": "UBS"})
    )
    resumo["Conclusão (%)"] = resumo["UBS"].map(comp_lookup).round(1)
    resumo["PHQ-9 Média"] = resumo["PHQ9_media"].round(1)
    resumo["GAD-7 Média"] = resumo["GAD7_media"].round(1)
    resumo = resumo[["UBS", "Participantes", "PHQ-9 Média", "GAD-7 Média", "Conclusão (%)"]].sort_values(
        "Participantes", ascending=False
    )
    st.dataframe(resumo, width='stretch', hide_index=True)


# ---------------------------------------------------------------------------
# Visão individual por participante
#
# P0.2: esta visão não compõe a navegação principal do MVP visual.
# A lógica analítica é preservada integralmente e permanece acessível
# via expander na página de UBS/gestão.
# ---------------------------------------------------------------------------
st.markdown("---")
with st.expander("👤 Consulta individual por participante (visão auxiliar)"):
    if True:
        st.subheader("Estatísticas por Participante")

        # Selectbox de user_id
        user_ids = sorted(df["user_id"].dropna().unique())
        selected_id = st.selectbox("Selecione o ID do participante", user_ids)

        df_user = df[df["user_id"] == selected_id]
        if df_user.empty:
            st.warning("Participante não encontrado.")
            st.stop()

        # Pega a primeira linha para dados de perfil (únicos por usuário)
        row = df_user.iloc[0]

        # --- Perfil ---
        st.markdown("---")
        st.subheader("Perfil")

        gender_label = {"F": "Feminino", "M": "Masculino"}.get(str(row.get("gender", "")), "Não informado")
        age_str = f"{int(row['age'])} anos" if pd.notna(row.get("age")) else "N/D"
        email_raw = str(row.get("email", "N/D"))
        # Mascara o email: mostra primeiros 3 chars + *** + domínio
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
            fig_phq = go.Figure(
                go.Indicator(
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
                )
            )
            fig_phq.update_layout(height=280)
            st.plotly_chart(fig_phq, width='stretch')
            st.markdown(
                f"<p style='text-align:center; color:{severity_color(phq_label)}; font-weight:bold'>"
                f"Depressão: {phq_label} (score {phq_val:.0f}/27)</p>",
                unsafe_allow_html=True,
            )

        with sc2:
            gad_val = float(gad) if gad is not None else 0
            fig_gad = go.Figure(
                go.Indicator(
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
                )
            )
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
        sessions["Sessão"] = "Sessão " + sessions["sessionNumber"].astype(int).astype(str)

        fig_sess = px.bar(
            sessions,
            x="Sessão",
            y=[1] * len(sessions),
            color="Status",
            color_discrete_map={"Concluída": "#2ecc71", "Não concluída": "#e74c3c", "N/D": "#bdc3c7"},
            labels={"y": ""},
            height=220,
        )
        fig_sess.update_yaxes(visible=False)
        fig_sess.update_layout(showlegend=True, bargap=0.1)
        st.plotly_chart(fig_sess, width='stretch')

        # Tabela de sessões
        with st.expander("Ver tabela de sessões"):
            st.dataframe(
                sessions[["Sessão", "Status", "completedDate"]].rename(
                    columns={"completedDate": "Data de conclusão"}
                ),
                width='stretch',
                hide_index=True,
            )

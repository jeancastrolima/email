import streamlit as st
import mysql.connector
import pandas as pd
import altair as alt
import time
import re
import requests
from mysql.connector import Error

# --- 1. Configurações Iniciais da Página ---
st.set_page_config(
    page_title="Central de Contatos Pro",
    page_icon="🚀",
    layout="wide"
)

# --- 2. Funções de Back-end ---

@st.cache_data(ttl=300)
def carregar_dados():
    """Busca todos os e-mails e os prepara para análise."""
    try:
        conn = mysql.connector.connect(**st.secrets.database)
        query = "SELECT id, email, data_insercao FROM emails"
        df = pd.read_sql(query, conn)
        conn.close()
        df.columns = ['ID', 'Email', 'Adicionado Em']
        df['Adicionado Em'] = pd.to_datetime(df['Adicionado Em'])
        df['Domínio'] = df['Email'].str.split('@').str[1].str.lower()
        return df
    except Exception as e:
        st.error(f"❌ Erro ao carregar dados do banco: {e}")
        return pd.DataFrame()

def enviar_email_resend(api_key, remetente, destinatario, assunto, corpo_html):
    """Envia um único e-mail usando a API do Resend."""
    url = "https://api.resend.com/emails"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"from": remetente, "to": [destinatario], "subject": assunto, "html": corpo_html}
    try:
        response = requests.post(url, headers=headers, json=payload)
        return (True, "Sucesso") if response.status_code in (200, 201) else (False, f"{response.status_code}")
    except Exception as e:
        return False, str(e)

def check_credentials():
    """Verifica as credenciais do usuário."""
    try:
        user_info = next((user for user in st.secrets.credentials.usernames if user["email"] == st.session_state["username"]), None)
        if user_info and user_info["password"] == st.session_state["password"]:
            st.session_state["authenticated"] = True
            st.session_state["user_name"] = user_info["name"]
        else:
            st.session_state["authenticated"] = False
    except:
        st.session_state["authenticated"] = False

# --- 3. Interface da Aplicação Principal ---
def main_app():
    # Estilo CSS customizado
    st.markdown("""
    <style>
        .metric-card { background-color: #262730; border-radius: 10px; padding: 20px; margin: 10px 0; border: 1px solid #4E4E4E; }
        .metric-card h3 { color: #BDBDBD; font-size: 16px; margin-bottom: 5px; }
        .metric-card p { color: #FAFAFA; font-size: 32px; font-weight: 700; margin: 0; }
    </style>
    """, unsafe_allow_html=True)
    
    df_principal = carregar_dados()

    # Barra Lateral
    st.sidebar.title(f"👋 Olá, {st.session_state.get('user_name', 'Usuário')}!")
    if st.sidebar.button("Sair (Logout)"):
        st.session_state["authenticated"] = False
        st.rerun()
    
    st.sidebar.markdown("---")
    st.sidebar.header("Filtros do Dashboard")
    dominios_unicos = sorted(df_principal['Domínio'].unique()) if not df_principal.empty else []
    dominios_selecionados = st.sidebar.multiselect("Filtrar por Domínio:", options=dominios_unicos)
    termo_busca = st.sidebar.text_input("Buscar por e-mail:")
    
    st.title("🚀 Central de Contatos")
    tab_dashboard, tab_sender = st.tabs(["📊 Dashboard de Análise", "✉️ Disparador de Campanhas"])
 
    # --- ABA 1: DASHBOARD ---
    with tab_dashboard:
        df_filtrado = df_principal.copy()
        if dominios_selecionados: 
            df_filtrado = df_filtrado[df_filtrado['Domínio'].isin(dominios_selecionados)]
        if termo_busca: 
            df_filtrado = df_filtrado[df_filtrado['Email'].str.contains(termo_busca, case=False, na=False)]
        
        if df_principal.empty:
            st.warning("A base de dados está vazia.")
        else:
            # Métricas
            col1, col2, col3 = st.columns(3)
            col1.markdown(f'<div class="metric-card"><h3>Total de Contatos</h3><p>{len(df_filtrado):,}</p></div>', unsafe_allow_html=True)
            col2.markdown(f'<div class="metric-card"><h3>Domínios Únicos</h3><p>{df_filtrado["Domínio"].nunique():,}</p></div>', unsafe_allow_html=True)
            ult_data = df_filtrado['Adicionado Em'].max().strftime('%d/%m/%Y') if not df_filtrado.empty else "N/A"
            col3.markdown(f'<div class="metric-card"><h3>Última Atualização</h3><p>{ult_data}</p></div>', unsafe_allow_html=True)
            
            # Gráficos
            col_g1, col_g2 = st.columns(2)
            with col_g1:
                top_dominios = df_filtrado['Domínio'].value_counts().nlargest(10).reset_index()
                top_dominios.columns = ['Domínio', 'Quantidade']
                st.altair_chart(alt.Chart(top_dominios).mark_bar().encode(
                    x='Quantidade:Q', y=alt.Y('Domínio:N', sort='-x'), tooltip=['Domínio', 'Quantidade']
                ).properties(title="Top 10 Domínios", height=300), use_container_width=True)
            
            with col_g2:
                # Evolução temporal simplificada
                df_filtrado['Mês'] = df_filtrado['Adicionado Em'].dt.to_period('M').astype(str)
                evolucao = df_filtrado.groupby('Mês').size().reset_index(name='Qtd')
                st.altair_chart(alt.Chart(evolucao).mark_line(point=True).encode(
                    x='Mês:O', y='Qtd:Q', tooltip=['Mês', 'Qtd']
                ).properties(title="Contatos por Mês", height=300), use_container_width=True)

            # Tabela de Dados
            st.subheader("🗂️ Lista de Contatos")
            st.dataframe(df_filtrado[['ID', 'Email', 'Domínio', 'Adicionado Em']], use_container_width=True, hide_index=True)

    # --- ABA 2: DISPARADOR (Lógica Refatorada) ---
    with tab_sender:
        st.header("✉️ Envio B2B (Filtro Automático)")
        
        # Filtro de Lixo Digital (Movido para dentro da aba para não pesar o Dashboard)
        lixo_digital = ['gmail.com', 'hotmail.com', 'outlook.com', 'yahoo.com', 'uol.com.br', 'terra.com.br', 'gov.br', 'mil.br', 'edu.br']
        regex_exclusao = "|".join(lixo_digital)
        df_b2b = df_principal[~df_principal['Email'].str.contains(regex_exclusao, case=False, na=False)].copy()

        st.subheader("1. Seleção de Empresas")
        df_empresas = df_b2b.groupby('Domínio').size().reset_index(name='Contatos')
        df_empresas.insert(0, 'Selecionar', False)

        df_selecao = st.data_editor(
            df_empresas,
            hide_index=True,
            use_container_width=True,
            column_config={"Selecionar": st.column_config.CheckboxColumn("Enviar?"), "Domínio": "Empresa", "Contatos": "Qtd"},
            key="editor_envio"
        )

        dominios_eleitos = df_selecao[df_selecao['Selecionar'] == True]['Domínio'].tolist()
        lista_final = df_b2b[df_b2b['Domínio'].isin(dominios_eleitos)]['Email'].tolist()

        if dominios_eleitos:
            st.success(f"🎯 {len(dominios_eleitos)} empresas selecionadas | {len(lista_final)} e-mails prontos.")

        st.markdown("---")
        st.subheader("2. Compor Mensagem")
        col_ed, col_prev = st.columns(2)
        with col_ed:
            assunto = st.text_input("Assunto do E-mail:")
            corpo_html = st.text_area("HTML do E-mail:", height=300, value="<html><body><p>Olá!</p></body></html>")
        with col_prev:
            st.markdown("🔍 **Pré-visualização**")
            st.components.v1.html(corpo_html, height=330, scrolling=True)

        if st.button("🚀 INICIAR DISPARO EM MASSA", type="primary", use_container_width=True):
            if not assunto or not lista_final:
                st.error("Verifique o assunto e se há empresas selecionadas.")
            else:
                progress_bar = st.progress(0)
                status_txt = st.empty()
                sucessos, falhas = 0, 0
                
                api_key = st.secrets.resend.api_key
                remetente = st.secrets.resend.verified_sender

                for i, email in enumerate(lista_final):
                    ok, erro = enviar_email_resend(api_key, remetente, email, assunto, corpo_html)
                    if ok: sucessos += 1
                    else: falhas += 1
                    
                    percent = (i + 1) / len(lista_final)
                    progress_bar.progress(percent)
                    status_txt.info(f"Enviando {i+1}/{len(lista_final)} | ✅ {sucessos} | ❌ {falhas}")
                    time.sleep(0.5) # Evitar Rate Limit
                
                st.success(f"Concluído! Sucessos: {sucessos}, Falhas: {falhas}")

# --- 4. Gerenciamento de Login ---
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

if st.session_state["authenticated"]:
    main_app()
else:
    st.markdown("<h1 style='text-align: center;'>🚀 Central de Contatos</h1>", unsafe_allow_html=True)
    _, col_login, _ = st.columns([1, 1.5, 1])
    with col_login:
        with st.container(border=True):
            st.subheader("Login de Acesso")
            st.text_input("E-mail", key="username")
            st.text_input("Senha", type="password", key="password")
            if st.button("Entrar", use_container_width=True, type="primary"):
                check_credentials()
                if st.session_state["authenticated"]:
                    st.rerun()
                else:
                    st.error("Credenciais inválidas.")
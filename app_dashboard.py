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
        if response.status_code in (200, 201):
            return True, "Enviado com sucesso"
        else:
            return False, f"Erro {response.status_code}: {response.text}"
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
    # Estilo CSS para métricas (idêntico ao original)
    st.markdown("""
    <style>
        .metric-card { background-color: #262730; border-radius: 10px; padding: 20px; margin: 10px 0; box-shadow: 0 4px 8px rgba(0,0,0,0.2); border: 1px solid #4E4E4E; }
        .metric-card h3 { color: #BDBDBD; font-size: 18px; font-weight: 400; margin: 0; }
        .metric-card p { color: #FAFAFA; font-size: 36px; font-weight: 700; margin: 0; }
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
    termo_busca = st.sidebar.text_input("Buscar por texto no e-mail:")
    
    st.title("🚀 Central de Contatos")
    tab_dashboard, tab_sender = st.tabs(["📊 Dashboard", "✉️ Disparador de E-mails"])
 
    # --- ABA: DASHBOARD ---
    with tab_dashboard:
        st.header("Análise Interativa da Base de Contatos")
        df_filtrado = df_principal.copy()
        if dominios_selecionados: df_filtrado = df_filtrado[df_filtrado['Domínio'].isin(dominios_selecionados)]
        if termo_busca: df_filtrado = df_filtrado[df_filtrado['Email'].str.contains(termo_busca, case=False, na=False)]
        
        if df_principal.empty:
            st.warning("Nenhum dado encontrado no banco de dados.")
        else:
            # Métricas em cards
            total_emails = len(df_filtrado)
            total_dominios = df_filtrado['Domínio'].nunique()
            data_mais_recente = df_filtrado['Adicionado Em'].max().strftime('%d/%m/%Y') if not df_filtrado.empty else "N/A"
            
            col1, col2, col3 = st.columns(3)
            col1.markdown(f'<div class="metric-card"><h3>E-mails na Seleção</h3><p>{total_emails:,}</p></div>', unsafe_allow_html=True)
            col2.markdown(f'<div class="metric-card"><h3>Domínios na Seleção</h3><p>{total_dominios:,}</p></div>', unsafe_allow_html=True)
            col3.markdown(f'<div class="metric-card"><h3>Última Inserção</h3><p>{data_mais_recente}</p></div>', unsafe_allow_html=True)
            
            st.markdown("---")
            
            # Gráficos (RESTAURADOS)
            col_graf1, col_graf2 = st.columns(2)
            
            with col_graf1:
                st.subheader("📈 Top 10 Domínios")
                if not df_filtrado.empty:
                    top_dominios = df_filtrado['Domínio'].value_counts().nlargest(10).reset_index()
                    top_dominios.columns = ['Domínio', 'Quantidade']
                    chart_dominios = alt.Chart(top_dominios).mark_bar(cornerRadiusTopLeft=5, cornerRadiusTopRight=5).encode(
                        x=alt.X('Quantidade:Q', title='Nº de E-mails'),
                        y=alt.Y('Domínio:N', title='Domínio', sort='-x'),
                        tooltip=['Domínio', 'Quantidade']
                    ).properties(height=350)
                    st.altair_chart(chart_dominios, use_container_width=True)
            
            with col_graf2:
                st.subheader("📅 E-mails por Mês")
                if not df_filtrado.empty:
                    emails_por_dia = df_filtrado.set_index('Adicionado Em').resample('M').size().reset_index(name='Quantidade')
                    emails_por_dia.columns = ['Mês', 'Quantidade']
                    chart_tempo = alt.Chart(emails_por_dia).mark_line(point=True, strokeWidth=3).encode(
                        x=alt.X('Mês:T', title='Data'),
                        y=alt.Y('Quantidade:Q', title='Nº Adicionados'),
                        tooltip=['Mês', 'Quantidade']
                    ).properties(height=350)
                    st.altair_chart(chart_tempo, use_container_width=True)

            st.markdown("---")
            st.subheader("🗂️ Navegar pelos Contatos")
            st.dataframe(df_filtrado[['ID', 'Email', 'Domínio', 'Adicionado Em']], use_container_width=True, hide_index=True)

    # --- ABA: DISPARADOR ---
    with tab_sender:
        st.header("✉️ Nova Campanha B2B")
        
        # Filtro de e-mails corporativos (Limpeza automática)
        lixo = ['gmail.com', 'hotmail.com', 'outlook.com', 'yahoo.com', 'uol.com.br', 'terra.com.br', 'gov.br', 'mil.br']
        df_b2b = df_principal[~df_principal['Email'].str.contains("|".join(lixo), case=False, na=False)].copy()

        st.subheader("1. Seleção de Empresas")
        df_empresas = df_b2b.groupby('Domínio').size().reset_index(name='Qtd Contatos')
        df_empresas.insert(0, 'Selecionar', False)

        df_selecao = st.data_editor(
            df_empresas,
            hide_index=True,
            use_container_width=True,
            column_config={"Selecionar": st.column_config.CheckboxColumn("Enviar?"), "Domínio": "Empresa"},
            key="editor_dominios_envio"
        )

        dominios_eleitos = df_selecao[df_selecao['Selecionar'] == True]['Domínio'].tolist()
        lista_final_envio = df_b2b[df_b2b['Domínio'].isin(dominios_eleitos)]['Email'].tolist()

        if dominios_eleitos:
            st.success(f"🎯 **{len(lista_final_envio):,}** e-mails selecionados.")

        st.markdown("---")
        st.subheader("2. Mensagem e Disparo")
        col_ed, col_prev = st.columns(2)
        with col_ed:
            assunto = st.text_input("Assunto do E-mail:", key="send_sub")
            corpo_html = st.text_area("Corpo (HTML):", height=300, value="<html><body><h3>Olá!</h3><p>Sua proposta aqui.</p></body></html>")
        with col_prev:
            st.markdown("##### **👁️ Pré-visualização**")
            st.components.v1.html(corpo_html, height=350, scrolling=True)

        if st.button("🚀 INICIAR ENVIO EM MASSA", type="primary", use_container_width=True):
            if not assunto or not lista_final_envio:
                st.error("⚠️ Preencha o assunto e selecione as empresas na tabela.")
            else:
                st.markdown("---")
                barra_progresso = st.progress(0)
                status_texto = st.empty()
                log_container = st.expander("📄 Log de Envios Detalhado", expanded=True)
                
                sucessos, falhas = 0, 0
                total = len(lista_final_envio)
                api_key = st.secrets.resend.api_key
                remetente = st.secrets.resend.verified_sender

                for i, email in enumerate(lista_final_envio):
                    sucesso, msg = enviar_email_resend(api_key, remetente, email, assunto, corpo_html)
                    
                    if sucesso:
                        sucessos += 1
                        log_container.write(f"✅ **{email}**: {msg}")
                    else:
                        falhas += 1
                        log_container.error(f"❌ **{email}**: {msg}")
                    
                    percentual = (i + 1) / total
                    barra_progresso.progress(percentual)
                    status_texto.info(f"Processando: {i+1} de {total} | Sucessos: {sucessos} | Falhas: {falhas}")
                    time.sleep(0.5)

                st.success(f"🏁 Processo concluído! Sucessos: {sucessos} | Falhas: {falhas}")

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
            st.subheader("Acesso restrito")
            st.text_input("Usuário", key="username")
            st.text_input("Senha", type="password", key="password")
            if st.button("Entrar", use_container_width=True, type="primary"):
                check_credentials()
                if st.session_state["authenticated"]: st.rerun()
                else: st.error("Usuário ou senha inválida.")
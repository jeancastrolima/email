import streamlit as st
import mysql.connector
import pandas as pd
import altair as alt
import time
import re
import requests
from mysql.connector import Error

# --- 1. Configurações Iniciais ---
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

# --- 3. Interface da Aplicação ---
def main_app():
    # Estilo CSS para métricas
    st.markdown("""
    <style>
        .metric-card { background-color: #262730; border-radius: 10px; padding: 20px; border: 1px solid #4E4E4E; margin-bottom: 10px; }
        .metric-card h3 { color: #BDBDBD; font-size: 16px; margin: 0; }
        .metric-card p { color: #FAFAFA; font-size: 30px; font-weight: 700; margin: 0; }
    </style>
    """, unsafe_allow_html=True)
    
    df_principal = carregar_dados()

    # Sidebar
    st.sidebar.title(f"👋 Olá, {st.session_state.get('user_name', 'Usuário')}!")
    if st.sidebar.button("Sair (Logout)"):
        st.session_state["authenticated"] = False
        st.rerun()
    
    st.sidebar.markdown("---")
    st.sidebar.header("Filtros de Visualização")
    dominios_unicos = sorted(df_principal['Domínio'].unique()) if not df_principal.empty else []
    dom_sel = st.sidebar.multiselect("Filtrar por Domínio:", options=dominios_unicos)
    busca = st.sidebar.text_input("Buscar e-mail:")
    
    st.title("🚀 Central de Contatos")
    tab_dash, tab_send = st.tabs(["📊 Dashboard", "✉️ Disparador de Campanhas"])
 
    # --- DASHBOARD ---
    with tab_dash:
        df_f = df_principal.copy()
        if dom_sel: df_f = df_f[df_f['Domínio'].isin(dom_sel)]
        if busca: df_f = df_f[df_f['Email'].str.contains(busca, case=False, na=False)]
        
        c1, c2, c3 = st.columns(3)
        c1.markdown(f'<div class="metric-card"><h3>Contatos</h3><p>{len(df_f):,}</p></div>', unsafe_allow_html=True)
        c2.markdown(f'<div class="metric-card"><h3>Domínios</h3><p>{df_f["Domínio"].nunique():,}</p></div>', unsafe_allow_html=True)
        ult = df_f['Adicionado Em'].max().strftime('%d/%m/%Y') if not df_f.empty else "N/A"
        c3.markdown(f'<div class="metric-card"><h3>Última Inserção</h3><p>{ult}</p></div>', unsafe_allow_html=True)
        
        st.subheader("🗂️ Navegação")
        st.dataframe(df_f[['ID', 'Email', 'Domínio', 'Adicionado Em']], use_container_width=True, hide_index=True)

    # --- DISPARADOR ---
    with tab_send:
        st.header("✉️ Nova Campanha B2B")
        
        # Filtro de e-mails corporativos
        lixo = ['gmail.com', 'hotmail.com', 'outlook.com', 'yahoo.com', 'uol.com.br', 'terra.com.br', 'gov.br']
        df_b2b = df_principal[~df_principal['Email'].str.contains("|".join(lixo), case=False, na=False)].copy()

        st.subheader("1. Seleção de Empresas")
        df_emp = df_b2b.groupby('Domínio').size().reset_index(name='Contatos')
        df_emp.insert(0, 'Selecionar', False)

        df_sel_user = st.data_editor(
            df_emp,
            hide_index=True,
            use_container_width=True,
            column_config={"Selecionar": st.column_config.CheckboxColumn("Enviar?"), "Domínio": "Empresa"},
            key="editor_campanha"
        )

        eleitos = df_sel_user[df_sel_user['Selecionar'] == True]['Domínio'].tolist()
        lista_envio = df_b2b[df_b2b['Domínio'].isin(eleitos)]['Email'].tolist()

        if eleitos:
            st.success(f"🎯 **{len(lista_envio)}** e-mails selecionados de **{len(eleitos)}** empresas.")

        st.markdown("---")
        st.subheader("2. Mensagem e Disparo")
        col_a, col_b = st.columns(2)
        with col_a:
            assunto = st.text_input("Assunto:", placeholder="Ex: Proposta de Parceria")
            corpo = st.text_area("Conteúdo HTML:", height=250, value="<html><body><p>Olá!</p></body></html>")
        with col_b:
            st.markdown("👁️ **Pré-visualização**")
            st.components.v1.html(corpo, height=280, scrolling=True)

        if st.button("🚀 INICIAR ENVIOS", type="primary", use_container_width=True):
            if not assunto or not lista_envio:
                st.warning("Preencha o assunto e selecione as empresas na tabela acima.")
            else:
                st.markdown("---")
                # --- ÁREA DE LOGS (RESTRIURADA) ---
                progresso = st.progress(0)
                status_msg = st.empty()
                
                # O expander onde os logs detalhados aparecerão
                log_expander = st.expander("📄 Log de Envios Detalhado", expanded=True)
                
                sucessos, falhas = 0, 0
                total = len(lista_envio)
                
                api_key = st.secrets.resend.api_key
                remetente = st.secrets.resend.verified_sender

                for i, email in enumerate(lista_envio):
                    ok, retorno = enviar_email_resend(api_key, remetente, email, assunto, corpo)
                    
                    if ok:
                        sucessos += 1
                        log_expander.write(f"✅ **{email}**: {retorno}")
                    else:
                        falhas += 1
                        log_expander.error(f"❌ **{email}**: {retorno}")
                    
                    # Atualiza progresso e status em tempo real
                    progresso.progress((i + 1) / total)
                    status_msg.info(f"Processando: {i+1}/{total} | Sucessos: {sucessos} | Falhas: {falhas}")
                    
                    time.sleep(0.4) # Delay para respeitar limites da API
                
                st.success(f"🏁 Finalizado! Enviados: {sucessos} | Falhas: {falhas}")

# --- 4. Login ---
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

if st.session_state["authenticated"]:
    main_app()
else:
    st.markdown("<h1 style='text-align: center;'>🚀 Central de Contatos</h1>", unsafe_allow_html=True)
    _, col_l, _ = st.columns([1, 1.5, 1])
    with col_l:
        with st.container(border=True):
            st.text_input("E-mail", key="username")
            st.text_input("Senha", type="password", key="password")
            if st.button("Entrar", use_container_width=True, type="primary"):
                check_credentials()
                if st.session_state["authenticated"]: st.rerun()
                else: st.error("Login inválido.")
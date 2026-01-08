import streamlit as st
import mysql.connector
import pandas as pd
import altair as alt
import time
import os
import re
import mailbox
from mysql.connector import Error
import requests
import streamlit.components.v1 as components
from streamlit_tinymce import tinymce

# --- 1. Configurações Iniciais da Página ---
st.set_page_config(
    page_title="AlexExpert - Central de Contatos",
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
        if not df.empty:
            df.columns = ['ID', 'Email', 'Adicionado Em']
            df['Adicionado Em'] = pd.to_datetime(df['Adicionado Em'])
            df['Domínio'] = df['Email'].str.split('@').str[1].str.lower()
        return df
    except Exception as e:
        st.error(f"❌ Erro ao carregar dados: {e}")
        return pd.DataFrame()

def enviar_email_resend(api_key, remetente, destinatario, assunto, corpo_html):
    """Envia um único e-mail usando a API do Resend via Requests."""
    url = "https://api.resend.com/emails"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "from": remetente,
        "to": [destinatario],
        "subject": assunto,
        "html": corpo_html
    }
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

def inserir_lote_db(lote_emails):
    """Insere e-mails no banco de dados."""
    if not lote_emails: return 0
    try:
        conn = mysql.connector.connect(**st.secrets.database)
        cursor = conn.cursor()
        query = "INSERT IGNORE INTO emails (email) VALUES (%s)"
        dados = [(email,) for email in lote_emails]
        cursor.executemany(query, dados)
        conn.commit()
        count = cursor.rowcount
        conn.close()
        return count
    except Exception as e:
        st.error(f"Erro ao inserir no banco: {e}")
        return 0

def processar_mbox_em_streaming(caminho_arquivo):
    """Processa arquivo MBOX e extrai e-mails."""
    try:
        mbox = mailbox.mbox(caminho_arquivo, create=False)
        processadas = 0
        novos = 0
        lote = set()
        status_text = st.empty()
        
        for msg in mbox:
            processadas += 1
            for campo in ("From", "To", "Cc"):
                val = str(msg.get(campo, ""))
                emails = re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", val)
                for e in emails:
                    lote.add(e.lower())
            
            if len(lote) >= 1000:
                novos += inserir_lote_db(list(lote))
                lote.clear()
                status_text.info(f"Processando MBOX... {processadas} mensagens lidas.")
        
        if lote:
            novos += inserir_lote_db(list(lote))
        return processadas, novos
    except Exception as e:
        st.error(f"Erro no MBOX: {e}")
        return 0, 0

# --- 3. Interface da Aplicação Principal ---

def main_app():
    df_principal = carregar_dados()

    # Barra Lateral
    st.sidebar.title(f"👋 Olá, {st.session_state['user_name']}!")
    if st.sidebar.button("Sair (Logout)"):
        st.session_state["authenticated"] = False
        st.rerun()
    
    st.sidebar.markdown("---")
    dominios = sorted(df_principal['Domínio'].unique()) if not df_principal.empty else []
    dominios_sel = st.sidebar.multiselect("Filtrar por Domínio:", options=dominios)
    busca = st.sidebar.text_input("Buscar por e-mail:")

    st.title("🚀 Central de Contatos AlexExpert")
    tab_dash, tab_send, tab_ext = st.tabs(["📊 Dashboard", "✉️ Disparador Profissional", "📂 Extrator MBOX"])

    # --- ABA DASHBOARD ---
    with tab_dash:
        df_f = df_principal.copy()
        if dominios_sel: df_f = df_f[df_f['Domínio'].isin(dominios_sel)]
        if busca: df_f = df_f[df_f['Email'].str.contains(busca, case=False)]

        col1, col2 = st.columns(2)
        col1.metric("Total de Contatos", f"{len(df_f):,}")
        col2.metric("Domínios Únicos", f"{df_f['Domínio'].nunique() if not df_f.empty else 0}")
        
        if not df_f.empty:
            st.subheader("Análise de Base")
            top_10 = df_f['Domínio'].value_counts().nlargest(10).reset_index()
            chart = alt.Chart(top_10).mark_bar().encode(x='count', y=alt.Y('Domínio', sort='-x'))
            st.altair_chart(chart, use_container_width=True)
            st.dataframe(df_f.head(100), use_container_width=True)

    # --- ABA DISPARADOR (TINYMCE) ---
    with tab_send:
        st.header("✉️ Envio de Campanha")
        email_list = df_f['Email'].tolist() if not df_f.empty else []
        st.info(f"Público-alvo: **{len(email_list):,}** e-mails.")

        assunto = st.text_input("Assunto do E-mail:", placeholder="Digite o assunto...")
        
        st.markdown("**Editor de Conteúdo Profissional** (Redimensione imagens e edite HTML no botão `<>`)")
        conteudo_html = tinymce(
            key="editor_unax",
            height=500,
            content="<p>Olá! Digite sua mensagem aqui ou cole seu HTML.</p>"
        )

        with st.expander("👁️ Pré-visualização"):
            components.html(conteudo_html, height=400, scrolling=True)

        if st.button("🚀 INICIAR DISPARO EM MASSA", type="primary"):
            if not assunto or not conteudo_html:
                st.error("Preencha o assunto e o corpo do e-mail.")
            else:
                barra = st.progress(0)
                status_txt = st.empty()
                log = st.expander("Log de Envios", expanded=True)
                
                sucessos, falhas = 0, 0
                api_key = st.secrets.resend.api_key
                remetente = st.secrets.resend.verified_sender

                for i, email in enumerate(email_list):
                    # Chamada da API
                    ok, msg = enviar_email_resend(api_key, remetente, email, assunto, conteudo_html)
                    
                    if ok:
                        sucessos += 1
                        log.success(f"✅ {email}: Enviado")
                    else:
                        falhas += 1
                        log.error(f"❌ {email}: {msg}")
                    
                    # Atualiza progresso
                    progresso = (i + 1) / len(email_list)
                    barra.progress(progresso)
                    status_txt.info(f"Enviando {i+1}/{len(email_list)} | ✅ {sucessos} | ❌ {falhas}")
                    
                    # --- CORREÇÃO DO ERRO 429 ---
                    # Aguarda 0.6 segundos entre envios para respeitar o limite de 2 req/seg do Resend
                    time.sleep(0.6) 
                
                st.success(f"🏁 Finalizado! {sucessos} enviados com sucesso.")

    # --- ABA EXTRATOR ---
    with tab_ext:
        st.header("📂 Importação de MBOX")
        caminho = st.text_input("Caminho do arquivo .mbox no servidor:")
        if st.button("Executar Extração"):
            if os.path.exists(caminho):
                m, e = processar_mbox_em_streaming(caminho)
                st.success(f"Processado: {m} mensagens. Novos e-mails: {e}")
                st.cache_data.clear()
            else:
                st.error("Arquivo não encontrado.")

# --- 4. Login ---
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

if st.session_state["authenticated"]:
    main_app()
else:
    st.markdown("<h1 style='text-align: center;'>🚀 Login AlexExpert</h1>", unsafe_allow_html=True)
    _, login_col, _ = st.columns([1, 1.2, 1])
    with login_col:
        with st.container(border=True):
            u = st.text_input("Usuário (E-mail)")
            p = st.text_input("Senha", type="password")
            if st.button("Entrar", use_container_width=True, type="primary"):
                st.session_state["username"] = u
                st.session_state["password"] = p
                check_credentials()
                if st.session_state["authenticated"]: st.rerun()
                else: st.error("Acesso negado.")
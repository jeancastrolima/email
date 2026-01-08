import streamlit as st
import mysql.connector
import pandas as pd
import altair as alt
import time
import os
import re
import mailbox
from collections import Counter
from mysql.connector import Error
import requests
import streamlit.components.v1 as components
from streamlit_quill import st_quill


# --- 1. Configurações Iniciais da Página ---
st.set_page_config(
    page_title="Central de Contatos Completa",
    page_icon="🚀",
    layout="wide"
)

# --- 2. Funções de Back-end (todas as funcionalidades) ---

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
        st.error(f"❌ Erro ao carregar dados: {e}")
        return pd.DataFrame()

def enviar_email_resend(api_key, remetente, destinatario, assunto, corpo_html):
    """Envia um único e-mail usando a API do Resend."""
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
            return False, f"{response.status_code} - {response.text}"

    except Exception as e:
        return False, str(e)

def check_credentials():
    """Verifica as credenciais do usuário contra o arquivo secrets.toml."""
    try:
        user_info = next((user for user in st.secrets.credentials.usernames if user["email"] == st.session_state["username"]), None)
        if user_info and user_info["password"] == st.session_state["password"]:
            st.session_state["authenticated"] = True
            st.session_state["user_name"] = user_info["name"]
        else:
            st.session_state["authenticated"] = False
    except (AttributeError, KeyError):
        st.session_state["authenticated"] = False

def eh_email_provavelmente_real(email):
    """Filtro heurístico para validar e-mails."""
    try:
        local_part, domain_part = email.split('@')
    except ValueError: return False
    if '+' in local_part: return False
    DOMINIOS_BLOQUEADOS = {"amazonses.com", "sendgrid.net", "sparkpostmail.com", "mailgun.org", "mktomail.com", "mandrillapp.com", "tracksale.com.br", "zendesk.com"}
    if any(domain_part.endswith(d) for d in DOMINIOS_BLOQUEADOS): return False
    if re.search(r'[a-f0-9]{10,}', local_part): return False
    palavras_sistema = ["noreply", "mailer-daemon", "donotreply", "bounce", "no-reply", "support", "reply-", "contato"]
    if any(local_part.startswith(p) for p in palavras_sistema): return False
    if local_part.count('-') > 3 or local_part.count('.') > 3 or local_part.count('_') > 2: return False
    if len(local_part) > 40 or len(local_part) < 3: return False
    letras = ''.join(filter(str.isalpha, local_part))
    if len(letras) > 5:
        vogais = "aeiouy"
        num_vogais = sum(1 for char in letras if char in vogais)
        if (num_vogais / len(letras)) < 0.20: return False
    return True

def extrair_emails_de_cabecalho(cabecalho):
    if not cabecalho: return []
    texto_limpo = str(cabecalho).replace("\n", " ").replace("\r", " ")
    return re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", texto_limpo)

def inserir_lote_db(conn, lote_emails):
    if not conn or not lote_emails: return 0
    cursor = conn.cursor()
    query = "INSERT IGNORE INTO emails (email) VALUES (%s)"
    dados_para_inserir = [(email,) for email in lote_emails]
    try:
        cursor.executemany(query, dados_para_inserir)
        conn.commit()
        return cursor.rowcount
    except Error as e:
        st.error(f"Erro ao inserir lote no banco: {e}")
        return 0
    finally:
        cursor.close()

def processar_mbox_em_streaming(caminho_arquivo):
    try:
        conn = mysql.connector.connect(**st.secrets.database)
    except Error as e:
        st.error(f"Não foi possível conectar ao banco de dados: {e}")
        return 0, 0
    try:
        mbox = mailbox.mbox(caminho_arquivo, create=False)
    except Exception as e:
        st.error(f"Erro crítico ao tentar abrir o arquivo MBOX: {e}")
        return 0, 0
    
    TAMANHO_LOTE = 5000
    lote_para_db = set()
    mensagens_processadas = 0
    total_emails_novos = 0
    campos_alvo = ("From", "To", "Cc", "Bcc", "Reply-To", "Return-Path")
    status_text = st.empty()
    start_time = time.time()

    for msg in mbox:
        mensagens_processadas += 1
        for campo in campos_alvo:
            cabecalho = msg.get(campo)
            for email in extrair_emails_de_cabecalho(cabecalho):
                if eh_email_provavelmente_real(email.lower()):
                    lote_para_db.add(email.lower())
        
        if mensagens_processadas % TAMANHO_LOTE == 0:
            novos_inseridos = inserir_lote_db(conn, list(lote_para_db))
            total_emails_novos += novos_inseridos
            lote_para_db.clear()
            elapsed_time = time.time() - start_time
            if elapsed_time > 0:
                msgs_por_segundo = mensagens_processadas / elapsed_time
                status_text.info(f"Processando... | Mensagens: {mensagens_processadas:,} | Novos e-mails: {total_emails_novos:,} | Velocidade: {msgs_por_segundo:.2f} msg/s")

    if lote_para_db:
        novos_inseridos = inserir_lote_db(conn, list(lote_para_db))
        total_emails_novos += novos_inseridos
    
    conn.close()
    status_text.success("**Processo Concluído!**")
    return mensagens_processadas, total_emails_novos

# --- 3. Interface da Aplicação Principal (Pós-Login) ---
def main_app():
    # Estilo CSS
    st.markdown("""
    <style>
        .metric-card { background-color: #262730; border-radius: 10px; padding: 20px; margin: 10px 0; box-shadow: 0 4px 8px rgba(0,0,0,0.2); border: 1px solid #4E4E4E; }
        .metric-card h3 { color: #BDBDBD; font-size: 18px; font-weight: 400; }
        .metric-card p { color: #FAFAFA; font-size: 36px; font-weight: 700; }
    </style>
    """, unsafe_allow_html=True)
    
    df_principal = carregar_dados()

    # Barra Lateral
    st.sidebar.title(f"👋 Olá, {st.session_state['user_name']}!")
    if st.sidebar.button("Sair (Logout)"):
        st.session_state["authenticated"] = False
        st.rerun()
    st.sidebar.markdown("---")
    st.sidebar.info(f"**Remetente Configurado:**\n`{st.secrets.resend.verified_sender}`")
    st.sidebar.markdown("---")
    st.sidebar.header("Filtros do Dashboard")
    dominios_unicos = df_principal['Domínio'].unique() if 'Domínio' in df_principal else []
    dominios_selecionados = st.sidebar.multiselect("Filtrar por Domínio:", options=sorted(dominios_unicos))
    termo_busca = st.sidebar.text_input("Buscar por texto no e-mail:")
    
    # Conteúdo Principal com Abas
    st.title("🚀 Central de Contatos")
    tab_dashboard, tab_sender, tab_extractor = st.tabs(["📊 Dashboard", "✉️ Disparador de E-mails", "📂 Extrator de MBOX"])
    
    with tab_dashboard:
        st.header("Análise Interativa da Base de Contatos")
        df_filtrado = df_principal.copy()
        if dominios_selecionados: df_filtrado = df_filtrado[df_filtrado['Domínio'].isin(dominios_selecionados)]
        if termo_busca: df_filtrado = df_filtrado[df_filtrado['Email'].str.contains(termo_busca, case=False, na=False)]
        
        if df_principal.empty:
            st.warning("Nenhum dado encontrado no banco de dados.")
        else:
            total_emails = df_filtrado['ID'].count()
            total_dominios_filtrado = df_filtrado['Domínio'].nunique()
            data_mais_recente = df_filtrado['Adicionado Em'].max().strftime('%d/%m/%Y') if not df_filtrado.empty else "N/A"
            col1, col2, col3 = st.columns(3)
            col1.markdown(f'<div class="metric-card"><h3>E-mails na Seleção</h3><p>{total_emails:,}</p></div>', unsafe_allow_html=True)
            col2.markdown(f'<div class="metric-card"><h3>Domínios na Seleção</h3><p>{total_dominios_filtrado:,}</p></div>', unsafe_allow_html=True)
            col3.markdown(f'<div class="metric-card"><h3>Última Atualização</h3><p>{data_mais_recente}</p></div>', unsafe_allow_html=True)
            
            st.markdown("---")
            col_graf1, col_graf2 = st.columns(2)
            with col_graf1:
                st.subheader("📈 Top 10 Domínios")
                if not df_filtrado.empty:
                    top_dominios = df_filtrado['Domínio'].value_counts().nlargest(10).reset_index()
                    top_dominios.columns = ['Domínio', 'Quantidade']
                    chart_dominios = alt.Chart(top_dominios).mark_bar(cornerRadiusTopLeft=5, cornerRadiusTopRight=5).encode(x=alt.X('Quantidade:Q', title='Nº de E-mails'), y=alt.Y('Domínio:N', title='Domínio', sort='-x'), tooltip=['Domínio', 'Quantidade']).properties(height=350)
                    st.altair_chart(chart_dominios, use_container_width=True)
            with col_graf2:
                st.subheader("📅 E-mails Adicionados ao Longo do Tempo")
                if not df_filtrado.empty:
                    emails_por_dia = df_filtrado.set_index('Adicionado Em').resample('M').size().reset_index(name='Quantidade')
                    emails_por_dia.columns = ['Mês', 'Quantidade']
                    chart_tempo = alt.Chart(emails_por_dia).mark_line(point=True, strokeWidth=3).encode(x=alt.X('Mês:T', title='Data'), y=alt.Y('Quantidade:Q', title='Nº de E-mails Adicionados'), tooltip=['Mês', 'Quantidade']).properties(height=350)
                    st.altair_chart(chart_tempo, use_container_width=True)

            st.markdown("---")
            st.subheader("🗂️ Navegue por Todos os Contatos")
            # Lógica de paginação
            if 'page_num' not in st.session_state: st.session_state.page_num = 1
            items_per_page = 20
            total_items = len(df_filtrado)
            total_pages = max(1, (total_items // items_per_page) + (1 if total_items % items_per_page > 0 else 0))
            if st.session_state.page_num > total_pages: st.session_state.page_num = 1
            start_idx = (st.session_state.page_num - 1) * items_per_page
            end_idx = start_idx + items_per_page
            df_paginado = df_filtrado.iloc[start_idx:end_idx]
            col_pag1, col_pag2, col_pag3 = st.columns([1, 2, 1])
            if col_pag1.button("⬅️ Anterior", disabled=(st.session_state.page_num <= 1)):
                st.session_state.page_num -= 1
                st.rerun()
            col_pag2.write(f"Página **{st.session_state.page_num}** de **{total_pages}**")
            if col_pag3.button("Próxima ➡️", disabled=(st.session_state.page_num >= total_pages)):
                st.session_state.page_num += 1
                st.rerun()
            st.data_editor(df_paginado[['ID', 'Email', 'Domínio', 'Adicionado Em']], use_container_width=True, hide_index=True, disabled=True, column_config={"ID": st.column_config.NumberColumn("ID", width="small"), "Email": st.column_config.TextColumn("Email", width="large"), "Domínio": st.column_config.TextColumn("Domínio", width="medium"), "Adicionado Em": st.column_config.DatetimeColumn("Adicionado Em", format="D/M/YYYY HH:mm")})

    with tab_sender:
        st.header("Criar e Enviar Campanha via SendGrid")
        st.subheader("1. Selecione o Público-Alvo")
        dominios_para_envio = st.multiselect("Filtre por domínio (deixe em branco para selecionar TODOS):", options=dominios_unicos, key="sender_domains")
        if dominios_para_envio: lista_final_envio = df_principal[df_principal['Domínio'].isin(dominios_para_envio)]['Email'].tolist()
        else: lista_final_envio = df_principal['Email'].tolist()
        st.info(f"Público selecionado: **{len(lista_final_envio):,}** e-mails.")

        st.subheader("2. Componha sua Mensagem")
        col_editor, col_preview = st.columns(2)
        with col_editor:
            assunto = st.text_input("Assunto do E-mail:", key="sender_subject")
            corpo_html = st.text_area("Corpo do E-mail (HTML):", height=500, key="sender_body", value="<!DOCTYPE html><html>...</html>")
        with col_preview:
            st.markdown("##### **👁️ Pré-visualização**")
            components.html(corpo_html, height=550, scrolling=True)

        st.subheader("3. Iniciar o Disparo")
# No seu arquivo, localize este botão dentro da tab_sender
        if st.button("🚀 Iniciar Envio em Massa", type="primary"):
            if not assunto or not corpo_html:
                st.error("⚠️ Por favor, preencha o assunto e o corpo do e-mail.")
            elif len(lista_final_envio) == 0:
                st.warning("⚠️ A lista de destinatários está vazia.")
            else:
                st.markdown("---")
                st.subheader("⏳ Progresso do Envio")
                
                # Containers de status na interface
                barra_progresso = st.progress(0)
                status_texto = st.empty()
                log_container = st.expander("Ver Log de Envios", expanded=False)
                
                sucessos = 0
                falhas = 0
                total = len(lista_final_envio)
                
                # Chaves vindas do st.secrets
                api_key = st.secrets.resend.api_key
                remetente = st.secrets.resend.verified_sender


                for i, email in enumerate(lista_final_envio):
                    # Chama sua função existente
                    sucesso, msg = enviar_email_resend(
    api_key, remetente, email, assunto, corpo_html
)

                    
                    if sucesso:
                        sucessos += 1
                        log_container.write(f"✅ {email}: Enviado")
                    else:
                        falhas += 1
                        log_container.error(f"❌ {email}: Erro ({msg})")
                    
                    # Atualiza barra e texto
                    percentual = (i + 1) / total
                    barra_progresso.progress(percentual)
                    status_texto.info(f"Processando: {i+1} de {total} | ✅ Sucessos: {sucessos} | ❌ Falhas: {falhas}")
                    
                    # Pequena pausa para não travar a interface e respeitar limites de taxa
                    time.sleep(0.1) 

                st.success(f"✅ Processo concluído! {sucessos} e-mails enviados e {falhas} falhas.")

    with tab_extractor:
        st.header("📂 Extrair E-mails de Arquivos MBOX")
        mbox_path = st.text_input("Cole o caminho completo do arquivo MBOX:", key="extractor_path")
        if mbox_path:
            if not os.path.exists(mbox_path):
                st.error("❌ Caminho inválido.")
            else:
                st.success(f"✅ Arquivo encontrado: **{os.path.basename(mbox_path)}**")
                if st.button("▶️ Iniciar Extração", type="primary"):
                    with st.spinner("Processando..."):
                        mensagens, emails_salvos = processar_mbox_em_streaming(mbox_path)
                    st.subheader("🏁 Resumo da Extração")
                    col1, col2 = st.columns(2)
                    col1.metric("Mensagens Verificadas", f"{mensagens:,}")
                    col2.metric("Novos E-mails Salvos", f"{emails_salvos:,}")
                    st.cache_data.clear()
                    if st.button("🔄 Recarregar Aplicação"):
                        st.rerun()

# --- 4. Ponto de Entrada: Login ou App ---
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

if st.session_state.get("authenticated", False):
    main_app()
else:
    # Interface da Tela de Login
    st.markdown("<h1 style='text-align: center;'>🚀 Central de Contatos</h1>", unsafe_allow_html=True)
    _, col_login, _ = st.columns([1, 1.5, 1])
    with col_login:
        with st.container(border=True):
            st.image("https://i.imgur.com/2s42eL8.png") # Logotipo mais genérico
            st.subheader("Por favor, faça o login para continuar")
            st.text_input("Usuário (E-mail)", key="username")
            st.text_input("Senha", type="password", key="password")
            if st.button("Entrar", use_container_width=True, type="primary"):
                check_credentials()
                if st.session_state.get("authenticated", False):
                    st.rerun()
                else:
                    st.error("Usuário ou senha inválida.")
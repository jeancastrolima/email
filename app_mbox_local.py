import os
import re # Essencial para a nova regra
import mailbox
from collections import Counter
import streamlit as st
import mysql.connector
from mysql.connector import Error

st.set_page_config(page_title="📧 MBOX Analyzer Pro", page_icon="📧", layout="wide")
DB_CONFIG = {'host': 'localhost', 'user': 'root', 'password': '', 'database': 'gerenciador_emails'}

# <<< VERSÃO FINAL: Função de Validação de E-mails (v4 - Heurística Avançada)
def eh_email_provavelmente_real(email):
    try:
        local_part, domain_part = email.split('@')
    except ValueError:
        return False
    if '+' in local_part:
        return False
    DOMINIOS_BLOQUEADOS = {"amazonses.com", "sendgrid.net", "sparkpostmail.com", "mailgun.org", "mktomail.com", "mandrillapp.com", "tracksale.com.br", "zendesk.com"}
    if any(domain_part.endswith(d) for d in DOMINIOS_BLOQUEADOS):
        return False
    if re.search(r'[a-f0-9]{10,}', local_part):
        return False
    palavras_sistema = ["noreply", "mailer-daemon", "donotreply", "bounce", "no-reply", "support", "reply-", "contato"]
    if any(local_part.startswith(p) for p in palavras_sistema):
        return False
    if local_part.count('-') > 3 or local_part.count('.') > 3 or local_part.count('_') > 2:
        return False
    if len(local_part) > 40 or len(local_part) < 3:
        return False
    letras = ''.join(filter(str.isalpha, local_part))
    if len(letras) > 5:
        vogais = "aeiouy"
        num_vogais = sum(1 for char in letras if char in vogais)
        if (num_vogais / len(letras)) < 0.20:
            return False
    return True

# ... Todo o resto do seu código permanece exatamente o mesmo ...
def criar_conexao():
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        return conn
    except Error as e:
        st.error(f"Erro ao conectar ao MySQL: {e}")
        return None

def inserir_emails_db(conn, lista_emails):
    if not conn or not lista_emails: return 0
    cursor = conn.cursor()
    query = "INSERT IGNORE INTO emails (email) VALUES (%s)"
    tamanho_lote = 1000
    total_inserido = 0
    status = st.status(f"Iniciando inserção de {len(lista_emails):,} e-mails...", expanded=True)
    try:
        for i in range(0, len(lista_emails), tamanho_lote):
            lote = lista_emails[i:i + tamanho_lote]
            dados_para_inserir = [(email,) for email in lote]
            status.write(f"Inserindo lote {i//tamanho_lote + 1}: e-mails de {i+1} a {i+len(lote)}...")
            cursor.executemany(query, dados_para_inserir)
            conn.commit()
            total_inserido += cursor.rowcount
        status.update(label="Inserção concluída!", state="complete", expanded=False)
        return total_inserido
    except Error as e:
        status.update(label=f"Erro na inserção: {e}", state="error")
        return total_inserido
    finally:
        cursor.close()

def extrair_emails_de_cabecalho(cabecalho):
    if not cabecalho: return []
    texto_limpo = str(cabecalho).replace("\n", " ").replace("\r", " ")
    return re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", texto_limpo)

def processar_arquivo_mbox(caminho_arquivo):
    try:
        mbox = mailbox.mbox(caminho_arquivo, create=False)
    except Exception as e:
        st.error(f"Erro ao abrir o arquivo MBOX: {e}")
        return None, None, 0
    total_msgs = len(mbox)
    barra_progresso = st.progress(0, text=f"Analisando 0 de {total_msgs:,} mensagens...")
    emails_unicos = set()
    contador_dominios = Counter()
    campos_alvo = ("From", "To", "Cc", "Bcc", "Reply-To", "Return-Path")
    for i, msg in enumerate(mbox):
        try:
            for campo in campos_alvo:
                cabecalho = msg.get(campo)
                for email in extrair_emails_de_cabecalho(cabecalho):
                    email_lower = email.lower()
                    if eh_email_provavelmente_real(email_lower):
                        emails_unicos.add(email_lower)
                        try:
                            dominio = email_lower.split("@")[1]
                            contador_dominios[dominio] += 1
                        except IndexError: pass
        except Exception: continue
        if (i + 1) % 500 == 0 or (i + 1) == total_msgs:
            percentual = (i + 1) / total_msgs
            barra_progresso.progress(percentual, text=f"Analisando {i+1:,} de {total_msgs:,} mensagens...")
    barra_progresso.empty()
    return sorted(list(emails_unicos)), contador_dominios, total_msgs

# Interface Principal do Aplicativo
st.title("📧 MBOX Analyzer Pro - Filtro Avançado")
st.markdown("Extraia e-mails de arquivos `.mbox` com um filtro inteligente para focar em e-mails originais.")

mbox_path = st.text_input(
    "📂 Cole o caminho completo do arquivo MBOX",
    placeholder="Ex: C:\\Users\\SeuNome\\Downloads\\meus_emails.mbox"
)

if mbox_path:
    if not os.path.exists(mbox_path):
        st.error("❌ Caminho inválido ou arquivo não encontrado.")
    else:
        st.success(f"✅ Arquivo encontrado: **{os.path.basename(mbox_path)}**")
        with st.spinner("Analisando com filtro avançado..."):
            emails_unicos, dominios, total_msgs = processar_arquivo_mbox(mbox_path)
        if emails_unicos is not None:
            st.success(f"✨ Análise concluída! Encontrados **{len(emails_unicos):,}** e-mails originais e únicos.")
            col1, col2 = st.columns(2)
            col1.metric("E-mails Originais Únicos", f"{len(emails_unicos):,}")
            col2.metric("Total de Mensagens Verificadas", f"{total_msgs:,}")
            # ... resto da interface com as abas, que continua a mesma
            tab1, tab2, tab3 = st.tabs(["📊 Resumo de Domínios", "📋 Lista de E-mails", "💾 Salvar e Baixar"])
            with tab1:
                st.subheader("🏆 Top 20 Domínios com Mais Ocorrências")
                top_dominios = [{"Domínio": d, "Quantidade": q} for d, q in dominios.most_common(20)]
                st.dataframe(top_dominios, use_container_width=True, hide_index=True)
            with tab2:
                st.subheader("🔍 Filtrar e Visualizar E-mails")
                filtro_dominio = st.text_input("Filtrar por domínio (ex: gmail.com)").strip().lower()
                if filtro_dominio:
                    emails_filtrados = [e for e in emails_unicos if filtro_dominio in e]
                    st.write(f"Mostrando **{len(emails_filtrados):,}** e-mails para o filtro '**{filtro_dominio}**'")
                    st.dataframe(emails_filtrados, height=500, use_container_width=True, hide_index=True)
                else:
                    st.write(f"Mostrando todos os **{len(emails_unicos):,}** e-mails encontrados.")
                    st.dataframe(emails_unicos, height=500, use_container_width=True, hide_index=True)
            with tab3:
                st.subheader("💾 Salvar no Banco de Dados MySQL")
                if st.button("Inserir E-mails no Banco de Dados"):
                    conn = criar_conexao()
                    if conn:
                        novos_inseridos = inserir_emails_db(conn, emails_unicos)
                        st.success(f"Operação concluída! **{novos_inseridos}** novos e-mails foram adicionados ao banco.")
                        duplicados = len(emails_unicos) - novos_inseridos
                        if duplicados > 0:
                            st.info(f"**{duplicados}** e-mails já existiam no banco e foram ignorados.")
                        conn.close()
                st.divider()
                st.subheader("📥 Baixar como Arquivo de Texto")
                st.download_button(
                    label="Clique para baixar a lista de e-mails (.txt)",
                    data="\n".join(emails_unicos),
                    file_name=f"emails_originais_{os.path.basename(mbox_path)}.txt",
                    mime="text/plain"
                )
else:
    st.info("ℹ️ Insira o caminho para um arquivo .mbox para iniciar a análise.")
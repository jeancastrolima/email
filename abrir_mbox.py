import mailbox
from tkinter import Tk
from tkinter.filedialog import askopenfilename
from email.header import decode_header
from email.utils import getaddresses

# Oculta a janela principal do Tkinter
Tk().withdraw()

# Seleciona o arquivo .mbox
arquivo_mbox = askopenfilename(
    title="Selecione o arquivo .mbox",
    filetypes=[("Arquivos MBOX", "*.mbox")]
)

if arquivo_mbox:
    print(f"Abrindo: {arquivo_mbox}\n")
    mbox = mailbox.mbox(arquivo_mbox)

    emails_extraidos = set()  # Para evitar duplicados

    for mensagem in mbox:
        campos = ['from', 'to', 'cc', 'bcc']

        for campo in campos:
            valor = mensagem[campo]
            if valor:
                # Decodifica o header, ignorando codificações desconhecidas
                if not isinstance(valor, str):
                    partes = decode_header(valor)
                    decoded = []
                    for t in partes:
                        if isinstance(t[0], bytes):
                            try:
                                decoded.append(t[0].decode(t[1] or 'utf-8', errors='ignore'))
                            except:
                                decoded.append(t[0].decode('utf-8', errors='ignore'))
                        else:
                            decoded.append(t[0])
                    valor = ''.join(decoded)

                # Extrai os endereços de e-mail
                for nome, email in getaddresses([valor]):
                    if email:
                        emails_extraidos.add(email.strip())

    # Exibe os e-mails extraídos
    print("E-mails encontrados:")
    for email in sorted(emails_extraidos):
        print(email)

else:
    print("Nenhum arquivo selecionado.")

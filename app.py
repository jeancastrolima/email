# app.py
# VERSÃO CONSULTIVA: IA responde a dúvidas de aplicação e sempre oferece o especialista.

import os
from flask import Flask, request, session
from twilio.twiml.messaging_response import MessagingResponse
from dotenv import load_dotenv
import google.generativeai as genai

# --- CONFIGURAÇÃO INICIAL E BANCOS DE DADOS (Sem alterações) ---
load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY")

QUOTE_FORM_LINK = "https://b24-67kaln.bitrix24.site/crm_form_9zihg/"

PRODUCT_DATABASE = {
    'lanopro_50_eal': {'name': 'Revestimento LanoPro 50 EAL', 'type': 'Revestimento Protetor Premium', 'description': 'Máxima proteção contra corrosão em ambientes agressivos.', 'benefits': ['Proteção de longo prazo', 'Ideal para ambientes marítimos']},
    'lanopro_15_eal': {'name': 'Revestimento LanoPro 15 EAL', 'type': 'Lubrificante de Película Fina', 'description': 'Película semi-seca com excelente penetração e proteção anticorrosiva.', 'benefits': ['Excelente penetração', 'Não atrai sujeira']},
    'alfa_x': {'name': 'Alfa-X', 'type': 'Nano Condicionador de Metais', 'description': 'Tratamento para o metal que cria uma camada nano protetora, reduzindo atrito e desgaste.', 'benefits': ['Redução drástica de atrito', 'Aumenta a vida útil do equipamento']},
    # ... (catálogo completo)
}
SERVICES_DATABASE = {
    '1': {'name': 'Análise de Óleo Laboratorial', 'description': 'Análise completa para detectar desgaste, contaminação e a degradação do fluido.'},
    '2': {'name': 'Planos de Lubrificação Personalizados', 'description': 'Desenvolvemos um plano completo para otimizar a vida útil dos seus ativos.'},
    '3': {'name': 'Treinamentos para Equipes', 'description': 'Capacitamos sua equipe com as melhores práticas de lubrificação e manutenção preditiva.'},
}

def send_specialist_lead(email, question, product_name):
    print("\n--- NOVO LEAD QUALIFICADO PARA ESPECIALISTA ---")
    print(f"Email do Cliente: {email}\nProduto de Interesse: {product_name}\nDúvida Específica: {question}")
    print("-------------------------------------------\n")
    return True

try:
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
    model = genai.GenerativeModel('gemini-1.5-flash')
    print("-> Modelo Gemini 1.5 Flash carregado com sucesso.")
except Exception as e:
    print(f"!!! ERRO ao configurar a API do Gemini: {e} !!!"); model = None

# --- FUNÇÃO DA IA (MODIFICADA PARA DIFERENTES CONTEXTOS) ---
def get_ai_response(question, chat_history, context=None):
    if not model: return "Desculpe, minha IA está offline."
    
    system_prompt = ""
    full_prompt = ""
    # Modo 1: Apresentação de Produto
    if context and context.get('type') == 'product_presentation':
        product_data = context['data']
        system_prompt = ("Você é AlexExpert, especialista de produtos da UNAX GROUP. Apresente o produto a seguir de forma clara e persuasiva. "
                         "No final, inclua a frase exata: 'Se tiver alguma dúvida sobre a aplicação deste produto, me diga qual é e eu encaminho para um de nossos especialistas te ajudar.'")
        context_str = (f"Dados:\n- Nome: {product_data['name']}\n- Tipo: {product_data['type']}\n- Descrição: {product_data['description']}\n- Benefícios: {', '.join(product_data['benefits'])}")
        full_prompt = system_prompt + "\n\n" + context_str
        chat = model.start_chat(history=[]) # Chat limpo para esta tarefa
    # Modo 2: Resposta a Dúvida de Aplicação
    elif context and context.get('type') == 'product_follow_up':
        product_name = context['product_name']
        system_prompt = ("Você é AlexExpert. O cliente está com uma dúvida de aplicação sobre um produto que acabou de ver. "
                         "Responda a pergunta do cliente de forma objetiva, usando seu conhecimento geral sobre lubrificação industrial. "
                         "Após sua resposta, pergunte de forma clara se a informação foi suficiente ou se ele prefere que um especialista entre em contato para um detalhamento técnico. "
                         "Exemplo de finalização: 'Esta informação ajuda? Ou prefere que um especialista entre em contato para detalhar isso com você?'")
        full_prompt = f"{system_prompt}\n\nProduto em discussão: {product_name}\n\nDúvida do cliente: {question}"
        chat = model.start_chat(history=chat_history)
    # Modo 3: Pergunta Geral
    else:
        system_prompt = "Você é AlexExpert, assistente virtual da UNAX GROUP. Responda às dúvidas sobre lubrificação. Se não souber, peça para ele falar com um especialista no menu."
        full_prompt = system_prompt + "\n Pergunta: " + question
        chat = model.start_chat(history=chat_history)
        
    try:
        print(f"-> Enviando para IA (Contexto: {context.get('type', 'Geral') if context else 'Geral'}): '{question}'")
        response = chat.send_message(full_prompt)
        return response.text
    except Exception as e:
        print(f"!!! ERRO na API Gemini: {e} !!!"); return "Desculpe, não consegui processar sua solicitação."

# --- FUNÇÃO CENTRAL DE LÓGICA DO CHATBOT ---
def process_message(incoming_msg, session_data):
    stage = session_data.get('stage', 'main_menu')
    if 'chat_history' not in session_data: session_data['chat_history'] = []
    response_text = ""
    positive_responses = ['sim', 's', 'quero', 'prefiro', 'especialista', 'contato', 'pode ser']
    negative_responses = ['não', 'n', 'nao', 'ajudou', 'suficiente', 'obrigado']

    if incoming_msg in ['*', 'cancelar']:
        session_data = {'stage': 'main_menu', 'chat_history': []}; stage = 'main_menu'; incoming_msg = ''
        if incoming_msg == 'cancelar':
            response_text = "Ação cancelada. Voltando ao menu principal.\n\n"

    if stage == 'main_menu':
        menu_text = ("Olá! Sou *AlexExpert*. Como posso te ajudar hoje?\n\n"
                     "*1* - Ver Produtos ⚙️\n*2* - Ver Serviços 🛠️\n*3* - Pedir Cotação 💰\n*4* - Falar com Especialista 👨‍🔧")
        response_text += menu_text
        if incoming_msg == '1':
            response_text = "Nossos produtos:\n*1* - LanoPro 50 EAL\n*2* - LanoPro 15 EAL\n*3* - Alfa-X\n\nDigite o número para eu te apresentar o produto, ou `*` para voltar."
            session_data['stage'] = 'products_detail_selection'
        elif incoming_msg == '3':
            response_text = (f"Para solicitar sua cotação, preencha nosso formulário online:\n\n➡️ {QUOTE_FORM_LINK}\n\nApós preencher, nossa equipe entrará em contato.")
            session_data['stage'] = 'main_menu'
        elif incoming_msg == '4':
            response_text = "Aguarde, por favor. Iremos te transferir para nosso time de especialistas."
            session_data['stage'] = 'main_menu'
        elif incoming_msg.lower() not in ['oi', 'olá', 'menu', 'ajuda', '']:
            response_text = get_ai_response(incoming_msg, session_data['chat_history'])
    
    elif stage == 'products_detail_selection':
        product_map = {'1': 'lanopro_50_eal', '2': 'lanopro_15_eal', '3': 'alfa_x'}
        product_key = product_map.get(incoming_msg)
        if product_key:
            product_data = PRODUCT_DATABASE.get(product_key)
            if product_data:
                context = {'type': 'product_presentation', 'data': product_data}
                response_text = get_ai_response(question="", chat_history=[], context=context)
                session_data['stage'] = 'specialist_handoff'
                session_data['last_product_viewed'] = product_data['name']
        else:
            response_text = "Opção inválida. Digite o número de um produto ou `*` para voltar."

    # --- FLUXO CONSULTIVO (ETAPA 1: IA RESPONDE A DÚVIDA) ---
    elif stage == 'specialist_handoff':
        user_question = incoming_msg
        product_name = session_data.get('last_product_viewed', 'o produto')
        
        context = {'type': 'product_follow_up', 'product_name': product_name}
        response_text = get_ai_response(user_question, session_data['chat_history'], context=context)
        
        session_data['stage'] = 'final_handoff_decision'
        session_data['specialist_question'] = user_question # Salva a pergunta original

    # --- FLUXO CONSULTIVO (ETAPA 2: USUÁRIO DECIDE SE QUER O ESPECIALISTA) ---
    elif stage == 'final_handoff_decision':
        if incoming_msg.lower() in positive_responses:
            response_text = "Entendido. Para que nosso especialista possa entrar em contato e aprofundar na sua dúvida, por favor, informe seu melhor *e-mail*."
            session_data['stage'] = 'capture_email_for_specialist'
        elif incoming_msg.lower() in negative_responses:
            response_text = "Ótimo! Fico feliz em ajudar. Se precisar de mais alguma coisa, estou à disposição. Voltando ao menu principal."
            return process_message('', {'stage': 'main_menu'}) # Reinicia para o menu principal
        else:
            response_text = "Desculpe, não entendi. Você gostaria de falar com um especialista sobre isso? (sim/não)"

    elif stage == 'capture_email_for_specialist':
        user_email = incoming_msg
        user_question = session_data.get('specialist_question', 'N/A')
        product_name = session_data.get('last_product_viewed', 'N/A')
        
        send_specialist_lead(user_email, user_question, product_name)
        
        response_text = "Perfeito! Seu contato e sua dúvida foram encaminhados. Um especialista entrará em contato em breve. Posso ajudar com algo mais?"
        session_data['stage'] = 'main_menu'

    # (Outros estágios - serviços, etc. - permanecem os mesmos)
    else:
        response_text = "Ocorreu um erro. Redirecionando para o menu principal."
        session_data = {'stage': 'main_menu', 'chat_history': []}

    session_data['chat_history'].append({"role": "user", "parts": [incoming_msg]}); session_data['chat_history'].append({"role": "model", "parts": [response_text]}); session_data['chat_history'] = session_data['chat_history'][-10:]
    return response_text, session_data

# --- ROTA WEB E EXECUÇÃO (sem alterações) ---
@app.route('/whatsapp', methods=['POST'])
def whatsapp_reply():
    incoming_msg = request.values.get('Body', '').strip().lower()
    response_text, new_session_data = process_message(incoming_msg, session.copy())
    for key, value in new_session_data.items():
        session[key] = value
    resp = MessagingResponse(); resp.message(response_text)
    return str(resp)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
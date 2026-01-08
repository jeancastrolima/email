# console_chat.py
# Simulador de chat para testar a lógica do bot no terminal.

from app import process_message

def start_chat():
    print("--- Simulador de Chat UNAX GROUP (com IA) ---")
    print("Digite 'sair' para terminar ou '*' para ir ao menu principal.")
    print("-" * 50)

    session_data = {}

    welcome_message, session_data = process_message('', session_data)
    print(f"🤖 AlexExpert:\n{welcome_message}\n")

    while True:
        user_input = input("🙂 Você: ")

        if user_input.lower() == 'sair':
            print("\n--- Conversa encerrada. ---")
            break

        bot_response, session_data = process_message(user_input, session_data)

        print(f"\n🤖 AlexExpert:\n{bot_response}\n")

if __name__ == "__main__":
    start_chat()
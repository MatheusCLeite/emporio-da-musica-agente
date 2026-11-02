import os

# Vem antes de qualquer load_dotenv: testes não devem enviar traces mesmo com o tracing ligado no .env.
os.environ["LANGSMITH_TRACING"] = "false"

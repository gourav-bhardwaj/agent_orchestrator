from langfuse import get_client
from openinference.instrumentation.openai_agents import OpenAIAgentsInstrumentor
from dotenv import load_dotenv

load_dotenv(override=True)

OpenAIAgentsInstrumentor().instrument()

langfuse = get_client()

if langfuse.auth_check():
    print("Langfuse connected successfully!")
else:
    print("Langfuse connection failed!")




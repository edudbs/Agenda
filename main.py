import os
import datetime
import json
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from google.oauth2 import service_account
from googleapiclient.discovery import build
from google import genai
from google.genai.errors import APIError
from typing import List, Dict

# --- Inicialização ---

app = FastAPI()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Autenticação simples por token
API_TOKEN = os.getenv("API_TOKEN", "changeme")

def check_auth(token: str):
    """Verifica o token de autorização simples."""
    if token != API_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")

# --- Configuração de Clientes ---

# Google Calendar Service
def get_calendar_service():
    """Tenta autenticar usando credenciais da Conta de Serviço (Service Account)."""
    try:
        creds_json_str = os.getenv("GOOGLE_CREDENTIALS")
        if not creds_json_str:
            return None
        
        # Carrega a string JSON da variável de ambiente de forma segura (CORRIGIDO)
        creds_info = json.loads(creds_json_str)

        SCOPES = ["https://www.googleapis.com/auth/calendar"]
        
        creds = service_account.Credentials.from_service_account_info(
            creds_info,
            scopes=SCOPES
        )
        service = build("calendar", "v3", credentials=creds)
        return service

    except json.JSONDecodeError:
        print("Erro Calendar: GOOGLE_CREDENTIALS não é um JSON válido.")
        return None
    except Exception as e:
        print(f"Erro Calendar ao construir o serviço: {e}")
        return None


# Gemini Client
def get_gemini_client():
    """Inicializa o cliente Gemini."""
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        return None
    try:
        return genai.Client(api_key=key)
    except Exception as e:
        print(f"Erro Gemini Client: {e}")
        return None


# --- Funções de Ferramenta (Tools) para o Gemini ---

def format_event(e: Dict) -> Dict:
    """Função auxiliar para formatar um evento do Google Calendar."""
    start = e["start"].get("dateTime", e["start"].get("date"))
    return {
        "summary": e.get("summary", "Sem título"),
        "start": start
    }

def list_calendar_events(max_results: int = 10) -> List[Dict]:
    """
    Lista os próximos compromissos da agenda do usuário.
    Use esta função para verificar a disponibilidade atual do usuário.
    
    Args:
        max_results: O número máximo de eventos a serem listados.
    """
    service = get_calendar_service()
    if not service:
        # Retorna erro que o Gemini pode interpretar.
        return [{"error": "Serviço de calendário não configurado ou inacessível."}] 

    now = datetime.datetime.utcnow().isoformat() + "Z"
    
    try:
        events_result = service.events().list(
            calendarId="edudbs@gmail.com",
            timeMin=now,
            maxResults=max_results,
            singleEvents=True,
            orderBy="startTime"
        ).execute()

        events = events_result.get("items", [])
        return [format_event(e) for e in events]
    except Exception as e:
        return [{"error": f"Erro ao listar eventos: {e}"}]


def add_calendar_event(summary: str, start_datetime: str, end_datetime: str, timezone: str = "UTC") -> Dict:
    """
    Cria um novo compromisso na agenda do Google.
    Os horários DEVEM ser fornecidos em formato ISO 8601 (Ex: 2024-12-01T10:00:00).
    
    Args:
        summary: O título do evento.
        start_datetime: A data e hora de início.
        end_datetime: A data e hora de término.
        timezone: O fuso horário do evento (Ex: America/Sao_Paulo).
    """
    service = get_calendar_service()
    if not service:
        return {"error": "Serviço de calendário não configurado ou inacessível."}

    event_body = {
        "summary": summary,
        "start": {"dateTime": start_datetime, "timeZone": timezone},
        "end": {"dateTime": end_datetime, "timeZone": timezone}
    }

    try:
        event = service.events().insert(calendarId="edudbs@gmail.com", body=event_body).execute()
        return {"created": True, "event_id": event.get("id"), "summary": event.get("summary")}
    except Exception as e:
        return {"error": f"Erro ao criar evento: {e}"}


# --- Endpoints da API ---

@app.get("/ping")
def ping():
    """Endpoint de status para verificar as configurações."""
    # A verificação de 'calendar_configured' agora checa se a variável está presente.
    return {
        "status": "ok",
        "calendar_configured": bool(os.getenv("GOOGLE_CREDENTIALS")),
        "gemini_configured": bool(os.getenv("GEMINI_API_KEY"))
    }

@app.get("/events")
def get_events(token: str = Header(None)):
    check_auth(token)
    
    result = list_calendar_events(max_results=20)
    
    if "error" in result[0]:
        raise HTTPException(status_code=500, detail=result[0]["error"])

    return {"events": result}


@app.post("/add_event")
def create_event(summary: str, start_datetime: str, end_datetime: str, token: str = Header(None)):
    check_auth(token)
    
    result = add_calendar_event(summary, start_datetime, end_datetime)
    
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
        
    return result


# --- Agente Inteligente (Gemini Function Calling) ---

@app.get("/chat")
def chat(query: str, token: str):
    check_auth(token)
    client = get_gemini_client()
    if not client:
        raise HTTPException(status_code=500, detail="Erro de Configuração do Gemini. Verifique a chave API.")

    # 1. Definir o sistema de instrução
    system_instruction = (
        "Você é um agente de planejamento e calendário. SUA FUNÇÃO PRIMÁRIA E ÚNICA É INTERAGIR COM A AGENDA DO USUÁRIO "
    "USANDO AS FERRAMENTAS FORNECIDAS. NUNCA RESPONDA PERGUNTAS SOBRE AGENDA SEM USAR UMA FERRAMENTA. "
    "Use a função 'list_calendar_events' para qualquer consulta de disponibilidade. "
    "Use a função 'add_calendar_event' para qualquer solicitação de agendamento. "
    "Responda ao usuário com base no resultado da execução da ferramenta."
    )

    # Ferramentas disponíveis para o modelo
    tools = [list_calendar_events, add_calendar_event]

    try:
        # 2. Primeira Chamada ao Gemini (para decidir se chama uma função)
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=query,
            config=genai.types.GenerateContentConfig(
                system_instruction=system_instruction,
                tools=tools
            )
        )

        # 3. Processar a Resposta: Checar se houve uma solicitação de Function Call
        if not response.function_calls:
            # Resposta direta do modelo
            return {"answer": response.text, "function_used": None}
        
        # Se houver Function Call, executa-a:
        tool_call = response.function_calls[0]
        tool_output = None
        
        # Encontra e executa a função Python correspondente
        if tool_call.name == "list_calendar_events":
            args = dict(tool_call.args)
            tool_output = list_calendar_events(**args)
        
        elif tool_call.name == "add_calendar_event":
            args = dict(tool_call.args)
            tool_output = add_calendar_event(**args)
        
        else:
            tool_output = {"error": f"Função desconhecida: {tool_call.name}"}

        # 4. Segunda Chamada ao Gemini (Feed de volta do resultado da função)
        second_response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[
                {"role": "user", "parts": [{"text": query}]},
                {"role": "model", "parts": [response.candidates[0].content.parts[0]]}, # Solicitação original do modelo
                {"role": "tool", "parts": [{"functionResponse": {"name": tool_call.name, "response": tool_output}}]} # Resultado real da execução
            ],
            config=genai.types.GenerateContentConfig(
                system_instruction=system_instruction,
                tools=tools
            )
        )

        return {"answer": second_response.text, "function_used": tool_call.name}

    except APIError as e:
        raise HTTPException(status_code=500, detail=f"Erro na API do Gemini: {e}")
    except Exception as e:
        # Erro genérico de execução ou Service Account/Calendar API
        raise HTTPException(status_code=500, detail=f"Erro interno do agente: {e}")

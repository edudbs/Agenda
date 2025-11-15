import os
import datetime
import json
from fastapi import FastAPI, HTTPException
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
        
        # Carrega a string JSON da variável de ambiente
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
    return {
        "status": "ok",
        "calendar_configured": bool(os.getenv("GOOGLE_CREDENTIALS")),
        "gemini_configured": bool(os.getenv("GEMINI_API_KEY"))
    }

@app.get("/events")
def get_events(token: str): 
    check_auth(token)
    
    result = list_calendar_events(max_results=20)
    
    if "error" in result[0]:
        raise HTTPException(status_code=500, detail=result[0]["error"])

    return {"events": result}


@app.post("/add_event")
def create_event(summary: str, start_datetime: str, end_datetime: str, token: str):
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

    # ----------------------------------------------------------------------------------
    # CORREÇÃO 1: INJEÇÃO DE DATA/HORA ATUAL E NOVA INSTRUÇÃO DE SISTEMA PARA TEMPO RELATIVO
    # ----------------------------------------------------------------------------------
    
    # Calcular Data e Hora Atual (em UTC) para o Gemini
    now_utc = datetime.datetime.utcnow().isoformat(timespec='seconds') + 'Z'
    
    # 1. Definir o sistema de instrução (Inteligência e Formato)
    system_instruction = (
        f"Você é um planejador de agenda altamente inteligente e prestativo, especializado em otimizar o tempo do usuário. "
        f"A data e hora atual do sistema (UTC) são: **{now_utc}**. " # <--- CONTEXTO DE DATA/HORA
        "Sua função principal é manipular e analisar a agenda do Google Calendar do usuário. "
        "Siga estas regras rigorosamente: "
        
        "**REGRA CHAVE:** Antes de chamar 'add_calendar_event', você deve converter **TODAS** as referências de tempo (hoje, amanhã, próxima semana, etc.) para o formato ISO 8601 completo (Ex: 2025-11-15T17:30:00). Você **nunca** deve passar palavras como 'amanhã' ou 'hoje' nos argumentos de tempo."
        
        "1. SEMPRE use a função 'list_calendar_events' ao planejar, sugerir ou resumir o dia/semana do usuário. "
        "2. Use a função 'add_calendar_event' apenas para agendar novos compromissos, garantindo que a data e hora estejam completas. "
        "3. Ao planejar ou sugerir, use a lista de eventos para identificar lacunas de tempo livre. "
        "4. Mantenha um tom profissional, proativo e consultivo."
        "5. Ao listar compromissos ou sugerir planos, formate o resultado usando estritamente listas de Markdown (itemize ou numeradas) para que cada item ou sugestão ocupe uma linha separada. NUNCA use parágrafos longos para listas."
    )
    # ----------------------------------------------------------------------------------
    
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
        
        # -------------------------------------------------------------------------
        # CORREÇÃO 2: BLOCO CORRIGIDO PARA RESOLVER O PROBLEMA DE RELATÓRIO 'function_used:null'
        # -------------------------------------------------------------------------

        if not response.function_calls:
            # Caso 1: O modelo responde diretamente, sem usar a ferramenta.
            return {"answer": response.text, "function_used": None}

        # Caso 2: O modelo solicita uma chamada de função (Function Calling).

        # Extrai a primeira função e garante que o nome seja uma string serializável
        tool_call = response.function_calls[0]
        function_name = str(tool_call.name) # <--- GARANTIA DE STRING SIMPLES
        
        tool_output = None
        args = dict(tool_call.args)

        # Encontra e executa a função Python correspondente (usando o nome extraído)
        if function_name == "list_calendar_events":
            tool_output = list_calendar_events(**args)
        
        elif function_name == "add_calendar_event":
            tool_output = add_calendar_event(**args)
        
        else:
            tool_output = {"error": f"Função desconhecida: {function_name}"}

        # 4. Segunda Chamada ao Gemini (Feed de volta do resultado da função)
        second_response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[
                {"role": "user", "parts": [{"text": query}]},
                {"role": "model", "parts": [response.candidates[0].content.parts[0]]},
                {"role": "tool", "parts": [{"functionResponse": {"name": tool_call.name, "response": tool_output}}]}
            ],
            config=genai.types.GenerateContentConfig(
                system_instruction=system_instruction,
                tools=tools
            )
        )

        # Retorno Final: Usa a variável function_name, que resolve o erro de relatório
        return {"answer": second_response.text, "function_used": function_name}
        
        # -------------------------------------------------------------------------
        # FIM DO BLOCO CORRIGIDO
        # -------------------------------------------------------------------------

    except APIError as e:
        raise HTTPException(status_code=500, detail=f"Erro na API do Gemini: {e}")
    except Exception as e:
        # Erro genérico de execução ou Service Account/Calendar API
        raise HTTPException(status_code=500, detail=f"Erro interno do agente: {e}")

import os
import datetime
import json
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from google.oauth2 import service_account
from googleapiclient.discovery import build
from google import genai # Novo cliente Gemini
from google.genai.errors import APIError # Para capturar erros da API Gemini
from typing import List, Dict

# --- Inicialização ---

# Inicializa FastAPI
app = FastAPI()

# CORS (libera acesso ao seu servidor)
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
    """Tenta autenticar usando credenciais da Conta de Serviço."""
    try:
        creds_json_str = os.getenv("GOOGLE_CREDENTIALS")
        if not creds_json_str:
            return None
        
        # 1. Carrega a string JSON da variável de ambiente de forma segura (Corrigido)
        creds_info = json.loads(creds_json_str)

        # 2. Cria as credenciais da Conta de Serviço
        # Se você compartilhou sua agenda com o e-mail da Service Account, o escopo full é necessário.
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


# Gemini Client (Substitui OpenAI Client)
def get_gemini_client():
    """Inicializa o cliente Gemini."""
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        # Nota: O SDK geralmente busca a chave automaticamente se estiver setada.
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
        # Retorna lista vazia ou erro que o Gemini pode interpretar.
        return [{"error": "Serviço de calendário não configurado ou inacessível."}] 

    now = datetime.datetime.utcnow().isoformat() + "Z"
    
    try:
        events_result = service.events().list(
            calendarId="primary",
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
    Os horários DEVEM

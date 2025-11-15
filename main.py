import os
import datetime
import json
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from google.oauth2 import service_account
from googleapiclient.discovery import build
from google import genai
from google.genai.errors import APIError
from typing import List, Dict, Optional
# Importação necessária para lidar com o histórico de conversas
from google.genai.types import Content, Part 

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
CALENDAR_ID = os.getenv("CALENDAR_ID", "edudbs@gmail.com") # Melhor usar variável de ambiente
USER_TIMEZONE = "America/Sao_Paulo" 

def format_event(e: Dict) -> Dict:
    """Função auxiliar para formatar um evento do Google Calendar."""
    start = e["start"].get("dateTime", e["start"].get("date"))
    return {
        "summary": e.get("summary", "Sem título"),
        "start": start,
        "event_id": e.get("id") 
    }

def list_calendar_events(max_results: int = 10, start_datetime: str = None, end_datetime: str = None) -> List[Dict]:
    """
    Lista os próximos compromissos da agenda do usuário, opcionalmente filtrando por um intervalo de datas.
    
    Args:
        max_results: O número máximo de eventos a serem listados.
        start_datetime: A data e hora de início (ISO 8601 com 'Z' para UTC).
        end_datetime: A data e hora de fim (ISO 8601 com 'Z' para UTC).
    """
    service = get_calendar_service()
    if not service:
        return [{"error": "Serviço de calendário não configurado ou inacessível."}] 

    time_min_filter = start_datetime if start_datetime else (datetime.datetime.utcnow().isoformat() + "Z")
    time_max_filter = end_datetime if end_datetime else None

    try:
        events_result = service.events().list(
            calendarId=CALENDAR_ID,
            timeMin=time_min_filter,
            timeMax=time_max_filter,
            maxResults=max_results,
            singleEvents=True,
            orderBy="startTime"
        ).execute()

        events = events_result.get("items", [])
        return [format_event(e) for e in events]
    except Exception as e:
        return [{"error": f"Erro ao listar eventos no Google Calendar: {e}"}]

def add_calendar_event(summary: str, start_datetime: str, end_datetime: str, timezone: str = USER_TIMEZONE) -> Dict:
    """
    Cria um novo compromisso na agenda do Google.
    
    Args:
        summary: O título do evento.
        start_datetime: A data e hora de início (ISO 8601, local).
        end_datetime: A data e hora de término (ISO 8601, local).
        timezone: O fuso horário do evento (America/Sao_Paulo).
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
        event = service.events().insert(calendarId=CALENDAR_ID, body=event_body).execute()
        return {"created": True, "event_id": event.get("id"), "summary": event.get("summary")}
    except Exception as e:
        return {"error": f"Erro ao criar evento: {e}"}

# --- FUNÇÃO 1: EXCLUIR EVENTO ---
def delete_calendar_event(event_id: str) -> Dict:
    """
    Exclui um compromisso da agenda do Google Calendar.
    
    Args:
        event_id: O ID do evento a ser excluído. Este ID deve ser obtido primeiro listando os eventos.
    """
    service = get_calendar_service()
    if not service:
        return {"error": "Serviço de calendário não configurado ou inacessível."}

    try:
        service.events().delete(calendarId=CALENDAR_ID, eventId=event_id).execute()
        return {"deleted": True, "event_id": event_id, "message": "Evento excluído com sucesso."}
    except Exception as e:
        return {"error": f"Erro ao excluir evento (ID: {event_id}): {e}"}

# --- FUNÇÃO 2: MODIFICAR EVENTO ---
def modify_calendar_event(event_id: str, summary: Optional[str] = None, start_datetime: Optional[str] = None, end_datetime: Optional[str] = None, timezone: str = USER_TIMEZONE) -> Dict:
    """
    Modifica um compromisso existente na agenda. Pelo menos um campo deve ser fornecido para modificação.
    
    Args:
        event_id: O ID do evento a ser modificado.
        summary: (Opcional) Novo título do evento.
        start_datetime: (Opcional) Nova data e hora de início (ISO 8601, local).
        end_datetime: (Opcional) Nova data e hora de término (ISO 8601, local).
        timezone: O fuso horário a ser aplicado (America/Sao_Paulo).
    """
    service = get_calendar_service()
    if not service:
        return {"error": "Serviço de calendário não configurado ou inacessível."}

    try:
        # 1. Obter o evento existente (necessário para o método 'update')
        existing_event = service.events().get(calendarId=CALENDAR_ID, eventId=event_id).execute()
        
        # 2. Aplicar as alterações
        if summary is not None:
            existing_event['summary'] = summary
        
        if start_datetime is not None:
            existing_event['start'] = {'dateTime': start_datetime, 'timeZone': timezone}
        
        if end_datetime is not None:
            existing_event['end'] = {'dateTime': end_datetime, 'timeZone': timezone}

        # 3. Enviar o evento atualizado
        updated_event = service.events().update(calendarId=CALENDAR_ID, eventId=event_id, body=existing_event).execute()
        
        return {"modified": True, "event_id": event_id, "new_summary": updated_event.get("summary")}
    
    except Exception as e:
        return {"error": f"Erro ao modificar evento (ID: {event_id}): {e}"}


# --- Endpoints da API ---

# NOVO ENDPOINT DE HEALTH CHECK (Corrigindo o problema do Render)
@app.get("/")
def health_check():
    """Endpoint essencial para o Render verificar se o serviço está ativo."""
    return {"status": "Serviço ativo", "info": "A API está respondendo"}

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


# --- Agente Inteligente (Gemini Function Calling com Histórico) ---

@app.get("/chat")
def chat(query: str, token: str, history: Optional[str] = None):
    check_auth(token)
    client = get_gemini_client()
    if not client:
        raise HTTPException(status_code=500, detail="Erro de Configuração do Gemini. Verifique a chave API.")

    
    # Calcular Data e Hora Atual (em UTC) para o Gemini
    now_utc = datetime.datetime.utcnow().isoformat(timespec='seconds') + 'Z'
    
    system_instruction = (
        f"Você é um planejador de agenda altamente inteligente e prestativo. "
        f"A data e hora atual do sistema (UTC) são: **{now_utc}**. " 
        f"O fuso horário local do usuário para criação de eventos é: **{USER_TIMEZONE}**."
        "Sua função principal é manipular e analisar a agenda do Google Calendar do usuário. "
        
        "**IMPORTANTE:** Você está recebendo o histórico da conversa. Use-o para responder a perguntas de acompanhamento ou confirmações (ex: 'sim', 'não')."
        
        "Siga estas regras rigorosamente: "
        
        "**REGRA CHAVE DE DATA/TEMPO:** Converta TODAS as referências de tempo para o formato ISO 8601. "
        
        "1. **LISTAGEM (list_calendar_events):** Se for buscar eventos, use as datas no fuso horário **UTC (sufixo 'Z')** para `start_datetime` e `end_datetime`. Ex: `2025-11-17T00:00:00Z`."

        "2. **CRIAÇÃO (add_calendar_event):** Se for criar um evento, use a data/hora no fuso horário **local do usuário (sem sufixo Z)**, e **DEVE** passar `{USER_TIMEZONE}` para o argumento `timezone`. Ex: `2025-11-17T10:00:00` e `timezone='America/Sao_Paulo'`."
        
        "3. **EXCLUSÃO E MODIFICAÇÃO:** "
        "   a. Para **excluir** (`delete_calendar_event`) ou **modificar** (`Calendar`), você **DEVE** ter o **`event_id`**. "
        "   b. Se o usuário pedir para alterar ou excluir um evento, mas não fornecer o ID, você **DEVE** primeiro chamar `list_calendar_events` para listar os eventos relevantes e encontrar o `event_id`. Se houver ambiguidade, peça ao usuário para especificar qual evento pelo horário ou título exato."
        "   c. Para **modificar**, mantenha o fuso horário local (sem sufixo Z) e passe `{USER_TIMEZONE}` para o argumento `timezone`."
        
        "4. **Formatação de Saída:** Ao listar compromissos ou sugerir planos, formate o resultado usando estritamente listas de Markdown (itemize ou numeradas)."
        
        "5. Mantenha um tom profissional, proativo e consultivo."
    )
    
    # --- Processamento do Histórico de Conversa (CORREÇÃO DE ROBUSTEZ) ---
    full_conversation_parts = []
    # Verifica se há histórico e se não é uma string vazia/null
    if history and history != 'null':
        try:
            history_data = json.loads(history)
            for turn in history_data:
                if 'role' in turn and 'text' in turn:
                    # Cria o objeto Content para cada turno do histórico
                    full_conversation_parts.append(
                        Content(
                            role=turn['role'], 
                            parts=[Part(text=turn['text'])]
                        )
                    )
        except json.JSONDecodeError:
            print("Formato de histórico JSON inválido recebido.")
            
    # Adiciona a consulta atual como o último turno do usuário
    full_conversation_parts.append(
        Content(
            role="user",
            parts=[Part(text=query)]
        )
    )

    # Ferramentas disponíveis (todas)
    tools = [list_calendar_events, add_calendar_event, delete_calendar_event, modify_calendar_event]

    try:
        # 1. Primeira Chamada ao Gemini (com histórico completo)
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=full_conversation_parts, # Usa o histórico completo
            config=genai.types.GenerateContentConfig(
                system_instruction=system_instruction,
                tools=tools
            )
        )

        # 2. Processar a Resposta: Checar se houve uma solicitação de Function Call
        
        if not response.function_calls:
            # Caso 1: O modelo responde diretamente. (Inclui respostas a confirmações)
            return {"answer": response.text, "function_used": None}

        # Caso 2: O modelo solicita uma chamada de função.
        tool_call = response.function_calls[0]
        function_name = str(tool_call.name)
        
        tool_output = None
        args = dict(tool_call.args)

        # Encontra e executa a função Python correspondente
        if function_name == "list_calendar_events":
            tool_output = list_calendar_events(**args)
        
        elif function_name == "add_calendar_event":
            tool_output = add_calendar_event(**args)
        
        elif function_name == "delete_calendar_event":
            tool_output = delete_calendar_event(**args)
            
        elif function_name == "modify_calendar_event":
            tool_output = modify_calendar_event(**args)
            
        else:
            tool_output = {"error": f"Função desconhecida: {function_name}"}

        # 3. Segunda Chamada ao Gemini (Feed de volta do resultado da função)
        
        # Base: Histórico completo (incluindo a última query do usuário)
        history_for_second_call = full_conversation_parts[:] 

        # Adiciona: 
        # a) Resposta inicial do Modelo (chamada de função)
        history_for_second_call.append(response.candidates[0].content)

        # b) Saída da Ferramenta (resultado da função executada)
        history_for_second_call.append(
            Content(
                role="tool",
                parts=[
                    Part.from_function_response(
                        name=tool_call.name, 
                        response=tool_output
                    )
                ]
            )
        )
        
        # Chama o modelo com o histórico estendido
        second_response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=history_for_second_call,
            config=genai.types.GenerateContentConfig(
                system_instruction=system_instruction,
                tools=tools
            )
        )

        # Retorno Final
        return {"answer": second_response.text, "function_used": function_name}
        
    except APIError as e:
        raise HTTPException(status_code=500, detail=f"Erro na API do Gemini: {e}")
    except Exception as e:
        # Se for um erro da função do Google Calendar, tentamos extrair o detalhe
        error_detail = str(e)
        if hasattr(e, 'resp') and 'content' in e.resp:
             try:
                 error_detail = json.loads(e.resp['content'])['error']['message']
             except Exception:
                 pass
        raise HTTPException(status_code=500, detail=f"Erro interno do agente: {error_detail}")

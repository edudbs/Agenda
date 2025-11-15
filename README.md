# Agente de Planejamento - FastAPI (Service Account)

## Conteúdo do pacote
- main.py: API FastAPI que integra com Google Calendar (Service Account) e OpenAI.
- requirements.txt: dependências Python.
- render.yaml: configuração para deploy no Render.

## Passos rápidos para usar (resumido)

1. **Variáveis de ambiente no Render**
   - `GOOGLE_CREDENTIALS_JSON`: cole **o conteúdo inteiro** do JSON da service account (não envie o arquivo no repositório).
   - `CALENDAR_ID` (opcional): seu e-mail do Google (ex: seu.email@gmail.com). Se não definido, a API tentará usar 'primary' (pode referir-se ao calendário da service account).
   - `OPENAI_API_KEY`: sua chave OpenAI.
   - `OPENAI_MODEL` (opcional): modelo a usar (ex: gpt-4o-mini).

2. **Compartilhar sua agenda**
   - No Google Calendar, compartilhe sua agenda com o e-mail da service account (ex: `agenda@agenda-478300.iam.gserviceaccount.com`) com permissão "Fazer alterações nos eventos".

3. **Deploy**
   - Coloque os arquivos no repositório e conecte ao Render (ou faça Manual Deploy).
   - Verifique logs e acesse `/ping`, `/events`, `/suggest` e `/plan`.

4. **Obter um plano**
   - POST `/plan` com JSON body:
     ```
     {
       "date": "2025-11-15",
       "tasks": ["Revisar contrato", "Estudar inglês 1h"]
     }
     ```

## Observações de segurança
- Nunca comite suas credenciais (service account JSON) no repositório.
- Use apenas variáveis de ambiente no Render.
- O `refresh_token` não é necessário com service account.


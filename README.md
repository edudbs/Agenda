# Agenda AI Assistant

Assistente inteligente de agenda com integração ao Google Calendar, IA generativa via Gemini e API em FastAPI.

O projeto evoluiu de um MVP simples de automação de agenda para um agente conversacional capaz de:
- interpretar linguagem natural
- consultar compromissos
- criar, alterar e excluir eventos
- manter contexto de conversa
- operar via API e integrações externas
- utilizar Function Calling com IA

---

# Funcionalidades

## Gerenciamento Inteligente de Agenda
- Listagem de eventos
- Criação de compromissos
- Alteração de eventos existentes
- Exclusão de eventos
- Busca contextual na agenda

## IA Conversacional
- Interpretação de linguagem natural
- Histórico de conversa
- Respostas contextuais
- Confirmações conversacionais (“sim”, “não”, etc.)

## Integração com Google Calendar
- OAuth Google
- Leitura e escrita de eventos
- Suporte a timezone
- Manipulação segura de calendário

## API REST
Endpoints para:
- health check
- status
- chat inteligente
- eventos

## Deploy Cloud
Pronto para deploy no Render.

---

# Stack Tecnológica

- Python 3
- FastAPI
- Google Gemini API
- Google Calendar API
- OAuth 2.0 Google
- Render
- Google API Client

---

# Arquitetura

```text
Usuário
   ↓
Telegram / Cliente HTTP
   ↓
FastAPI
   ↓
Gemini (Function Calling)
   ↓
Ferramentas Python
   ↓
Google Calendar API
```

---

# Estrutura do Projeto

```text
.
├── main.py
├── requirements.txt
├── render.yaml
└── README.md
```

---

# Fluxo do Sistema

## 1. Usuário envia uma mensagem

Exemplo:

```text
Marque uma reunião amanhã às 14h
```

---

## 2. Gemini interpreta a intenção

O modelo:
- entende data/hora
- identifica intenção
- escolhe a ferramenta apropriada

---

## 3. Function Calling

O Gemini chama automaticamente funções Python como:

- `list_calendar_events`
- `add_calendar_event`
- `modify_calendar_event`
- `delete_calendar_event`

---

## 4. Google Calendar é atualizado

A API executa a ação no calendário do usuário.

---

## 5. Resposta amigável é retornada

Exemplo:

```text
Reunião criada com sucesso para amanhã às 14h.
```

---

# Histórico de Conversa

O sistema mantém histórico contextual da conversa.

Exemplo:

```text
Usuário:
Crie uma reunião amanhã às 10h

Assistente:
Qual será o título?

Usuário:
Reunião financeira

Assistente:
Evento criado com sucesso.
```

---

# Variáveis de Ambiente

## Obrigatórias

### Gemini

```env
GEMINI_API_KEY=
```

---

### Segurança da API

```env
API_TOKEN=
```

---

### Google Calendar

```env
GOOGLE_CREDENTIALS=
```

Conteúdo JSON completo das credenciais Google.

---

### Calendar ID

```env
CALENDAR_ID=
```

Exemplo:

```env
CALENDAR_ID=seuemail@gmail.com
```

---

# Timezone

Atualmente configurado para:

```python
America/Sao_Paulo
```

---

# Endpoints

## Health Check

```http
GET /
```

Resposta:

```json
{
  "status": "Serviço ativo"
}
```

---

## Ping

```http
GET /ping
```

Verifica:
- Gemini
- Google Calendar
- configurações gerais

---

## Chat Inteligente

```http
GET /chat
```

### Parâmetros

| Parâmetro | Tipo | Descrição |
|---|---|---|
| query | string | mensagem do usuário |
| token | string | token de autenticação |
| history | string/json | histórico opcional |

---

### Exemplo

```http
/chat?query=Quais compromissos tenho amanhã?&token=SEU_TOKEN
```

---

## Eventos

### Listar

```http
GET /events
```

---

### Criar

```http
POST /add_event
```

Parâmetros:
- summary
- start_datetime
- end_datetime
- token

---

# OAuth Google

O sistema utiliza autenticação Google para acesso ao Calendar.

Fluxo:
1. Usuário autoriza acesso
2. Google retorna callback
3. Tokens são armazenados
4. API passa a operar no calendário autorizado

---

# Segurança

## Recomendações

- Nunca subir credenciais no GitHub
- Utilizar apenas variáveis de ambiente
- Restringir CORS em produção
- Utilizar HTTPS
- Rotacionar tokens periodicamente

---

# Deploy no Render

## 1. Criar Web Service

Conecte o repositório GitHub ao Render.

---

## 2. Configurar variáveis de ambiente

Adicionar:
- `GEMINI_API_KEY`
- `GOOGLE_CREDENTIALS`
- `CALENDAR_ID`
- `API_TOKEN`

---

## 3. Deploy

O Render fará:
- build automático
- instalação de dependências
- execução da API FastAPI

---

# Exemplo de Uso

## Perguntas suportadas

```text
Quais compromissos tenho hoje?
```

```text
Crie um evento amanhã às 15h
```

```text
Remarque minha reunião de sexta
```

```text
Apague o compromisso das 10h
```

---

# Roadmap

## Melhorias futuras

- Interface web
- Dashboard de agenda
- Integração WhatsApp
- Memória persistente
- Múltiplos calendários
- Sugestões automáticas de horários
- Planejamento inteligente do dia
- Integração com tarefas
- Banco de dados
- Sistema de usuários
- Painel administrativo

---

# Observações

Este projeto está em evolução contínua e a arquitetura pode mudar conforme novas funcionalidades forem implementadas.

---

# Licença

Uso privado / interno.

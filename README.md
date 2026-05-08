# API de Consulta CPF/CNPJ para CRM DataCrazy

API completa com painel de configuração para consultar CPF e CNPJ e enviar automaticamente para leads no WhatsApp via CRM DataCrazy.

## 🚀 Deploy no Railway

### Passo 1: Criar conta no Railway
1. Acesse [railway.app](https://railway.app)
2. Faça login com GitHub

### Passo 2: Criar novo projeto
1. Clique em **"New Project"**
2. Selecione **"Deploy from GitHub repo"**
3. Conecte seu repositório GitHub com este código

### Passo 3: Configurar variáveis de ambiente
No Railway, vá em **Variables** e adicione:

| Variável | Descrição |
|----------|-----------|
| `CRM_API_KEY` | Chave da API do CRM DataCrazy |
| `CPF_API_TOKEN` | Token da API cpf-brasil.org |
| `SECRET_KEY` | Chave secreta (opcional) |

### Passo 4: Deploy
O Railway fará o deploy automaticamente. Você receberá uma URL como:
```
https://seu-projeto.railway.app
```

---

## 📋 Como Usar

### 1. Acessar o Painel
Acesse a URL do seu deploy (ex: `https://seu-projeto.railway.app`)

### 2. Configurar Chaves
Na aba **Configurações**, insira:
- Chave API do CRM DataCrazy
- Token da API de CPF

### 3. Personalizar Mensagem
Na aba **Template da Mensagem**, personalize como a resposta será enviada.

Variáveis disponíveis para CPF:
- `{cpf_mascarado}` - CPF parcialmente oculto (123.***.**56-78)
- `{cpf}` - CPF completo
- `{nome}` - Nome do titular
- `{nascimento}` - Data de nascimento
- `{sexo}` - Sexo
- `{nome_mae}` - Nome da mãe

Variáveis para CNPJ na resposta automática padrão:
- `{cnpj}` - CNPJ formatado
- `{cnpj_numeros}` - CNPJ apenas com números
- `{razao_social}` - Razão social da empresa

### 4. Gerar Código JavaScript
Na aba **Código JavaScript**:
1. Insira a URL da sua API
2. Clique em **"Gerar Código JavaScript"**
3. Copie o código gerado

### 5. Configurar no CRM DataCrazy
1. Vá em **Automações** > **Criar Nova Automação**
2. Configure o gatilho (ex: quando lead enviar mensagem)
3. Adicione ação **"Executar JavaScript"**
4. Cole o código gerado
5. Salve a automação

---

## 🔧 Endpoints da API

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| GET | `/` | Painel de configuração |
| GET | `/health` | Health check |
| GET/POST | `/api/config` | Configurações da API |
| POST | `/api/webhook/datacrazy` | Webhook principal |
| POST | `/api/consultar-cpf` | Consulta CPF/CNPJ direta |
| POST | `/api/gerar-javascript` | Gera código JS |

---

## 📁 Estrutura do Projeto

```
cpf_api_final/
├── app.py              # Aplicação Flask principal
├── templates/
│   └── index.html      # Painel de configuração
├── requirements.txt    # Dependências Python
├── Procfile           # Configuração Railway/Heroku
├── runtime.txt        # Versão do Python
├── .gitignore         # Arquivos ignorados
└── README.md          # Este arquivo
```

---

## 🔒 Segurança

- As chaves de API são armazenadas apenas em memória
- Mensagens são formatadas para evitar banimento no WhatsApp
- CPF é parcialmente mascarado nas respostas
- CNPJ é consultado pela BrasilAPI e retorna CNPJ formatado e razão social

---

## 📞 Suporte

- **CRM DataCrazy:** https://help.datacrazy.io/
- **API CPF:** https://dash.cpf-brasil.org/

---

Desenvolvido para integração CRM DataCrazy + Consulta de CPF

"""
API de Consulta de CPF para CRM DataCrazy
=========================================
Sistema Multi-Conta com Logs Persistentes

Variáveis de ambiente:
- CPF_API_TOKEN: Token da API de CPF (cpf-brasil.org)
- SECRET_KEY: Chave secreta para o painel (opcional)
"""

from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import re
import os
import json
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import threading

app = Flask(__name__)
CORS(app)

# ==================== CONFIGURAÇÕES ====================

# Diretório para dados persistentes (Railway usa /app por padrão)
DATA_DIR = os.environ.get('DATA_DIR', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data'))
os.makedirs(DATA_DIR, exist_ok=True)

CRM_API_BASE = "https://api.g1.datacrazy.io"
CPF_API_TOKEN = os.environ.get('CPF_API_TOKEN', '')
SECRET_KEY = os.environ.get('SECRET_KEY', 'admin123')

DEFAULT_TEMPLATE = """Olá! Encontrei os dados do CPF consultado:

CPF: {cpf_mascarado}
Nome: {nome}
Nascimento: {nascimento}
Sexo: {sexo}
Mãe: {nome_mae}

Caso precise de mais informações, estou à disposição."""

# ==================== OTIMIZAÇÕES ====================

executor = ThreadPoolExecutor(max_workers=10)

def criar_sessao_otimizada():
    session = requests.Session()
    retry_strategy = Retry(total=2, backoff_factor=0.1, status_forcelist=[500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=20, pool_maxsize=20)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session

crm_session = criar_sessao_otimizada()
cpf_session = criar_sessao_otimizada()

# ==================== SISTEMA MULTI-CONTA ====================

accounts_lock = threading.Lock()
logs_lock = threading.Lock()

def get_accounts_file():
    return os.path.join(DATA_DIR, 'accounts.json')

def get_logs_file():
    return os.path.join(DATA_DIR, 'logs.json')

def load_accounts():
    """Carrega contas do arquivo."""
    try:
        with open(get_accounts_file(), 'r') as f:
            return json.load(f)
    except:
        return {}

def save_accounts(accounts):
    """Salva contas no arquivo."""
    with accounts_lock:
        with open(get_accounts_file(), 'w') as f:
            json.dump(accounts, f, ensure_ascii=False, indent=2)

def load_logs():
    """Carrega logs do arquivo."""
    try:
        with open(get_logs_file(), 'r') as f:
            return json.load(f)
    except:
        return {}

def save_logs(logs_data):
    """Salva logs no arquivo."""
    with logs_lock:
        with open(get_logs_file(), 'w') as f:
            json.dump(logs_data, f, ensure_ascii=False, indent=2)

def get_account(account_id):
    """Retorna uma conta específica."""
    accounts = load_accounts()
    return accounts.get(account_id)

def get_account_by_api_key(api_key):
    """Encontra conta pela chave de API."""
    accounts = load_accounts()
    for acc_id, acc in accounts.items():
        if acc.get('crm_api_key') == api_key:
            return acc_id, acc
    return None, None

def add_log(account_id, tipo, cpf, status, detalhes='', lead_phone='', lead_name='', account_name=''):
    """Adiciona um log para uma conta específica."""
    logs_data = load_logs()
    
    # Pega o nome da conta se não foi fornecido
    if not account_name:
        acc = get_account(account_id)
        account_name = acc.get('name', 'Desconhecida') if acc else 'Desconhecida'
    
    if account_id not in logs_data:
        logs_data[account_id] = []
    
    logs_data[account_id].insert(0, {
        'data': datetime.now().strftime('%d/%m/%Y %H:%M:%S'),
        'tipo': tipo,
        'cpf': cpf if cpf else '-',
        'status': status,
        'detalhes': detalhes,
        'lead_phone': lead_phone or '-',
        'lead_name': lead_name or '-',
        'account_name': account_name
    })
    
    # Mantém apenas os últimos 500 logs por conta
    if len(logs_data[account_id]) > 500:
        logs_data[account_id] = logs_data[account_id][:500]
    
    save_logs(logs_data)

# ==================== CONFIGURAÇÃO GLOBAL ====================

config = {
    'cpf_api_token': CPF_API_TOKEN
}

# ==================== FUNÇÕES AUXILIARES ====================

def detectar_cnpj(texto):
    """Detecta se o texto contém um CNPJ (14 dígitos)."""
    if not texto:
        return False
    
    numeros = re.sub(r'[^\d]', '', texto)
    
    if len(numeros) == 14:
        return True
    
    padrao_cnpj = r'\d{2}[\.]?\d{3}[\.]?\d{3}[\/]?\d{4}[\-]?\d{2}'
    if re.search(padrao_cnpj, texto):
        return True
    
    return False


def extrair_cpf(texto):
    """Extrai CPF de um texto. Retorna None se for CNPJ."""
    if not texto:
        return None
    
    if detectar_cnpj(texto):
        return None
    
    numeros = re.sub(r'[^\d]', '', texto)
    
    if len(numeros) == 14:
        return None
    
    if len(numeros) >= 11:
        for i in range(len(numeros) - 10):
            cpf_candidato = numeros[i:i+11]
            if validar_cpf_rapido(cpf_candidato):
                return cpf_candidato
    
    return None


def validar_cpf_rapido(cpf):
    """Validação rápida de CPF."""
    if not cpf or len(cpf) != 11 or cpf == cpf[0] * 11:
        return False
    
    soma1 = sum(int(cpf[i]) * (10 - i) for i in range(9))
    d1 = 0 if soma1 % 11 < 2 else 11 - (soma1 % 11)
    
    soma2 = sum(int(cpf[i]) * (11 - i) for i in range(10))
    d2 = 0 if soma2 % 11 < 2 else 11 - (soma2 % 11)
    
    return cpf[-2:] == f"{d1}{d2}"


def buscar_mensagens_conversa(conversation_id, api_key):
    """Busca mensagens da conversa."""
    if not api_key:
        return None
    
    url = f"{CRM_API_BASE}/api/v1/conversations/{conversation_id}/messages"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Connection": "keep-alive"
    }
    
    try:
        response = crm_session.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        messages = data.get('messages', data.get('data', [])) if isinstance(data, dict) else data
        
        if isinstance(messages, list):
            return [m for m in messages if m.get('received') == True]
        return messages
    except:
        return None


def consultar_cpf(cpf):
    """Consulta CPF na API."""
    token = config.get('cpf_api_token') or CPF_API_TOKEN
    if not token:
        return None
    
    url = f"https://api.cpf-brasil.org/cpf/{cpf}"
    headers = {
        "X-API-Key": token,
        "Content-Type": "application/json",
        "Connection": "keep-alive"
    }
    
    try:
        response = cpf_session.get(url, headers=headers, timeout=15)
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                return data.get('data')
        return None
    except:
        return None


def enviar_mensagem_conversa(conversation_id, mensagem, api_key):
    """Envia mensagem para uma conversa."""
    if not api_key:
        return None
    
    url = f"{CRM_API_BASE}/api/v1/conversations/{conversation_id}/messages"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Connection": "keep-alive"
    }
    
    try:
        response = crm_session.post(url, headers=headers, json={"body": mensagem}, timeout=10)
        response.raise_for_status()
        return response.json()
    except:
        return None


def formatar_cpf(cpf, formato='mascarado'):
    """Formata o CPF."""
    if formato == 'completo':
        return f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"
    elif formato == 'parcial':
        return f"***{cpf[3:9]}**"
    return f"{cpf[:3]}.***.**{cpf[-4:-2]}-{cpf[-2:]}"


def formatar_mensagem(dados_cpf, cpf, account):
    """Formata a mensagem de resposta usando template da conta."""
    template = account.get('message_template', DEFAULT_TEMPLATE)
    msg_erro = account.get('msg_erro', "Desculpe, não foi possível consultar os dados do CPF informado.")
    formato = account.get('formato_cpf', 'mascarado')
    
    if not dados_cpf:
        return msg_erro
    
    dados = {
        'cpf': f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}",
        'cpf_mascarado': formatar_cpf(cpf, formato),
        'nome': dados_cpf.get('NOME', dados_cpf.get('nome', 'Não disponível')),
        'nascimento': dados_cpf.get('NASC', dados_cpf.get('nascimento', '')),
        'sexo': dados_cpf.get('SEXO', dados_cpf.get('sexo', '')),
        'nome_mae': dados_cpf.get('NOME_MAE', dados_cpf.get('nome_mae', ''))
    }
    
    try:
        mensagem = template.format(**dados)
    except KeyError:
        mensagem = DEFAULT_TEMPLATE.format(**dados)
    
    linhas = [l for l in mensagem.split('\n') if not l.strip().endswith(':') or not l.strip()]
    return '\n'.join(linhas)


# ==================== ROTAS ====================

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/health')
def health():
    return jsonify({"status": "ok", "timestamp": datetime.now().isoformat()})


# ==================== ROTAS DE CONTAS ====================

@app.route('/api/accounts', methods=['GET', 'POST'])
def api_accounts():
    """Lista ou cria contas."""
    if request.method == 'GET':
        accounts = load_accounts()
        # Retorna lista sem expor chaves completas
        result = []
        for acc_id, acc in accounts.items():
            result.append({
                'id': acc_id,
                'name': acc.get('name', 'Sem nome'),
                'crm_api_key_preview': '***' + acc.get('crm_api_key', '')[-10:] if len(acc.get('crm_api_key', '')) > 10 else ''
            })
        return jsonify({"success": True, "accounts": result})
    
    # POST - Criar nova conta
    data = request.get_json()
    name = data.get('name', 'Nova Conta')
    crm_api_key = data.get('crm_api_key', '')
    
    accounts = load_accounts()
    
    # Gera ID único
    acc_id = f"acc_{datetime.now().strftime('%Y%m%d%H%M%S')}_{len(accounts)}"
    
    accounts[acc_id] = {
        'name': name,
        'crm_api_key': crm_api_key,
        'message_template': DEFAULT_TEMPLATE,
        'formato_cpf': 'mascarado',
        'msg_erro': 'Desculpe, não foi possível consultar os dados do CPF informado.',
        'created_at': datetime.now().isoformat()
    }
    
    save_accounts(accounts)
    
    return jsonify({"success": True, "account_id": acc_id, "message": "Conta criada!"})


@app.route('/api/accounts/<account_id>', methods=['GET', 'PUT', 'DELETE'])
def api_account(account_id):
    """Gerencia uma conta específica."""
    accounts = load_accounts()
    
    if account_id not in accounts:
        return jsonify({"success": False, "error": "Conta não encontrada"}), 404
    
    if request.method == 'GET':
        acc = accounts[account_id].copy()
        acc['id'] = account_id
        # Mascara a chave
        if len(acc.get('crm_api_key', '')) > 10:
            acc['crm_api_key_preview'] = '***' + acc['crm_api_key'][-10:]
        return jsonify({"success": True, "account": acc})
    
    if request.method == 'PUT':
        data = request.get_json()
        
        if 'name' in data:
            accounts[account_id]['name'] = data['name']
        if 'crm_api_key' in data and data['crm_api_key']:
            accounts[account_id]['crm_api_key'] = data['crm_api_key']
        if 'message_template' in data:
            accounts[account_id]['message_template'] = data['message_template']
        if 'formato_cpf' in data:
            accounts[account_id]['formato_cpf'] = data['formato_cpf']
        if 'msg_erro' in data:
            accounts[account_id]['msg_erro'] = data['msg_erro']
        
        save_accounts(accounts)
        add_log(account_id, 'CONFIG', '-', 'Sucesso', 'Configurações atualizadas')
        
        return jsonify({"success": True, "message": "Conta atualizada!"})
    
    if request.method == 'DELETE':
        del accounts[account_id]
        save_accounts(accounts)
        
        # Remove logs da conta
        logs_data = load_logs()
        if account_id in logs_data:
            del logs_data[account_id]
            save_logs(logs_data)
        
        return jsonify({"success": True, "message": "Conta removida!"})


# ==================== ROTAS DE LOGS ====================

@app.route('/api/accounts/<account_id>/logs', methods=['GET', 'DELETE'])
def api_account_logs(account_id):
    """Gerencia logs de uma conta."""
    logs_data = load_logs()
    
    if request.method == 'DELETE':
        if account_id in logs_data:
            logs_data[account_id] = []
            save_logs(logs_data)
        return jsonify({"success": True, "message": "Logs limpos!"})
    
    account_logs = logs_data.get(account_id, [])
    return jsonify({"success": True, "logs": account_logs[:100]})


# ==================== CONFIGURAÇÃO GLOBAL ====================

@app.route('/api/config', methods=['GET', 'POST'])
def api_config():
    """Configuração global (token CPF)."""
    if request.method == 'GET':
        return jsonify({
            'cpf_api_token': '***' + config.get('cpf_api_token', '')[-10:] if len(config.get('cpf_api_token', '')) > 10 else ''
        })
    
    data = request.get_json()
    if 'cpf_api_token' in data and data['cpf_api_token']:
        config['cpf_api_token'] = data['cpf_api_token']
    
    return jsonify({"success": True, "message": "Configuração salva!"})


# ==================== GERAR JAVASCRIPT ====================

@app.route('/api/accounts/<account_id>/javascript', methods=['GET'])
def gerar_javascript(account_id):
    """Gera código JavaScript para uma conta."""
    accounts = load_accounts()
    
    if account_id not in accounts:
        return jsonify({"success": False, "error": "Conta não encontrada"}), 404
    
    acc = accounts[account_id]
    # Usa a URL do request, garantindo HTTPS em produção
    api_url = request.host_url.rstrip('/')
    # Força HTTPS se não for localhost
    if 'localhost' not in api_url and '127.0.0.1' not in api_url:
        api_url = api_url.replace('http://', 'https://')
    api_key = acc.get('crm_api_key', '')
    
    codigo = f'''(async () => {{
    const conversationId = await session.getValue('conversationId');
    const leadPhone = await session.getValue('leadPhone');
    const leadName = await session.getValue('leadName');
    
    let mensagem = null;
    try {{ mensagem = await session.getValue('lastMessage.body'); }} catch (e) {{}}
    if (!mensagem) {{
        try {{
            const lm = await session.getValue('lastMessage');
            if (lm) mensagem = lm.body || lm.text || lm;
        }} catch (e) {{}}
    }}
    
    if (!conversationId) return;
    
    const response = await fetch('{api_url}/api/webhook/datacrazy', {{
        method: 'POST',
        headers: {{ 
            'Content-Type': 'application/json',
            'X-CRM-API-Key': '{api_key}'
        }},
        body: JSON.stringify({{ conversationId, leadPhone, leadName, mensagem }})
    }});
    
    const data = await response.json();
    console.log('Resposta:', JSON.stringify(data));
}})();'''
    
    return jsonify({"success": True, "javascript": codigo})


# ==================== WEBHOOK PRINCIPAL ====================

@app.route('/api/webhook/datacrazy', methods=['POST'])
def webhook_datacrazy():
    """Endpoint principal - identifica conta pela chave de API."""
    try:
        data = request.get_json(force=True) if request.data else {}
        
        # Pega a chave de API do header ou do corpo
        api_key = request.headers.get('X-CRM-API-Key') or data.get('crm_api_key', '')
        
        # Encontra a conta pela chave
        account_id, account = get_account_by_api_key(api_key)
        
        if not account:
            return jsonify({"success": False, "error": "Conta não encontrada para esta chave de API"}), 401
        
        conversation_id = data.get('conversationId')
        lead_phone = data.get('leadPhone', '')
        lead_name = data.get('leadName', '')
        mensagem_direta = data.get('mensagem')
        
        if not conversation_id:
            add_log(account_id, 'WEBHOOK', '-', 'Erro', 'conversationId não fornecido', lead_phone, lead_name)
            return jsonify({"success": False, "error": "conversationId é obrigatório"}), 400
        
        # Extrai CPF
        cpf = extrair_cpf(mensagem_direta) if mensagem_direta else None
        
        if not cpf:
            mensagens = buscar_mensagens_conversa(conversation_id, api_key)
            
            if mensagens:
                try:
                    mensagens = sorted(mensagens, key=lambda x: x.get('createdAt', ''), reverse=True)
                except:
                    pass
                
                for msg in mensagens[:10]:
                    body = msg.get('body', '')
                    if body:
                        cpf = extrair_cpf(body)
                        if cpf:
                            break
        
        if not cpf:
            add_log(account_id, 'CONSULTA', '-', 'Erro', 'CPF não encontrado', lead_phone, lead_name)
            return jsonify({"success": False, "error": "CPF não encontrado nas mensagens"}), 404
        
        if not validar_cpf_rapido(cpf):
            add_log(account_id, 'CONSULTA', cpf, 'Erro', 'CPF inválido', lead_phone, lead_name)
            return jsonify({"success": False, "error": "CPF inválido", "cpf_encontrado": cpf}), 400
        
        # Consulta CPF
        dados_cpf = consultar_cpf(cpf)
        mensagem_resposta = formatar_mensagem(dados_cpf, cpf, account)
        
        # Envia mensagem
        resultado_envio = enviar_mensagem_conversa(conversation_id, mensagem_resposta, api_key)
        
        # Log
        nome_titular = dados_cpf.get('NOME', dados_cpf.get('nome', '')) if dados_cpf else ''
        if resultado_envio:
            add_log(account_id, 'CONSULTA', cpf, 'Sucesso', f'Titular: {nome_titular}', lead_phone, lead_name)
        else:
            add_log(account_id, 'CONSULTA', cpf, 'Parcial', f'Titular: {nome_titular} (msg não enviada)', lead_phone, lead_name)
        
        return jsonify({
            "success": True,
            "cpf": cpf,
            "cpf_valido": True,
            "dados": dados_cpf,
            "mensagem_formatada": mensagem_resposta,
            "conversationId": conversation_id,
            "mensagem_enviada": resultado_envio is not None,
            "account": account.get('name')
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ==================== CONSULTA DIRETA ====================

@app.route('/api/consultar-cpf', methods=['POST'])
def consultar_cpf_endpoint():
    try:
        data = request.get_json()
        cpf_raw = data.get('cpf', '')
        cpf = re.sub(r'[^\d]', '', cpf_raw)
        
        if len(cpf) != 11:
            return jsonify({"success": False, "error": "CPF deve ter 11 dígitos"}), 400
        
        if not validar_cpf_rapido(cpf):
            return jsonify({"success": False, "error": "CPF inválido"}), 400
        
        dados = consultar_cpf(cpf)
        
        return jsonify({
            "success": True if dados else False,
            "cpf": cpf,
            "dados": dados
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ==================== ESTATÍSTICAS ====================

@app.route('/api/accounts/<account_id>/stats')
def api_account_stats(account_id):
    """Estatísticas de uma conta."""
    logs_data = load_logs()
    account_logs = logs_data.get(account_id, [])
    
    total = len(account_logs)
    sucesso = len([l for l in account_logs if l['status'] == 'Sucesso'])
    
    return jsonify({
        "total_consultas": total,
        "msg_enviadas": sucesso,
        "taxa_sucesso": f"{(sucesso/total*100):.0f}%" if total > 0 else "100%"
    })


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 3000))
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)

"""
API de Consulta de CPF para CRM DataCrazy
=========================================
Sistema Multi-Conta com Logs Persistentes (CORRIGIDO)

Correções aplicadas:
- Removido limite de 500 logs por conta (agora ilimitado)
- Removido limite de 100 logs na exibição (agora com paginação)
- Adicionado endpoint de exportação CSV
- Adicionado endpoint para logs completos (sem limite)
- Adicionada paginação na API de logs

Variáveis de ambiente:
- CPF_API_TOKEN: Token da API de CPF (cpf-brasil.org)
- SECRET_KEY: Chave secreta para o painel (opcional)
- MAX_LOGS_PER_ACCOUNT: Limite máximo de logs por conta (padrão: 0 = ilimitado)
"""

from flask import Flask, request, jsonify, render_template, Response
from flask_cors import CORS
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import re
import os
import json
import io
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import threading

app = Flask(__name__)
CORS(app)

# ==================== CONFIGURAÇÕES ====================

DATA_DIR = os.environ.get('DATA_DIR', '/app/storage')
os.makedirs(DATA_DIR, exist_ok=True)

CRM_API_BASE = "https://api.g1.datacrazy.io"
CPF_API_TOKEN = os.environ.get('CPF_API_TOKEN', '')
SECRET_KEY = os.environ.get('SECRET_KEY', 'admin123')

# CORREÇÃO: Limite configurável de logs (0 = ilimitado)
MAX_LOGS_PER_ACCOUNT = int(os.environ.get('MAX_LOGS_PER_ACCOUNT', '0'))

DEFAULT_TEMPLATE = """Olá! Encontrei os dados do CPF consultado:

CPF: {cpf_mascarado}
Nome: {nome}
Nascimento: {nascimento}
Sexo: {sexo}
Mãe: {nome_mae}

Caso precise de mais informações, estou à disposição."""

DEFAULT_CNPJ_TEMPLATE = """Olá! Encontrei os dados do CNPJ consultado:

CNPJ: {cnpj}
Razão Social: {razao_social}

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
cnpj_session = criar_sessao_otimizada()

# ==================== SISTEMA MULTI-CONTA ====================

accounts_lock = threading.Lock()
logs_lock = threading.Lock()

def get_accounts_file():
    return os.path.join(DATA_DIR, 'accounts.json')

def get_logs_file():
    return os.path.join(DATA_DIR, 'logs.json')

def load_accounts():
    try:
        with open(get_accounts_file(), 'r') as f:
            accounts = json.load(f)
            for acc in accounts.values():
                acc.setdefault('cnpj_message_template', DEFAULT_CNPJ_TEMPLATE)
                acc.setdefault('msg_erro_cnpj', 'Desculpe, não foi possível consultar os dados do CNPJ informado.')
            return accounts
    except:
        return {}

def save_accounts(accounts):
    with accounts_lock:
        with open(get_accounts_file(), 'w') as f:
            json.dump(accounts, f, ensure_ascii=False, indent=2)

def load_logs():
    try:
        with open(get_logs_file(), 'r') as f:
            return json.load(f)
    except:
        return {}

def save_logs(logs_data):
    with logs_lock:
        with open(get_logs_file(), 'w') as f:
            json.dump(logs_data, f, ensure_ascii=False, indent=2)

def get_account(account_id):
    accounts = load_accounts()
    return accounts.get(account_id)

def get_account_by_api_key(api_key):
    accounts = load_accounts()
    for acc_id, acc in accounts.items():
        if acc.get('crm_api_key') == api_key:
            return acc_id, acc
    return None, None

def add_log(account_id, tipo, cpf, status, detalhes='', lead_phone='', lead_name='', account_name=''):
    """Adiciona um log para uma conta específica."""
    logs_data = load_logs()
    
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
    
    # CORREÇÃO: Limite configurável (0 = sem limite, antes era fixo em 500)
    if MAX_LOGS_PER_ACCOUNT > 0 and len(logs_data[account_id]) > MAX_LOGS_PER_ACCOUNT:
        logs_data[account_id] = logs_data[account_id][:MAX_LOGS_PER_ACCOUNT]
    
    save_logs(logs_data)

# ==================== CONFIGURAÇÃO GLOBAL ====================

config = {
    'cpf_api_token': CPF_API_TOKEN
}

# ==================== FUNÇÕES AUXILIARES ====================

def somente_numeros(texto):
    return re.sub(r'[^\d]', '', texto or '')


def validar_cpf_rapido(cpf):
    cpf = somente_numeros(cpf)
    if not cpf or len(cpf) != 11 or cpf == cpf[0] * 11:
        return False
    soma1 = sum(int(cpf[i]) * (10 - i) for i in range(9))
    d1 = 0 if soma1 % 11 < 2 else 11 - (soma1 % 11)
    soma2 = sum(int(cpf[i]) * (11 - i) for i in range(10))
    d2 = 0 if soma2 % 11 < 2 else 11 - (soma2 % 11)
    return cpf[-2:] == f"{d1}{d2}"


def validar_cnpj_rapido(cnpj):
    cnpj = somente_numeros(cnpj)
    if not cnpj or len(cnpj) != 14 or cnpj == cnpj[0] * 14:
        return False

    pesos_1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    pesos_2 = [6] + pesos_1

    soma1 = sum(int(cnpj[i]) * pesos_1[i] for i in range(12))
    resto1 = soma1 % 11
    d1 = 0 if resto1 < 2 else 11 - resto1

    soma2 = sum(int(cnpj[i]) * pesos_2[i] for i in range(13))
    resto2 = soma2 % 11
    d2 = 0 if resto2 < 2 else 11 - resto2

    return cnpj[-2:] == f"{d1}{d2}"


def detectar_cnpj(texto):
    return extrair_cnpj(texto) is not None


def extrair_cnpj(texto):
    if not texto:
        return None

    padrao_cnpj = r'\d{2}[\.]?\d{3}[\.]?\d{3}[\/]?\d{4}[\-]?\d{2}'
    for match in re.findall(padrao_cnpj, texto):
        cnpj = somente_numeros(match)
        if validar_cnpj_rapido(cnpj):
            return cnpj

    numeros = somente_numeros(texto)
    if len(numeros) == 14 and validar_cnpj_rapido(numeros):
        return numeros

    if len(numeros) > 14:
        for i in range(len(numeros) - 13):
            cnpj_candidato = numeros[i:i+14]
            if validar_cnpj_rapido(cnpj_candidato):
                return cnpj_candidato

    return None


def extrair_cpf(texto):
    if not texto:
        return None

    padrao_cpf = r'\d{3}[\.]?\d{3}[\.]?\d{3}[\-]?\d{2}'
    for match in re.findall(padrao_cpf, texto):
        cpf = somente_numeros(match)
        if validar_cpf_rapido(cpf):
            return cpf

    numeros = somente_numeros(texto)
    if len(numeros) == 11 and validar_cpf_rapido(numeros):
        return numeros

    if len(numeros) > 11:
        for i in range(len(numeros) - 10):
            cpf_candidato = numeros[i:i+11]
            if validar_cpf_rapido(cpf_candidato):
                return cpf_candidato

    return None


def extrair_documento(texto):
    """Retorna uma tupla (tipo, numero), onde tipo é 'cpf' ou 'cnpj'."""
    cnpj = extrair_cnpj(texto)
    if cnpj:
        return 'cnpj', cnpj

    cpf = extrair_cpf(texto)
    if cpf:
        return 'cpf', cpf

    return None, None

def buscar_mensagens_conversa(conversation_id, api_key):
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
            received_messages = [m for m in messages if m.get('received') == True]
            if received_messages:
                received_messages.sort(key=lambda x: x.get('createdAt', x.get('timestamp', '')), reverse=True)
                return received_messages[:3]
            return []
        return messages
    except:
        return None

def consultar_cpf(cpf):
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


def consultar_cnpj(cnpj):
    cnpj = somente_numeros(cnpj)
    if not validar_cnpj_rapido(cnpj):
        return None

    url = f"https://brasilapi.com.br/api/cnpj/v1/{cnpj}"
    headers = {
        "Content-Type": "application/json",
        "Connection": "keep-alive",
        "User-Agent": "apicpf2-cpf-cnpj/1.0"
    }
    try:
        response = cnpj_session.get(url, headers=headers, timeout=15)
        if response.status_code == 200:
            return response.json()
        return None
    except:
        return None

def enviar_mensagem_conversa(conversation_id, mensagem, api_key):
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
    if formato == 'completo':
        return f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"
    elif formato == 'parcial':
        return f"***{cpf[3:9]}**"
    return f"{cpf[:3]}.***.**{cpf[-4:-2]}-{cpf[-2:]}"


def formatar_cnpj(cnpj):
    cnpj = somente_numeros(cnpj)
    if len(cnpj) != 14:
        return cnpj
    return f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}"


def formatar_mensagem(dados_cpf, cpf, account):
    template = account.get('message_template', DEFAULT_TEMPLATE)
    msg_erro = account.get('msg_erro', "Desculpe, não foi possível consultar os dados do CPF informado.")
    formato = account.get('formato_cpf', 'mascarado')
    
    if not dados_cpf:
        return msg_erro
    
    nome_original = dados_cpf.get('NOME', dados_cpf.get('nome', 'Não disponível'))
    nome_maiusculo = nome_original.upper() if nome_original else 'NÃO DISPONÍVEL'
    nome_mae_original = dados_cpf.get('NOME_MAE', dados_cpf.get('nome_mae', ''))
    nome_mae_maiusculo = nome_mae_original.upper() if nome_mae_original else ''
    
    dados = {
        'cpf': f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}",
        'cpf_mascarado': formatar_cpf(cpf, formato),
        'nome': nome_maiusculo,
        'nascimento': dados_cpf.get('NASC', dados_cpf.get('nascimento', '')),
        'sexo': dados_cpf.get('SEXO', dados_cpf.get('sexo', '')),
        'nome_mae': nome_mae_maiusculo
    }
    
    try:
        mensagem = template.format(**dados)
    except KeyError:
        mensagem = DEFAULT_TEMPLATE.format(**dados)
    
    linhas = [l for l in mensagem.split('\n') if not l.strip().endswith(':') or not l.strip()]
    return '\n'.join(linhas)


def formatar_mensagem_cnpj(dados_cnpj, cnpj, account):
    template = account.get('cnpj_message_template', DEFAULT_CNPJ_TEMPLATE)
    msg_erro = account.get('msg_erro_cnpj', "Desculpe, não foi possível consultar os dados do CNPJ informado.")

    if not dados_cnpj:
        return msg_erro

    dados = {
        'cnpj': formatar_cnpj(cnpj),
        'cnpj_numeros': somente_numeros(cnpj),
        'razao_social': dados_cnpj.get('razao_social') or dados_cnpj.get('nome') or 'Não disponível'
    }

    try:
        mensagem = template.format(**dados)
    except KeyError:
        mensagem = DEFAULT_CNPJ_TEMPLATE.format(**dados)

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
    if request.method == 'GET':
        accounts = load_accounts()
        result = []
        for acc_id, acc in accounts.items():
            result.append({
                'id': acc_id,
                'name': acc.get('name', 'Sem nome'),
                'crm_api_key_preview': '***' + acc.get('crm_api_key', '')[-10:] if len(acc.get('crm_api_key', '')) > 10 else ''
            })
        return jsonify({"success": True, "accounts": result})
    
    data = request.get_json()
    name = data.get('name', 'Nova Conta')
    crm_api_key = data.get('crm_api_key', '')
    accounts = load_accounts()
    acc_id = f"acc_{datetime.now().strftime('%Y%m%d%H%M%S')}_{len(accounts)}"
    accounts[acc_id] = {
        'name': name,
        'crm_api_key': crm_api_key,
        'message_template': DEFAULT_TEMPLATE,
        'cnpj_message_template': DEFAULT_CNPJ_TEMPLATE,
        'formato_cpf': 'mascarado',
        'msg_erro': 'Desculpe, não foi possível consultar os dados do CPF informado.',
        'msg_erro_cnpj': 'Desculpe, não foi possível consultar os dados do CNPJ informado.',
        'created_at': datetime.now().isoformat()
    }
    save_accounts(accounts)
    return jsonify({"success": True, "account_id": acc_id, "message": "Conta criada!"})

@app.route('/api/accounts/<account_id>', methods=['GET', 'PUT', 'DELETE'])
def api_account(account_id):
    accounts = load_accounts()
    if account_id not in accounts:
        return jsonify({"success": False, "error": "Conta não encontrada"}), 404
    
    if request.method == 'GET':
        acc = accounts[account_id].copy()
        acc['id'] = account_id
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
        if 'cnpj_message_template' in data:
            accounts[account_id]['cnpj_message_template'] = data['cnpj_message_template']
        if 'formato_cpf' in data:
            accounts[account_id]['formato_cpf'] = data['formato_cpf']
        if 'msg_erro' in data:
            accounts[account_id]['msg_erro'] = data['msg_erro']
        if 'msg_erro_cnpj' in data:
            accounts[account_id]['msg_erro_cnpj'] = data['msg_erro_cnpj']
        save_accounts(accounts)
        add_log(account_id, 'CONFIG', '-', 'Sucesso', 'Configurações atualizadas')
        return jsonify({"success": True, "message": "Conta atualizada!"})
    
    if request.method == 'DELETE':
        del accounts[account_id]
        save_accounts(accounts)
        logs_data = load_logs()
        if account_id in logs_data:
            del logs_data[account_id]
            save_logs(logs_data)
        return jsonify({"success": True, "message": "Conta removida!"})


# ==================== ROTAS DE LOGS (CORRIGIDO) ====================

@app.route('/api/accounts/<account_id>/logs', methods=['GET', 'DELETE'])
def api_account_logs(account_id):
    """Gerencia logs de uma conta - AGORA COM PAGINAÇÃO E SEM LIMITE."""
    logs_data = load_logs()
    
    if request.method == 'DELETE':
        if account_id in logs_data:
            logs_data[account_id] = []
            save_logs(logs_data)
        return jsonify({"success": True, "message": "Logs limpos!"})
    
    account_logs = logs_data.get(account_id, [])
    
    # CORREÇÃO: Paginação
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    show_all = request.args.get('all', 'false').lower() == 'true'
    
    # Filtros opcionais
    status_filter = request.args.get('status', '').strip()
    search_filter = request.args.get('search', '').strip().lower()
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()
    
    filtered_logs = account_logs
    
    if status_filter:
        filtered_logs = [l for l in filtered_logs if l.get('status', '').lower() == status_filter.lower()]
    
    if search_filter:
        filtered_logs = [l for l in filtered_logs if 
            search_filter in l.get('cpf', '').lower() or
            search_filter in l.get('lead_name', '').lower() or
            search_filter in l.get('lead_phone', '').lower() or
            search_filter in l.get('detalhes', '').lower() or
            search_filter in l.get('account_name', '').lower()
        ]
    
    if date_from:
        try:
            date_from_dt = datetime.strptime(date_from, '%Y-%m-%d')
            filtered_logs = [l for l in filtered_logs if 
                datetime.strptime(l.get('data', '01/01/2000 00:00:00'), '%d/%m/%Y %H:%M:%S') >= date_from_dt
            ]
        except:
            pass
    
    if date_to:
        try:
            date_to_dt = datetime.strptime(date_to + ' 23:59:59', '%Y-%m-%d %H:%M:%S')
            filtered_logs = [l for l in filtered_logs if 
                datetime.strptime(l.get('data', '01/01/2000 00:00:00'), '%d/%m/%Y %H:%M:%S') <= date_to_dt
            ]
        except:
            pass
    
    total = len(filtered_logs)
    
    if show_all:
        return jsonify({
            "success": True, 
            "logs": filtered_logs,
            "total": total,
            "showing": "all"
        })
    
    per_page = min(per_page, 500)
    start = (page - 1) * per_page
    end = start + per_page
    total_pages = (total + per_page - 1) // per_page if per_page > 0 else 1
    
    return jsonify({
        "success": True, 
        "logs": filtered_logs[start:end],
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
        "has_next": page < total_pages,
        "has_prev": page > 1
    })


# ==================== EXPORTAÇÃO TXT (NOVO) ====================

@app.route('/api/accounts/<account_id>/logs/export', methods=['GET'])
def export_account_logs(account_id):
    """Exporta TODOS os logs de uma conta em TXT."""
    logs_data = load_logs()
    account_logs = logs_data.get(account_id, [])
    
    status_filter = request.args.get('status', '').strip()
    search_filter = request.args.get('search', '').strip().lower()
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()
    
    filtered_logs = account_logs
    
    if status_filter:
        filtered_logs = [l for l in filtered_logs if l.get('status', '').lower() == status_filter.lower()]
    if search_filter:
        filtered_logs = [l for l in filtered_logs if 
            search_filter in l.get('cpf', '').lower() or
            search_filter in l.get('lead_name', '').lower() or
            search_filter in l.get('lead_phone', '').lower() or
            search_filter in l.get('detalhes', '').lower()
        ]
    if date_from:
        try:
            date_from_dt = datetime.strptime(date_from, '%Y-%m-%d')
            filtered_logs = [l for l in filtered_logs if 
                datetime.strptime(l.get('data', '01/01/2000 00:00:00'), '%d/%m/%Y %H:%M:%S') >= date_from_dt
            ]
        except:
            pass
    if date_to:
        try:
            date_to_dt = datetime.strptime(date_to + ' 23:59:59', '%Y-%m-%d %H:%M:%S')
            filtered_logs = [l for l in filtered_logs if 
                datetime.strptime(l.get('data', '01/01/2000 00:00:00'), '%d/%m/%Y %H:%M:%S') <= date_to_dt
            ]
        except:
            pass
    
    # Gera TXT formatado
    acc = get_account(account_id)
    account_name = acc.get('name', 'conta') if acc else 'conta'
    
    lines = []
    lines.append('=' * 60)
    lines.append(f'  LOGS DE CONSULTAS - {account_name.upper()}')
    lines.append(f'  Exportado em: {datetime.now().strftime("%d/%m/%Y %H:%M:%S")}')
    lines.append(f'  Total de registros: {len(filtered_logs)}')
    lines.append('=' * 60)
    lines.append('')
    
    for i, log in enumerate(filtered_logs, 1):
        lines.append(f'--- Consulta #{i} ---')
        lines.append(f'Data/Hora:  {log.get("data", "-")}')
        lines.append(f'Lead:       {log.get("lead_name", "-")}')
        lines.append(f'Telefone:   {log.get("lead_phone", "-")}')
        lines.append(f'Documento:  {log.get("cpf", "-")}')
        lines.append(f'Status:     {log.get("status", "-")}')
        lines.append(f'Detalhes:   {log.get("detalhes", "-")}')
        lines.append('')
    
    lines.append('=' * 60)
    lines.append(f'  FIM - {len(filtered_logs)} registros exportados')
    lines.append('=' * 60)
    
    output = '\n'.join(lines)
    
    safe_name = re.sub(r'[^\w\-]', '_', account_name)
    filename = f"logs_{safe_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    
    return Response(
        output,
        mimetype='text/plain',
        headers={
            'Content-Disposition': f'attachment; filename={filename}',
            'Content-Type': 'text/plain; charset=utf-8'
        }
    )


# ==================== CONFIGURAÇÃO GLOBAL ====================

@app.route('/api/config', methods=['GET', 'POST'])
def api_config():
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
    accounts = load_accounts()
    if account_id not in accounts:
        return jsonify({"success": False, "error": "Conta não encontrada"}), 404
    
    acc = accounts[account_id]
    api_url = request.host_url.rstrip('/')
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
    try:
        data = request.get_json(force=True) if request.data else {}
        api_key = request.headers.get('X-CRM-API-Key') or data.get('crm_api_key', '')
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
        
        documento_tipo, documento = extrair_documento(mensagem_direta) if mensagem_direta else (None, None)
        
        if not documento:
            mensagens = buscar_mensagens_conversa(conversation_id, api_key)
            if mensagens:
                try:
                    mensagens = sorted(mensagens, key=lambda x: x.get('createdAt', ''), reverse=True)
                except:
                    pass
                for msg in mensagens[:10]:
                    body = msg.get('body', '')
                    if body:
                        documento_tipo, documento = extrair_documento(body)
                        if documento:
                            break
        
        if not documento:
            add_log(account_id, 'CONSULTA', '-', 'Erro', 'CPF/CNPJ não encontrado', lead_phone, lead_name)
            return jsonify({"success": False, "error": "CPF ou CNPJ não encontrado nas mensagens"}), 404
        
        if documento_tipo == 'cnpj':
            if not validar_cnpj_rapido(documento):
                add_log(account_id, 'CONSULTA', documento, 'Erro', 'CNPJ inválido', lead_phone, lead_name)
                return jsonify({"success": False, "error": "CNPJ inválido", "cnpj_encontrado": documento}), 400

            dados_cnpj = consultar_cnpj(documento)
            mensagem_resposta = formatar_mensagem_cnpj(dados_cnpj, documento, account)
            resultado_envio = enviar_mensagem_conversa(conversation_id, mensagem_resposta, api_key)
            razao_social = dados_cnpj.get('razao_social', '') if dados_cnpj else ''

            if resultado_envio:
                add_log(account_id, 'CONSULTA', documento, 'Sucesso', f'Razão Social: {razao_social}', lead_phone, lead_name)
            else:
                add_log(account_id, 'CONSULTA', documento, 'Parcial', f'Razão Social: {razao_social} (msg não enviada)', lead_phone, lead_name)

            return jsonify({
                "success": True,
                "tipo": "cnpj",
                "cnpj": documento,
                "cnpj_formatado": formatar_cnpj(documento),
                "cnpj_valido": True,
                "razao_social": razao_social,
                "dados": {
                    "cnpj": documento,
                    "cnpj_formatado": formatar_cnpj(documento),
                    "razao_social": razao_social
                } if dados_cnpj else None,
                "mensagem_formatada": mensagem_resposta,
                "conversationId": conversation_id,
                "mensagem_enviada": resultado_envio is not None,
                "account": account.get('name')
            })
        
        cpf = documento
        if not validar_cpf_rapido(cpf):
            add_log(account_id, 'CONSULTA', cpf, 'Erro', 'CPF inválido', lead_phone, lead_name)
            return jsonify({"success": False, "error": "CPF inválido", "cpf_encontrado": cpf}), 400
        
        dados_cpf = consultar_cpf(cpf)
        mensagem_resposta = formatar_mensagem(dados_cpf, cpf, account)
        resultado_envio = enviar_mensagem_conversa(conversation_id, mensagem_resposta, api_key)
        
        nome_titular = dados_cpf.get('NOME', dados_cpf.get('nome', '')) if dados_cpf else ''
        if resultado_envio:
            add_log(account_id, 'CONSULTA', cpf, 'Sucesso', f'Titular: {nome_titular}', lead_phone, lead_name)
        else:
            add_log(account_id, 'CONSULTA', cpf, 'Parcial', f'Titular: {nome_titular} (msg não enviada)', lead_phone, lead_name)
        
        return jsonify({
            "success": True,
            "tipo": "cpf",
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
        data = request.get_json() or {}
        documento_raw = data.get('documento') or data.get('cpf') or data.get('cnpj') or ''
        documento_tipo, documento = extrair_documento(documento_raw)

        if not documento:
            return jsonify({"success": False, "error": "Informe um CPF ou CNPJ válido"}), 400

        if documento_tipo == 'cnpj':
            if not validar_cnpj_rapido(documento):
                return jsonify({"success": False, "error": "CNPJ inválido"}), 400
            dados = consultar_cnpj(documento)
            razao_social = dados.get('razao_social') if dados else None
            return jsonify({
                "success": True if dados else False,
                "tipo": "cnpj",
                "cnpj": documento,
                "cnpj_formatado": formatar_cnpj(documento),
                "razao_social": razao_social,
                "dados": {
                    "cnpj": documento,
                    "cnpj_formatado": formatar_cnpj(documento),
                    "razao_social": razao_social
                } if dados else None
            })

        if not validar_cpf_rapido(documento):
            return jsonify({"success": False, "error": "CPF inválido"}), 400
        dados = consultar_cpf(documento)
        return jsonify({
            "success": True if dados else False,
            "tipo": "cpf",
            "cpf": documento,
            "dados": dados
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ==================== ESTATÍSTICAS ====================

@app.route('/api/accounts/<account_id>/stats')
def api_account_stats(account_id):
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

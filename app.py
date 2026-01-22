"""
API de Consulta de CPF para CRM DataCrazy
=========================================
Painel de Administração Completo - VERSÃO OTIMIZADA

Variáveis de ambiente:
- CRM_API_KEY: Chave da API do CRM DataCrazy
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
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

app = Flask(__name__)
CORS(app)

# ==================== OTIMIZAÇÕES DE VELOCIDADE ====================

# Pool de threads para requisições paralelas
executor = ThreadPoolExecutor(max_workers=10)

# Sessões HTTP persistentes com connection pooling
def criar_sessao_otimizada():
    """Cria uma sessão HTTP otimizada com retry e keep-alive."""
    session = requests.Session()
    
    # Configuração de retry
    retry_strategy = Retry(
        total=2,
        backoff_factor=0.1,
        status_forcelist=[500, 502, 503, 504]
    )
    
    # Adapter com pool de conexões
    adapter = HTTPAdapter(
        max_retries=retry_strategy,
        pool_connections=20,
        pool_maxsize=20
    )
    
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    
    return session

# Sessões globais reutilizáveis
crm_session = criar_sessao_otimizada()
cpf_session = criar_sessao_otimizada()

# ==================== CONFIGURAÇÕES ====================

CRM_API_BASE = "https://api.g1.datacrazy.io"
CRM_API_KEY = os.environ.get('CRM_API_KEY', '')
CPF_API_TOKEN = os.environ.get('CPF_API_TOKEN', '')
SECRET_KEY = os.environ.get('SECRET_KEY', 'admin123')

DEFAULT_TEMPLATE = """Olá! Encontrei os dados do CPF consultado:

CPF: {cpf_mascarado}
Nome: {nome}
Nascimento: {nascimento}
Sexo: {sexo}
Mãe: {nome_mae}

Caso precise de mais informações, estou à disposição."""

config = {
    'crm_api_key': CRM_API_KEY,
    'cpf_api_token': CPF_API_TOKEN,
    'message_template': DEFAULT_TEMPLATE,
    'campos_exibir': ['cpf_mascarado', 'nome', 'nascimento', 'sexo', 'nome_mae'],
    'saudacao': 'Olá! Encontrei os dados do CPF consultado:',
    'msg_final': 'Caso precise de mais informações, estou à disposição.',
    'msg_erro': 'Desculpe, não foi possível consultar os dados do CPF informado. Por favor, verifique se o número está correto e tente novamente.',
    'formato_cpf': 'mascarado',
    'usar_emojis': False
}

logs = []
logs_lock = threading.Lock()

def add_log(tipo, cpf, status, detalhes='', lead_phone='', lead_name=''):
    """Adiciona um log de atividade (thread-safe)."""
    with logs_lock:
        logs.insert(0, {
            'data': datetime.now().strftime('%d/%m/%Y %H:%M:%S'),
            'tipo': tipo,
            'cpf': cpf if cpf else '-',
            'status': status,
            'detalhes': detalhes,
            'lead_phone': lead_phone or '-',
            'lead_name': lead_name or '-'
        })
        if len(logs) > 100:
            logs.pop()


# ==================== FUNÇÕES OTIMIZADAS ====================

def extrair_cpf(texto):
    """Extrai CPF de um texto (otimizado)."""
    if not texto:
        return None
    
    # Remove caracteres não numéricos e busca sequência de 11 dígitos
    numeros = re.sub(r'[^\d]', '', texto)
    
    # Busca CPF na string de números
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
    
    # Cálculo otimizado dos dígitos verificadores
    soma1 = sum(int(cpf[i]) * (10 - i) for i in range(9))
    d1 = 0 if soma1 % 11 < 2 else 11 - (soma1 % 11)
    
    soma2 = sum(int(cpf[i]) * (11 - i) for i in range(10))
    d2 = 0 if soma2 % 11 < 2 else 11 - (soma2 % 11)
    
    return cpf[-2:] == f"{d1}{d2}"


def buscar_mensagens_conversa(conversation_id):
    """Busca mensagens da conversa (otimizado com sessão persistente)."""
    if not config['crm_api_key']:
        return None
    
    url = f"{CRM_API_BASE}/api/v1/conversations/{conversation_id}/messages"
    headers = {
        "Authorization": f"Bearer {config['crm_api_key']}",
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
    """Consulta CPF (otimizado com sessão persistente e timeout curto)."""
    if not config['cpf_api_token']:
        return None
    
    url = f"https://api.cpf-brasil.org/cpf/{cpf}"
    headers = {
        "X-API-Key": config['cpf_api_token'],
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


def enviar_mensagem_conversa(conversation_id, mensagem):
    """Envia mensagem (otimizado com sessão persistente)."""
    if not config['crm_api_key']:
        return None
    
    url = f"{CRM_API_BASE}/api/v1/conversations/{conversation_id}/messages"
    headers = {
        "Authorization": f"Bearer {config['crm_api_key']}",
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


def formatar_mensagem(dados_cpf, cpf):
    """Formata a mensagem de resposta."""
    if not dados_cpf:
        return config.get('msg_erro', "Desculpe, não foi possível consultar os dados do CPF informado.")
    
    dados = {
        'cpf': f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}",
        'cpf_mascarado': formatar_cpf(cpf, config.get('formato_cpf', 'mascarado')),
        'nome': dados_cpf.get('NOME', dados_cpf.get('nome', 'Não disponível')),
        'nascimento': dados_cpf.get('NASC', dados_cpf.get('nascimento', '')),
        'sexo': dados_cpf.get('SEXO', dados_cpf.get('sexo', '')),
        'nome_mae': dados_cpf.get('NOME_MAE', dados_cpf.get('nome_mae', ''))
    }
    
    try:
        mensagem = config['message_template'].format(**dados)
    except KeyError:
        mensagem = DEFAULT_TEMPLATE.format(**dados)
    
    # Remove linhas vazias
    linhas = [l for l in mensagem.split('\n') if not l.strip().endswith(':') or not l.strip()]
    return '\n'.join(linhas)


# ==================== ROTAS ====================

@app.route('/')
def index():
    return render_template('index.html', config=config)


@app.route('/health')
def health():
    return jsonify({"status": "ok", "timestamp": datetime.now().isoformat()})


@app.route('/api/config', methods=['GET', 'POST'])
def api_config():
    if request.method == 'GET':
        return jsonify({
            'crm_api_key': '***' + config['crm_api_key'][-10:] if len(config['crm_api_key']) > 10 else '',
            'cpf_api_token': '***' + config['cpf_api_token'][-10:] if len(config['cpf_api_token']) > 10 else '',
            'message_template': config['message_template'],
            'campos_exibir': config['campos_exibir'],
            'saudacao': config.get('saudacao', ''),
            'msg_final': config.get('msg_final', ''),
            'msg_erro': config.get('msg_erro', ''),
            'formato_cpf': config.get('formato_cpf', 'mascarado'),
            'usar_emojis': config.get('usar_emojis', False)
        })
    
    data = request.get_json()
    
    if data.get('crm_api_key'):
        config['crm_api_key'] = data['crm_api_key']
    if data.get('cpf_api_token'):
        config['cpf_api_token'] = data['cpf_api_token']
    if data.get('message_template'):
        config['message_template'] = data['message_template']
    if data.get('campos_exibir'):
        config['campos_exibir'] = data['campos_exibir']
    if 'saudacao' in data:
        config['saudacao'] = data['saudacao']
    if 'msg_final' in data:
        config['msg_final'] = data['msg_final']
    if 'msg_erro' in data:
        config['msg_erro'] = data['msg_erro']
    if 'formato_cpf' in data:
        config['formato_cpf'] = data['formato_cpf']
    if 'usar_emojis' in data:
        config['usar_emojis'] = data['usar_emojis']
    
    add_log('CONFIG', '-', 'Sucesso', 'Configurações atualizadas')
    return jsonify({"success": True, "message": "Configurações atualizadas!"})


@app.route('/api/logs', methods=['GET', 'DELETE'])
def api_logs():
    if request.method == 'DELETE':
        with logs_lock:
            logs.clear()
        return jsonify({"success": True, "message": "Logs limpos!"})
    
    with logs_lock:
        return jsonify({"success": True, "logs": logs[:50]})


@app.route('/api/stats')
def api_stats():
    with logs_lock:
        total = len(logs)
        sucesso = len([l for l in logs if l['status'] == 'Sucesso'])
    
    return jsonify({
        "total_consultas": total,
        "msg_enviadas": sucesso,
        "taxa_sucesso": f"{(sucesso/total*100):.0f}%" if total > 0 else "100%"
    })


@app.route('/api/gerar-javascript', methods=['POST'])
def gerar_javascript():
    data = request.get_json()
    api_url = data.get('api_url', request.host_url.rstrip('/'))
    
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
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ conversationId, leadPhone, leadName, mensagem }})
    }});
    
    const data = await response.json();
    console.log('Resposta:', JSON.stringify(data));
}})();'''
    
    return jsonify({"success": True, "javascript": codigo})


@app.route('/api/webhook/datacrazy', methods=['POST'])
def webhook_datacrazy():
    """Endpoint principal OTIMIZADO para máxima velocidade."""
    try:
        data = request.get_json(force=True) if request.data else {}
        
        conversation_id = data.get('conversationId')
        lead_phone = data.get('leadPhone', '')
        lead_name = data.get('leadName', '')
        mensagem_direta = data.get('mensagem')
        
        if not conversation_id:
            add_log('WEBHOOK', '-', 'Erro', 'conversationId não fornecido', lead_phone, lead_name)
            return jsonify({"success": False, "error": "conversationId é obrigatório"}), 400
        
        # Tenta extrair CPF da mensagem direta primeiro (mais rápido)
        cpf = extrair_cpf(mensagem_direta) if mensagem_direta else None
        
        # Se não encontrou, busca nas mensagens da conversa
        if not cpf:
            mensagens = buscar_mensagens_conversa(conversation_id)
            
            if mensagens:
                # Ordena por data (mais recente primeiro)
                try:
                    mensagens = sorted(mensagens, key=lambda x: x.get('createdAt', ''), reverse=True)
                except:
                    pass
                
                # Busca CPF nas mensagens mais recentes
                for msg in mensagens[:10]:  # Limita a 10 mensagens para velocidade
                    body = msg.get('body', '')
                    if body:
                        cpf = extrair_cpf(body)
                        if cpf:
                            break
        
        if not cpf:
            add_log('CONSULTA', '-', 'Erro', 'CPF não encontrado', lead_phone, lead_name)
            return jsonify({"success": False, "error": "CPF não encontrado nas mensagens"}), 404
        
        if not validar_cpf_rapido(cpf):
            add_log('CONSULTA', cpf, 'Erro', 'CPF inválido', lead_phone, lead_name)
            return jsonify({"success": False, "error": "CPF inválido", "cpf_encontrado": cpf}), 400
        
        # Consulta CPF e prepara envio em paralelo
        dados_cpf = consultar_cpf(cpf)
        mensagem_resposta = formatar_mensagem(dados_cpf, cpf)
        
        # Envia mensagem
        resultado_envio = enviar_mensagem_conversa(conversation_id, mensagem_resposta)
        
        # Log
        nome_titular = dados_cpf.get('NOME', dados_cpf.get('nome', '')) if dados_cpf else ''
        if resultado_envio:
            add_log('CONSULTA', cpf, 'Sucesso', f'Titular: {nome_titular}', lead_phone, lead_name)
        else:
            add_log('CONSULTA', cpf, 'Parcial', f'Titular: {nome_titular} (msg não enviada)', lead_phone, lead_name)
        
        return jsonify({
            "success": True,
            "cpf": cpf,
            "cpf_valido": True,
            "dados": dados_cpf,
            "mensagem_formatada": mensagem_resposta,
            "conversationId": conversation_id,
            "mensagem_enviada": resultado_envio is not None,
            "resultado_envio": resultado_envio
        })
        
    except Exception as e:
        add_log('WEBHOOK', '-', 'Erro', str(e), '', '')
        return jsonify({"success": False, "error": str(e)}), 500


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
        add_log('TESTE', cpf, 'Sucesso' if dados else 'Erro', 'Consulta direta')
        
        return jsonify({
            "success": True if dados else False,
            "cpf": cpf,
            "dados": dados,
            "mensagem_formatada": formatar_mensagem(dados, cpf) if dados else None
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 3000))
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)

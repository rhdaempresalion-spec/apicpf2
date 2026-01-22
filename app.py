"""
API de Consulta de CPF para CRM DataCrazy
=========================================
Painel de Administração Completo

Variáveis de ambiente:
- CRM_API_KEY: Chave da API do CRM DataCrazy
- CPF_API_TOKEN: Token da API de CPF (cpf-brasil.org)
- SECRET_KEY: Chave secreta para o painel (opcional)
"""

from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import requests
import re
import os
import json
from datetime import datetime

app = Flask(__name__)
CORS(app)

# Configurações via variáveis de ambiente
CRM_API_BASE = "https://api.g1.datacrazy.io"
CRM_API_KEY = os.environ.get('CRM_API_KEY', '')
CPF_API_TOKEN = os.environ.get('CPF_API_TOKEN', '')
SECRET_KEY = os.environ.get('SECRET_KEY', 'admin123')

# Template padrão da mensagem
DEFAULT_TEMPLATE = """Olá! Encontrei os dados do CPF consultado:

CPF: {cpf_mascarado}
Nome: {nome}
Nascimento: {nascimento}
Sexo: {sexo}
Mãe: {nome_mae}

Caso precise de mais informações, estou à disposição."""

# Configurações em memória (em produção, use banco de dados)
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

# Logs em memória
logs = []

def add_log(tipo, cpf, status, detalhes='', lead_phone='', lead_name=''):
    """Adiciona um log de atividade."""
    logs.insert(0, {
        'data': datetime.now().strftime('%d/%m/%Y %H:%M:%S'),
        'tipo': tipo,
        'cpf': cpf[:3] + '***' + cpf[-2:] if cpf and len(cpf) >= 5 else '-',
        'status': status,
        'detalhes': detalhes,
        'lead_phone': lead_phone or '-',
        'lead_name': lead_name or '-'
    })
    # Mantém apenas os últimos 100 logs
    if len(logs) > 100:
        logs.pop()


def extrair_cpf(texto):
    """Extrai CPF de um texto."""
    if not texto:
        return None
    
    texto_limpo = texto.replace(" ", "").replace(".", "").replace("-", "").replace("/", "")
    
    padrao_formatado = r'\d{3}[\.\s]?\d{3}[\.\s]?\d{3}[\-\.\s]?\d{2}'
    match_formatado = re.search(padrao_formatado, texto)
    if match_formatado:
        cpf = re.sub(r'[^\d]', '', match_formatado.group())
        if len(cpf) == 11:
            return cpf
    
    padrao_cpf = r'\d{11}'
    match = re.search(padrao_cpf, texto_limpo)
    if match:
        return match.group()
    
    match_original = re.search(padrao_cpf, re.sub(r'[^\d]', '', texto))
    if match_original:
        return match_original.group()
    
    return None


def validar_cpf(cpf):
    """Valida se o CPF é válido matematicamente."""
    if not cpf or len(cpf) != 11:
        return False
    
    if cpf == cpf[0] * 11:
        return False
    
    def calcular_digito(cpf_parcial, pesos):
        soma = sum(int(d) * p for d, p in zip(cpf_parcial, pesos))
        resto = soma % 11
        return '0' if resto < 2 else str(11 - resto)
    
    pesos1 = [10, 9, 8, 7, 6, 5, 4, 3, 2]
    digito1 = calcular_digito(cpf[:9], pesos1)
    
    pesos2 = [11, 10, 9, 8, 7, 6, 5, 4, 3, 2]
    digito2 = calcular_digito(cpf[:9] + digito1, pesos2)
    
    return cpf[-2:] == digito1 + digito2


def buscar_mensagens_conversa(conversation_id):
    """Busca as mensagens de uma conversa no CRM DataCrazy."""
    if not config['crm_api_key']:
        print("ERRO: CRM_API_KEY não configurada")
        return None
    
    url = f"{CRM_API_BASE}/api/v1/conversations/{conversation_id}/messages"
    headers = {
        "Authorization": f"Bearer {config['crm_api_key']}",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        if isinstance(data, dict):
            messages = data.get('messages', data.get('data', []))
        else:
            messages = data
        
        if isinstance(messages, list):
            lead_messages = [m for m in messages if m.get('received') == True]
            return lead_messages
        
        return messages
    except requests.exceptions.RequestException as e:
        print(f"Erro ao buscar mensagens: {e}")
        return None


def consultar_cpf(cpf):
    """Consulta dados do CPF na API cpf-brasil.org."""
    if not config['cpf_api_token']:
        print("ERRO: CPF_API_TOKEN não configurado")
        return None
    
    url = f"https://api.cpf-brasil.org/cpf/{cpf}"
    headers = {
        "X-API-Key": config['cpf_api_token'],
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=60)
        
        if response.status_code == 200:
            data = response.json()
            if data.get('success') == True:
                return data.get('data')
        return None
    except requests.exceptions.RequestException as e:
        print(f"Erro ao consultar CPF: {e}")
        return None


def enviar_mensagem_conversa(conversation_id, mensagem):
    """Envia mensagem para uma conversa no CRM DataCrazy."""
    if not config['crm_api_key']:
        return None
    
    url = f"{CRM_API_BASE}/api/v1/conversations/{conversation_id}/messages"
    headers = {
        "Authorization": f"Bearer {config['crm_api_key']}",
        "Content-Type": "application/json"
    }
    
    payload = {"body": mensagem}
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Erro ao enviar mensagem: {e}")
        return None


def formatar_cpf(cpf, formato='mascarado'):
    """Formata o CPF de acordo com o formato escolhido."""
    if formato == 'completo':
        return f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"
    elif formato == 'parcial':
        return f"***{cpf[3:9]}**"
    else:  # mascarado
        return f"{cpf[:3]}.***.**{cpf[-4:-2]}-{cpf[-2:]}"


def formatar_mensagem(dados_cpf, cpf):
    """Formata a mensagem usando o template configurado."""
    if not dados_cpf:
        return config.get('msg_erro', "Desculpe, não foi possível consultar os dados do CPF informado.")
    
    cpf_formatado = formatar_cpf(cpf, config.get('formato_cpf', 'mascarado'))
    
    # Prepara os dados para o template
    dados = {
        'cpf': f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}",
        'cpf_mascarado': cpf_formatado,
        'nome': dados_cpf.get('NOME', dados_cpf.get('nome', 'Não disponível')),
        'nascimento': dados_cpf.get('NASC', dados_cpf.get('nascimento', '')),
        'sexo': dados_cpf.get('SEXO', dados_cpf.get('sexo', '')),
        'nome_mae': dados_cpf.get('NOME_MAE', dados_cpf.get('nome_mae', ''))
    }
    
    # Usa o template configurado
    try:
        mensagem = config['message_template'].format(**dados)
    except KeyError:
        mensagem = DEFAULT_TEMPLATE.format(**dados)
    
    # Remove linhas vazias de campos não preenchidos
    linhas = mensagem.split('\n')
    linhas_filtradas = []
    for linha in linhas:
        if not linha.strip().endswith(':') and linha.strip():
            linhas_filtradas.append(linha)
        elif not linha.strip():
            linhas_filtradas.append(linha)
    
    return '\n'.join(linhas_filtradas)


# ==================== ROTAS ====================

@app.route('/')
def index():
    """Página inicial - Painel de configuração."""
    return render_template('index.html', config=config)


@app.route('/health')
def health():
    """Health check."""
    return jsonify({"status": "ok", "timestamp": datetime.now().isoformat()})


@app.route('/api/config', methods=['GET', 'POST'])
def api_config():
    """Endpoint para configurar a API."""
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
    """Endpoint para gerenciar logs."""
    if request.method == 'DELETE':
        logs.clear()
        return jsonify({"success": True, "message": "Logs limpos!"})
    
    return jsonify({"success": True, "logs": logs[:50]})


@app.route('/api/stats')
def api_stats():
    """Retorna estatísticas de uso."""
    total = len(logs)
    sucesso = len([l for l in logs if l['status'] == 'Sucesso'])
    
    return jsonify({
        "total_consultas": total,
        "msg_enviadas": sucesso,
        "taxa_sucesso": f"{(sucesso/total*100):.0f}%" if total > 0 else "100%"
    })


@app.route('/api/gerar-javascript', methods=['POST'])
def gerar_javascript():
    """Gera o código JavaScript para o CRM DataCrazy."""
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
    """Endpoint principal que recebe dados do CRM DataCrazy."""
    try:
        data = request.get_json(force=True) if request.data else {}
        
        conversation_id = data.get('conversationId')
        lead_phone = data.get('leadPhone', '')
        lead_name = data.get('leadName', '')
        mensagem_direta = data.get('mensagem')
        
        if not conversation_id:
            add_log('WEBHOOK', '-', 'Erro', 'conversationId não fornecido', lead_phone, lead_name)
            return jsonify({
                "success": False,
                "error": "conversationId é obrigatório"
            }), 400
        
        # Primeiro tenta extrair CPF da mensagem direta
        cpf = None
        if mensagem_direta:
            cpf = extrair_cpf(mensagem_direta)
        
        # Se não encontrou, busca nas mensagens da conversa
        if not cpf:
            mensagens = buscar_mensagens_conversa(conversation_id)
            
            if mensagens and isinstance(mensagens, list):
                try:
                    mensagens_ordenadas = sorted(
                        mensagens, 
                        key=lambda x: x.get('createdAt', ''), 
                        reverse=True
                    )
                except:
                    mensagens_ordenadas = mensagens
                
                for msg in mensagens_ordenadas:
                    body = msg.get('body', '')
                    if body:
                        cpf_encontrado = extrair_cpf(body)
                        if cpf_encontrado:
                            cpf = cpf_encontrado
                            break
        
        if not cpf:
            add_log('CONSULTA', '-', 'Erro', 'CPF não encontrado nas mensagens', lead_phone, lead_name)
            return jsonify({
                "success": False,
                "error": "CPF não encontrado nas mensagens"
            }), 404
        
        if not validar_cpf(cpf):
            add_log('CONSULTA', cpf, 'Erro', 'CPF inválido', lead_phone, lead_name)
            return jsonify({
                "success": False,
                "error": "CPF inválido",
                "cpf_encontrado": cpf
            }), 400
        
        # Consulta dados do CPF
        dados_cpf = consultar_cpf(cpf)
        
        # Formata mensagem
        mensagem_resposta = formatar_mensagem(dados_cpf, cpf)
        
        # Envia a mensagem
        resultado_envio = enviar_mensagem_conversa(conversation_id, mensagem_resposta)
        
        # Pega o nome do titular do CPF consultado
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
        print(f"Erro no webhook: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/consultar-cpf', methods=['POST'])
def consultar_cpf_endpoint():
    """Endpoint direto para consultar CPF."""
    try:
        data = request.get_json()
        cpf_raw = data.get('cpf', '')
        
        cpf = re.sub(r'[^\d]', '', cpf_raw)
        
        if len(cpf) != 11:
            return jsonify({
                "success": False,
                "error": "CPF deve ter 11 dígitos"
            }), 400
        
        if not validar_cpf(cpf):
            return jsonify({
                "success": False,
                "error": "CPF inválido"
            }), 400
        
        dados = consultar_cpf(cpf)
        
        add_log('TESTE', cpf, 'Sucesso' if dados else 'Erro', 'Consulta direta')
        
        return jsonify({
            "success": True if dados else False,
            "cpf": cpf,
            "dados": dados,
            "mensagem_formatada": formatar_mensagem(dados, cpf) if dados else None
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 3000))
    app.run(host='0.0.0.0', port=port, debug=False)

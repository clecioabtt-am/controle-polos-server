from flask import Flask, request, jsonify
import os
import json
import secrets
from datetime import datetime, date
import requests

app = Flask(__name__)

PARTNERS_FILE = "partners.json"

# ========= CONFIG ASAAS =========
# Recomendo usar variável de ambiente:
# No PowerShell (temporário):  $env:ASAAS_API_KEY="SUA_CHAVE_AQUI"
ASAAS_API_KEY = os.getenv("ASAAS_API_KEY", "SUA_CHAVE_API_AQUI")
ASAAS_BASE_URL = os.getenv("ASAAS_BASE_URL", "https://www.asaas.com/api/v3")


def asaas_headers():
    return {
        "accept": "application/json",
        "content-type": "application/json",
        "access_token": ASAAS_API_KEY
    }


# ========= FUNÇÕES UTILITÁRIAS =========
def load_partners():
    if not os.path.exists(PARTNERS_FILE):
        return {}
    with open(PARTNERS_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}


def save_partners(data):
    with open(PARTNERS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


def generate_access_key():
    raw = secrets.token_urlsafe(8)
    key = "".join(ch for ch in raw if ch.isalnum()).upper()
    return key[:12]


def is_expired(expira_em_str: str) -> bool:
    if not expira_em_str:
        return False
    try:
        d = datetime.strptime(expira_em_str, "%Y-%m-%d").date()
    except ValueError:
        return False
    return date.today() > d


# ========= ROTAS BÁSICAS =========
@app.route("/teste", methods=["GET"])
def teste():
    return jsonify({"mensagem": "Servidor Flask funcionando corretamente!"})


# ========= PAINEL /admin (bonito) COM REMOVER CHAVE =========
@app.route("/admin", methods=["GET", "POST"])
def admin():
    partners = load_partners()
    mensagem = ""

    if request.method == "POST":
        # Se veio pedido de remoção de chave
        delete_key = (request.form.get("delete_key") or "").strip()
        if delete_key:
            if delete_key in partners:
                info = partners.pop(delete_key)
                save_partners(partners)
                mensagem = f"Chave {delete_key} removida ({info.get('nome', 'Sem nome')})."
            else:
                mensagem = f"Chave {delete_key} não encontrada."
        else:
            # Operação de criação/edição de chave
            nome = (request.form.get("nome") or "").strip()
            polo = (request.form.get("polo") or "").strip()
            expira_em = (request.form.get("expira_em") or "").strip()
            chave_manual = (request.form.get("chave") or "").strip()

            if not nome:
                mensagem = "Preencha pelo menos o nome do parceiro."
            else:
                if chave_manual:
                    chave = chave_manual.upper()
                else:
                    chave = generate_access_key()

                partners[chave] = {
                    "nome": nome,
                    "polo": polo,
                    "expira_em": expira_em
                }
                save_partners(partners)
                mensagem = f"Chave gerada para {nome}: {chave}"

    # HTML bonito com botão de remover
    html = f"""
    <!DOCTYPE html>
    <html lang="pt-br">
    <head>
        <meta charset="utf-8">
        <title>Painel de Parceiros - Controle de Gestão de Polo</title>
        <style>
            * {{
                box-sizing: border-box;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            }}
            body {{
                margin: 0;
                padding: 0;
                background: #0D47A1;
                background: linear-gradient(135deg, #0D47A1, #1976D2);
                color: #333;
            }}
            .container {{
                max-width: 1100px;
                margin: 40px auto;
                padding: 16px;
            }}
            .card {{
                background: #FFFFFF;
                border-radius: 12px;
                box-shadow: 0 6px 18px rgba(0,0,0,0.15);
                padding: 24px;
                margin-bottom: 24px;
            }}
            .header-title {{
                color: #0D47A1;
                margin: 0 0 4px 0;
                font-size: 24px;
                font-weight: 700;
            }}
            .header-subtitle {{
                margin: 0;
                color: #555;
                font-size: 14px;
            }}
            .badge {{
                display: inline-block;
                padding: 4px 10px;
                border-radius: 999px;
                font-size: 11px;
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: .03em;
            }}
            .badge-primary {{
                background: rgba(25,118,210,0.1);
                color: #0D47A1;
            }}
            .badge-success {{
                background: rgba(46,125,50,0.1);
                color: #2E7D32;
            }}
            .form-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
                gap: 16px;
                margin-top: 16px;
            }}
            label {{
                font-size: 13px;
                font-weight: 600;
                color: #555;
                display: block;
                margin-bottom: 4px;
            }}
            input[type="text"] {{
                width: 100%;
                padding: 10px 12px;
                border-radius: 8px;
                border: 1px solid #CDD2D7;
                font-size: 14px;
                outline: none;
                transition: border-color .2s, box-shadow .2s;
            }}
            input[type="text"]:focus {{
                border-color: #1976D2;
                box-shadow: 0 0 0 2px rgba(25,118,210,0.2);
            }}
            .btn-primary {{
                display: inline-block;
                margin-top: 16px;
                padding: 10px 20px;
                border-radius: 999px;
                border: none;
                outline: none;
                cursor: pointer;
                background: linear-gradient(135deg, #D32F2F, #B71C1C);
                color: #FFF;
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: .06em;
                font-size: 13px;
                box-shadow: 0 4px 10px rgba(0,0,0,0.25);
                transition: transform .1s, box-shadow .1s, opacity .2s;
            }}
            .btn-primary:hover {{
                transform: translateY(-1px);
                box-shadow: 0 6px 14px rgba(0,0,0,0.25);
                opacity: 0.95;
            }}
            .btn-delete {{
                padding: 6px 12px;
                border-radius: 999px;
                border: none;
                cursor: pointer;
                background: #FCE4EC;
                color: #C2185B;
                font-size: 11px;
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: .05em;
                transition: background .2s, transform .1s;
            }}
            .btn-delete:hover {{
                background: #F8BBD0;
                transform: translateY(-1px);
            }}
            .msg {{
                margin-top: 10px;
                font-size: 13px;
                color: #2E7D32;
            }}
            .table-wrapper {{
                overflow-x: auto;
            }}
            table {{
                width: 100%;
                border-collapse: collapse;
                margin-top: 12px;
                font-size: 13px;
            }}
            th, td {{
                padding: 8px 10px;
                text-align: left;
                border-bottom: 1px solid #E0E0E0;
                white-space: nowrap;
            }}
            th {{
                background: #F5F5F5;
                font-weight: 700;
                color: #555;
            }}
            tr:hover td {{
                background: #FAFAFA;
            }}
            .status-ativa {{
                color: #2E7D32;
                font-weight: 600;
            }}
            .status-expirada {{
                color: #D32F2F;
                font-weight: 600;
            }}
            .chip {{
                display: inline-block;
                padding: 3px 8px;
                border-radius: 999px;
                font-size: 11px;
                background: #E3F2FD;
                color: #0D47A1;
            }}
            @media (max-width: 600px) {{
                .header-title {{
                    font-size: 20px;
                }}
                .card {{
                    padding: 18px;
                }}
                th, td {{
                    font-size: 12px;
                }}
            }}
        </style>
    </head>
    <body>
        <div class="container">

            <div class="card">
                <div style="display:flex; justify-content:space-between; align-items:center; gap:8px; flex-wrap:wrap;">
                    <div>
                        <h1 class="header-title">Painel de Parceiros</h1>
                        <p class="header-subtitle">
                            Gere, liste e remova as chaves de acesso dos coordenadores de polo.
                        </p>
                    </div>
                    <div>
                        <span class="badge badge-primary">Controle de Gestão de Polo</span>
                    </div>
                </div>
            </div>

            <div class="card">
                <h2 style="margin-top:0; font-size:18px; color:#0D47A1;">Gerar nova chave de acesso</h2>
                <p style="margin:0; font-size:13px; color:#555;">
                    Preencha os dados do coordenador. Você pode deixar o campo "Chave manual"
                    vazio para o sistema gerar uma chave automaticamente.
                </p>

                {"<div class='msg'>" + mensagem + "</div>" if mensagem else ""}

                <form method="post">
                    <div class="form-grid">
                        <div>
                            <label>Nome do parceiro *</label>
                            <input type="text" name="nome" placeholder="Ex: Luciano, Jaina, Gabriel">
                        </div>
                        <div>
                            <label>Polo</label>
                            <input type="text" name="polo" placeholder="Ex: Polo Barreirinha">
                        </div>
                        <div>
                            <label>Data de expiração (YYYY-MM-DD)</label>
                            <input type="text" name="expira_em" placeholder="Ex: 2025-12-31">
                        </div>
                        <div>
                            <label>Chave manual (opcional)</label>
                            <input type="text" name="chave" placeholder="Se vazio, gera automático">
                        </div>
                    </div>

                    <button type="submit" class="btn-primary">Gerar / Salvar chave</button>
                </form>
            </div>

            <div class="card">
                <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
                    <h2 style="margin:0; font-size:18px; color:#0D47A1;">Chaves cadastradas</h2>
                    <span class="badge badge-success">Total: {len(partners)}</span>
                </div>
                <div class="table-wrapper">
                    <table>
                        <tr>
                            <th>Chave</th>
                            <th>Nome</th>
                            <th>Polo</th>
                            <th>Expira em</th>
                            <th>Status</th>
                            <th>Ações</th>
                        </tr>
    """

    for chave, info in partners.items():
        expira_em = info.get("expira_em", "")
        status = "Ativa"
        status_class = "status-ativa"
        if is_expired(expira_em):
            status = "Expirada"
            status_class = "status-expirada"

        html += f"""
                        <tr>
                            <td><span class="chip">{chave}</span></td>
                            <td>{info.get('nome', '')}</td>
                            <td>{info.get('polo', '')}</td>
                            <td>{expira_em}</td>
                            <td class="{status_class}">{status}</td>
                            <td>
                                <form method="post" onsubmit="return confirm('Remover a chave {chave}?');" style="display:inline;">
                                    <input type="hidden" name="delete_key" value="{chave}">
                                    <button type="submit" class="btn-delete">Remover</button>
                                </form>
                            </td>
                        </tr>
        """

    html += """
                    </table>
                </div>
            </div>
        </div>
    </body>
    </html>
    """

    return html


# ========= LOGIN PARA O APP ANDROID =========
@app.route("/login", methods=["POST"])
def login():
    partners = load_partners()
    dados = request.get_json() or {}

    chave_acesso = (dados.get("chave_acesso") or "").strip().upper()

    if not chave_acesso:
        return jsonify({"status": "erro", "mensagem": "Chave de acesso vazia."}), 400

    info = partners.get(chave_acesso)
    if not info:
        return jsonify({"status": "erro", "mensagem": "Chave de acesso inválida."}), 401

    if is_expired(info.get("expira_em", "")):
        return jsonify({"status": "erro", "mensagem": "Chave expirada."}), 403

    return jsonify({
        "status": "ok",
        "mensagem": "Acesso autorizado.",
        "parceiro": info.get("nome", ""),
        "polo": info.get("polo", ""),
        "chave": chave_acesso
    })


# ========= ROTA: LISTAR ALUNOS POR POLO =========
@app.route("/api/alunos", methods=["GET"])
def api_alunos():
    """
    GET /api/alunos?polo=Polo Barreirinha
    Retorna lista de alunos (clientes) do Asaas cujo 'complement' contém o nome do polo.
    """
    polo = (request.args.get("polo") or "").strip()
    if not polo:
        return jsonify({"erro": "Parâmetro 'polo' é obrigatório"}), 400

    if ASAAS_API_KEY == "SUA_CHAVE_API_AQUI":
        return jsonify({"erro": "Configure a ASAAS_API_KEY no servidor."}), 500

    url = f"{ASAAS_BASE_URL}/customers"
    limit = 100
    offset = 0
    alunos = []

    while True:
        params = {
            "limit": limit,
            "offset": offset
        }
        resp = requests.get(url, headers=asaas_headers(), params=params)
        if resp.status_code != 200:
            return jsonify({
                "erro": "Erro ao consultar clientes no Asaas",
                "status_code": resp.status_code,
                "detalhe": resp.text
            }), resp.status_code

        data = resp.json()
        customers = data.get("data", [])

        for c in customers:
            complemento = (c.get("complement") or "").lower()
            if polo.lower() in complemento:
                alunos.append({
                    "id": c.get("id"),
                    "nome": c.get("name"),
                    "cpf": c.get("cpfCnpj")
                })

        has_more = data.get("hasMore")
        if not has_more:
            break

        offset += limit

    return jsonify(alunos)


# ========= ROTA: EMITIR FATURA =========
@app.route("/api/emitir_fatura", methods=["POST"])
def api_emitir_fatura():
    """
    JSON esperado:
    {
      "aluno_id": "cus_000x1",
      "valor": 250.0,
      "vencimento": "2025-03-10",
      "forma": "PIX",   # ou "BOLETO" / "BOLETO_PIX"
      "descricao": "Mensalidade Fevereiro - Polo X"
    }
    """
    if ASAAS_API_KEY == "SUA_CHAVE_API_AQUI":
        return jsonify({"erro": "Configure a ASAAS_API_KEY no servidor."}), 500

    payload = request.get_json() or {}

    aluno_id = payload.get("aluno_id")
    valor = payload.get("valor")
    vencimento = payload.get("vencimento")
    forma = (payload.get("forma") or "").upper()
    descricao = payload.get("descricao") or ""

    if not aluno_id or not valor or not vencimento:
        return jsonify({
            "erro": "Campos obrigatórios: aluno_id, valor, vencimento."
        }), 400

    if forma == "PIX":
        billing_type = "PIX"
    else:
        billing_type = "BOLETO"

    body = {
        "customer": aluno_id,
        "value": float(valor),
        "dueDate": vencimento,
        "description": descricao,
        "billingType": billing_type
    }

    url = f"{ASAAS_BASE_URL}/payments"
    resp = requests.post(url, headers=asaas_headers(), json=body)

    if resp.status_code not in (200, 201):
        return jsonify({
            "erro": "Erro ao criar fatura no Asaas",
            "status_code": resp.status_code,
            "detalhe": resp.text
        }), resp.status_code

    data = resp.json()

    return jsonify({
        "status": "ok",
        "aluno_id": aluno_id,
        "fatura_id": data.get("id"),
        "status_fatura": data.get("status"),
        "link_pagamento": data.get("invoiceUrl"),
        "valor": data.get("value"),
        "vencimento": data.get("dueDate")
    })


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)

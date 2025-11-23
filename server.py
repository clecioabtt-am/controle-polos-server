from flask import Flask, request, jsonify
import os
import json
import secrets
from datetime import datetime, date
import requests

app = Flask(__name__)

PARTNERS_FILE = "partners.json"

# ========= CONFIG ASAAS =========
ASAAS_API_KEY = os.getenv("ASAAS_API_KEY", "SUA_CHAVE_API_AQUI")
ASAAS_BASE_URL = os.getenv("ASAAS_BASE_URL", "https://www.asaas.com/api/v3")


def asaas_headers():
    return {
        "accept": "application/json",
        "content-type": "application/json",
        "access_token": ASAAS_API_KEY
    }


# ========= UTILITÁRIOS =========
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


# ========= TESTE =========
@app.route("/teste", methods=["GET"])
def teste():
    return jsonify({"mensagem": "Servidor funcionando com sucesso!"})


# ========= PAINEL /admin =========
@app.route("/admin", methods=["GET", "POST"])
def admin():
    partners = load_partners()
    mensagem = ""

    if request.method == "POST":
        delete_key = (request.form.get("delete_key") or "").strip()

        if delete_key:
            if delete_key in partners:
                info = partners.pop(delete_key)
                save_partners(partners)
                mensagem = f"Chave {delete_key} removida ({info.get('nome', 'Sem nome')})."
            else:
                mensagem = f"Chave {delete_key} não encontrada."
        else:
            nome = (request.form.get("nome") or "").strip()
            polo = (request.form.get("polo") or "").strip()
            expira_em = (request.form.get("expira_em") or "").strip()
            chave_manual = (request.form.get("chave") or "").strip()

            if not nome:
                mensagem = "Preencha pelo menos o nome do parceiro."
            else:
                chave = chave_manual.upper() if chave_manual else generate_access_key()

                partners[chave] = {
                    "nome": nome,
                    "polo": polo,
                    "expira_em": expira_em
                }
                save_partners(partners)
                mensagem = f"Chave gerada para {nome}: {chave}"

    html = f"""
    <!DOCTYPE html>
    <html lang="pt-br">
    <head>
        <meta charset="utf-8">
        <title>Painel de Parceiros</title>
        <style>
            body {{
                background: #0D47A1;
                margin: 0;
                padding: 0;
                font-family: Arial, sans-serif;
            }}
            .container {{
                max-width: 1100px;
                margin: 40px auto;
                background: white;
                border-radius: 10px;
                padding: 20px;
            }}
            table {{
                width: 100%;
                border-collapse: collapse;
            }}
            th, td {{
                border-bottom: 1px solid #ddd;
                padding: 8px;
            }}
            th {{
                background: #f2f2f2;
            }}
            .msg {{
                color: green;
                margin-top: 10px;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Painel de Parceiros</h1>
            {"<div class='msg'>" + mensagem + "</div>" if mensagem else ""}
            <form method="POST">
                <p><b>Nome:</b> <input name="nome"></p>
                <p><b>Polo:</b> <input name="polo"></p>
                <p><b>Expira em:</b> <input name="expira_em" placeholder="2025-12-31"></p>
                <p><b>Chave manual (opcional):</b> <input name="chave"></p>
                <button type="submit">Salvar / Gerar Chave</button>
            </form>

            <h2>Chaves cadastradas</h2>
            <table>
                <tr>
                    <th>Chave</th>
                    <th>Nome</th>
                    <th>Polo</th>
                    <th>Expira em</th>
                    <th>Status</th>
                    <th>Ação</th>
                </tr>
    """

    for chave, info in partners.items():
        expira_em = info.get("expira_em", "")
        exp = "Expirada" if is_expired(expira_em) else "Ativa"
        cor = "red" if exp == "Expirada" else "green"

        html += f"""
            <tr>
                <td>{chave}</td>
                <td>{info.get('nome')}</td>
                <td>{info.get('polo')}</td>
                <td>{expira_em}</td>
                <td style="color:{cor};">{exp}</td>
                <td>
                    <form method="POST">
                        <input type="hidden" name="delete_key" value="{chave}">
                        <button style="color:red;">Remover</button>
                    </form>
                </td>
            </tr>
        """

    html += """
            </table>
        </div>
    </body>
    </html>
    """

    return html


# ========= LOGIN ANDROID =========
@app.route("/login", methods=["POST"])
def login():
    partners = load_partners()
    dados = request.get_json() or {}

    chave = (dados.get("chave_acesso") or "").strip().upper()

    if chave == "":
        return jsonify({"status": "erro", "mensagem": "Chave vazia"}), 400

    info = partners.get(chave)
    if not info:
        return jsonify({"status": "erro", "mensagem": "Chave inválida"}), 401

    if is_expired(info.get("expira_em", "")):
        return jsonify({"status": "erro", "mensagem": "Chave expirada"}), 403

    return jsonify({
        "status": "ok",
        "mensagem": "Acesso autorizado",
        "polo": info.get("polo"),
        "parceiro": info.get("nome"),
        "chave": chave
    })


# ========= ROTA: CADASTRAR / ATUALIZAR ALUNO =========
@app.route("/api/cadastrar_aluno", methods=["POST"])
def cadastrar_aluno():
    try:
        dados = request.get_json() or {}

        nome = dados.get("nome")
        cpf = dados.get("cpf")
        comp = dados.get("complemento")

        if not nome or not cpf or not comp:
            return jsonify({
                "status": "erro",
                "mensagem": "Campos obrigatórios: nome, cpf, complemento"
            }), 400

        url = f"{ASAAS_BASE_URL}/customers?cpfCnpj={cpf}"
        r = requests.get(url, headers=asaas_headers())
        r.raise_for_status()
        data = r.json()

        if data.get("totalCount", 0) > 0:
            aluno_id = data["data"][0]["id"]
            body = {
                "name": nome,
                "cpfCnpj": cpf,
                "complement": comp
            }
            url_update = f"{ASAAS_BASE_URL}/customers/{aluno_id}"
            r = requests.post(url_update, headers=asaas_headers(), json=body)
            r.raise_for_status()
            return jsonify({
                "status": "ok",
                "mensagem": "Cadastro atualizado com sucesso!",
                "aluno_id": aluno_id
            })

        body = {
            "name": nome,
            "cpfCnpj": cpf,
            "complement": comp
        }
        r = requests.post(f"{ASAAS_BASE_URL}/customers", headers=asaas_headers(), json=body)
        r.raise_for_status()
        novo = r.json()

        return jsonify({
            "status": "ok",
            "mensagem": "Aluno cadastrado com sucesso!",
            "aluno_id": novo.get("id")
        })

    except Exception as e:
        return jsonify({
            "status": "erro",
            "mensagem": f"Erro ao cadastrar aluno: {str(e)}"
        }), 500


# ========= ROTA: EMITIR FATURA =========
@app.route("/api/emitir_fatura", methods=["POST"])
def emitir_fatura():
    try:
        dados = request.get_json() or {}

        nome = dados.get("nome")
        cpf = dados.get("cpf")
        valor = dados.get("valor")
        venc = dados.get("vencimento")
        forma = (dados.get("forma") or "").upper()
        descricao = dados.get("descricao")

        if not nome or not cpf or not valor or not venc or not descricao:
            return jsonify({
                "status": "erro",
                "mensagem": "Campos obrigatórios: nome, cpf, valor, vencimento, descricao"
            }), 400

        url_consulta = f"{ASAAS_BASE_URL}/customers?cpfCnpj={cpf}"
        r = requests.get(url_consulta, headers=asaas_headers())
        r.raise_for_status()
        data = r.json()

        if data.get("totalCount", 0) == 0:
            return jsonify({
                "status": "erro",
                "mensagem": "Aluno não encontrado no Asaas para este CPF."
            }), 404

        aluno_id = data["data"][0]["id"]

        billing_type = "PIX" if forma == "PIX" else "BOLETO"

        payload = {
            "customer": aluno_id,
            "value": float(valor),
            "dueDate": venc,
            "description": descricao,
            "billingType": billing_type
        }

        r = requests.post(f"{ASAAS_BASE_URL}/payments", headers=asaas_headers(), json=payload)
        r.raise_for_status()
        fatura = r.json()

        return jsonify({
            "status": "ok",
            "mensagem": "Fatura emitida com sucesso!",
            "fatura_id": fatura.get("id"),
            "link_pagamento": fatura.get("invoiceUrl"),
            "valor": fatura.get("value"),
            "vencimento": fatura.get("dueDate")
        })

    except Exception as e:
        return jsonify({
            "status": "erro",
            "mensagem": f"Erro ao emitir fatura: {str(e)}"
        }), 500


# ========= EXECUÇÃO LOCAL =========
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)

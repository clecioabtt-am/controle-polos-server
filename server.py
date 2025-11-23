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


# ========= LOGIN =========
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

        # validação
        if not nome or not cpf or not comp:
            return jsonify({
                "success": False,
                "message": "Campos obrigatórios: nome, cpf, complemento"
            }), 400

        # consulta aluno no Asaas
        url = f"{ASAAS_BASE_URL}/customers?cpfCnpj={cpf}"
        r = requests.get(url, headers=asaas_headers())
        r.raise_for_status()
        data = r.json()

        # Se já existe → atualiza
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
                "success": True,
                "message": "Cadastro atualizado com sucesso!",
                "aluno_id": aluno_id
            })

        # Se não existe → cria
        body = {
            "name": nome,
            "cpfCnpj": cpf,
            "complement": comp
        }

        r = requests.post(f"{ASAAS_BASE_URL}/customers", headers=asaas_headers(), json=body)
        r.raise_for_status()
        novo = r.json()

        return jsonify({
            "success": True,
            "message": "Aluno cadastrado com sucesso!",
            "aluno_id": novo.get("id")
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Erro ao cadastrar aluno: {str(e)}"
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
                "success": False,
                "message": "Campos obrigatórios: nome, cpf, valor, vencimento, descricao"
            }), 400

        # Buscar cliente pelo CPF
        url_consulta = f"{ASAAS_BASE_URL}/customers?cpfCnpj={cpf}"
        r = requests.get(url_consulta, headers=asaas_headers())
        r.raise_for_status()
        data = r.json()

        if data.get("totalCount", 0) == 0:
            return jsonify({
                "success": False,
                "message": "Aluno não encontrado no Asaas para este CPF."
            }), 404

        aluno_id = data["data"][0]["id"]

        # Billing type
        billing_type = "PIX" if forma == "PIX" else "BOLETO"

        # Criar fatura
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
            "success": True,
            "message": "Fatura emitida com sucesso!",
            "fatura_id": fatura.get("id"),
            "link_pagamento": fatura.get("invoiceUrl"),
            "valor": fatura.get("value"),
            "vencimento": fatura.get("dueDate")
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Erro ao emitir fatura: {str(e)}"
        }), 500


# ========= EXECUÇÃO =========
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)

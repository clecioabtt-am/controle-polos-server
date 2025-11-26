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
        "access_token": ASAAS_API_KEY,
    }


# ========= UTILITÁRIOS =========
def load_partners():
    if not os.path.exists(PARTNERS_FILE):
        return {}
    try:
        with open(PARTNERS_FILE, "r", encoding="utf-8") as f:
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


def ensure_asaas_configured():
    """Retorna (ok: bool, resposta_erro: flask.Response|None)."""
    if ASAAS_API_KEY == "SUA_CHAVE_API_AQUI" or not ASAAS_API_KEY:
        return (
            False,
            jsonify(
                {
                    "status": "erro",
                    "mensagem": "Configure a variável ASAAS_API_KEY no Render/ambiente do servidor.",
                }
            ),
        )
    return True, None


# Helper: buscar todos clientes de um polo (complement = polo)
def get_customers_by_polo(polo: str):
    polo_norm = (polo or "").strip().lower()
    clientes = []
    url = f"{ASAAS_BASE_URL}/customers"
    limit = 100
    offset = 0

    # Segurança para não ficar em loop infinito
    max_loops = 50

    for _ in range(max_loops):
        try:
            params = {"limit": limit, "offset": offset}
            r = requests.get(url, headers=asaas_headers(), params=params, timeout=30)
            r.raise_for_status()
            data = r.json()
        except Exception:
            # Se der erro numa página, interrompe e devolve o que já encontrou
            break

        lista = data.get("data", [])
        if not lista:
            break

        for c in lista:
            comp = (c.get("complement") or "").strip().lower()
            if comp == polo_norm:
                clientes.append(c)

        if len(lista) < limit:
            break
        offset += limit

    return clientes


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
                    "expira_em": expira_em,
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

    return jsonify(
        {
            "status": "ok",
            "mensagem": "Acesso autorizado",
            "polo": info.get("polo"),
            "parceiro": info.get("nome"),
            "chave": chave,
        }
    )


# ========= ROTA: CADASTRAR / ATUALIZAR ALUNO =========
@app.route("/api/cadastrar_aluno", methods=["POST"])
def cadastrar_aluno():
    ok, resp_err = ensure_asaas_configured()
    if not ok:
        return resp_err, 500

    try:
        dados = request.get_json() or {}

        nome = dados.get("nome")
        cpf = dados.get("cpf")
        comp = dados.get("complemento")

        if not nome or not cpf or not comp:
            return (
                jsonify(
                    {
                        "status": "erro",
                        "mensagem": "Campos obrigatórios: nome, cpf, complemento",
                    }
                ),
                400,
            )

        url = f"{ASAAS_BASE_URL}/customers"
        params = {"cpfCnpj": cpf}
        r = requests.get(url, headers=asaas_headers(), params=params, timeout=30)
        r.raise_for_status()
        data = r.json()

        if data.get("totalCount", 0) > 0:
            aluno_id = data["data"][0]["id"]
            body = {"name": nome, "cpfCnpj": cpf, "complement": comp}
            url_update = f"{ASAAS_BASE_URL}/customers/{aluno_id}"
            r = requests.post(
                url_update, headers=asaas_headers(), json=body, timeout=30
            )
            r.raise_for_status()
            return jsonify(
                {
                    "status": "ok",
                    "mensagem": "Cadastro atualizado com sucesso!",
                    "aluno_id": aluno_id,
                }
            )

        body = {"name": nome, "cpfCnpj": cpf, "complement": comp}
        r = requests.post(
            f"{ASAAS_BASE_URL}/customers",
            headers=asaas_headers(),
            json=body,
            timeout=30,
        )
        r.raise_for_status()
        novo = r.json()

        return jsonify(
            {
                "status": "ok",
                "mensagem": "Aluno cadastrado com sucesso!",
                "aluno_id": novo.get("id"),
            }
        )

    except requests.RequestException as e:
        return (
            jsonify(
                {
                    "status": "erro",
                    "mensagem": f"Erro de comunicação com Asaas: {str(e)}",
                }
            ),
            502,
        )
    except Exception as e:
        return (
            jsonify(
                {"status": "erro", "mensagem": f"Erro ao cadastrar aluno: {str(e)}"}
            ),
            500,
        )


# ========= ROTA: EMITIR FATURA =========
@app.route("/api/emitir_fatura", methods=["POST"])
def emitir_fatura():
    ok, resp_err = ensure_asaas_configured()
    if not ok:
        return resp_err, 500

    try:
        dados = request.get_json() or {}

        nome = dados.get("nome")
        cpf = dados.get("cpf")
        valor = dados.get("valor")
        venc = dados.get("vencimento")
        forma = (dados.get("forma") or "").upper()
        descricao = dados.get("descricao")

        if not nome or not cpf or not valor or not venc or not descricao:
            return (
                jsonify(
                    {
                        "status": "erro",
                        "mensagem": "Campos obrigatórios: nome, cpf, valor, vencimento, descricao",
                    }
                ),
                400,
            )

        url_consulta = f"{ASAAS_BASE_URL}/customers"
        params = {"cpfCnpj": cpf}
        r = requests.get(url_consulta, headers=asaas_headers(), params=params, timeout=30)
        r.raise_for_status()
        data = r.json()

        if data.get("totalCount", 0) == 0:
            return (
                jsonify(
                    {
                        "status": "erro",
                        "mensagem": "Aluno não encontrado no Asaas para este CPF.",
                    }
                ),
                404,
            )

        aluno_id = data["data"][0]["id"]

        billing_type = "PIX" if forma == "PIX" else "BOLETO"

        payload = {
            "customer": aluno_id,
            "value": float(valor),
            "dueDate": venc,
            "description": descricao,
            "billingType": billing_type,
        }

        r = requests.post(
            f"{ASAAS_BASE_URL}/payments",
            headers=asaas_headers(),
            json=payload,
            timeout=30,
        )
        r.raise_for_status()
        fatura = r.json()

        return jsonify(
            {
                "status": "ok",
                "mensagem": "Fatura emitida com sucesso!",
                "fatura_id": fatura.get("id"),
                "link_pagamento": fatura.get("invoiceUrl"),
                "valor": fatura.get("value"),
                "vencimento": fatura.get("dueDate"),
            }
        )

    except requests.RequestException as e:
        return (
            jsonify(
                {
                    "status": "erro",
                    "mensagem": f"Erro de comunicação com Asaas: {str(e)}",
                }
            ),
            502,
        )
    except Exception as e:
        return (
            jsonify(
                {"status": "erro", "mensagem": f"Erro ao emitir fatura: {str(e)}"}
            ),
            500,
        )


# ========= ROTA: VERIFICAR FATURAS =========
@app.route("/api/verificar_faturas", methods=["POST"])
def verificar_faturas():
    ok, resp_err = ensure_asaas_configured()
    if not ok:
        return resp_err, 500

    try:
        dados = request.get_json() or {}
        nome = dados.get("nome")
        cpf = dados.get("cpf")

        if not nome or not cpf:
            return (
                jsonify(
                    {
                        "status": "erro",
                        "mensagem": "Campos obrigatórios: nome, cpf",
                    }
                ),
                400,
            )

        url = f"{ASAAS_BASE_URL}/customers"
        params = {"cpfCnpj": cpf}
        r = requests.get(url, headers=asaas_headers(), params=params, timeout=30)
        r.raise_for_status()
        data = r.json()

        if data.get("totalCount") == 0:
            return (
                jsonify(
                    {"status": "erro", "mensagem": "Aluno não encontrado."}
                ),
                404,
            )

        aluno_id = data["data"][0]["id"]

        url_pay = f"{ASAAS_BASE_URL}/payments"
        r = requests.get(
            url_pay,
            headers=asaas_headers(),
            params={"customer": aluno_id, "limit": 100},
            timeout=30,
        )
        r.raise_for_status()
        lista = r.json().get("data", [])

        faturas = []
        for fat in lista:
            faturas.append(
                {
                    "id": fat.get("id"),
                    "valor": fat.get("value"),
                    "vencimento": fat.get("dueDate"),
                    "status": fat.get("status"),
                    "forma": fat.get("billingType"),
                    "descricao": fat.get("description"),
                    "link_pagamento": fat.get("invoiceUrl"),
                }
            )

        return jsonify(
            {
                "status": "ok",
                "mensagem": f"{len(faturas)} faturas encontradas.",
                "faturas": faturas,
            }
        )

    except requests.RequestException as e:
        return (
            jsonify(
                {
                    "status": "erro",
                    "mensagem": f"Erro de comunicação com Asaas: {str(e)}",
                }
            ),
            502,
        )
    except Exception as e:
        return (
            jsonify(
                {"status": "erro", "mensagem": f"Erro ao verificar faturas: {str(e)}"}
            ),
            500,
        )


# ========= ROTA: ÚLTIMO LINK DE PAGAMENTO =========
@app.route("/api/ultimo_link_pagamento", methods=["POST"])
def ultimo_link_pagamento():
    ok, resp_err = ensure_asaas_configured()
    if not ok:
        return resp_err, 500

    try:
        dados = request.get_json() or {}
        nome = dados.get("nome")
        cpf = dados.get("cpf")

        if not nome or not cpf:
            return (
                jsonify(
                    {
                        "status": "erro",
                        "mensagem": "Campos obrigatórios: nome, cpf",
                    }
                ),
                400,
            )

        url = f"{ASAAS_BASE_URL}/customers"
        params = {"cpfCnpj": cpf}
        r = requests.get(url, headers=asaas_headers(), params=params, timeout=30)
        r.raise_for_status()
        data = r.json()

        if data.get("totalCount") == 0:
            return (
                jsonify(
                    {"status": "erro", "mensagem": "Aluno não encontrado."}
                ),
                404,
            )

        aluno_id = data["data"][0]["id"]

        url_pay = f"{ASAAS_BASE_URL}/payments"
        r = requests.get(
            url_pay,
            headers=asaas_headers(),
            params={"customer": aluno_id, "limit": 100},
            timeout=30,
        )
        r.raise_for_status()
        lista = r.json().get("data", [])

        if not lista:
            return (
                jsonify(
                    {
                        "status": "erro",
                        "mensagem": "Nenhuma fatura encontrada.",
                    }
                ),
                404,
            )

        lista_ordenada = sorted(lista, key=lambda x: x.get("dueDate") or "")
        ultima = lista_ordenada[-1]

        return jsonify(
            {
                "status": "ok",
                "mensagem": "Última fatura localizada.",
                "fatura_id": ultima.get("id"),
                "descricao": ultima.get("description"),
                "valor": ultima.get("value"),
                "vencimento": ultima.get("dueDate"),
                "link_pagamento": ultima.get("invoiceUrl"),
            }
        )

    except requests.RequestException as e:
        return (
            jsonify(
                {
                    "status": "erro",
                    "mensagem": f"Erro de comunicação com Asaas: {str(e)}",
                }
            ),
            502,
        )
    except Exception as e:
        return (
            jsonify(
                {"status": "erro", "mensagem": f"Erro ao buscar último link: {str(e)}"}
            ),
            500,
        )


# ========= ROTA: RELATÓRIO POR POLO - HISTÓRICO =========
@app.route("/api/relatorio_polo_historico", methods=["POST"])
def relatorio_polo_historico():
    ok, resp_err = ensure_asaas_configured()
    if not ok:
        return resp_err, 500

    try:
        dados = request.get_json() or {}
        polo = dados.get("polo")

        if not polo:
            return (
                jsonify(
                    {"status": "erro", "mensagem": "Campo obrigatório: polo"}
                ),
                400,
            )

        clientes = get_customers_by_polo(polo)
        if not clientes:
            return (
                jsonify(
                    {
                        "status": "erro",
                        "mensagem": f"Nenhum cliente encontrado para o polo {polo}.",
                    }
                ),
                404,
            )

        registros = []

        for cli in clientes:
            aluno_id = cli.get("id")
            nome = cli.get("name")
            cpf = cli.get("cpfCnpj")
            comp = cli.get("complement")

            try:
                url_pay = f"{ASAAS_BASE_URL}/payments"
                r = requests.get(
                    url_pay,
                    headers=asaas_headers(),
                    params={"customer": aluno_id, "limit": 100},
                    timeout=30,
                )
                r.raise_for_status()
                lista = r.json().get("data", [])
            except Exception:
                # Se der erro para um cliente, apenas ignora esse cliente
                continue

            for fat in lista:
                registros.append(
                    {
                        "nome": nome,
                        "cpf": cpf,
                        "polo": comp,
                        "fatura_id": fat.get("id"),
                        "descricao": fat.get("description"),
                        "valor": fat.get("value"),
                        "valor_liquido": fat.get("netValue"),
                        "vencimento": fat.get("dueDate"),
                        "status": fat.get("status"),
                        "data_pagamento": fat.get("paymentDate"),
                        "link_pagamento": fat.get("invoiceUrl"),
                    }
                )

        registros.sort(key=lambda x: (x.get("nome") or "", x.get("vencimento") or ""))

        return jsonify(
            {
                "status": "ok",
                "mensagem": f"{len(registros)} faturas encontradas para o polo {polo}.",
                "polo": polo,
                "faturas": registros,
            }
        )

    except Exception as e:
        return (
            jsonify(
                {
                    "status": "erro",
                    "mensagem": f"Erro ao gerar relatório por polo (histórico): {str(e)}",
                }
            ),
            500,
        )


# ========= ROTA: RELATÓRIO POR POLO - PAGAMENTOS =========
@app.route("/api/relatorio_polo_pagamentos", methods=["POST"])
def relatorio_polo_pagamentos():
    ok, resp_err = ensure_asaas_configured()
    if not ok:
        return resp_err, 500

    try:
        dados = request.get_json() or {}
        polo = dados.get("polo")
        data_inicial = dados.get("data_inicial")
        data_final = dados.get("data_final")

        if not polo or not data_inicial or not data_final:
            return (
                jsonify(
                    {
                        "status": "erro",
                        "mensagem": "Campos obrigatórios: polo, data_inicial, data_final",
                    }
                ),
                400,
            )

        try:
            dt_ini = datetime.strptime(data_inicial, "%Y-%m-%d").date()
            dt_fim = datetime.strptime(data_final, "%Y-%m-%d").date()
        except ValueError:
            return (
                jsonify(
                    {
                        "status": "erro",
                        "mensagem": "Datas devem estar no formato YYYY-MM-DD",
                    }
                ),
                400,
            )

        clientes = get_customers_by_polo(polo)
        if not clientes:
            return (
                jsonify(
                    {
                        "status": "erro",
                        "mensagem": f"Nenhum cliente encontrado para o polo {polo}.",
                    }
                ),
                404,
            )

        pagamentos = []

        for cli in clientes:
            aluno_id = cli.get("id")
            nome = cli.get("name")
            cpf = cli.get("cpfCnpj")
            comp = cli.get("complement")

            try:
                url_pay = f"{ASAAS_BASE_URL}/payments"
                r = requests.get(
                    url_pay,
                    headers=asaas_headers(),
                    params={"customer": aluno_id, "limit": 100},
                    timeout=30,
                )
                r.raise_for_status()
                lista = r.json().get("data", [])
            except Exception:
                continue

            for fat in lista:
                status = fat.get("status")
                if status != "RECEIVED":
                    continue

                pay_date_str = fat.get("paymentDate")
                if not pay_date_str:
                    continue

                try:
                    pay_date = datetime.strptime(pay_date_str, "%Y-%m-%d").date()
                except ValueError:
                    continue

                if not (dt_ini <= pay_date <= dt_fim):
                    continue

                valor_liq = (
                    fat.get("netValue")
                    if fat.get("netValue") is not None
                    else fat.get("value")
                )

                pagamentos.append(
                    {
                        "nome": nome,
                        "cpf": cpf,
                        "polo": comp,
                        "fatura_id": fat.get("id"),
                        "descricao": fat.get("description"),
                        "valor_liquido": valor_liq,
                        "data_pagamento": pay_date_str,
                        "vencimento": fat.get("dueDate"),
                        "status": status,
                        "link_pagamento": fat.get("invoiceUrl"),
                    }
                )

        pagamentos.sort(key=lambda x: x.get("data_pagamento") or "")

        return jsonify(
            {
                "status": "ok",
                "mensagem": f"{len(pagamentos)} pagamentos encontrados para o polo {polo}.",
                "polo": polo,
                "data_inicial": data_inicial,
                "data_final": data_final,
                "pagamentos": pagamentos,
            }
        )

    except Exception as e:
        return (
            jsonify(
                {
                    "status": "erro",
                    "mensagem": f"Erro ao gerar relatório por polo (pagamentos): {str(e)}",
                }
            ),
            500,
        )


# ========= EXECUÇÃO LOCAL =========
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)

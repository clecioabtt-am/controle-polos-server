from flask import Flask, request, jsonify
import os
import secrets
from datetime import datetime, date
import requests
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)

# ========= CONFIG BANCO DE DADOS (PARCEIROS) =========
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///partners.db")
app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

# ========= CHAVES FIXAS (NUNCA APAGAM) =========
FIXED_KEYS = {
    "JAINA.POLO": {"nome": "Jaina", "polo": "Polo Jaina", "expira_em": None},
    "GABRIEL.POLO": {"nome": "Gabriel", "polo": "Polo Gabriel", "expira_em": None},
    "LUCIANO.POLO": {"nome": "Luciano", "polo": "Polo Luciano", "expira_em": None},
}

# ========= CONFIG ASAAS =========
ASAAS_API_KEY = os.getenv("ASAAS_API_KEY", "SUA_CHAVE_API_AQUI")
ASAAS_BASE_URL = os.getenv("ASAAS_BASE_URL", "https://www.asaas.com/api/v3")

# Timeout padrão de rede (segurança)
DEFAULT_TIMEOUT = int(os.getenv("DEFAULT_TIMEOUT", "30"))


def asaas_headers():
    return {
        "accept": "application/json",
        "content-type": "application/json",
        "access_token": ASAAS_API_KEY,
    }


# ========= MODELO BANCO =========
class Partner(db.Model):
    __tablename__ = "partners"

    chave = db.Column(db.String(32), primary_key=True)
    nome = db.Column(db.String(200), nullable=False)
    polo = db.Column(db.String(200))
    expira_em = db.Column(db.String(10))  # YYYY-MM-DD

    def to_dict(self):
        return {
            "chave": self.chave,
            "nome": self.nome,
            "polo": self.polo,
            "expira_em": self.expira_em,
        }


# ========= GARANTIR CHAVES FIXAS =========
def ensure_fixed_keys():
    for chave, info in FIXED_KEYS.items():
        existente = Partner.query.get(chave)
        if not existente:
            novo = Partner(
                chave=chave,
                nome=info["nome"],
                polo=info["polo"],
                expira_em=info["expira_em"],
            )
            db.session.add(novo)
    db.session.commit()


# ========= UTILITÁRIOS =========
def generate_access_key():
    while True:
        raw = secrets.token_urlsafe(8)
        key = "".join(ch for ch in raw if ch.isalnum()).upper()[:12]
        if not Partner.query.get(key):
            return key


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


def _norm(s: str) -> str:
    return (s or "").strip().lower()


# Helper: buscar todos clientes de um polo (complement = polo)
# OBS: isso ainda varre o /customers inteiro. Mantive por compatibilidade,
# mas agora tem trava de loops.
def get_customers_by_polo(polo: str, *, max_loops: int = 50, limit: int = 100):
    polo_norm = _norm(polo)
    clientes = []
    url = f"{ASAAS_BASE_URL}/customers"
    offset = 0

    session = requests.Session()

    for _ in range(max_loops):
        try:
            params = {"limit": limit, "offset": offset}
            r = session.get(url, headers=asaas_headers(), params=params, timeout=DEFAULT_TIMEOUT)
            r.raise_for_status()
            data = r.json()
        except Exception:
            break

        lista = data.get("data", [])
        if not lista:
            break

        for c in lista:
            comp = _norm(c.get("complement"))
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
    mensagem = ""

    if request.method == "POST":
        delete_key = (request.form.get("delete_key") or "").strip()

        if delete_key:
            if delete_key in FIXED_KEYS:
                mensagem = f"A chave {delete_key} é fixa e não pode ser removida."
            else:
                parceiro = Partner.query.get(delete_key)
                if parceiro:
                    db.session.delete(parceiro)
                    db.session.commit()
                    mensagem = f"Chave {delete_key} removida."
                else:
                    mensagem = f"Chave {delete_key} não encontrada."
        else:
            nome = (request.form.get("nome") or "").strip()
            polo = (request.form.get("polo") or "").strip()
            expira_em = (request.form.get("expira_em") or "").strip()
            chave_manual = (request.form.get("chave") or "").strip().upper()

            if not nome:
                mensagem = "Preencha pelo menos o nome do parceiro."
            else:
                if chave_manual:
                    if chave_manual in FIXED_KEYS:
                        mensagem = "Você não pode sobrescrever uma chave fixa."
                    else:
                        parceiro = Partner.query.get(chave_manual)
                        if parceiro:
                            parceiro.nome = nome
                            parceiro.polo = polo
                            parceiro.expira_em = expira_em
                        else:
                            db.session.add(
                                Partner(
                                    chave=chave_manual,
                                    nome=nome,
                                    polo=polo,
                                    expira_em=expira_em,
                                )
                            )
                        db.session.commit()
                        mensagem = f"Chave salva: {chave_manual}"
                else:
                    chave = generate_access_key()
                    db.session.add(
                        Partner(
                            chave=chave,
                            nome=nome,
                            polo=polo,
                            expira_em=expira_em,
                        )
                    )
                    db.session.commit()
                    mensagem = f"Chave gerada para {nome}: {chave}"

    parceiros = Partner.query.order_by(Partner.nome.asc()).all()

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
            .fixo {{
                color: blue;
                font-weight: bold;
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

    for p in parceiros:
        expira_em = p.expira_em or ""
        exp = "Expirada" if is_expired(expira_em) else "Ativa"
        cor = "red" if exp == "Expirada" else "green"
        fixa = p.chave in FIXED_KEYS

        html += f"""
            <tr>
                <td class='{"fixo" if fixa else ""}'>{p.chave}</td>
                <td>{p.nome}</td>
                <td>{p.polo or ""}</td>
                <td>{expira_em}</td>
                <td style="color:{cor};">{exp}</td>
        """

        if fixa:
            html += "<td>Fixa</td></tr>"
        else:
            html += f"""
                <td>
                    <form method="POST">
                        <input type="hidden" name="delete_key" value="{p.chave}">
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
    dados = request.get_json() or {}
    chave = (dados.get("chave_acesso") or "").strip().upper()

    if not chave:
        return jsonify({"status": "erro", "mensagem": "Chave vazia"}), 400

    parceiro = Partner.query.get(chave)
    if not parceiro:
        return jsonify({"status": "erro", "mensagem": "Chave inválida"}), 401

    if is_expired(parceiro.expira_em or ""):
        return jsonify({"status": "erro", "mensagem": "Chave expirada"}), 403

    return jsonify(
        {
            "status": "ok",
            "mensagem": "Acesso autorizado",
            "polo": parceiro.polo,
            "parceiro": parceiro.nome,
            "chave": parceiro.chave,
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
            return jsonify({"status": "erro", "mensagem": "Campos obrigatórios: nome, cpf, complemento"}), 400

        session = requests.Session()

        url = f"{ASAAS_BASE_URL}/customers"
        params = {"cpfCnpj": cpf}
        r = session.get(url, headers=asaas_headers(), params=params, timeout=DEFAULT_TIMEOUT)
        r.raise_for_status()
        data = r.json()

        if data.get("totalCount", 0) > 0:
            aluno_id = data["data"][0]["id"]
            body = {"name": nome, "cpfCnpj": cpf, "complement": comp}
            url_update = f"{ASAAS_BASE_URL}/customers/{aluno_id}"
            r = session.post(url_update, headers=asaas_headers(), json=body, timeout=DEFAULT_TIMEOUT)
            r.raise_for_status()
            return jsonify({"status": "ok", "mensagem": "Cadastro atualizado com sucesso!", "aluno_id": aluno_id})

        body = {"name": nome, "cpfCnpj": cpf, "complement": comp}
        r = session.post(f"{ASAAS_BASE_URL}/customers", headers=asaas_headers(), json=body, timeout=DEFAULT_TIMEOUT)
        r.raise_for_status()
        novo = r.json()

        return jsonify({"status": "ok", "mensagem": "Aluno cadastrado com sucesso!", "aluno_id": novo.get("id")})

    except requests.RequestException as e:
        return jsonify({"status": "erro", "mensagem": f"Erro de comunicação com Asaas: {str(e)}"}), 502
    except Exception as e:
        return jsonify({"status": "erro", "mensagem": f"Erro ao cadastrar aluno: {str(e)}"}), 500


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
            return jsonify({"status": "erro", "mensagem": "Campos obrigatórios: nome, cpf, valor, vencimento, descricao"}), 400

        session = requests.Session()

        url_consulta = f"{ASAAS_BASE_URL}/customers"
        params = {"cpfCnpj": cpf}
        r = session.get(url_consulta, headers=asaas_headers(), params=params, timeout=DEFAULT_TIMEOUT)
        r.raise_for_status()
        data = r.json()

        if data.get("totalCount", 0) == 0:
            return jsonify({"status": "erro", "mensagem": "Aluno não encontrado no Asaas para este CPF."}), 404

        aluno_id = data["data"][0]["id"]
        billing_type = "PIX" if forma == "PIX" else "BOLETO"

        payload = {
            "customer": aluno_id,
            "value": float(valor),
            "dueDate": venc,
            "description": descricao,
            "billingType": billing_type,
        }

        r = session.post(f"{ASAAS_BASE_URL}/payments", headers=asaas_headers(), json=payload, timeout=DEFAULT_TIMEOUT)
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
        return jsonify({"status": "erro", "mensagem": f"Erro de comunicação com Asaas: {str(e)}"}), 502
    except Exception as e:
        return jsonify({"status": "erro", "mensagem": f"Erro ao emitir fatura: {str(e)}"}), 500


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
            return jsonify({"status": "erro", "mensagem": "Campos obrigatórios: nome, cpf"}), 400

        session = requests.Session()

        url = f"{ASAAS_BASE_URL}/customers"
        params = {"cpfCnpj": cpf}
        r = session.get(url, headers=asaas_headers(), params=params, timeout=DEFAULT_TIMEOUT)
        r.raise_for_status()
        data = r.json()

        if data.get("totalCount") == 0:
            return jsonify({"status": "erro", "mensagem": "Aluno não encontrado."}), 404

        aluno_id = data["data"][0]["id"]

        url_pay = f"{ASAAS_BASE_URL}/payments"
        r = session.get(url_pay, headers=asaas_headers(), params={"customer": aluno_id, "limit": 100}, timeout=DEFAULT_TIMEOUT)
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

        return jsonify({"status": "ok", "mensagem": f"{len(faturas)} faturas encontradas.", "faturas": faturas})

    except requests.RequestException as e:
        return jsonify({"status": "erro", "mensagem": f"Erro de comunicação com Asaas: {str(e)}"}), 502
    except Exception as e:
        return jsonify({"status": "erro", "mensagem": f"Erro ao verificar faturas: {str(e)}"}), 500


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
            return jsonify({"status": "erro", "mensagem": "Campos obrigatórios: nome, cpf"}), 400

        session = requests.Session()

        url = f"{ASAAS_BASE_URL}/customers"
        params = {"cpfCnpj": cpf}
        r = session.get(url, headers=asaas_headers(), params=params, timeout=DEFAULT_TIMEOUT)
        r.raise_for_status()
        data = r.json()

        if data.get("totalCount") == 0:
            return jsonify({"status": "erro", "mensagem": "Aluno não encontrado."}), 404

        aluno_id = data["data"][0]["id"]

        url_pay = f"{ASAAS_BASE_URL}/payments"
        r = session.get(url_pay, headers=asaas_headers(), params={"customer": aluno_id, "limit": 100}, timeout=DEFAULT_TIMEOUT)
        r.raise_for_status()
        lista = r.json().get("data", [])

        if not lista:
            return jsonify({"status": "erro", "mensagem": "Nenhuma fatura encontrada."}), 404

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
        return jsonify({"status": "erro", "mensagem": f"Erro de comunicação com Asaas: {str(e)}"}), 502
    except Exception as e:
        return jsonify({"status": "erro", "mensagem": f"Erro ao buscar último link: {str(e)}"}), 500


# ========= ROTA: RELATÓRIO POR POLO - HISTÓRICO (OTIMIZADA) =========
@app.route("/api/relatorio_polo_historico", methods=["POST"])
def relatorio_polo_historico():
    ok, resp_err = ensure_asaas_configured()
    if not ok:
        return resp_err, 500

    try:
        dados = request.get_json() or {}
        polo = dados.get("polo")

        # filtros opcionais (recomendado)
        data_inicial = dados.get("data_inicial")  # "YYYY-MM-DD" (opcional) -> usa paymentDate
        data_final = dados.get("data_final")      # "YYYY-MM-DD" (opcional) -> usa paymentDate
        status_filtro = (dados.get("status") or "").strip().upper()  # ex: RECEIVED

        # limites anti-SIGKILL (ajuste conforme sua realidade)
        max_clientes = int(dados.get("max_clientes", 300))
        max_faturas_por_cliente = int(dados.get("max_faturas_cliente", 50))
        max_registros = int(dados.get("max_registros", 5000))

        if not polo:
            return jsonify({"status": "erro", "mensagem": "Campo obrigatório: polo"}), 400

        dt_ini = None
        dt_fim = None
        if data_inicial:
            dt_ini = datetime.strptime(data_inicial, "%Y-%m-%d").date()
        if data_final:
            dt_fim = datetime.strptime(data_final, "%Y-%m-%d").date()

        clientes = get_customers_by_polo(polo)
        if not clientes:
            return jsonify({"status": "erro", "mensagem": f"Nenhum cliente encontrado para o polo {polo}."}), 404

        clientes = clientes[:max_clientes]

        registros = []
        session = requests.Session()

        for cli in clientes:
            if len(registros) >= max_registros:
                break

            aluno_id = cli.get("id")
            nome = cli.get("name")
            cpf = cli.get("cpfCnpj")
            comp = cli.get("complement")

            try:
                url_pay = f"{ASAAS_BASE_URL}/payments"
                r = session.get(
                    url_pay,
                    headers=asaas_headers(),
                    params={"customer": aluno_id, "limit": max_faturas_por_cliente},
                    timeout=DEFAULT_TIMEOUT,
                )
                r.raise_for_status()
                lista = r.json().get("data", [])
            except Exception:
                continue

            for fat in lista:
                if len(registros) >= max_registros:
                    break

                st = (fat.get("status") or "").upper()
                if status_filtro and st != status_filtro:
                    continue

                pay_date_str = fat.get("paymentDate")

                # filtro por período baseado em paymentDate
                if dt_ini or dt_fim:
                    if not pay_date_str:
                        continue
                    try:
                        pay_date = datetime.strptime(pay_date_str, "%Y-%m-%d").date()
                    except ValueError:
                        continue
                    if dt_ini and pay_date < dt_ini:
                        continue
                    if dt_fim and pay_date > dt_fim:
                        continue

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
                        "status": st,
                        "data_pagamento": pay_date_str,
                        "link_pagamento": fat.get("invoiceUrl"),
                    }
                )

        registros.sort(key=lambda x: (x.get("nome") or "", x.get("vencimento") or ""))

        return jsonify(
            {
                "status": "ok",
                "mensagem": f"{len(registros)} registros retornados (limitado para evitar travamento).",
                "polo": polo,
                "max_clientes": max_clientes,
                "max_faturas_cliente": max_faturas_por_cliente,
                "max_registros": max_registros,
                "faturas": registros,
            }
        )

    except Exception as e:
        return jsonify({"status": "erro", "mensagem": f"Erro ao gerar relatório por polo (histórico): {str(e)}"}), 500


# ========= ROTA: RELATÓRIO POR POLO - PAGAMENTOS (OTIMIZADA) =========
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

        # limites (ajuste conforme sua realidade)
        max_clientes = int(dados.get("max_clientes", 300))
        max_faturas_por_cliente = int(dados.get("max_faturas_cliente", 100))
        max_pagamentos = int(dados.get("max_pagamentos", 5000))

        if not polo or not data_inicial or not data_final:
            return jsonify({"status": "erro", "mensagem": "Campos obrigatórios: polo, data_inicial, data_final"}), 400

        try:
            dt_ini = datetime.strptime(data_inicial, "%Y-%m-%d").date()
            dt_fim = datetime.strptime(data_final, "%Y-%m-%d").date()
        except ValueError:
            return jsonify({"status": "erro", "mensagem": "Datas devem estar no formato YYYY-MM-DD"}), 400

        clientes = get_customers_by_polo(polo)
        if not clientes:
            return jsonify({"status": "erro", "mensagem": f"Nenhum cliente encontrado para o polo {polo}."}), 404

        clientes = clientes[:max_clientes]

        pagamentos = []
        session = requests.Session()

        for cli in clientes:
            if len(pagamentos) >= max_pagamentos:
                break

            aluno_id = cli.get("id")
            nome = cli.get("name")
            cpf = cli.get("cpfCnpj")
            comp = cli.get("complement")

            try:
                url_pay = f"{ASAAS_BASE_URL}/payments"
                r = session.get(
                    url_pay,
                    headers=asaas_headers(),
                    params={"customer": aluno_id, "limit": max_faturas_por_cliente},
                    timeout=DEFAULT_TIMEOUT,
                )
                r.raise_for_status()
                lista = r.json().get("data", [])
            except Exception:
                continue

            for fat in lista:
                if len(pagamentos) >= max_pagamentos:
                    break

                status = (fat.get("status") or "").upper()
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

                valor_liq = fat.get("netValue") if fat.get("netValue") is not None else fat.get("value")

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
                "max_clientes": max_clientes,
                "max_faturas_cliente": max_faturas_por_cliente,
                "max_pagamentos": max_pagamentos,
                "pagamentos": pagamentos,
            }
        )

    except Exception as e:
        return jsonify({"status": "erro", "mensagem": f"Erro ao gerar relatório por polo (pagamentos): {str(e)}"}), 500


# ========= CRIAR TABELAS + INSERIR CHAVES FIXAS =========
with app.app_context():
    db.create_all()
    ensure_fixed_keys()


# ========= EXECUÇÃO LOCAL =========
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)

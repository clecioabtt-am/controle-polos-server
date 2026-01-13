vsdvss
dfrom flask import Flask, request, jsonify
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

DEFAULT_TIMEOUT = int(os.getenv("DEFAULT_TIMEOUT", "30"))

DEFAULT_MAX_CLIENTES = int(os.getenv("DEFAULT_MAX_CLIENTES", "250"))
DEFAULT_MAX_FATURAS_CLIENTE = int(os.getenv("DEFAULT_MAX_FATURAS_CLIENTE", "60"))
DEFAULT_MAX_REGISTROS = int(os.getenv("DEFAULT_MAX_REGISTROS", "5000"))


# ========= HEADERS =========
def asaas_headers():
    return {
        "accept": "application/json",
        "content-type": "application/json",
        "access_token": ASAAS_API_KEY,
    }


def _norm(s: str) -> str:
    return (s or "").strip().lower()


def ensure_asaas_configured():
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


# ========= FIXAS =========
def ensure_fixed_keys():
    for chave, info in FIXED_KEYS.items():
        if not Partner.query.get(chave):
            db.session.add(
                Partner(
                    chave=chave,
                    nome=info["nome"],
                    polo=info["polo"],
                    expira_em=info["expira_em"],
                )
            )
    db.session.commit()


# ========= UTIL =========
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


# ========= ASAAS HELPERS =========
def get_customers_by_polo(
    polo: str,
    *,
    max_loops: int = 60,
    limit: int = 100,
    max_customers: int = 250,
):
    """
    Busca clientes cujo 'complement' == polo.
    IMPORTANTE: para cedo quando atingir max_customers (evita timeout).
    """
    polo_norm = _norm(polo)
    clientes = []
    offset = 0
    url = f"{ASAAS_BASE_URL}/customers"

    session = requests.Session()

    for _ in range(max_loops):
        if len(clientes) >= max_customers:
            break

        try:
            r = session.get(
                url,
                headers=asaas_headers(),
                params={"limit": limit, "offset": offset},
                timeout=DEFAULT_TIMEOUT,
            )
            r.raise_for_status()
            data = r.json()
        except Exception:
            break

        lista = data.get("data", [])
        if not lista:
            break

        for c in lista:
            if _norm(c.get("complement")) == polo_norm:
                clientes.append(c)
                if len(clientes) >= max_customers:
                    break

        if len(lista) < limit:
            break

        offset += limit

    return clientes


# ========= TESTE =========
@app.route("/teste", methods=["GET"])
def teste():
    return jsonify({"mensagem": "Servidor funcionando com sucesso!"})


# ========= ADMIN =========
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
                    db.session.add(Partner(chave=chave, nome=nome, polo=polo, expira_em=expira_em))
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


# ========= LOGIN =========
@app.route("/login", methods=["POST"])
def login():
    dados = request.get_json(silent=True) or {}
    chave = (dados.get("chave_acesso") or "").strip().upper()

    if not chave:
        return jsonify({"status": "erro", "mensagem": "Chave vazia"}), 200

    parceiro = Partner.query.get(chave)
    if not parceiro:
        return jsonify({"status": "erro", "mensagem": "Chave inválida"}), 200

    if is_expired(parceiro.expira_em or ""):
        return jsonify({"status": "erro", "mensagem": "Chave expirada"}), 200

    return jsonify(
        {
            "status": "ok",
            "mensagem": "Acesso autorizado",
            "polo": parceiro.polo,
            "parceiro": parceiro.nome,
            "chave": parceiro.chave,
        }
    ), 200


# ========= RELATÓRIO HISTÓRICO =========
@app.route("/api/relatorio_polo_historico", methods=["POST"])
def relatorio_polo_historico():
    ok, resp_err = ensure_asaas_configured()
    if not ok:
        base = resp_err.get_json() if hasattr(resp_err, "get_json") else {"status": "erro", "mensagem": "Erro de configuração."}
        base.update({"polo": None, "faturas": []})
        return jsonify(base), 200

    try:
        dados = request.get_json(silent=True) or {}
        polo = dados.get("polo")

        if not polo:
            return jsonify({"status": "erro", "mensagem": "Campo obrigatório: polo", "polo": None, "faturas": []}), 200

        max_clientes = int(dados.get("max_clientes", DEFAULT_MAX_CLIENTES))
        max_faturas_cliente = int(dados.get("max_faturas_cliente", DEFAULT_MAX_FATURAS_CLIENTE))
        max_registros = int(dados.get("max_registros", DEFAULT_MAX_REGISTROS))

        status_filtro = (dados.get("status") or "").strip().upper()  # opcional
        data_inicial = dados.get("data_inicial")  # opcional YYYY-MM-DD (paymentDate)
        data_final = dados.get("data_final")      # opcional YYYY-MM-DD (paymentDate)

        dt_ini = None
        dt_fim = None
        if data_inicial:
            dt_ini = datetime.strptime(data_inicial, "%Y-%m-%d").date()
        if data_final:
            dt_fim = datetime.strptime(data_final, "%Y-%m-%d").date()

        clientes = get_customers_by_polo(polo, max_customers=max_clientes)
        if not clientes:
            return jsonify({"status": "erro", "mensagem": f"Nenhum cliente encontrado para o polo {polo}.", "polo": polo, "faturas": []}), 200

        session = requests.Session()
        registros = []

        for cli in clientes:
            if len(registros) >= max_registros:
                break

            aluno_id = cli.get("id")
            nome = cli.get("name")
            cpf = cli.get("cpfCnpj")
            comp = cli.get("complement")

            try:
                r = session.get(
                    f"{ASAAS_BASE_URL}/payments",
                    headers=asaas_headers(),
                    params={"customer": aluno_id, "limit": max_faturas_cliente},
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
                "mensagem": f"{len(registros)} faturas encontradas para o polo {polo}.",
                "polo": polo,
                "faturas": registros,
            }
        ), 200

    except Exception as e:
        d = request.get_json(silent=True) or {}
        return jsonify(
            {
                "status": "erro",
                "mensagem": f"Erro ao gerar relatório por polo (histórico): {str(e)}",
                "polo": d.get("polo"),
                "faturas": [],
            }
        ), 200


# ========= RELATÓRIO PAGAMENTOS =========
@app.route("/api/relatorio_polo_pagamentos", methods=["POST"])
def relatorio_polo_pagamentos():
    ok, resp_err = ensure_asaas_configured()
    if not ok:
        base = resp_err.get_json() if hasattr(resp_err, "get_json") else {"status": "erro", "mensagem": "Erro de configuração."}
        base.update({"polo": None, "data_inicial": None, "data_final": None, "pagamentos": []})
        return jsonify(base), 200

    try:
        dados = request.get_json(silent=True) or {}
        polo = dados.get("polo")
        data_inicial = dados.get("data_inicial")
        data_final = dados.get("data_final")

        if not polo or not data_inicial or not data_final:
            return jsonify(
                {
                    "status": "erro",
                    "mensagem": "Campos obrigatórios: polo, data_inicial, data_final",
                    "polo": polo,
                    "data_inicial": data_inicial,
                    "data_final": data_final,
                    "pagamentos": [],
                }
            ), 200

        max_clientes = int(dados.get("max_clientes", DEFAULT_MAX_CLIENTES))
        max_faturas_cliente = int(dados.get("max_faturas_cliente", DEFAULT_MAX_FATURAS_CLIENTE))
        max_pagamentos = int(dados.get("max_pagamentos", DEFAULT_MAX_REGISTROS))

        try:
            dt_ini = datetime.strptime(data_inicial, "%Y-%m-%d").date()
            dt_fim = datetime.strptime(data_final, "%Y-%m-%d").date()
        except ValueError:
            return jsonify(
                {
                    "status": "erro",
                    "mensagem": "Datas devem estar no formato YYYY-MM-DD",
                    "polo": polo,
                    "data_inicial": data_inicial,
                    "data_final": data_final,
                    "pagamentos": [],
                }
            ), 200

        clientes = get_customers_by_polo(polo, max_customers=max_clientes)
        if not clientes:
            return jsonify(
                {
                    "status": "erro",
                    "mensagem": f"Nenhum cliente encontrado para o polo {polo}.",
                    "polo": polo,
                    "data_inicial": data_inicial,
                    "data_final": data_final,
                    "pagamentos": [],
                }
            ), 200

        session = requests.Session()
        pagamentos = []

        for cli in clientes:
            if len(pagamentos) >= max_pagamentos:
                break

            aluno_id = cli.get("id")
            nome = cli.get("name")
            cpf = cli.get("cpfCnpj")
            comp = cli.get("complement")

            try:
                r = session.get(
                    f"{ASAAS_BASE_URL}/payments",
                    headers=asaas_headers(),
                    params={"customer": aluno_id, "limit": max_faturas_cliente},
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
                "pagamentos": pagamentos,
            }
        ), 200

    except Exception as e:
        d = request.get_json(silent=True) or {}
        return jsonify(
            {
                "status": "erro",
                "mensagem": f"Erro ao gerar relatório por polo (pagamentos): {str(e)}",
                "polo": d.get("polo"),
                "data_inicial": d.get("data_inicial"),
                "data_final": d.get("data_final"),
                "pagamentos": [],
            }
        ), 200


# ========= INIT DB =========
with app.app_context():
    db.create_all()
    ensure_fixed_keys()


# ========= RUN LOCAL =========
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)

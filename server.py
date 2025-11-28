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
    "JAINA.POLO": {
        "nome": "Jaina",
        "polo": "Polo Jaina",
        "expira_em": None,
    },
    "GABRIEL.POLO": {
        "nome": "Gabriel",
        "polo": "Polo Gabriel",
        "expira_em": None,
    },
    "LUCIANO.POLO": {
        "nome": "Luciano",
        "polo": "Polo Luciano",
        "expira_em": None,
    },
}

# ========= CONFIG ASAAS =========
ASAAS_API_KEY = os.getenv("ASAAS_API_KEY", "SUA_CHAVE_API_AQUI")
ASAAS_BASE_URL = os.getenv("ASAAS_BASE_URL", "https://www.asaas.com/api/v3")


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
        return date.today() > d
    except:
        return False


def ensure_asaas_configured():
    if ASAAS_API_KEY == "SUA_CHAVE_API_AQUI" or not ASAAS_API_KEY:
        return (False, jsonify({
            "status": "erro",
            "mensagem": "Configure a variável ASAAS_API_KEY no Render."
        }))
    return True, None


def get_customers_by_polo(polo: str):
    polo_norm = (polo or "").strip().lower()
    clientes = []
    url = f"{ASAAS_BASE_URL}/customers"
    limit = 100
    offset = 0

    for _ in range(50):
        try:
            params = {"limit": limit, "offset": offset}
            r = requests.get(url, headers=asaas_headers(), params=params, timeout=30)
            r.raise_for_status()
            data = r.json()
        except:
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
@app.route("/teste")
def teste():
    return jsonify({"mensagem": "Servidor funcionando!"})

# ========= PAINEL ADMIN =========
@app.route("/admin", methods=["GET", "POST"])
def admin():
    mensagem = ""

    if request.method == "POST":
        delete_key = (request.form.get("delete_key") or "").strip()

        # ❌ Impedir deletar chaves fixas
        if delete_key in FIXED_KEYS:
            mensagem = f"⚠️ A chave {delete_key} é fixa e não pode ser removida."
        elif delete_key:
            parceiro = Partner.query.get(delete_key)
            if parceiro:
                db.session.delete(parceiro)
                db.session.commit()
                mensagem = f"Chave removida: {delete_key}"
            else:
                mensagem = f"Chave {delete_key} não encontrada."
        else:
            nome = (request.form.get("nome") or "").strip()
            polo = (request.form.get("polo") or "").strip()
            expira_em = (request.form.get("expira_em") or "").strip()
            chave_manual = (request.form.get("chave") or "").strip().upper()

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
                        db.session.add(Partner(
                            chave=chave_manual,
                            nome=nome,
                            polo=polo,
                            expira_em=expira_em,
                        ))
                    db.session.commit()
                    mensagem = f"Chave salva: {chave_manual}"
            else:
                chave = generate_access_key()
                db.session.add(Partner(
                    chave=chave, nome=nome, polo=polo, expira_em=expira_em
                ))
                db.session.commit()
                mensagem = f"Chave gerada: {chave}"

    parceiros = Partner.query.order_by(Partner.nome.asc()).all()

    # HTML…
    html = """
    <!DOCTYPE html>
    <html><head><meta charset="utf-8"><title>Painel</title>
    <style>
        body { background:#0D47A1; color:black; font-family:Arial; }
        .container { background:white; padding:20px; margin:40px auto; width:1100px; border-radius:10px; }
        table { width:100%; border-collapse:collapse; }
        th,td { border-bottom:1px solid #ddd; padding:8px; }
        th { background:#f2f2f2; }
        .msg { color:green; }
        .fixo { color:blue; font-weight:bold; }
    </style></head><body>
    <div class='container'>
        <h1>Painel de Parceiros</h1>
    """
    if mensagem:
        html += f"<div class='msg'>{mensagem}</div>"

    html += """
        <form method="POST">
            <p><b>Nome:</b> <input name="nome"></p>
            <p><b>Polo:</b> <input name="polo"></p>
            <p><b>Expira em:</b> <input name="expira_em"></p>
            <p><b>Chave manual:</b> <input name="chave"></p>
            <button>Salvar</button>
        </form>

        <h2>Chaves cadastradas</h2>
        <table>
        <tr><th>Chave</th><th>Nome</th><th>Polo</th><th>Expira</th><th>Status</th><th>Ação</th></tr>
    """

    for p in parceiros:
        exp = "Expirada" if is_expired(p.expira_em or "") else "Ativa"
        cor = "red" if exp == "Expirada" else "green"
        fixa = p.chave in FIXED_KEYS

        html += f"""
        <tr>
            <td class='{"fixo" if fixa else ""}'>{p.chave}</td>
            <td>{p.nome}</td>
            <td>{p.polo or ""}</td>
            <td>{p.expira_em or ""}</td>
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
            </td></tr>
            """

    html += "</table></div></body></html>"
    return html

# ========= LOGIN ANDROID =========
@app.route("/login", methods=["POST"])
def login():
    dados = request.get_json() or {}
    chave = (dados.get("chave_acesso") or "").strip().upper()

    parceiro = Partner.query.get(chave)
    if not parceiro:
        return jsonify({"status": "erro", "mensagem": "Chave inválida"}), 401

    if is_expired(parceiro.expira_em or ""):
        return jsonify({"status": "erro", "mensagem": "Chave expirada"}), 403

    return jsonify({
        "status": "ok",
        "mensagem": "Acesso autorizado",
        "polo": parceiro.polo,
        "parceiro": parceiro.nome,
        "chave": parceiro.chave,
    })

# ==========================================
# (resto do seu código Asaas permanece igual)
# ==========================================

# ========= CRIAR TABELAS + INSERIR CHAVES FIXAS =========
with app.app_context():
    db.create_all()
    ensure_fixed_keys()

# ========= RUN LOCAL =========
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)

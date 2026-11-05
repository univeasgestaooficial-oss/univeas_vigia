import os
import json
import uuid
from datetime import datetime
from fastapi import FastAPI, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import firebase_admin
from firebase_admin import credentials, firestore

# ==========================================
# 1. CONEXÃO COM O GOOGLE FIRESTORE
# ==========================================
# Busca o JSON de credenciais armazenado de forma segura na Vercel
firebase_env = os.getenv("FIREBASE_CREDENTIALS")

if firebase_env and not firebase_admin._apps:
    try:
        cred_dict = json.loads(firebase_env)
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)
    except Exception as e:
        print(f"Erro ao inicializar Firebase: {e}")

# Instância global do banco de dados
db = firestore.client() if firebase_admin._apps else None

# ==========================================
# 2. INICIALIZAÇÃO DA API
# ==========================================
app = FastAPI(title="SIGA UNIVEAS - Produção Firebase")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def checar_db():
    if not db:
        raise HTTPException(status_code=500, detail="Banco de dados não conectado.")


# ==========================================
# 3. MÓDULO ADMINISTRADOR - ALUNOS (CRUD COMPLETO)
# ==========================================

@app.get("/api/v1/alunos")
async def listar_alunos():
    """LÊ dados reais do banco (R - Read)"""
    checar_db()
    docs = db.collection("alunos").stream()
    alunos = [{"id": doc.id, **doc.to_dict()} for doc in docs]
    return alunos


@app.post("/api/v1/alunos/matricular")
async def matricular_aluno(
        nome: str = Form(...), cpf: str = Form(...), email: str = Form(...),
        telefone: str = Form(...), endereco: str = Form(...), curso_id: str = Form(...)
):
    """SALVA um novo aluno no banco (C - Create)"""
    checar_db()
    matricula_gerada = f"#{datetime.now().strftime('%Y%m')}{str(uuid.uuid4().int)[:4]}"

    novo_aluno = {
        "matricula": matricula_gerada,
        "cpf": cpf,
        "nome": nome,
        "email": email,
        "telefone": telefone,
        "endereco": endereco,
        "curso": curso_id,
        "status": "Pendente",
        "data_cadastro": datetime.now().isoformat()
    }

    # Adiciona a coleção 'alunos'
    _, doc_ref = db.collection("alunos").add(novo_aluno)
    return {"sucesso": True, "id": doc_ref.id, "matricula": matricula_gerada}


@app.put("/api/v1/alunos/{aluno_id}")
async def alterar_aluno(aluno_id: str, nome: str = Form(None), status: str = Form(None)):
    """ALTERA dados de um aluno existente (U - Update)"""
    checar_db()
    ref = db.collection("alunos").document(aluno_id)

    if not ref.get().exists:
        raise HTTPException(status_code=404, detail="Aluno não encontrado.")

    atualizacoes = {}
    if nome: atualizacoes["nome"] = nome
    if status: atualizacoes["status"] = status

    ref.update(atualizacoes)
    return {"sucesso": True, "mensagem": "Aluno atualizado com sucesso"}


@app.delete("/api/v1/alunos/{aluno_id}")
async def excluir_aluno(aluno_id: str):
    """EXCLUI um aluno do banco (D - Delete)"""
    checar_db()
    db.collection("alunos").document(aluno_id).delete()
    return {"sucesso": True, "mensagem": "Aluno removido com sucesso"}


# ==========================================
# 4. MÓDULO ADMINISTRADOR - DOCENTES E CURSOS
# ==========================================

@app.get("/api/v1/docentes")
async def listar_docentes():
    checar_db()
    docs = db.collection("docentes").stream()
    return [{"id": doc.id, **doc.to_dict()} for doc in docs]


@app.post("/api/v1/docentes")
async def cadastrar_docente(nome_prestador: str = Form(...), cpf_prestador: str = Form(...),
                            tipo_profissional: str = Form(...)):
    checar_db()
    registro_gerado = f"#PR{str(uuid.uuid4().int)[:4]}"
    novo_docente = {
        "registro": registro_gerado,
        "nome": nome_prestador,
        "cpf": cpf_prestador,
        "tipo_profissional": tipo_profissional,
        "status": "Ativo"
    }
    db.collection("docentes").add(novo_docente)
    return {"sucesso": True, "mensagem": "Docente salvo."}


@app.delete("/api/v1/docentes/{docente_id}")
async def excluir_docente(docente_id: str):
    checar_db()
    db.collection("docentes").document(docente_id).delete()
    return {"sucesso": True}


@app.get("/api/v1/cursos")
async def listar_cursos():
    checar_db()
    docs = db.collection("cursos").stream()
    return [{"id": doc.id, **doc.to_dict()} for doc in docs]


@app.post("/api/v1/cursos")
async def registrar_curso(codigo: str = Form(...), nome_curso: str = Form(...), valor_mensalidade: float = Form(...)):
    checar_db()
    db.collection("cursos").add({"codigo": codigo, "nome_curso": nome_curso, "valor_mensalidade": valor_mensalidade})
    return {"sucesso": True}


# ==========================================
# 5. MÓDULO FINANCEIRO
# ==========================================
@app.get("/api/v1/financeiro/mensalidades")
async def listar_mensalidades():
    checar_db()
    docs = db.collection("mensalidades").stream()
    return {"lista": [{"id": doc.id, **doc.to_dict()} for doc in docs]}


@app.post("/api/v1/financeiro/baixar/{mensalidade_id}")
async def dar_baixa_mensalidade(mensalidade_id: str):
    """Carimba a mensalidade como PAGA"""
    checar_db()
    db.collection("mensalidades").document(mensalidade_id).update(
        {"status": "Pago", "data_pagamento": datetime.now().isoformat()})
    return {"sucesso": True, "mensagem": "Baixa realizada."}

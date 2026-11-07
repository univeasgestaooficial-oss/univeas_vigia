import os
import json
import uuid
from datetime import datetime
from fastapi.middleware.cors import CORSMiddleware
import firebase_admin
from fastapi import FastAPI, Form, HTTPException, File, UploadFile
from firebase_admin import credentials, firestore, storage
# ==========================================
# 1. CONEXÃO COM O GOOGLE FIRESTORE
# ==========================================
# Busca o JSON de credenciais armazenado de forma segura na Vercel
firebase_env = os.getenv("FIREBASE_CREDENTIALS")

if firebase_env and not firebase_admin._apps:
    try:
        cred_dict = json.loads(firebase_env)
        cred = credentials.Certificate(cred_dict)

        firebase_admin.initialize_app(cred, {
            'storageBucket': 'seu-projeto-id.appspot.com'
        })
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
# 2.5 AUTENTICAÇÃO DO ADMINISTRADOR
# ==========================================
@app.post("/api/v1/master")
async def login_administrador(senha: str = Form(...)):
    senha_segura_vercel = os.getenv("KEY_ADMIN")
    if not senha_segura_vercel:
        raise HTTPException(status_code=500, detail="Erro interno: Variável KEY_ADMIN não configurada na Vercel.")
    if senha == senha_segura_vercel:
        # Se a senha bater, retorna o token de acesso para o JS salvar no localStorage
        return {
            "sucesso": True,
            "token_siga": "admin_token_autorizado",
            "redirecionar": "/admin.html"
        }
    else:
        raise HTTPException(status_code=401, detail="Senha incorreta. Acesso negado.")


# ==========================================
# 2.6 AUTENTICAÇÃO DO PROFESSOR (DOCENTE)
# ==========================================
@app.post("/api/v1/auth/docente")
async def login_docente(registro: str = Form(...), cpf: str = Form(...)):
    """Valida o acesso do professor consultando a coleção 'docentes' no Firestore"""
    checar_db()

    # Faz a busca no banco procurando o documento exato
    docs = db.collection("docentes").where("registro", "==", registro).where("cpf", "==", cpf).stream()

    docente_encontrado = None
    for doc in docs:
        docente_encontrado = {"id": doc.id, **doc.to_dict()}
        break  # Pega o primeiro que bater

    if docente_encontrado:
        # Se encontrou, gera o token e devolve os dados
        return {
            "sucesso": True,
            "token_siga": f"docente_{docente_encontrado['id']}",
            "nome_professor": docente_encontrado["nome"],
            "registro": docente_encontrado["registro"]
        }
    else:
        raise HTTPException(status_code=401, detail="Registro ou CPF incorretos. Acesso negado.")


# ==========================================
# 2.7 AUTENTICAÇÃO DO ALUNO (ESTUDANTE)
# ==========================================
@app.post("/api/v1/auth/aluno")
async def login_aluno(matricula: str = Form(...), cpf: str = Form(...)):
    """Valida o acesso do aluno consultando a coleção 'alunos' no Firestore"""
    checar_db()

    # Faz a busca no banco procurando o documento exato
    docs = db.collection("alunos").where("matricula", "==", matricula).where("cpf", "==", cpf).stream()

    aluno_encontrado = None
    for doc in docs:
        aluno_encontrado = {"id": doc.id, **doc.to_dict()}
        break

    if aluno_encontrado:
        return {
            "sucesso": True,
            "token_siga": f"aluno_{aluno_encontrado['id']}",
            "nome_aluno": aluno_encontrado["nome"],
            "matricula": aluno_encontrado["matricula"]
        }
    else:
        raise HTTPException(status_code=401, detail="Matrícula ou CPF incorretos. Acesso negado.")


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
async def cadastrar_docente(
        nome_prestador: str = Form(...),
        cpf_prestador: str = Form(...),
        telefone_prestador: str = Form(...),
        tipo_profissional: str = Form(...),
        curso_id: str = Form(...)  # <- ADICIONADO AQUI PARA LIGAR AO CURSO
):
    checar_db()
    registro_gerado = f"#PR{str(uuid.uuid4().int)[:4]}"
    novo_docente = {
        "registro": registro_gerado,
        "nome": nome_prestador,
        "cpf": cpf_prestador,
        "telefone": telefone_prestador,
        "tipo_profissional": tipo_profissional,
        "curso_id": curso_id,  # <- SALVANDO NO BANCO DE DADOS
        "status": "Ativo"
    }
    db.collection("docentes").add(novo_docente)
    return {"sucesso": True, "mensagem": "Docente salvo com vínculo ao curso."}


@app.delete("/api/v1/docentes/{docente_id}")
async def excluir_docente(docente_id: str):
    checar_db()
    db.collection("docentes").document(docente_id).delete()
    return {"sucesso": True}


@app.get("/api/v1/cursos")
async def listar_cursos():
    """Lista todos os cursos"""
    checar_db()
    docs = db.collection("cursos").stream()
    return [{"id": doc.id, **doc.to_dict()} for doc in docs]


@app.get("/api/v1/cursos/{curso_id}")
async def obter_curso(curso_id: str):
    """Busca um curso específico pelo ID (usado para o modal de Edição)"""
    checar_db()
    doc = db.collection("cursos").document(curso_id).get()

    if not doc.exists:
        raise HTTPException(status_code=404, detail="Curso não encontrado.")

    return {"id": doc.id, **doc.to_dict()}


@app.post("/api/v1/cursos")
async def registrar_curso(
        codigo: str = Form(...),
        categoria: str = Form(None),
        nome_curso: str = Form(...),
        modalidade: str = Form(None),
        duracao: str = Form(None),
        valor_matricula: float = Form(None),
        valor_mensalidade: float = Form(...),
        descricao: str = Form(""),
        disciplinas_json: str = Form(...),
        promocao_ativa: str = Form(None),
        valor_promocional: str = Form(None),
        foto_capa: str = Form(None) # <- AGORA RECEBE APENAS O TEXTO DO LINK
):
    checar_db()

    # Processa a matriz de disciplinas
    try:
        grade_curricular = json.loads(disciplinas_json)
    except Exception:
        grade_curricular = []

    # Monta o pacote de dados
    novo_curso = {
        "codigo": codigo,
        "categoria": categoria,
        "nome_curso": nome_curso,
        "modalidade": modalidade,
        "duracao": duracao,
        "valor_matricula": valor_matricula,
        "valor_mensalidade": valor_mensalidade,
        "descricao": descricao,
        "grade_curricular": grade_curricular,
        "promocao_ativa": promocao_ativa,
        "valor_promocional": valor_promocional,
        "foto_capa": foto_capa # <- SALVA O LINK DIRETO NO BANCO
    }

    db.collection("cursos").add(novo_curso)
    return {"sucesso": True, "mensagem": "Curso registrado com matriz acadêmica e link da foto!"}


@app.put("/api/v1/cursos/{curso_id}")
async def alterar_curso(
        curso_id: str,
        codigo: str = Form(None),
        nome_curso: str = Form(None),
        valor_mensalidade: float = Form(None),
        qtd_modulos: int = Form(None),
        qtd_avaliacoes: int = Form(None),
        tipo_avaliacao: str = Form(None),
        nomes_modulos: str = Form(None),
        descricao: str = Form(None),
        matriz_curricular: str = Form(None),
        disciplinas_json: str = Form(None)
):
    """Edita um curso existente"""
    checar_db()
    ref = db.collection("cursos").document(curso_id)

    if not ref.get().exists:
        raise HTTPException(status_code=404, detail="Curso não encontrado.")

    atualizacoes = {}
    if codigo is not None: atualizacoes["codigo"] = codigo
    if nome_curso is not None: atualizacoes["nome_curso"] = nome_curso
    if valor_mensalidade is not None: atualizacoes["valor_mensalidade"] = float(valor_mensalidade)
    if qtd_modulos is not None: atualizacoes["qtd_modulos"] = int(qtd_modulos)
    if qtd_avaliacoes is not None: atualizacoes["qtd_avaliacoes"] = int(qtd_avaliacoes)
    if tipo_avaliacao is not None: atualizacoes["tipo_avaliacao"] = tipo_avaliacao
    if descricao is not None: atualizacoes["descricao"] = descricao
    if matriz_curricular is not None: atualizacoes["matriz_curricular"] = matriz_curricular

    if nomes_modulos is not None:
        atualizacoes["modulos_lista"] = [m.strip() for m in nomes_modulos.split(",")]

    if disciplinas_json is not None:
        try:
            atualizacoes["grade_curricular"] = json.loads(disciplinas_json)
        except Exception:
            pass

    ref.update(atualizacoes)
    return {"sucesso": True, "mensagem": "Curso atualizado com sucesso!"}


@app.delete("/api/v1/cursos/{curso_id}")
async def excluir_curso(curso_id: str):
    """Exclui permanentemente um curso do banco de dados"""
    checar_db()
    db.collection("cursos").document(curso_id).delete()
    return {"sucesso": True, "mensagem": "Curso excluído permanentemente."}


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


# ==========================================
# 6. MÓDULO DO DOCENTE (PORTAL DO PROFESSOR)
# ==========================================
from fastapi import Header


def validar_token_docente(authorization: str):
    """Extrai o ID do docente do token de sessão enviado pelo JS"""
    if not authorization or not authorization.startswith("Bearer docente_"):
        raise HTTPException(status_code=401, detail="Acesso não autorizado.")
    return authorization.replace("Bearer docente_", "")


@app.get("/api/v1/docente/dashboard")
async def obter_dashboard_docente(authorization: str = Header(None)):
    """Rota para carregar os números da tela principal do professor"""
    checar_db()
    docente_id = validar_token_docente(authorization)

    # Busca quantas turmas/cursos este professor tem
    # (Como o seu sistema é direto, ele busca os cursos vinculados ao ID do professor)
    doc_prof = db.collection("docentes").document(docente_id).get()

    if not doc_prof.exists:
        raise HTTPException(status_code=404, detail="Perfil de professor não encontrado")

    dados_prof = doc_prof.to_dict()
    curso_id = dados_prof.get("curso_id")

    return {
        "turmas_ativas": 1 if curso_id else 0,
        "diarios_pendentes": 0,
        "aulas_semana": 0,
        "curso_vinculado": curso_id
    }


@app.get("/api/v1/docente/turmas")
async def listar_turmas_docente(authorization: str = Header(None)):
    """Carrega as disciplinas para exibir nos cards da aba 'Minhas Turmas'"""
    checar_db()
    docente_id = validar_token_docente(authorization)

    doc_prof = db.collection("docentes").document(docente_id).get()
    dados_prof = doc_prof.to_dict()
    curso_id = dados_prof.get("curso_id")

    if not curso_id:
        return []

    # Busca os detalhes do curso que ele leciona
    curso_ref = db.collection("cursos").document(curso_id).get()
    if not curso_ref.exists:
        return []

    curso_dados = curso_ref.to_dict()

    # Transforma os módulos da grade curricular em "Turmas/Disciplinas" para o professor
    turmas_formatadas = []
    for modulo in curso_dados.get("grade_curricular", []):
        turmas_formatadas.append({
            "id": f"{curso_id}_{modulo.get('nome')}",
            "nome_disciplina": modulo.get("nome"),
            "curso_pai": curso_dados.get("nome_curso"),
            "carga_horaria": modulo.get("ch_total", 0)
        })

    return turmas_formatadas


@app.post("/api/v1/docente/diario/salvar")
async def salvar_diario_eletronico(
        turma_id: str = Form(...),
        data_aula: str = Form(...),
        conteudo: str = Form(...),
        notas_faltas: str = Form(...),
        authorization: str = Header(None)
):
    """Salva as notas, faltas e o conteúdo ministrado pelo professor"""
    checar_db()
    docente_id = validar_token_docente(authorization)

    try:
        lista_notas = json.loads(notas_faltas)
    except Exception:
        lista_notas = []

    registro_diario = {
        "docente_id": docente_id,
        "turma_id": turma_id,
        "data_aula": data_aula,
        "conteudo_ministrado": conteudo,
        "avaliacoes": lista_notas,
        "data_registro": datetime.now().isoformat()
    }

    db.collection("diarios").add(registro_diario)

    return {"sucesso": True, "mensagem": "Diário registrado com sucesso!"}

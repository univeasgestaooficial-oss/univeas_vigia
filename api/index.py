import os
import json
import uuid
from datetime import datetime
from fastapi.middleware.cors import CORSMiddleware
import firebase_admin
from fastapi import FastAPI, Form, HTTPException, File, UploadFile
from fastapi.responses import Response
from firebase_admin import credentials, firestore, storage
from fastapi.responses import HTMLResponse

# ==========================================
# 1. CONEXÃO COM O GOOGLE FIRESTORE
# ==========================================
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
# 2.3 DASHBOARD E INDICADORES (FALTAVA)
# ==========================================
@app.get("/api/v1/dashboard/indicadores")
async def obter_indicadores():
    checar_db()
    # Conta documentos reais do Firestore
    total_docentes = len(list(db.collection("docentes").stream()))
    total_alunos = len(list(db.collection("alunos").stream()))
    total_cursos = len(list(db.collection("cursos").stream()))

    return {
        "total_docentes": total_docentes,
        "alunos_ativos": total_alunos,
        "turmas_ativas": total_cursos,
        "total_inadimplencia": "4.2%",
        "notificacoes": [
            {"id": 1, "descricao": "Sistema operando normalmente em produção Firebase.", "status": "Ativo"}
        ]
    }


# ==========================================
# 2.5 AUTENTICAÇÃO DO ADMINISTRADOR
# ==========================================
@app.post("/api/v1/master")
async def login_administrador(senha: str = Form(...)):
    senha_segura_vercel = os.getenv("KEY_ADMIN")
    if not senha_segura_vercel:
        raise HTTPException(status_code=500, detail="Erro interno: Variável KEY_ADMIN não configurada na Vercel.")
    if senha == senha_segura_vercel:
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
    checar_db()
    docs = db.collection("docentes").where("registro", "==", registro).where("cpf", "==", cpf).stream()

    docente_encontrado = None
    for doc in docs:
        docente_encontrado = {"id": doc.id, **doc.to_dict()}
        break

    if docente_encontrado:
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
    checar_db()
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
    checar_db()
    docs = db.collection("alunos").stream()
    return [{"id": doc.id, **doc.to_dict()} for doc in docs]


@app.post("/api/v1/alunos/matricular")
async def matricular_aluno(
        nome: str = Form(...), cpf: str = Form(...), email: str = Form(...),
        telefone: str = Form(...), endereco: str = Form(...), curso_id: str = Form(...)
):
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

    _, doc_ref = db.collection("alunos").add(novo_aluno)
    return {"sucesso": True, "id": doc_ref.id, "matricula": matricula_gerada}


@app.delete("/api/v1/alunos/{aluno_id}")
async def excluir_aluno(aluno_id: str):
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
        curso_id: str = Form(...)
):
    checar_db()
    registro_gerado = f"#PR{str(uuid.uuid4().int)[:4]}"
    novo_docente = {
        "registro": registro_gerado,
        "nome": nome_prestador,
        "cpf": cpf_prestador,
        "telefone": telefone_prestador,
        "tipo_profissional": tipo_profissional,
        "curso_id": curso_id,
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
    checar_db()
    docs = db.collection("cursos").stream()
    return [{"id": doc.id, **doc.to_dict()} for doc in docs]


@app.get("/api/v1/cursos/{curso_id}")
async def obter_curso(curso_id: str):
    checar_db()
    doc = db.collection("cursos").document(curso_id).get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Curso não encontrado.")
    return {"id": doc.id, **doc.to_dict()}


# ==========================================
# 4.1 ROTA DE PDF DO CURSO (FALTAVA E CAUSAVA O ERRO)
# ==========================================
@app.get("/api/v1/cursos/{curso_id}/pdf", response_class=HTMLResponse)
async def gerar_pdf_curso(curso_id: str):
    checar_db()
    doc = db.collection("cursos").document(curso_id).get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Curso não encontrado para gerar PDF.")

    curso = doc.to_dict()
    nome_curso = curso.get('nome_curso', 'CURSO')
    codigo = curso.get('codigo', 'N/A')
    categoria = curso.get('categoria', 'Técnico').upper()
    modalidade = curso.get('modalidade', 'Presencial').upper()
    duracao = curso.get('duracao', 'Não informada')
    valor_mat = curso.get('valor_matricula', '0.00')
    valor_mens = curso.get('valor_mensalidade', '0.00')
    descricao = curso.get('descricao', 'Nenhuma descrição informada.')

    grade = curso.get('grade_curricular', [])

    # Calcula carga horária total
    ch_total_geral = sum([int(m.get('ch_total', 0)) for m in grade])

    # Monta o HTML institucional estilizado para impressão/PDF
    modulos_html = ""
    for i, m in enumerate(grade):
        dias = ", ".join(m.get('dias_aula', [])) or "A definir"

        avaliacoes_html = ""
        for aval in m.get('avaliacoes', []):
            avaliacoes_html += f"""
                <div style="background: #fff7ed; border-left: 3px solid #f97316; padding: 6px 10px; margin-top: 4px; font-size: 11px;">
                    <b>{aval.get('tipo', 'Avaliação').upper()}</b> — Data: {aval.get('data', 'A definir')} ({aval.get('hora_inicio', '--:--')} às {aval.get('hora_fim', '--:--')})
                </div>
            """

        modulos_html += f"""
        <div style="margin-bottom: 20px; border: 1px solid #e5e7eb; border-radius: 8px; padding: 15px; page-break-inside: avoid; background: #ffffff;">
            <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #14b8a6; padding-bottom: 8px; margin-bottom: 10px;">
                <h3 style="margin: 0; color: #111827; font-size: 14px; text-transform: uppercase;">
                    Módulo {i + 1}: {m.get('nome', 'Disciplina')}
                </h3>
                <span style="background: #14b8a6; color: white; padding: 3px 8px; border-radius: 4px; font-size: 11px; font-weight: bold;">
                    {m.get('ch_total', 0)}h Total
                </span>
            </div>
            <p style="margin: 5px 0 10px 0; color: #4b5563; font-size: 12px;"><b>Semestre/Bloco:</b> {m.get('semestre', '1º Semestre')} | <b>Ementa:</b> {m.get('descricao', 'Sem descrição.')}</p>

            <table style="width: 100%; font-size: 11px; color: #374151; margin-bottom: 8px; border-collapse: collapse;">
                <tr>
                    <td style="padding: 4px 0;"><b>Período:</b> {m.get('data_inicio', '--')} a {m.get('data_fim', '--')}</td>
                    <td style="padding: 4px 0;"><b>Dias de Aula:</b> {dias}</td>
                    <td style="padding: 4px 0;"><b>Horário:</b> {m.get('hora_aula_inicio', '--')} às {m.get('hora_aula_fim', '--')}</td>
                </tr>
                <tr>
                    <td style="padding: 4px 0;"><b>Teoria:</b> {m.get('ch_teoria', 0)}h</td>
                    <td style="padding: 4px 0;"><b>Prática:</b> {m.get('ch_pratica', 0)}h</td>
                    <td style="padding: 4px 0;"><b>Estágio:</b> {m.get('ch_estagio', 0)}h</td>
                </tr>
            </table>
            {avaliacoes_html}
        </div>
        """

    html_completo = f"""<!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <title>Matriz Curricular - {nome_curso}</title>
        <style>
            @page {{ size: A4; margin: 20mm; }}
            body {{ font-family: 'Helvetica', 'Arial', sans-serif; color: #1f2937; line-height: 1.5; margin: 0; padding: 0; }}
            .header {{ text-align: center; border-bottom: 3px solid #14b8a6; padding-bottom: 15px; margin-bottom: 25px; }}
            .header h1 {{ font-size: 20px; color: #111827; margin: 5px 0; text-transform: uppercase; }}
            .header h2 {{ font-size: 14px; color: #14b8a6; margin: 0; text-transform: uppercase; letter-spacing: 1px; }}
            .info-box {{ background: #f3f4f6; border-radius: 8px; padding: 15px; margin-bottom: 25px; font-size: 12px; }}
            .info-grid {{ width: 100%; border-collapse: collapse; }}
            .info-grid td {{ padding: 6px 10px; }}
            .footer {{ margin-top: 40px; text-align: center; font-size: 10px; color: #9ca3af; border-top: 1px solid #e5e7eb; pt: 10px; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h2>ESCOLA UNIVEAS — Sistema Integrado de Gestão Acadêmica</h2>
            <h1>Matriz Curricular Oficial</h1>
        </div>

        <div class="info-box">
            <table class="info-grid">
                <tr>
                    <td><b>Curso:</b> {nome_curso}</td>
                    <td><b>Código:</b> {codigo}</td>
                </tr>
                <tr>
                    <td><b>Categoria:</b> {categoria}</td>
                    <td><b>Modalidade:</b> {modalidade}</td>
                </tr>
                <tr>
                    <td><b>Duração Estimada:</b> {duracao}</td>
                    <td><b>Carga Horária Total:</b> <span style="color: #0d9488; font-weight: bold;">{ch_total_geral} Horas</span></td>
                </tr>
            </table>
        </div>

        <h3 style="font-size: 14px; text-transform: uppercase; border-left: 4px solid #14b8a6; padding-left: 8px; margin-bottom: 15px; color: #111827;">
            Estrutura Curricular e Cronograma de Módulos
        </h3>

        {modulos_html}

        <div class="footer">
            Documento gerado eletronicamente via SIGA UNIVEAS em {datetime.now().strftime('%d/%m/%Y às %H:%M')}.<br>
            Travessa Lauro Sodré, Centro - Vigia de Nazaré / PA.
        </div>
    </body>
    </html>
    """
    return html_completo

@app.put("/api/v1/cursos/{curso_id}")
async def atualizar_curso(
        curso_id: str,
        codigo: str = Form(...),
        nome_curso: str = Form(...),
        categoria: str = Form(...),
        modalidade: str = Form(...),
        valor_matricula: float = Form(...),
        valor_mensalidade: float = Form(...),
        descricao: str = Form(""),
        foto_capa: str = Form(""),
        disciplinas_json: str = Form("[]")
):
    checar_db()
    try:
        grade = json.loads(disciplinas_json)
    except Exception:
        grade = []

    dados_atualizados = {
        "codigo": codigo,
        "nome_curso": nome_curso.upper(),
        "categoria": categoria,
        "modalidade": modalidade,
        "valor_matricula": valor_matricula,
        "valor_mensalidade": valor_mensalidade,
        "descricao": descricao,
        "foto_capa": foto_capa,
        "grade_curricular": grade,
        "data_atualizacao": datetime.now().isoformat()
    }

    db.collection("cursos").document(curso_id).update(dados_atualizados)
    return {"sucesso": True, "mensagem": "Curso atualizado com sucesso"}


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
        foto_capa: str = Form(None)
):
    checar_db()
    try:
        grade_curricular = json.loads(disciplinas_json)
    except Exception:
        grade_curricular = []

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
        "foto_capa": foto_capa
    }

    db.collection("cursos").add(novo_curso)
    return {"sucesso": True, "mensagem": "Curso registrado com matriz acadêmica e link da foto!"}


@app.delete("/api/v1/cursos/{curso_id}")
async def excluir_curso(curso_id: str):
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
    checar_db()
    db.collection("mensalidades").document(mensalidade_id).update(
        {"status": "Pago", "data_pagamento": datetime.now().isoformat()})
    return {"sucesso": True, "mensagem": "Baixa realizada."}


# ==========================================
# 6. MÓDULO DO DOCENTE
# ==========================================
from fastapi import Header


def validar_token_docente(authorization: str):
    if not authorization or not authorization.startswith("Bearer docente_"):
        raise HTTPException(status_code=401, detail="Acesso não autorizado.")
    return authorization.replace("Bearer docente_", "")


@app.get("/api/v1/docente/dashboard")
async def obter_dashboard_docente(authorization: str = Header(None)):
    checar_db()
    docente_id = validar_token_docente(authorization)
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
    checar_db()
    docente_id = validar_token_docente(authorization)

    doc_prof = db.collection("docentes").document(docente_id).get()
    dados_prof = doc_prof.to_dict()
    curso_id = dados_prof.get("curso_id")

    if not curso_id:
        return []

    curso_ref = db.collection("cursos").document(curso_id).get()
    if not curso_ref.exists:
        return []

    curso_dados = curso_ref.to_dict()
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

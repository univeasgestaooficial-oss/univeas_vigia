import os
import json
import uuid
from datetime import datetime
from fastapi.middleware.cors import CORSMiddleware
import firebase_admin
from fastapi import FastAPI, Form, HTTPException, File, UploadFile
from fastapi.responses import Response
from firebase_admin import credentials, firestore, storage
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi import Response
from weasyprint import HTML
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


@app.get("/api/v1/cursos/{curso_id}/pdf")
async def gerar_pdf_curso(curso_id: str):
    checar_db()
    doc = db.collection("cursos").document(curso_id).get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Curso não encontrado.")

    curso = doc.to_dict()
    nome_curso = curso.get('nome_curso', 'CURSO')
    grade = curso.get('grade_curricular', [])

    modulos_html = ""
    for i, m in enumerate(grade):
        disciplinas = m.get('disciplinas', [])
        linhas_tabela = ""
        ch_teoria_mod = 0
        ch_pratica_mod = 0
        ch_es_mod = 0
        ch_total_mod = 0

        if disciplinas:
            for disc in disciplinas:
                t = int(disc.get('ch_teoria', 0))
                p = int(disc.get('ch_pratica', 0))
                es = int(disc.get('ch_es', 0))
                tot = t + p + es

                ch_teoria_mod += t
                ch_pratica_mod += p
                ch_es_mod += es
                ch_total_mod += tot

                linhas_tabela += f"""
                <tr>
                    <td>{disc.get('nome', 'Disciplina')}</td>
                    <td style="text-align: center;">{t if t > 0 else '-'}</td>
                    <td style="text-align: center;">{p if p > 0 else '-'}</td>
                    <td style="text-align: center;">{es if es > 0 else '-'}</td>
                    <td style="text-align: center; font-weight: bold;">{tot}</td>
                </tr>
                """
        else:
            t = int(m.get('ch_teoria', m.get('ch_total', 0)))
            ch_teoria_mod += t
            ch_total_mod += t
            linhas_tabela += f"""
            <tr>
                <td>{m.get('nome', 'Módulo / Disciplina')}</td>
                <td style="text-align: center;">{t}</td>
                <td style="text-align: center;">-</td>
                <td style="text-align: center;">-</td>
                <td style="text-align: center; font-weight: bold;">{t}</td>
            </tr>
            """

        cert_html = ""
        cert_texto = m.get('certificacao_intermediaria', '')
        if cert_texto:
            cert_html = f'<div class="cert-heading">{cert_texto}</div>'

        modulos_html += f"""
        <div class="module-wrapper">
            <div class="module-heading">Módulo {i + 1}: {m.get('nome', '')}</div>
            {cert_html}
            <table>
                <thead>
                    <tr>
                        <th rowspan="2" class="col-disciplina">Disciplinas</th>
                        <th colspan="4">Carga Horária</th>
                    </tr>
                    <tr>
                        <th class="col-ch">Teoria</th>
                        <th class="col-ch">Prática</th>
                        <th class="col-ch">ES</th>
                        <th class="col-ch">Total</th>
                    </tr>
                </thead>
                <tbody>
                    {linhas_tabela}
                    <tr class="total-row">
                        <td>CH DO MÓDULO</td>
                        <td style="text-align: center;">{ch_teoria_mod}</td>
                        <td style="text-align: center;">{ch_pratica_mod}</td>
                        <td style="text-align: center;">{ch_es_mod if ch_es_mod > 0 else '-'}</td>
                        <td style="text-align: center;">{ch_total_mod}</td>
                    </tr>
                </tbody>
            </table>
        </div>
        """

    html_completo = f"""<!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <title>Matriz Curricular - {nome_curso}</title>
        <style>
            @page {{
                size: A4;
                margin: 15mm;
                @bottom-right {{
                    content: "Página " counter(page) " de " counter(pages);
                    font-size: 8.5pt;
                    color: #64748b;
                    font-family: 'Helvetica', sans-serif;
                }}
                @bottom-left {{
                    content: "UNIVEAS — Sistema Integrado de Gestão Acadêmica";
                    font-size: 8.5pt;
                    color: #64748b;
                    font-family: 'Helvetica', sans-serif;
                }}
            }}
            *, *::before, *::after {{ box-sizing: border-box; }}
            body {{
                font-family: 'Helvetica', 'Arial', sans-serif;
                color: #1e293b;
                line-height: 1.4;
                margin: 0;
                padding: 0;
                background-color: #ffffff;
                font-size: 10pt;
            }}
            .header-card {{
                background: linear-gradient(135deg, #0f766e 0%, #14b8a6 100%);
                color: white;
                padding: 20px;
                border-radius: 8px;
                margin-bottom: 20px;
                text-align: center;
            }}
            .institution-name {{
                font-size: 18pt;
                font-weight: 900;
                letter-spacing: 2px;
                margin: 0 0 4px 0;
                text-transform: uppercase;
            }}
            .institution-subtitle {{
                font-size: 10.5pt;
                font-weight: 600;
                color: #ccfbf1;
                margin: 0 0 8px 0;
                text-transform: uppercase;
            }}
            .institution-info {{
                font-size: 8.5pt;
                color: #f1f5f9;
                margin: 0;
            }}
            .doc-title-box {{
                background: #ffffff;
                border: 1px solid #cbd5e1;
                border-left: 5px solid #0f766e;
                padding: 10px 15px;
                border-radius: 6px;
                margin-bottom: 15px;
                display: flex;
                justify-content: space-between;
                align-items: center;
            }}
            .doc-title {{
                font-size: 11pt;
                font-weight: bold;
                color: #0f172a;
                margin: 0;
                text-transform: uppercase;
            }}
            .doc-meta {{
                font-size: 9pt;
                font-weight: bold;
                color: #0f766e;
                background: #f0fdf4;
                padding: 4px 8px;
                border-radius: 4px;
                border: 1px solid #bbf7d0;
            }}
            .module-wrapper {{
                margin-bottom: 15px;
                page-break-inside: avoid;
                background: white;
                border-radius: 6px;
                border: 1px solid #cbd5e1;
                overflow: hidden;
            }}
            .module-heading {{
                font-size: 9.5pt;
                font-weight: bold;
                color: #0f172a;
                background-color: #f1f5f9;
                border-bottom: 1px solid #cbd5e1;
                padding: 6px 10px;
                text-transform: uppercase;
            }}
            .cert-heading {{
                font-size: 8.5pt;
                font-weight: bold;
                color: #1e293b;
                background-color: #f8fafc;
                border-bottom: 1px solid #e2e8f0;
                padding: 5px 10px;
                text-transform: uppercase;
            }}
            table {{
                width: 100%;
                border-collapse: collapse;
                margin: 0;
                font-size: 9pt;
            }}
            th, td {{
                border: 1px solid #cbd5e1;
                padding: 5px 8px;
                vertical-align: middle;
            }}
            th {{
                background-color: #f8fafc;
                color: #334155;
                font-weight: bold;
                text-align: center;
                text-transform: uppercase;
                font-size: 8pt;
            }}
            .col-disciplina {{ text-align: left; width: 60%; color: #0f172a; }}
            .col-ch {{ text-align: center; width: 10%; }}
            .total-row td {{ font-weight: bold; background-color: #f8fafc; color: #0f766e; }}
            .signature-section {{
                margin-top: 35px;
                page-break-inside: avoid;
            }}
            .signature-grid {{
                width: 100%;
                border-collapse: collapse;
            }}
            .signature-grid td {{
                border: none;
                text-align: center;
                padding-top: 30px;
                width: 50%;
            }}
            .signature-line {{
                width: 75%;
                margin: 0 auto 5px auto;
                border-top: 1.5px solid #475569;
            }}
            .signature-text {{
                font-size: 8.5pt;
                color: #334155;
                font-weight: bold;
            }}
        </style>
    </head>
    <body>

        <div class="header-card">
            <h1 class="institution-name">UNIVEAS</h1>
            <div class="institution-subtitle">União Vigiense de Ensino e Assistência à Saúde</div>
            <p class="institution-info">
                CNPJ: 53.199.321/0001-23 &nbsp;|&nbsp; Tv. Josino Cardoso, nº 126 – Centro, Vigia/PA
            </p>
        </div>

        <div class="doc-title-box">
            <div class="doc-title">Matriz Curricular do Curso {nome_curso}</div>
            <div class="doc-meta">MÓDULO-AULA: 45 min</div>
        </div>

        {modulos_html}

        <div class="signature-section">
            <table class="signature-grid">
                <tr>
                    <td>
                        <div class="signature-line"></div>
                        <div class="signature-text">Coordenação Pedagógica</div>
                    </td>
                    <td>
                        <div class="signature-line"></div>
                        <div class="signature-text">Direção Geral</div>
                    </td>
                </tr>
            </table>
        </div>

    </body>
    </html>
    """

    # Compila o HTML em um PDF real em bytes usando WeasyPrint
    pdf_bytes = HTML(string=html_content).write_pdf()

    # Retorna o arquivo binário PDF que o seu frontend já sabe capturar e baixar
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=Matriz_Curricular_{curso_id}.pdf"}
    )





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

import os
import json
import uuid
from datetime import datetime
from fastapi.middleware.cors import CORSMiddleware
import firebase_admin
from fastapi import FastAPI, Form, HTTPException, File, UploadFile, Response
from firebase_admin import credentials, firestore, storage
import traceback
import io
from fastapi import Response
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.platypus import Spacer, Paragraph, Image
import locale
import urllib.request
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
    alunos = [{"id": doc.id, **doc.to_dict()} for doc in docs]
    return alunos


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


@app.put("/api/v1/alunos/{aluno_id}")
async def alterar_aluno(aluno_id: str, nome: str = Form(None), status: str = Form(None)):
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
    """Lista todos os cursos com tratamento total contra erros de banco ou formato"""
    try:
        checar_db()
        docs = db.collection("cursos").stream()
        cursos = []
        for doc in docs:
            d = doc.to_dict() or {}
            d["id"] = doc.id
            cursos.append(d)
        return cursos
    except Exception as e:
        print(f"--- ERRO AO LISTAR CURSOS: {e} ---")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Erro interno ao buscar cursos: {str(e)}")


@app.get("/api/v1/cursos/{curso_id}")
async def obter_curso(curso_id: str):
    checar_db()
    doc = db.collection("cursos").document(curso_id).get()

    if not doc.exists:
        raise HTTPException(status_code=404, detail="Curso não encontrado.")

    return {"id": doc.id, **doc.to_dict()}


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
# 4.1 ROTA CIRÚRGICA DE PDF (IMPRESSÃO DA MATRIZ)
# ==========================================
@app.get("/api/v1/cursos/{curso_id}/pdf")
async def gerar_pdf_curso(curso_id: str):
    try:
        checar_db()
        doc_ref = db.collection("cursos").document(curso_id).get()
        if not doc_ref.exists:
            raise HTTPException(status_code=404, detail="Curso não encontrado no banco.")

        curso = doc_ref.to_dict() or {}
        nome_curso = str(curso.get('nome_curso') or 'CURSO')
        grade = curso.get('grade_curricular', [])
        if not isinstance(grade, list):
            grade = []

        buffer = io.BytesIO()
        pdf = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=40, leftMargin=40,
            topMargin=40, bottomMargin=40
        )

        elements = []
        styles = getSampleStyleSheet()

        title_style = ParagraphStyle(
            'HeaderTitle', parent=styles['Normal'],
            fontName='Helvetica-Bold', fontSize=14,
            textColor=colors.HexColor('#0f766e'), alignment=1, spaceAfter=4
        )

        subtitle_style = ParagraphStyle(
            'HeaderSubtitle', parent=styles['Normal'],
            fontName='Helvetica-Bold', fontSize=8.5,
            textColor=colors.HexColor('#334155'), alignment=1, spaceAfter=15
        )

        module_style = ParagraphStyle(
            'ModuleTitle', parent=styles['Normal'],
            fontName='Helvetica-Bold', fontSize=10,
            textColor=colors.HexColor('#0f172a'), spaceBefore=10, spaceAfter=5
        )

        elements.append(Paragraph("UNIVEAS", title_style))
        elements.append(Paragraph(
            "UNIÃO VIGIENSE DE ENSINO E ASSISTÊNCIA À SAÚDE<br/>CNPJ: 53.199.321/0001-23 | Tv. Josino Cardoso, nº 126 – Centro, Vigia/PA",
            subtitle_style))
        elements.append(Paragraph(f"<b>MATRIZ CURRICULAR DO CURSO: {nome_curso}</b>",
                                  ParagraphStyle('DocTitle', parent=styles['Normal'], fontName='Helvetica-Bold',
                                                 fontSize=11, textColor=colors.HexColor('#0f172a'), alignment=1,
                                                 spaceAfter=15)))

        if not grade:
            elements.append(
                Paragraph("<i>Nenhum módulo cadastrado na grade curricular deste curso.</i>", styles['Normal']))

        for i, m in enumerate(grade):
            if not isinstance(m, dict):
                continue
            mod_nome = str(m.get('nome') or f'Módulo {i + 1}')
            elements.append(Paragraph(f"MÓDULO {i + 1}: {mod_nome.upper()}", module_style))

            table_data = [['DISCIPLINAS', 'TEORIA', 'PRÁTICA', 'ES', 'TOTAL']]

            disciplinas = m.get('disciplinas', [])
            if not isinstance(disciplinas, list):
                disciplinas = []

            t_mod, p_mod, es_mod, tot_mod = 0, 0, 0, 0

            if disciplinas:
                for disc in disciplinas:
                    if not isinstance(disc, dict):
                        continue
                    t = int(disc.get('ch_teoria', 0) or 0)
                    p = int(disc.get('ch_pratica', 0) or 0)
                    es = int(disc.get('ch_es', 0) or 0)
                    tot = t + p + es

                    t_mod += t
                    p_mod += p
                    es_mod += es
                    tot_mod += tot

                    table_data.append([
                        str(disc.get('nome', 'Disciplina')),
                        str(t) if t > 0 else '-',
                        str(p) if p > 0 else '-',
                        str(es) if es > 0 else '-',
                        str(tot)
                    ])
            else:
                t = int(m.get('ch_teoria', 0) or m.get('ch_total', 0) or 0)
                t_mod += t
                tot_mod += t
                table_data.append([
                    mod_nome,
                    str(t), '-', '-', str(t)
                ])

            table_data.append([
                'CH DO MÓDULO',
                str(t_mod),
                str(p_mod),
                str(es_mod) if es_mod > 0 else '-',
                str(tot_mod)
            ])

            t_obj = Table(table_data, colWidths=[240, 65, 65, 50, 63])
            t_obj.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e2e8f0')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#0f172a')),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 8.5),
                ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#94a3b8')),
                ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#f1f5f9')),
                ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ]))

            elements.append(t_obj)
            elements.append(Spacer(1, 10))

        elements.append(Spacer(1, 20))
        sig_data = [
            ['________________________________________', '________________________________________'],
            ['Coordenação Pedagógica', 'Direção Geral']
        ]
        sig_table = Table(sig_data, colWidths=[241, 241])
        sig_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8.5),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#334155')),
            ('TOPPADDING', (0, 1), (-1, 1), 4),
        ]))
        elements.append(sig_table)

        pdf.build(elements)
        buffer.seek(0)

        return Response(
            content=buffer.getvalue(),
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=Matriz_Curricular_{curso_id}.pdf"}
        )

    except Exception as e:
        print("--- ERRO CRITICO NA GERACAO DO PDF ---")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Erro interno ao gerar PDF: {str(e)}")

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
# 6. MÓDULO DO DOCENTE (PORTAL DO PROFESSOR)
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


# ==========================================
# 7. MÓDULO DASHBOARD & ESTATÍSTICAS
# ==========================================
@app.get("/api/v1/dashboard/indicadores")
async def obter_indicadores_dashboard():
    checar_db()

    # Contagens diretas do banco (Usando list() por segurança na iteração simples do Firestore)
    alunos_docs = list(db.collection("alunos").stream())
    docentes_docs = list(db.collection("docentes").stream())
    cursos_docs = list(db.collection("cursos").stream())
    mensalidades_docs = list(db.collection("mensalidades").stream())

    # Cálculos específicos
    total_alunos = len(alunos_docs)
    total_docentes = len(docentes_docs)
    total_cursos = len(cursos_docs)

    # Exemplo: Filtrar alunos pendentes para o card de "Novas Matrículas/Pendentes"
    alunos_pendentes = len([a for a in alunos_docs if a.to_dict().get("status") == "Pendente"])

    # Cálculo rápido de inadimplência (Exemplo: Mensalidades Atrasadas)
    mensalidades_atrasadas = len([m for m in mensalidades_docs if m.to_dict().get("status") == "Atrasado"])
    total_mensalidades = len(mensalidades_docs) if mensalidades_docs else 1  # evita divisão por zero
    inadimplencia = round((mensalidades_atrasadas / total_mensalidades) * 100, 1) if mensalidades_docs else 0

    return {
        "total_alunos": total_alunos,
        "total_docentes": total_docentes,
        "total_cursos": total_cursos,
        "alunos_pendentes": alunos_pendentes,
        "inadimplencia_percent": f"{inadimplencia}%"
    }


# ==========================================
# 8. MÓDULO CONFIGURAÇÕES DO SISTEMA
# ==========================================
@app.get("/api/v1/configuracoes")
async def obter_configuracoes():
    checar_db()
    doc = db.collection("sistema").document("configuracoes").get()

    if doc.exists:
        return doc.to_dict()

    # Retorna o padrão (Fallback) caso ainda não tenha sido configurado
    return {
        "nome_instituicao": "UNIVEAS",
        "cnpj": "53.199.321/0001-23",
        "email": "contato@univeas.com.br",
        "telefone": "(91) 90000-0000",
        "endereco": "Tv. Josino Cardoso, nº 126 – Centro, Vigia/PA",
        "cor_tema": "#0f766e"
    }


@app.put("/api/v1/configuracoes")
async def atualizar_configuracoes(
        nome_instituicao: str = Form(None),
        cnpj: str = Form(None),
        telefone: str = Form(None),
        email: str = Form(None),
        endereco: str = Form(None),
        cor_tema: str = Form(None)
):
    checar_db()

    # Prepara apenas os dados que vieram preenchidos
    dados_atualizados = {
        "nome_instituicao": nome_instituicao,
        "cnpj": cnpj,
        "telefone": telefone,
        "email": email,
        "endereco": endereco,
        "cor_tema": cor_tema,
        "data_atualizacao": datetime.now().isoformat()
    }

    # Remove valores Nulos para não sobrescrever com vazio
    dados_limpos = {k: v for k, v in dados_atualizados.items() if v is not None}

    # O merge=True garante que só atualiza os campos enviados, preservando o resto
    db.collection("sistema").document("configuracoes").set(dados_limpos, merge=True)

    return {"sucesso": True, "mensagem": "Configurações institucionais atualizadas com sucesso."}


# ==========================================
# 9. MÓDULO DE DOCUMENTOS ACADÊMICOS
# ==========================================
@app.get("/api/v1/documentos")
async def listar_documentos():
    checar_db()
    docs = db.collection("documentos").stream()
    return [{"id": doc.id, **doc.to_dict()} for doc in docs]


@app.post("/api/v1/documentos/emitir")
async def registrar_emissao_documento(
        aluno_id: str = Form(...),
        tipo_documento: str = Form(...),  # ex: "Declaracao de Matricula", "Historico"
        observacao: str = Form("")
):
    checar_db()

    # Busca os dados do aluno para o registro
    aluno_ref = db.collection("alunos").document(aluno_id).get()
    if not aluno_ref.exists:
        raise HTTPException(status_code=404, detail="Aluno não encontrado")

    aluno_dados = aluno_ref.to_dict()
    codigo_validacao = f"DOC-{str(uuid.uuid4()).split('-')[0].upper()}"

    novo_doc = {
        "aluno_id": aluno_id,
        "nome_aluno": aluno_dados.get("nome"),
        "matricula": aluno_dados.get("matricula"),
        "tipo_documento": tipo_documento,
        "codigo_validacao": codigo_validacao,
        "observacao": observacao,
        "data_emissao": datetime.now().isoformat(),
        "emitido_por": "Administrador"
    }

    _, doc_ref = db.collection("documentos").add(novo_doc)
    return {
        "sucesso": True,
        "mensagem": f"{tipo_documento} registrado com sucesso.",
        "id_documento": doc_ref.id,
        "codigo_validacao": codigo_validacao
    }

# ==========================================
# 9.1 GERAÇÃO DE PDF DE DOCUMENTOS ACADÊMICOS
# ==========================================
@app.get("/api/v1/documentos/{documento_id}/pdf")
async def gerar_pdf_documento(documento_id: str):
    try:
        checar_db()

        # 1. Busca o registro da emissão
        doc_ref = db.collection("documentos").document(documento_id).get()
        if not doc_ref.exists:
            raise HTTPException(status_code=404, detail="Registro de documento não encontrado.")

        dados_emissao = doc_ref.to_dict()
        aluno_id = dados_emissao.get("aluno_id")
        tipo_doc = str(dados_emissao.get("tipo_documento", "DOCUMENTO ACADÊMICO")).upper()

        # 2. Busca os dados completos do aluno
        aluno_ref = db.collection("alunos").document(aluno_id).get()
        aluno = aluno_ref.to_dict() if aluno_ref.exists else {}

        # 3. Busca configurações da instituição
        sys_ref = db.collection("sistema").document("configuracoes").get()
        sys_dados = sys_ref.to_dict() if sys_ref.exists else {
            "nome_instituicao": "UNIVEAS",
            "cnpj": "53.199.321/0001-23",
            "endereco": "Tv. Josino Cardoso, nº 126 – Centro, Vigia/PA"
        }

        # 4. Configuração do ReportLab
        buffer = io.BytesIO()
        pdf = SimpleDocTemplate(
            buffer, pagesize=A4, rightMargin=50, leftMargin=50, topMargin=50, bottomMargin=50
        )

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'TitleStyle', parent=styles['Normal'], fontName='Helvetica-Bold',
            fontSize=16, alignment=TA_CENTER, spaceAfter=20, textColor=colors.HexColor('#0f766e')
        )
        subtitle_style = ParagraphStyle(
            'SubtitleStyle', parent=styles['Normal'], fontName='Helvetica',
            fontSize=10, alignment=TA_CENTER, spaceAfter=30, textColor=colors.HexColor('#334155')
        )
        body_style = ParagraphStyle(
            'BodyStyle', parent=styles['Normal'], fontName='Helvetica',
            fontSize=12, alignment=TA_JUSTIFY, leading=18, spaceAfter=20
        )
        footer_style = ParagraphStyle(
            'FooterStyle', parent=styles['Normal'], fontName='Helvetica-Oblique',
            fontSize=9, alignment=TA_CENTER, textColor=colors.gray
        )

        elements = []

        # Cabeçalho
        logo_url = "https://i.imgur.com/ki7mdS2.png"

        if logo_url:
            try:
                # Disfarça a requisição do Python como se fosse um navegador para burlar o bloqueio do Imgur
                req = urllib.request.Request(logo_url,
                                             headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
                with urllib.request.urlopen(req) as response:
                    img_data = io.BytesIO(response.read())

                    img = Image(img_data, width=80, height=80)
                    img.hAlign = 'CENTER'
                    elements.append(img)
                    elements.append(Spacer(1, 10))
            except Exception as e:
                print(f"Aviso: Não foi possível carregar o logo no PDF - {e}")

        # Título da Instituição (Apenas uma vez)
        elements.append(Paragraph(f"<b>{sys_dados.get('nome_instituicao')}</b>", title_style))
        elements.append(Paragraph(f"CNPJ: {sys_dados.get('cnpj')} | {sys_dados.get('endereco')}", subtitle_style))


        elements.append(Paragraph(f"<b>{sys_dados.get('nome_instituicao')}</b>", title_style))
        elements.append(Paragraph(f"CNPJ: {sys_dados.get('cnpj')} | {sys_dados.get('endereco')}", subtitle_style))

        # Título do Documento
        elements.append(Spacer(1, 20))
        elements.append(Paragraph(f"<b>{tipo_doc}</b>", ParagraphStyle(
            'DocType', parent=title_style, fontSize=14, textColor=colors.black, spaceAfter=40
        )))

        # Corpo do Texto Dinâmico
        nome = aluno.get('nome', 'NOME NÃO INFORMADO').upper()
        cpf = aluno.get('cpf', '000.000.000-00')
        matricula = aluno.get('matricula', 'S/N')
        curso_id = aluno.get('curso', '')

        # Nome do curso requer uma busca extra, mas usaremos um placeholder seguro se não encontrar
        nome_curso = "Curso Técnico/Profissionalizante"
        if curso_id:
            c_ref = db.collection("cursos").document(curso_id).get()
            if c_ref.exists:
                nome_curso = c_ref.to_dict().get("nome_curso", nome_curso).upper()

        if "DECLARAÇÃO" in tipo_doc:
            texto = f"""Declaramos para os devidos fins de comprovação que o(a) aluno(a) 
            <b>{nome}</b>, portador(a) do CPF <b>{cpf}</b>, está regularmente 
            matriculado(a) na instituição de ensino {sys_dados.get('nome_instituicao')}, 
            sob a matrícula <b>{matricula}</b>, no curso de <b>{nome_curso}</b>."""
            elements.append(Paragraph(texto, body_style))
        else:
            # Texto genérico para Históricos e Certificados
            texto = f"""Certificamos que o registro acadêmico referente ao(à) aluno(a) 
            <b>{nome}</b>, matrícula <b>{matricula}</b> (CPF: {cpf}), vinculado(a) ao 
            curso de <b>{nome_curso}</b>, encontra-se documentado nos arquivos desta instituição."""
            elements.append(Paragraph(texto, body_style))

        # Data atual (Formatada)
        data_atual = datetime.now().strftime("%d/%m/%Y")
        elements.append(Spacer(1, 40))
        elements.append(
            Paragraph(f"Vigia/PA, {data_atual}.", ParagraphStyle('DateStyle', parent=body_style, alignment=TA_CENTER)))

        # Assinaturas
        elements.append(Spacer(1, 60))
        sig_data = [
            ['________________________________________', '________________________________________'],
            ['Secretaria Acadêmica', 'Direção Geral']
        ]
        sig_table = Table(sig_data, colWidths=[200, 200])
        sig_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
        ]))
        elements.append(sig_table)

        # Rodapé com código de validação
        elements.append(Spacer(1, 50))
        cod_val = dados_emissao.get('codigo_validacao', 'N/A')
        elements.append(
            Paragraph(f"Documento emitido digitalmente via SIGA UNIVEAS.<br/>Código de Autenticidade: <b>{cod_val}</b>",
                      footer_style))

        pdf.build(elements)
        buffer.seek(0)

        nome_arquivo = tipo_doc.replace(" ", "_").replace("/", "-")
        return Response(
            content=buffer.getvalue(),
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={nome_arquivo}_{matricula}.pdf"}
        )

    except Exception as e:
        print("--- ERRO CRITICO NA GERACAO DO PDF DO DOCUMENTO ---")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")

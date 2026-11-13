import os
import json
import uuid
from datetime import datetime
from fastapi.middleware.cors import CORSMiddleware
import firebase_admin
from fastapi import FastAPI, Form, HTTPException, File, UploadFile, Response, Header
from firebase_admin import credentials, firestore, storage
import traceback
import io
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
import urllib.request
from typing import List, Optional
from pydantic import BaseModel


# ==========================================
# SCHEMAS PYDANTIC (Validação de JSON)
# ==========================================
class LancamentoAluno(BaseModel):
    aluno_id: str
    faltas: int
    notas: dict = {}
    nota_1: Optional[float] = None
    nota_2: Optional[float] = None


class DiarioPayload(BaseModel):
    turma_id: str
    data_aula: str
    conteudo_ministrado: str
    lancamentos: List[LancamentoAluno]


class MaterialEdicaoPayload(BaseModel):
    titulo: str
    url_arquivo: str


class PerfilDocentePayload(BaseModel):
    email: str
    telefone: str


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
            "nome_professor": docente_encontrado.get("nome", docente_encontrado.get("nome_prestador", "Professor")),
            "registro": docente_encontrado["registro"],
            "email": docente_encontrado.get("email", "Não cadastrado"),
            "telefone": docente_encontrado.get("telefone", "Não cadastrado")
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
        nome: str = Form(...),
        cpf: str = Form(...),
        email: str = Form(...),
        telefone: str = Form(...),
        endereco: str = Form(...),
        curso_id: str = Form(None),
        curso: str = Form(None),
        cursos_json: str = Form("[]"),
        data_nascimento: str = Form(None),
        dia_vencimento: str = Form(None),
        forma_pagamento: str = Form(None),
        pcd: str = Form(None),
        aceite_termos: str = Form(None)
):
    checar_db()
    c_id = curso_id or curso
    matricula_gerada = f"#{datetime.now().strftime('%Y%m')}{str(uuid.uuid4().int)[:4]}"

    try:
        lista_cursos = json.loads(cursos_json)
    except Exception:
        lista_cursos = [{"curso_id": c_id}] if c_id else []

    novo_aluno = {
        "matricula": matricula_gerada,
        "cpf": cpf,
        "nome": nome,
        "email": email,
        "telefone": telefone,
        "endereco": endereco,
        "curso": c_id,
        "cursos_json": lista_cursos,
        "data_nascimento": data_nascimento,
        "dia_vencimento": dia_vencimento,
        "forma_pagamento": forma_pagamento,
        "pcd": pcd,
        "aceite_termos": aceite_termos,
        "status": "Ativo",
        "data_cadastro": datetime.now().isoformat()
    }

    _, doc_ref = db.collection("alunos").add(novo_aluno)
    return {"sucesso": True, "id": doc_ref.id, "matricula": matricula_gerada}


@app.put("/api/v1/alunos/{aluno_id}")
async def alterar_aluno(
        aluno_id: str,
        nome: str = Form(None),
        cpf: str = Form(None),
        email: str = Form(None),
        telefone: str = Form(None),
        endereco: str = Form(None),
        curso_id: str = Form(None),
        curso: str = Form(None),
        cursos_json: str = Form(None),
        data_nascimento: str = Form(None),
        dia_vencimento: str = Form(None),
        forma_pagamento: str = Form(None),
        pcd: str = Form(None),
        status: str = Form(None),
        possui_pendencia_financeira: str = Form(None),
        detalhes_pendencia_financeira: str = Form(None),
        numero_nf: str = Form(None)
):
    checar_db()
    ref = db.collection("alunos").document(aluno_id)
    doc_atual = ref.get()

    if not doc_atual.exists:
        raise HTTPException(status_code=404, detail="Aluno não encontrado.")

    c_id = curso_id or curso
    lista_cursos = None
    if cursos_json is not None:
        try:
            lista_cursos = json.loads(cursos_json)
        except Exception:
            lista_cursos = []

    dados_atualizados = {
        "nome": nome,
        "cpf": cpf,
        "email": email,
        "telefone": telefone,
        "endereco": endereco,
        "curso": c_id,
        "cursos_json": lista_cursos,
        "data_nascimento": data_nascimento,
        "dia_vencimento": dia_vencimento,
        "forma_pagamento": forma_pagamento,
        "pcd": pcd,
        "status": status,
        "possui_pendencia_financeira": possui_pendencia_financeira,
        "detalhes_pendencia_financeira": detalhes_pendencia_financeira,
        "numero_nf": numero_nf,
        "data_atualizacao": datetime.now().isoformat()
    }

    dados_limpos = {k: v for k, v in dados_atualizados.items() if v is not None}
    if dados_limpos:
        ref.update(dados_limpos)

    return {"sucesso": True, "mensagem": "Aluno atualizado com sucesso"}


@app.post("/api/v1/alunos/{aluno_id}/pendencia")
async def atualizar_pendencia_aluno(
        aluno_id: str,
        possui_pendencia: str = Form(None),
        possui_pendencia_financeira: str = Form(None),
        detalhes_pendencia: str = Form(None),
        detalhes_pendencia_financeira: str = Form(None),
        numero_nf: str = Form(None)
):
    checar_db()
    ref = db.collection("alunos").document(aluno_id)
    if not ref.get().exists:
        raise HTTPException(status_code=404, detail="Aluno não encontrado.")

    pend = possui_pendencia_financeira or possui_pendencia or "Não"
    det = detalhes_pendencia_financeira or detalhes_pendencia or ""

    dados = {
        "possui_pendencia_financeira": pend,
        "detalhes_pendencia_financeira": det,
        "status": "Pendente" if pend == "Sim" else "Ativo"
    }
    if numero_nf is not None:
        dados["numero_nf"] = numero_nf

    ref.update(dados)
    return {"sucesso": True, "mensagem": "Situação financeira atualizada com sucesso!"}


@app.post("/api/v1/alunos/{aluno_id}/nf")
async def atualizar_nf_aluno(aluno_id: str, numero_nf: str = Form(...)):
    checar_db()
    ref = db.collection("alunos").document(aluno_id)
    if not ref.get().exists:
        raise HTTPException(status_code=404, detail="Aluno não encontrado.")
    ref.update({"numero_nf": numero_nf})
    return {"sucesso": True, "mensagem": "Nota Fiscal salva com sucesso!"}


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
        data_nascimento_prestador: str = Form(None),
        telefone_prestador: str = Form(...),
        email_prestador: str = Form(None),
        tipo_profissional: str = Form(...),
        turno_atuacao: str = Form(None),
        especialidade: str = Form(None),
        vinculos_json: str = Form("[]"),
        banco: str = Form(None),
        agencia: str = Form(None),
        conta: str = Form(None),
        chave_pix: str = Form(None)
):
    checar_db()
    registro_gerado = f"#PR{str(uuid.uuid4().int)[:4]}"

    novo_docente = {
        "registro": registro_gerado,
        "nome": nome_prestador,
        "cpf": cpf_prestador,
        "data_nascimento": data_nascimento_prestador,
        "telefone": telefone_prestador,
        "email": email_prestador,
        "tipo_profissional": tipo_profissional,
        "turno_atuacao": turno_atuacao,
        "especialidade": especialidade,
        "vinculos_json": vinculos_json,
        "banco": banco,
        "agencia": agencia,
        "conta": conta,
        "chave_pix": chave_pix,
        "status": "Ativo",
        "data_cadastro": datetime.now().isoformat()
    }

    db.collection("docentes").add(novo_docente)
    return {"sucesso": True, "mensagem": "Prestador salvo com sucesso."}


@app.put("/api/v1/docentes/{docente_id}")
async def atualizar_docente(
        docente_id: str,
        nome_prestador: str = Form(None),
        cpf_prestador: str = Form(None),
        data_nascimento_prestador: str = Form(None),
        telefone_prestador: str = Form(None),
        email_prestador: str = Form(None),
        tipo_profissional: str = Form(None),
        turno_atuacao: str = Form(None),
        especialidade: str = Form(None),
        vinculos_json: str = Form(None),
        banco: str = Form(None),
        agencia: str = Form(None),
        conta: str = Form(None),
        chave_pix: str = Form(None)
):
    checar_db()
    ref = db.collection("docentes").document(docente_id)

    if not ref.get().exists:
        raise HTTPException(status_code=404, detail="Prestador não encontrado.")

    dados_atualizados = {
        "nome": nome_prestador,
        "cpf": cpf_prestador,
        "data_nascimento": data_nascimento_prestador,
        "telefone": telefone_prestador,
        "email": email_prestador,
        "tipo_profissional": tipo_profissional,
        "turno_atuacao": turno_atuacao,
        "especialidade": especialidade,
        "vinculos_json": vinculos_json,
        "banco": banco,
        "agencia": agencia,
        "conta": conta,
        "chave_pix": chave_pix,
        "data_atualizacao": datetime.now().isoformat()
    }

    dados_limpos = {k: v for k, v in dados_atualizados.items() if v is not None}
    ref.update(dados_limpos)
    return {"sucesso": True, "mensagem": "Prestador atualizado com sucesso"}


@app.delete("/api/v1/docentes/{docente_id}")
async def excluir_docente(docente_id: str):
    checar_db()
    db.collection("docentes").document(docente_id).delete()
    return {"sucesso": True}


@app.get("/api/v1/cursos")
async def listar_cursos():
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
        disciplinas_json: str = Form("[]"),
        duracao: str = Form(None),
        promocao_ativa: str = Form(None),
        valor_promocional: str = Form(None)
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
        "duracao": duracao,
        "valor_matricula": valor_matricula,
        "valor_mensalidade": valor_mensalidade,
        "descricao": descricao,
        "foto_capa": foto_capa,
        "grade_curricular": grade,
        "promocao_ativa": promocao_ativa,
        "valor_promocional": valor_promocional,
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
                table_data.append([mod_nome, str(t), '-', '-', str(t)])

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
@app.get("/api/v1/financeiro/indicadores")
async def obter_indicadores_financeiros():
    checar_db()
    alunos_docs = list(db.collection("alunos").stream())
    cursos_docs = {doc.id: doc.to_dict() for doc in db.collection("cursos").stream()}

    total_recebido = 0
    total_receber = 0
    inadimplencia = 0
    pagamentos_mes = 0

    for doc_aluno in alunos_docs:
        dados = doc_aluno.to_dict()
        c_id = dados.get("curso")
        curso_info = cursos_docs.get(c_id, {})

        valor = 0
        if curso_info:
            if curso_info.get("promocao_ativa") == "Sim" and curso_info.get("valor_promocional"):
                try:
                    valor = float(curso_info.get("valor_promocional"))
                except:
                    valor = float(curso_info.get("valor_mensalidade", 0))
            else:
                try:
                    valor = float(curso_info.get("valor_mensalidade", 0))
                except:
                    valor = 0

        if dados.get("possui_pendencia_financeira") == "Sim" or dados.get("status") == "Pendente":
            inadimplencia += 1
            total_receber += valor
        else:
            total_recebido += valor
            pagamentos_mes += 1

    return {
        "total_recebido": total_recebido,
        "total_receber": total_receber,
        "inadimplencia": inadimplencia,
        "pagamentos_mes": pagamentos_mes
    }


# ==========================================
# 6. MÓDULO DO DOCENTE (PORTAL DO PROFESSOR)
# ==========================================
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
    vinculos_str = dados_prof.get("vinculos_json", "[]")

    try:
        vinculos = json.loads(vinculos_str)
    except:
        vinculos = []

    return {
        "turmas_ativas": len(vinculos),
        "diarios_pendentes": 0,
        "aulas_semana": len(vinculos),
        "curso_vinculado": vinculos[0].get("curso_id") if vinculos else None
    }


class TurmaConfigPayload(BaseModel):
    turma_id: str
    data_inicio: str = None
    data_fim: str = None
    ementa: str = None
    ch_teoria: int = 0
    ch_pratica: int = 0
    ch_estagio: int = 0
    ch_total: int = 0
    dias_aula: List[str] = []
    hora_inicio: str = None
    hora_fim: str = None
    avaliacoes: List[dict] = []
    justificativa: str = None


@app.get("/api/v1/docente/turmas")
async def listar_turmas_docente(authorization: str = Header(None)):
    checar_db()
    docente_id = validar_token_docente(authorization)
    doc_prof = db.collection("docentes").document(docente_id).get()

    if not doc_prof.exists:
        return []

    dados_prof = doc_prof.to_dict()
    vinculos_str = dados_prof.get("vinculos_json", "[]")

    try:
        vinculos = json.loads(vinculos_str)
    except:
        vinculos = []

    turmas_formatadas = []
    for vinc in vinculos:
        if not isinstance(vinc, dict):
            continue

        c_id = vinc.get("curso_id") or vinc.get("curso")
        mod_nome = vinc.get("modulo") or vinc.get("disciplina") or "Módulo/Disciplina"
        nome_curso = "Curso Vinculado"
        ch_total = 40
        detalhes_modulo = {}

        if c_id:
            c_ref = db.collection("cursos").document(c_id).get()
            if c_ref.exists:
                c_dados = c_ref.to_dict()
                nome_curso = c_dados.get("nome_curso", "CURSO DESCONHECIDO")
                nome_alvo = str(mod_nome).strip().upper()

                for m in c_dados.get("grade_curricular", []):
                    if not isinstance(m, dict): continue
                    m_nome = str(m.get("nome") or m.get("disciplina") or "").strip().upper()
                    if m_nome == nome_alvo:
                        detalhes_modulo = m
                        ch_total = int(m.get("ch_total", 40))
                        break

                    sub_disciplinas = m.get("disciplinas", [])
                    if isinstance(sub_disciplinas, list):
                        encontrou = False
                        for disc in sub_disciplinas:
                            if not isinstance(disc, dict): continue
                            d_nome = str(disc.get("nome") or disc.get("disciplina") or "").strip().upper()
                            if d_nome == nome_alvo:
                                detalhes_modulo = disc
                                ch_total = int(disc.get("ch_total", 40))
                                encontrou = True
                                break
                        if encontrou: break

        turmas_formatadas.append({
            "id": f"{c_id}_{mod_nome}",
            "nome_disciplina": mod_nome,
            "curso_pai": nome_curso,
            "carga_horaria": ch_total,
            "detalhes": detalhes_modulo
        })

    return turmas_formatadas


@app.post("/api/v1/docente/turmas/configurar")
async def configurar_disciplina(payload: TurmaConfigPayload, authorization: str = Header(None)):
    checar_db()
    validar_token_docente(authorization)

    try:
        curso_id, nome_alvo = payload.turma_id.split("_", 1)
        nome_alvo = nome_alvo.strip().upper()
    except:
        raise HTTPException(status_code=400, detail="ID da turma inválido")

    curso_ref = db.collection("cursos").document(curso_id)
    curso_doc = curso_ref.get()

    if not curso_doc.exists:
        raise HTTPException(status_code=404, detail="Curso não encontrado")

    curso_dados = curso_doc.to_dict()
    grade = curso_dados.get("grade_curricular", [])
    modulo_atualizado = False

    def atualizar_obj(obj):
        obj["data_inicio"] = payload.data_inicio
        obj["data_fim"] = payload.data_fim
        obj["descricao"] = payload.ementa
        obj["ementa"] = payload.ementa
        obj["ch_teoria"] = payload.ch_teoria
        obj["ch_pratica"] = payload.ch_pratica
        obj["ch_estagio"] = payload.ch_estagio
        obj["ch_total"] = payload.ch_total
        obj["dias_aula"] = payload.dias_aula
        obj['hora_aula_inicio'] = payload.hora_inicio
        obj['hora_aula_fim'] = payload.hora_fim
        obj["avaliacoes"] = [av for av in payload.avaliacoes]

    for m in grade:
        if not isinstance(m, dict): continue
        if str(m.get("nome") or m.get("disciplina") or "").strip().upper() == nome_alvo:
            atualizar_obj(m)
            modulo_atualizado = True
            break

        sub_disciplinas = m.get("disciplinas", [])
        if isinstance(sub_disciplinas, list):
            for disc in sub_disciplinas:
                if not isinstance(disc, dict): continue
                if str(disc.get("nome") or disc.get("disciplina") or "").strip().upper() == nome_alvo:
                    atualizar_obj(disc)
                    modulo_atualizado = True
                    break
        if modulo_atualizado: break

    if not modulo_atualizado:
        raise HTTPException(status_code=404, detail="Disciplina não encontrada na matriz do curso.")

    curso_ref.update({"grade_curricular": grade})
    return {"sucesso": True, "mensagem": "Configurações sincronizadas com sucesso!"}


@app.post("/api/v1/docente/diario/salvar")
async def salvar_diario_eletronico(payload: DiarioPayload, authorization: str = Header(None)):
    checar_db()
    docente_id = validar_token_docente(authorization)
    avaliacoes_dict = [lancamento.model_dump() for lancamento in payload.lancamentos]

    registro_diario = {
        "docente_id": docente_id,
        "turma_id": payload.turma_id,
        "data_aula": payload.data_aula,
        "conteudo_ministrado": payload.conteudo_ministrado,
        "avaliacoes": avaliacoes_dict,
        "data_registro": datetime.now().isoformat()
    }

    db.collection("diarios").add(registro_diario)
    return {"sucesso": True, "mensagem": "Diário registrado com sucesso!"}


class MaterialPayload(BaseModel):
    turma_id: str
    titulo: str
    url_arquivo: str
    data_postagem: Optional[str] = None


@app.post("/api/v1/docente/material/upload")
async def upload_material_didatico(payload: MaterialPayload, authorization: str = Header(None)):
    checar_db()
    docente_id = validar_token_docente(authorization)

    registro_material = {
        "docente_id": docente_id,
        "turma_id": payload.turma_id,
        "titulo": payload.titulo,
        "url_arquivo": payload.url_arquivo,
        "data_postagem": payload.data_postagem or datetime.now().strftime('%d/%m/%Y'),
        "data_envio": datetime.now().isoformat()
    }

    db.collection("materiais_didaticos").add(registro_material)
    return {"sucesso": True, "mensagem": "Link publicado com sucesso!"}


@app.get("/api/v1/docente/materiais")
async def listar_materiais_docente(authorization: str = Header(None)):
    checar_db()
    docente_id = validar_token_docente(authorization)
    docs = db.collection("materiais_didaticos").where("docente_id", "==", docente_id).stream()
    materiais = []

    for doc in docs:
        m = doc.to_dict()
        m["id"] = doc.id
        turma_id = m.get("turma_id", "")
        m["nome_turma"] = turma_id.split("_")[1] if "_" in turma_id else "Turma Vinculada"
        materiais.append(m)

    return materiais


# ==========================================
# 7. MÓDULO DASHBOARD & ESTATÍSTICAS
# ==========================================
@app.get("/api/v1/dashboard/indicadores")
async def obter_indicadores_dashboard():
    checar_db()
    alunos_docs = list(db.collection("alunos").stream())
    docentes_docs = list(db.collection("docentes").stream())
    cursos_docs = list(db.collection("cursos").stream())

    total_alunos = len(alunos_docs)
    total_docentes = len(docentes_docs)
    total_cursos = len(cursos_docs)

    inadimplencia_total = sum(1 for a in alunos_docs if a.to_dict().get("possui_pendencia_financeira") == "Sim")

    return {
        "total_alunos": total_alunos,
        "total_docentes": total_docentes,
        "total_cursos": total_cursos,
        "turmas_ativas": total_cursos,
        "total_inadimplencia": inadimplencia_total,
        "notificacoes": []
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

    return {
        "nome_instituicao": "UNIVEAS",
        "cnpj": "53.199.321/0001-23",
        "email": "contato@univeas.com.br",
        "telefone": "(91) 98325-2639",
        "endereco": "Tv. Josino Cardoso, nº 126 – Centro, Vigia/PA",
        "cor_tema": "#14b8a6"
    }


@app.put("/api/v1/configuracoes")
async def atualizar_configuracoes(
        nome_instituicao: str = Form(None),
        cnpj: str = Form(None),
        telefone_instituicao: str = Form(None),
        email_instituicao: str = Form(None),
        endereco_instituicao: str = Form(None),
        cor_tema: str = Form(None)
):
    checar_db()
    dados_atualizados = {
        "nome_instituicao": nome_instituicao,
        "cnpj": cnpj,
        "telefone": telefone_instituicao,
        "email": email_instituicao,
        "endereco": endereco_instituicao,
        "cor_tema": cor_tema,
        "data_atualizacao": datetime.now().isoformat()
    }
    dados_limpos = {k: v for k, v in dados_atualizados.items() if v is not None}
    db.collection("sistema").document("configuracoes").set(dados_limpos, merge=True)
    return {"sucesso": True, "mensagem": "Configurações atualizadas."}


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
        tipo_documento: str = Form(...),
        observacao: str = Form("")
):
    checar_db()
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
        "mensagem": f"{tipo_documento} registrado.",
        "id_documento": doc_ref.id,
        "codigo_validacao": codigo_validacao
    }


@app.get("/api/v1/documentos/{documento_id}/pdf")
async def gerar_pdf_documento(documento_id: str):
    try:
        checar_db()
        doc_ref = db.collection("documentos").document(documento_id).get()
        if not doc_ref.exists:
            raise HTTPException(status_code=404, detail="Registro não encontrado.")

        dados_emissao = doc_ref.to_dict()
        aluno_id = dados_emissao.get("aluno_id")
        tipo_doc = str(dados_emissao.get("tipo_documento", "DOCUMENTO ACADÊMICO")).upper()
        aluno_ref = db.collection("alunos").document(aluno_id).get()
        aluno = aluno_ref.to_dict() if aluno_ref.exists else {}

        sys_ref = db.collection("sistema").document("configuracoes").get()
        sys_dados = sys_ref.to_dict() if sys_ref.exists else {
            "nome_instituicao": "UNIVEAS",
            "cnpj": "53.199.321/0001-23",
            "endereco": "Tv. Josino Cardoso, nº 126 – Centro, Vigia/PA"
        }

        buffer = io.BytesIO()
        pdf = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=50, leftMargin=50, topMargin=50, bottomMargin=50)

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
        elements.append(Paragraph(f"<b>{sys_dados.get('nome_instituicao')}</b>", title_style))
        elements.append(Paragraph(f"CNPJ: {sys_dados.get('cnpj')} | {sys_dados.get('endereco')}", subtitle_style))
        elements.append(Spacer(1, 10))
        elements.append(Paragraph(f"<b>{tipo_doc}</b>",
                                  ParagraphStyle('DocType', parent=title_style, fontSize=14, textColor=colors.black,
                                                 spaceAfter=30)))

        nome = aluno.get('nome', 'NOME NÃO INFORMADO').upper()
        cpf = aluno.get('cpf', '000.000.000-00')
        matricula = aluno.get('matricula', 'S/N')
        curso_id = aluno.get('curso', '')

        nome_curso = "Curso Técnico/Profissionalizante"
        if curso_id:
            c_ref = db.collection("cursos").document(curso_id).get()
            if c_ref.exists:
                nome_curso = c_ref.to_dict().get("nome_curso", nome_curso).upper()

        texto = f"Declaramos para os devidos fins que o(a) aluno(a) <b>{nome}</b>, CPF <b>{cpf}</b>, está regularmente matriculado(a) na instituição {sys_dados.get('nome_instituicao')}, sob a matrícula <b>{matricula}</b>, no curso de <b>{nome_curso}</b>."
        elements.append(Paragraph(texto, body_style))

        data_atual = datetime.now().strftime("%d/%m/%Y")
        elements.append(Spacer(1, 40))
        elements.append(
            Paragraph(f"Vigia/PA, {data_atual}.", ParagraphStyle('DateStyle', parent=body_style, alignment=TA_CENTER)))

        elements.append(Spacer(1, 50))
        sig_data = [['________________________________________', '________________________________________'],
                    ['Secretaria Acadêmica', 'Direção Geral']]
        sig_table = Table(sig_data, colWidths=[200, 200])
        sig_table.setStyle(TableStyle(
            [('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
             ('FONTSIZE', (0, 0), (-1, -1), 10)]))
        elements.append(sig_table)

        pdf.build(elements)
        buffer.seek(0)
        nome_arquivo = tipo_doc.replace(" ", "_").replace("/", "-")

        return Response(
            content=buffer.getvalue(),
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={nome_arquivo}_{matricula}.pdf"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")


@app.get("/api/v1/docentes/pdf")
async def gerar_relatorio_docentes_pdf(q: str = None):
    try:
        checar_db()
        docs = db.collection("docentes").stream()
        docentes = [{"id": d.id, **d.to_dict()} for d in docs]

        if q:
            q_lower = q.lower()
            docentes = [d for d in docentes if
                        q_lower in str(d.get("nome", "")).lower() or q_lower in str(d.get("registro", "")).lower()]

        buffer = io.BytesIO()
        pdf = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=30, leftMargin=30, topMargin=40, bottomMargin=40)
        elements = []
        styles = getSampleStyleSheet()

        elements.append(Paragraph("<b>RELATÓRIO DO CORPO DOCENTE</b>",
                                  ParagraphStyle('Title', parent=styles['Normal'], fontName='Helvetica-Bold',
                                                 fontSize=14, alignment=TA_CENTER, spaceAfter=20)))

        table_data = [['REGISTRO', 'NOME', 'TELEFONE', 'TIPO']]
        for d in docentes:
            table_data.append(
                [str(d.get('registro', '-')), str(d.get('nome', '-')).upper(), str(d.get('telefone', '-')),
                 str(d.get('tipo_profissional', '-')).title()])

        t_obj = Table(table_data, colWidths=[80, 200, 100, 150])
        t_obj.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0f766e')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1'))
        ]))
        elements.append(t_obj)
        pdf.build(elements)
        buffer.seek(0)
        return Response(content=buffer.getvalue(), media_type="application/pdf",
                        headers={"Content-Disposition": "attachment; filename=Relatorio_Docentes.pdf"})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/alunos/pdf")
async def gerar_relatorio_alunos_pdf(q: str = None):
    try:
        checar_db()
        docs = db.collection("alunos").stream()
        alunos = [{"id": d.id, **d.to_dict()} for d in docs]

        if q:
            q_lower = q.lower()
            alunos = [a for a in alunos if
                      q_lower in str(a.get("nome", "")).lower() or q_lower in str(a.get("matricula", "")).lower()]

        buffer = io.BytesIO()
        pdf = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=30, leftMargin=30, topMargin=40, bottomMargin=40)
        elements = []
        styles = getSampleStyleSheet()

        elements.append(Paragraph("<b>RELATÓRIO DE ALUNOS MATRICULADOS</b>",
                                  ParagraphStyle('Title', parent=styles['Normal'], fontName='Helvetica-Bold',
                                                 fontSize=14, alignment=TA_CENTER, spaceAfter=20)))

        table_data = [['MATRÍCULA', 'NOME', 'TELEFONE', 'STATUS']]
        for a in alunos:
            table_data.append(
                [str(a.get('matricula', '-')), str(a.get('nome', '-')).upper(), str(a.get('telefone', '-')),
                 str(a.get('status', 'Ativo')).upper()])

        t_obj = Table(table_data, colWidths=[90, 220, 100, 120])
        t_obj.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0f766e')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1'))
        ]))
        elements.append(t_obj)
        pdf.build(elements)
        buffer.seek(0)
        return Response(content=buffer.getvalue(), media_type="application/pdf",
                        headers={"Content-Disposition": "attachment; filename=Relatorio_Alunos.pdf"})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/v1/docente/material/{material_id}")
async def excluir_material_didatico(material_id: str, authorization: str = Header(None)):
    checar_db()
    validar_token_docente(authorization)
    db.collection("materiais_didaticos").document(material_id).delete()
    return {"sucesso": True, "mensagem": "Material excluído com sucesso."}


@app.put("/api/v1/docente/material/{material_id}")
async def editar_material_didatico(material_id: str, payload: MaterialEdicaoPayload, authorization: str = Header(None)):
    checar_db()
    validar_token_docente(authorization)
    db.collection("materiais_didaticos").document(material_id).update({
        "titulo": payload.titulo,
        "url_arquivo": payload.url_arquivo
    })
    return {"sucesso": True, "mensagem": "Material atualizado com sucesso."}


@app.put("/api/v1/docente/perfil/atualizar")
async def atualizar_perfil_docente(payload: PerfilDocentePayload, authorization: str = Header(None)):
    checar_db()
    docente_id = validar_token_docente(authorization)
    db.collection("docentes").document(docente_id).update({
        "email": payload.email,
        "telefone": payload.telefone
    })
    return {"sucesso": True, "mensagem": "Contatos atualizados com sucesso."}


# ==========================================
# 10. MÓDULO DO ALUNO (PORTAL DO ESTUDANTE)
# ==========================================
def validar_token_aluno(authorization: str):
    if not authorization or not authorization.startswith("Bearer aluno_"):
        raise HTTPException(status_code=401, detail="Acesso não autorizado para aluno.")
    return authorization.replace("Bearer aluno_", "")


@app.get("/api/v1/aluno/dashboard")
async def obter_dashboard_aluno(authorization: str = Header(None)):
    checar_db()
    aluno_id = validar_token_aluno(authorization)
    aluno_doc = db.collection("alunos").document(aluno_id).get()

    if not aluno_doc.exists:
        raise HTTPException(status_code=404, detail="Aluno não encontrado")

    aluno_dados = aluno_doc.to_dict()
    curso_id = aluno_dados.get("curso")

    disciplinas_atuais = []
    if curso_id:
        curso_doc = db.collection("cursos").document(curso_id).get()
        if curso_doc.exists:
            c_dados = curso_doc.to_dict()
            nome_curso = c_dados.get("nome_curso", "Curso")
            for m in c_dados.get("grade_curricular", []):
                if isinstance(m, dict):
                    disciplinas_atuais.append({
                        "nome": m.get("nome") or m.get("disciplina") or "Módulo",
                        "curso": nome_curso
                    })

    diarios_docs = db.collection("diarios").stream()
    total_faltas = 0
    soma_notas = 0
    qtd_notas = 0

    for doc in diarios_docs:
        d_data = doc.to_dict()
        for lanc in d_data.get("avaliacoes", []):
            if str(lanc.get("aluno_id")) == str(aluno_id):
                total_faltas += int(lanc.get("faltas", 0))
                notas_dict = lanc.get("notas", {})
                for k, v in notas_dict.items():
                    try:
                        if v is not None and str(v).strip() != '':
                            v_clean = str(v).replace(',', '.')
                            soma_notas += float(v_clean)
                            qtd_notas += 1
                    except:
                        pass

    media_geral = round(soma_notas / qtd_notas, 1) if qtd_notas > 0 else 0.0

    return {
        "media_geral": media_geral,
        "faltas_totais": total_faltas,
        "status_financeiro": "Regular" if aluno_dados.get("possui_pendencia_financeira") != "Sim" else "Pendente",
        "disciplinas_atuais": disciplinas_atuais[:3]
    }


@app.get("/api/v1/aluno/cursos")
async def listar_cursos_aluno(authorization: str = Header(None)):
    checar_db()
    aluno_id = validar_token_aluno(authorization)
    aluno_doc = db.collection("alunos").document(aluno_id).get()

    if not aluno_doc.exists:
        return []

    aluno_dados = aluno_doc.to_dict()
    curso_id = aluno_dados.get("curso")
    cursos_lista = aluno_dados.get("cursos_json", [])

    ids_para_buscar = set()
    if curso_id:
        ids_para_buscar.add(curso_id)
    for c in cursos_lista:
        if isinstance(c, dict) and c.get("curso_id"):
            ids_para_buscar.add(c.get("curso_id"))

    resultado = []
    for c_id in ids_para_buscar:
        c_doc = db.collection("cursos").document(c_id).get()
        if c_doc.exists:
            resultado.append({"id": c_doc.id, **c_doc.to_dict()})

    return resultado


@app.get("/api/v1/aluno/boletim/{curso_id}")
async def obter_boletim_aluno(curso_id: str, authorization: str = Header(None)):
    checar_db()
    aluno_id = validar_token_aluno(authorization)

    aluno_doc = db.collection("alunos").document(aluno_id).get()
    if not aluno_doc.exists:
        raise HTTPException(status_code=404, detail="Aluno não encontrado")

    curso_doc = db.collection("cursos").document(curso_id).get()
    grade_curricular = []
    if curso_doc.exists:
        grade_curricular = curso_doc.to_dict().get("grade_curricular", [])

    diarios_docs = db.collection("diarios").stream()
    lancamentos_aluno = {}

    for doc in diarios_docs:
        d_data = doc.to_dict()
        t_id = d_data.get("turma_id", "")
        if not t_id.startswith(f"{curso_id}_"):
            continue

        parts = t_id.split("_", 1)
        if len(parts) > 1:
            nome_disc = parts[1]
            nome_disc_limpo = nome_disc.strip().upper()

            for lanc in d_data.get("avaliacoes", []):
                if str(lanc.get("aluno_id")) == str(aluno_id):
                    if nome_disc_limpo not in lancamentos_aluno:
                        lancamentos_aluno[nome_disc_limpo] = {"faltas": 0, "notas": {}}
                    try:
                        lancamentos_aluno[nome_disc_limpo]["faltas"] += int(lanc.get("faltas", 0))
                    except:
                        pass
                    lancamentos_aluno[nome_disc_limpo]["notas"].update(lanc.get("notas", {}))

    boletim_enriquecido = []

    for m in grade_curricular:
        if not isinstance(m, dict):
            continue

        semestre_modulo = m.get("semestre", "Semestre Único")
        sub_lista = m.get("disciplinas", [])
        itens_para_processar = sub_lista if (isinstance(sub_lista, list) and len(sub_lista) > 0) else [m]

        for disc_matriz in itens_para_processar:
            if not isinstance(disc_matriz, dict):
                continue

            nome_disc = disc_matriz.get("nome") or disc_matriz.get("disciplina")
            if not nome_disc:
                continue

            nome_limpo = nome_disc.strip().upper()
            dados_lancados = lancamentos_aluno.get(nome_limpo, {"faltas": 0, "notas": {}})

            notas_vals = []
            for v in dados_lancados["notas"].values():
                if v is not None and str(v).strip() != '':
                    try:
                        v_clean = str(v).replace(',', '.')
                        notas_vals.append(float(v_clean))
                    except:
                        pass

            media_final = round(sum(notas_vals) / len(notas_vals), 1) if notas_vals else None

            situacao = "Cursando"
            if media_final is not None:
                situacao = "Aprovado" if media_final >= 7.0 else "Em Recuperação"

            ementa_oficial = (
                    disc_matriz.get("descricao") or
                    disc_matriz.get("ementa") or
                    disc_matriz.get("detalhes") or
                    disc_matriz.get("resumo") or
                    m.get("descricao") or
                    m.get("ementa") or
                    "Nenhuma ementa detalhada informada na matriz curricular."
            )

            item_completo = {
                "disciplina": nome_disc,
                "semestre": semestre_modulo,
                "faltas": dados_lancados["faltas"],
                "media_final": media_final,
                "situacao": situacao,
                "notas": dados_lancados["notas"],
                "ementa": ementa_oficial,
                "foto_modulo": disc_matriz.get("foto_modulo", m.get("foto_modulo", "")),
                "ch_teoria": disc_matriz.get("ch_teoria", 0),
                "ch_pratica": disc_matriz.get("ch_pratica", 0),
                "ch_es": disc_matriz.get("ch_es", 0),
                "ch_total": disc_matriz.get("ch_total", 40),
                "avaliacoes_previstas": [av.get("tipo") if isinstance(av, dict) else av for av in
                                         disc_matriz.get("avaliacoes", ["AV1", "AV2", "Final"])]
            }
            boletim_enriquecido.append(item_completo)

    return boletim_enriquecido


@app.get("/api/v1/aluno/materiais/{curso_id}")
async def listar_materiais_aluno(curso_id: str, authorization: str = Header(None)):
    checar_db()
    validar_token_aluno(authorization)
    materiais = []
    docs = db.collection("materiais_didaticos").stream()
    for doc in docs:
        m = doc.to_dict()
        if curso_id in m.get("turma_id", ""):
            materiais.append({"id": doc.id, **m})
    return materiais


@app.get("/api/v1/aluno/perfil")
async def obter_perfil_aluno(authorization: str = Header(None)):
    checar_db()
    aluno_id = validar_token_aluno(authorization)
    doc = db.collection("alunos").document(aluno_id).get()

    if not doc.exists:
        raise HTTPException(status_code=404, detail="Aluno não encontrado")

    dados = doc.to_dict()
    valor_mensalidade = 350.0
    curso_id = dados.get("curso")

    if curso_id:
        c_doc = db.collection("cursos").document(curso_id).get()
        if c_doc.exists:
            c_info = c_doc.to_dict()
            if c_info.get("promocao_ativa") == "Sim" and c_info.get("valor_promocional"):
                try:
                    valor_mensalidade = float(c_info.get("valor_promocional"))
                except:
                    pass
            else:
                try:
                    valor_mensalidade = float(c_info.get("valor_mensalidade", 350.0))
                except:
                    pass

    return {
        "cpf": dados.get("cpf"),
        "email": dados.get("email"),
        "telefone": dados.get("telefone"),
        "endereco": dados.get("endereco"),
        "dia_vencimento": dados.get("dia_vencimento", 10),
        "valor_mensalidade": valor_mensalidade,
        "possui_pendencia_financeira": dados.get("possui_pendencia_financeira", "Não")
    }


@app.post("/api/v1/aluno/financeiro/comprovante")
async def aluno_enviar_comprovante_portal(comprovante: UploadFile = File(...), authorization: str = Header(None)):
    checar_db()
    aluno_id = validar_token_aluno(authorization)

    dados_comp = {
        "aluno_id": aluno_id,
        "nome_arquivo": comprovante.filename,
        "status": "Em Análise",
        "data_envio": datetime.now().isoformat()
    }
    db.collection("comprovantes_pagamento").add(dados_comp)
    return {"sucesso": True, "mensagem": "Comprovante enviado com sucesso!"}

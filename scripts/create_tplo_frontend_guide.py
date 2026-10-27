from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    Flowable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


OUT = Path("output/pdf/tplo_frontend_implementation_guide.pdf")
OUT.parent.mkdir(parents=True, exist_ok=True)
BLUE = colors.HexColor("#123B63")
TEAL = colors.HexColor("#0F766E")
LIGHT = colors.HexColor("#EEF4F8")
ORANGE = colors.HexColor("#F59E0B")
GRAY = colors.HexColor("#52606D")


class ScreenMockup(Flowable):
    def __init__(self, title: str, mode: str, width: float = 170 * mm, height: float = 76 * mm):
        super().__init__()
        self.title, self.mode, self.width, self.height = title, mode, width, height

    def draw(self):
        c = self.canv
        w, h = self.width, self.height
        c.setFillColor(colors.white)
        c.setStrokeColor(colors.HexColor("#CBD5E1"))
        c.roundRect(0, 0, w, h, 4 * mm, fill=1, stroke=1)
        c.setFillColor(BLUE)
        c.rect(0, h - 11 * mm, w, 11 * mm, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 9)
        c.drawString(5 * mm, h - 7 * mm, self.title)
        c.setFillColor(LIGHT)
        c.roundRect(5 * mm, 8 * mm, 88 * mm, h - 25 * mm, 2 * mm, fill=1, stroke=0)
        c.setFillColor(colors.HexColor("#D7E2EA"))
        c.rect(10 * mm, 16 * mm, 78 * mm, h - 41 * mm, fill=1, stroke=0)
        # Radiograph and anatomical overlay.
        c.setStrokeColor(TEAL)
        c.setLineWidth(1.4)
        c.line(31 * mm, 23 * mm, 68 * mm, h - 30 * mm)
        c.line(25 * mm, h - 34 * mm, 74 * mm, 28 * mm)
        c.setFillColor(ORANGE)
        for x, y in [(31, 23), (68, h / mm - 30), (25, h / mm - 34), (74, 28)]:
            c.circle(x * mm, y * mm, 1.8 * mm, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont("Helvetica", 7)
        c.drawString(12 * mm, 10 * mm, "Imagem + camadas de medicao")
        # Right panel.
        c.setFillColor(colors.HexColor("#F8FAFC"))
        c.roundRect(99 * mm, 8 * mm, w / mm * mm - 106 * mm, h - 25 * mm, 2 * mm, fill=1, stroke=0)
        c.setFillColor(BLUE)
        c.setFont("Helvetica-Bold", 8)
        c.drawString(105 * mm, h - 20 * mm, "TPLO - Etapa 3")
        lines = {
            "quality": ["Qualidade radiografica", "[x] lateral verdadeira", "[x] plato visivel", "[x] eixo centralizado", "Status: ELIGIBLE"],
            "measure": ["Medicoes assistidas", "Calibracao: 0.42 mm/px", "TPA: 24.0 graus", "Eixo tibial: 168.4 mm", "Resultado: CALCULATED"],
            "review": ["Revisao clinica", "[x] orientacao", "[x] qualidade", "[x] calibracao", "Acao: READY_FOR_REVIEW"],
            "final": ["Finalizacao", "Snapshot SHA-256", "Relatorio PNG", "Relatorio PDF", "Estado: FINALIZED"],
        }[self.mode]
        c.setFillColor(GRAY)
        c.setFont("Helvetica", 7.5)
        for i, line in enumerate(lines):
            c.drawString(105 * mm, h - (28 + i * 8) * mm, line)


styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="TitleBlue", parent=styles["Title"], textColor=BLUE, fontSize=22, leading=26, spaceAfter=10))
styles.add(ParagraphStyle(name="H1Blue", parent=styles["Heading1"], textColor=BLUE, fontSize=15, leading=18, spaceBefore=8, spaceAfter=6))
styles.add(ParagraphStyle(name="H2Teal", parent=styles["Heading2"], textColor=TEAL, fontSize=11, leading=14, spaceBefore=6, spaceAfter=4))
styles.add(ParagraphStyle(name="BodySmall", parent=styles["BodyText"], fontSize=9, leading=13, textColor=colors.HexColor("#243B53")))
styles.add(ParagraphStyle(name="Caption", parent=styles["BodyText"], fontSize=8, leading=10, textColor=GRAY, alignment=1))


def p(text, style="BodySmall"):
    return Paragraph(text, styles[style])


def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(GRAY)
    canvas.drawString(18 * mm, 10 * mm, "VetOrthoPlan - Guia de implementacao frontend - calibration")
    canvas.drawRightString(192 * mm, 10 * mm, f"Pagina {doc.page}")
    canvas.restoreState()


doc = SimpleDocTemplate(str(OUT), pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm, topMargin=16 * mm, bottomMargin=18 * mm)
story = []
story += [p("Guia de implementacao do fluxo TPLO", "TitleBlue"), p("Versao calibration | Backend e BFF publicados", "H2Teal")]
story += [p("Objetivo", "H1Blue"), p("Implementar no frontend o fluxo clinico de planejamento TPLO usando os endpoints ja publicados. A etapa 3 deve permitir medir a radiografia, marcar os pontos anatomicos, calcular o TPA, simular a osteotomia e conduzir o plano ate a revisao e finalizacao."), Spacer(1, 5 * mm)]
story += [p("O que ja existe no backend", "H1Blue")]
data = [["Bloco", "Contrato / comportamento", "Frontend deve consumir"], ["Plano", "GET/PUT com revisao otimista", "Carregar plano e tratar 409"], ["TPLO", "Marcos, TPA, medidas e simulacao", "Canvas + painel de propriedades"], ["Clinica", "Qualidade, revisao e auditoria", "Checklist e transicoes"], ["Entrega", "Snapshot imutavel e relatorios", "Finalizar e baixar PNG/PDF"]]
t = Table(data, colWidths=[30 * mm, 82 * mm, 62 * mm])
t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), BLUE), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("GRID", (0, 0), (-1, -1), .3, colors.HexColor("#CBD5E1")), ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#F8FAFC")), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 8), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5)]))
story += [t, PageBreak(), p("Tela 1 - Qualidade e elegibilidade", "H1Blue"), ScreenMockup("Planejamento TPLO / Qualidade", "quality"), p("Exemplo ilustrativo: a tela deve tornar visiveis os cinco criterios persistidos em radiographic_quality e o estado de elegibilidade. Os textos clinicos finais dependem da homologacao veterinaria.", "Caption"), p("Passo a passo", "H2Teal"), p("1. Carregar a imagem e o plano. 2. Exibir o checklist. 3. Salvar cada alteracao com base_revision. 4. Bloquear ELIGIBLE enquanto houver criterio diferente de PASS. 5. Mostrar erro de validacao retornado pelo backend."), PageBreak()]
story += [p("Tela 2 - Medicoes e pontos anatomicos", "H1Blue"), ScreenMockup("Planejamento TPLO / Medicoes", "measure"), p("Exemplo ilustrativo: os pontos devem ser editaveis sobre o canvas, com coordenadas normalizadas. O backend recalcula medidas a partir da imagem original e devolve tplo_measurement.", "Caption"), p("Passo a passo", "H2Teal"), p("1. Implementar zoom, pan e selecao de ferramenta. 2. Marcar condilo, plato e eixo tibial. 3. Mostrar linhas e angulos em tempo real. 4. Executar calibracao por linha ou circulo. 5. Persistir landmarks e objetos. 6. Refletir CALCULATED, NOT_ASSESSED e FAIL sem substituir o valor calculado pelo cliente."), PageBreak()]
story += [p("Tela 3 - Revisao clinica", "H1Blue"), ScreenMockup("Planejamento TPLO / Revisao", "review"), Spacer(1, 5 * mm), p("Finalizacao", "H2Teal"), ScreenMockup("Planejamento TPLO / Finalizacao", "final"), p("Exemplos ilustrativos: o frontend deve conduzir a transicao READY_FOR_REVIEW, mostrar a auditoria e exigir APPROVED antes de chamar finalize. Depois da finalizacao, o plano fica somente leitura.", "Caption"), PageBreak()]
story += [p("Ordem de implementacao para o frontend", "H1Blue")]
steps = ["1. Criar servico tipado para GET/PUT do plano e endpoints TPLO.", "2. Montar o canvas com camadas: imagem, pontos, linhas, angulos, osteotomia e anotacoes.", "3. Criar painel de qualidade, calibracao e medidas calculadas.", "4. Implementar autosave controlado por revisao, tratamento de 409 e indicador de salvamento.", "5. Implementar revisao clinica e estados DRAFT, READY_FOR_REVIEW, APPROVED e REJECTED.", "6. Implementar finalizacao, links temporarios e tela somente leitura.", "7. Criar testes BFF para respostas 200, 401, 403, 404, 409, 422 e 502."]
story += [p("<br/>".join(steps))]
story += [p("Quando entram os moldes de proteses", "H1Blue"), p("Os moldes nao sao necessarios para concluir a etapa de medicao e simulacao geometrica TPLO. Eles entram depois que o catalogo versionado de implantes estiver definido e antes da simulacao final de posicionamento do implante. Antes de carregar STL/OBJ, o contrato deve fixar unidade, sistema de coordenadas, lateridade, diametro compativel, versao, origem, licenca e checksum. Recomenda-se iniciar com um conjunto pequeno de moldes oficiais e validar escala e orientacao com o parceiro veterinario."), Spacer(1, 4 * mm), p("Referencias de endpoints", "H2Teal"), p("GET/PUT /api/v1/images/{image_id}/plan<br/>GET /api/v1/tplo/clinical-protocol<br/>GET /api/v1/tplo/rotation-table<br/>POST /api/v1/images/{image_id}/plan/finalize<br/>GET /api/v1/images/{image_id}/plan/finalization"), Spacer(1, 4 * mm), p("Importante: os exemplos de tela sao wireframes de orientacao. Os criterios clinicos, tolerancias e moldes precisam ser homologados pelo parceiro veterinario antes de uso assistencial.", "Caption")]
doc.build(story, onFirstPage=footer, onLaterPages=footer)
print(OUT)

import os
import sys
import math
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, HRFlowable, Image as RLImage
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from reportlab.pdfgen import canvas

def generate_diagram_image(image_path='output/workflow_copilot_diagram.png'):
    """Generate high-resolution (300 DPI equivalent) workflow diagram matching user specification."""
    os.makedirs(os.path.dirname(image_path), exist_ok=True)
    scale = 3
    W = 680 * scale
    H = 540 * scale  # Compact height to fit neatly in page

    img = Image.new('RGB', (W, H), color='#FFFFFF')
    draw = ImageDraw.Draw(img)

    f_title = ImageFont.truetype('C:/Windows/Fonts/segoeuib.ttf', 15 * scale)
    f_subtitle = ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf', 10.5 * scale)
    f_num = ImageFont.truetype('C:/Windows/Fonts/segoeuib.ttf', 11 * scale)
    f_card_title = ImageFont.truetype('C:/Windows/Fonts/segoeuib.ttf', 12.5 * scale)
    f_card_sub = ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf', 10 * scale)
    f_tag = ImageFont.truetype('C:/Windows/Fonts/segoeuib.ttf', 9.5 * scale)

    BG_BOX = '#F8FAFC'
    BORDER_BOX = '#CBD5E1'
    BADGE_BG = '#EA580C'  # Warna Ciri Khas Company (Signature Brand Orange)
    BADGE_TXT = '#FFFFFF'
    TEXT_MAIN = '#0F172A'
    TEXT_MUTED = '#475569'
    ARROW_COL = '#64748B'

    def draw_arrow_head(x, y, angle_rad, size=6*scale):
        p1 = (x, y)
        p2 = (x - size * math.cos(angle_rad - math.pi/6), y - size * math.sin(angle_rad - math.pi/6))
        p3 = (x - size * math.cos(angle_rad + math.pi/6), y - size * math.sin(angle_rad + math.pi/6))
        draw.polygon([p1, p2, p3], fill=ARROW_COL)

    def draw_node(x, y, w, h, badge_txt, title_txt, sub_txt, badge_w=36):
        box = [x * scale, y * scale, (x + w) * scale, (y + h) * scale]
        draw.rounded_rectangle(box, radius=7 * scale, fill=BG_BOX, outline=BORDER_BOX, width=scale)
        badge_box = [x * scale, y * scale, (x + badge_w) * scale, (y + h) * scale]
        draw.rounded_rectangle(badge_box, radius=7 * scale, fill=BADGE_BG)
        draw.rectangle([(x + badge_w - 5) * scale, y * scale, (x + badge_w) * scale, (y + h) * scale], fill=BADGE_BG)
        
        bbox = draw.textbbox((0, 0), badge_txt, font=f_num)
        bx = (x + badge_w / 2) * scale - (bbox[2] - bbox[0]) / 2
        by = (y + h / 2) * scale - (bbox[3] - bbox[1]) / 2 - 2 * scale
        draw.text((bx, by), badge_txt, font=f_num, fill=BADGE_TXT)
        
        content_center_x = (x + badge_w + (w - badge_w) / 2) * scale
        t_bbox = draw.textbbox((0, 0), title_txt, font=f_card_title)
        tx = content_center_x - (t_bbox[2] - t_bbox[0]) / 2
        ty = (y + 14) * scale
        draw.text((tx, ty), title_txt, font=f_card_title, fill=TEXT_MAIN)
        
        s_bbox = draw.textbbox((0, 0), sub_txt, font=f_card_sub)
        sx = content_center_x - (s_bbox[2] - s_bbox[0]) / 2
        sy = (y + 31) * scale
        draw.text((sx, sy), sub_txt, font=f_card_sub, fill=TEXT_MUTED)

    # Header
    title = 'The Workplace Brain — Enterprise Incident Co-Pilot'
    t_bb = draw.textbbox((0, 0), title, font=f_title)
    draw.text(((680*scale - (t_bb[2]-t_bb[0]))/2, 16*scale), title, font=f_title, fill=TEXT_MAIN)

    sub = 'Alur Kerja 6 Tahap Investigasi, AI RCA & ChatOps Automation'
    s_bb = draw.textbbox((0, 0), sub, font=f_subtitle)
    draw.text(((680*scale - (s_bb[2]-s_bb[0]))/2, 36*scale), sub, font=f_subtitle, fill=TEXT_MUTED)
    draw.line([(180*scale, 56*scale), (500*scale, 56*scale)], fill='#EA580C', width=scale)

    # 01: Trigger & 02: Ingestion
    draw_node(55, 72, 235, 52, '01', 'Alert Ingress Trigger', 'Prometheus Alertmanager / Webhook')
    draw_node(390, 72, 235, 52, '02', 'Ingestion & Normalisasi', 'Parsing context, cluster & severity')

    draw.line([(290*scale, 98*scale), (390*scale, 98*scale)], fill=ARROW_COL, width=2*scale)
    draw_arrow_head(390*scale, 98*scale, 0)

    draw.line([(507*scale, 124*scale), (507*scale, 155*scale)], fill=ARROW_COL, width=2*scale)
    draw_arrow_head(507*scale, 155*scale, math.pi/2)

    # 03: KB Lookup
    draw_node(55, 155, 570, 52, '03', 'Knowledge Base & Runbook Matching', 'Pencocokan SOP (K8s/Storage), topologi cluster, & riwayat insiden')

    draw.line([(340*scale, 207*scale), (340*scale, 238*scale)], fill=ARROW_COL, width=2*scale)
    draw_arrow_head(340*scale, 238*scale, math.pi/2)

    # 04: Diagnosis & AI RCA
    draw_node(55, 238, 570, 52, '04', 'Diagnosa Mendalam & AI RCA Synthesis', 'Read-only check (Pod K8s, Longhorn PV, Host) + AI Root Cause Analysis')

    draw.line([(340*scale, 290*scale), (340*scale, 321*scale)], fill=ARROW_COL, width=2*scale)
    draw_arrow_head(340*scale, 321*scale, math.pi/2)

    # 05a & 05b
    draw_node(55, 321, 280, 52, '05a', 'Executive PDF Report', 'Laporan teknis + kotak AI RCA')
    draw_node(345, 321, 280, 52, '05b', 'Interactive ChatOps Bot', 'Telegram @hlm_alert_bot & Teams')

    draw.line([(340*scale, 373*scale), (340*scale, 404*scale)], fill=ARROW_COL, width=2*scale)
    draw_arrow_head(340*scale, 404*scale, math.pi/2)

    # 06: Feedback Loop
    draw_node(55, 404, 570, 52, '06', 'Feedback Loop & Self-Improving KB', 'Audit trail insiden, update runbook, post-mortem generator')

    # Return curve
    p_start = (625*scale, 430*scale)
    p_c1 = (660*scale, 430*scale)
    p_c2 = (660*scale, 181*scale)
    p_end = (625*scale, 181*scale)
    curve_points = []
    for i in range(101):
        t = i / 100.0
        x = (1-t)**3 * p_start[0] + 3*(1-t)**2*t * p_c1[0] + 3*(1-t)*t**2 * p_c2[0] + t**3 * p_end[0]
        y = (1-t)**3 * p_start[1] + 3*(1-t)**2*t * p_c1[1] + 3*(1-t)*t**2 * p_c2[1] + t**3 * p_end[1]
        curve_points.append((x, y))

    dash_len = 10 * scale
    gap_len = 8 * scale
    cur_len = 0
    drawing = True
    for i in range(len(curve_points)-1):
        pt1 = curve_points[i]
        pt2 = curve_points[i+1]
        seg_len = math.hypot(pt2[0]-pt1[0], pt2[1]-pt1[1])
        if drawing:
            draw.line([pt1, pt2], fill='#475569', width=2*scale)
        cur_len += seg_len
        if drawing and cur_len >= dash_len:
            drawing = False
            cur_len = 0
        elif not drawing and cur_len >= gap_len:
            drawing = True
            cur_len = 0

    draw_arrow_head(625*scale, 181*scale, math.pi)

    # Tag 'update KB'
    tag_txt = 'update KB'
    tag_bb = draw.textbbox((0, 0), tag_txt, font=f_tag)
    tag_x = 645 * scale
    tag_y = 305 * scale
    draw.rounded_rectangle([tag_x - 32*scale, tag_y - 11*scale, tag_x + 32*scale, tag_y + 11*scale], radius=4*scale, fill='#F1F5F9', outline='#CBD5E1', width=scale)
    draw.text((tag_x - (tag_bb[2]-tag_bb[0])/2, tag_y - (tag_bb[3]-tag_bb[1])/2 - 2*scale), tag_txt, font=f_tag, fill='#334155')

    img.save(image_path, 'PNG', quality=95)
    return image_path


class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count):
        self.saveState()
        self.setFont('Helvetica', 8)
        self.setFillColor(colors.HexColor('#64748B'))
        
        # Running Header (Halaman 2 ke atas)
        if self._pageNumber > 1:
            self.drawString(20 * mm, A4[1] - 13 * mm, 'Platform Bigdata — Server Monitoring Agent & Incident Co-Pilot')
            self.setStrokeColor(colors.HexColor('#EA580C'))
            self.setLineWidth(1.2)
            self.line(20 * mm, A4[1] - 15 * mm, 45 * mm, A4[1] - 15 * mm)
            self.setStrokeColor(colors.HexColor('#CBD5E1'))
            self.setLineWidth(0.5)
            self.line(45 * mm, A4[1] - 15 * mm, A4[0] - 20 * mm, A4[1] - 15 * mm)
            
        # Running Footer (Semua Halaman)
        footer_text = f'Halaman {self._pageNumber} dari {page_count}'
        self.drawRightString(A4[0] - 20 * mm, 12 * mm, footer_text)
        self.drawString(20 * mm, 12 * mm, 'Dokumentasi Sistem Operasional Enterprise | Platform Bigdata — Confidential')
        self.setStrokeColor(colors.HexColor('#CBD5E1'))
        self.setLineWidth(0.5)
        self.line(20 * mm, 16 * mm, A4[0] - 20 * mm, 16 * mm)
        self.setStrokeColor(colors.HexColor('#EA580C'))
        self.setLineWidth(1.2)
        self.line(20 * mm, 16 * mm, 45 * mm, 16 * mm)
        self.restoreState()


def build_pdf():
    # 1. Pastikan diagram gambar PNG terbuat
    diagram_path = 'output/workflow_copilot_diagram.png'
    generate_diagram_image(diagram_path)

    # 2. Palet Warna Korporat Slate + Ciri Khas Brand Company (Orange #EA580C)
    C_BRAND_ORANGE = colors.HexColor('#EA580C')  # Warna Ciri Khas Company (Brand Orange)
    C_BRAND_DARK   = colors.HexColor('#C2410C')  # Deep Brand Orange (Formal & High-Contrast)
    C_HEADER_BG    = colors.HexColor('#C2410C')  # Judul Header Tabel Sesuai Thema Company
    C_TEXT_MAIN    = colors.HexColor('#0F172A')  # Slate 900
    C_TEXT_MUTED   = colors.HexColor('#475569')  # Slate 600
    C_ROW_ALT      = colors.HexColor('#F8FAFC')  # Slate 50
    C_BORDER       = colors.HexColor('#CBD5E1')  # Slate 300
    C_LINE         = colors.HexColor('#94A3B8')  # Slate 400

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        'DocTitle', parent=styles['Normal'],
        fontName='Helvetica-Bold', fontSize=16, leading=20,
        textColor=C_TEXT_MAIN, alignment=TA_CENTER
    )
    subtitle_style = ParagraphStyle(
        'DocSubTitle', parent=styles['Normal'],
        fontName='Helvetica', fontSize=8.5, leading=12,
        textColor=C_TEXT_MUTED, alignment=TA_CENTER
    )
    h1_style = ParagraphStyle(
        'H1', parent=styles['Normal'],
        fontName='Helvetica-Bold', fontSize=11, leading=14,
        textColor=C_TEXT_MAIN, spaceBefore=6, spaceAfter=3
    )
    h2_style = ParagraphStyle(
        'H2', parent=styles['Normal'],
        fontName='Helvetica-Bold', fontSize=9, leading=12,
        textColor=C_TEXT_MAIN, spaceBefore=4, spaceAfter=2
    )
    body_style = ParagraphStyle(
        'Body', parent=styles['Normal'],
        fontName='Helvetica', fontSize=7.8, leading=11,
        textColor=C_TEXT_MAIN, alignment=TA_JUSTIFY
    )
    cell_style = ParagraphStyle(
        'Cell', parent=styles['Normal'],
        fontName='Helvetica', fontSize=7.2, leading=9.5,
        textColor=C_TEXT_MAIN
    )
    cell_bold = ParagraphStyle(
        'CellBold', parent=cell_style,
        fontName='Helvetica-Bold'
    )
    cell_header = ParagraphStyle(
        'CellHeader', parent=cell_style,
        fontName='Helvetica-Bold', textColor=colors.white, alignment=TA_CENTER
    )

    output_pdf = 'output/Dokumentasi_Arsitektur_dan_Workflow_Agent.pdf'
    os.makedirs('output', exist_ok=True)

    doc = SimpleDocTemplate(
        output_pdf, pagesize=A4,
        leftMargin=20*mm, rightMargin=20*mm,
        topMargin=20*mm, bottomMargin=20*mm
    )

    story = []

    # =========================================================================
    # HALAMAN 1: IDENTITAS & RINGKASAN ARSITEKTUR KOMPONEN
    # =========================================================================
    # Garis aksen atas: Ciri khas warna company (Signature Orange)
    story.append(HRFlowable(width='100%', thickness=2.5, color=C_BRAND_ORANGE, spaceBefore=0, spaceAfter=2.5*mm))

    # Header Terpadu Sesuai Tema Dokumen
    brand_style = ParagraphStyle('Brand', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=10, leading=13)
    title_left_style = ParagraphStyle('TitleLeft', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=12.5, leading=15, textColor=C_TEXT_MAIN)
    sub_left_style = ParagraphStyle('SubLeft', parent=styles['Normal'], fontName='Helvetica', fontSize=7.8, leading=10.5, textColor=C_TEXT_MUTED)
    meta_style = ParagraphStyle('Meta', parent=styles['Normal'], fontName='Helvetica', fontSize=7.2, leading=9.5, textColor=C_TEXT_MAIN)

    header_left = [
        Paragraph('<font color="#EA580C"><b>■ PLATFORM BIGDATA</b></font> <font color="#64748B" size="7.5">| ENTERPRISE INFRASTRUCTURE &amp; AIOps</font>', brand_style),
        Paragraph('DOKUMENTASI ARSITEKTUR &amp; ALUR KERJA SISTEM', title_left_style),
        Paragraph('The Workplace Brain — Server Monitoring Agent &amp; Incident Co-Pilot', sub_left_style),
    ]
    header_right = [
        Paragraph('<b>Status:</b> Production Ready', meta_style),
        Paragraph('<b>Versi:</b> 2.5 (Enterprise Edition)', meta_style),
        Paragraph('<b>Infrastruktur:</b> <font color="#EA580C"><b>K8s Private Cloud</b></font>', meta_style),
    ]
    t_header = Table([[header_left, header_right]], colWidths=[118*mm, 52*mm])
    t_header.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
        ('TOPPADDING', (0,0), (-1,-1), 0),
        ('BOTTOMPADDING', (0,0), (-1,-1), 0),
        ('LINEBEFORE', (1,0), (1,0), 1.5, C_BRAND_ORANGE),
        ('LEFTPADDING', (1,0), (1,0), 3*mm),
    ]))
    story.append(t_header)
    story.append(Spacer(1, 1.5*mm))
    story.append(HRFlowable(width='100%', thickness=0.5, color=C_BORDER, spaceAfter=2.5*mm))

    story.append(Paragraph('<font color="#EA580C"><b>▌ 1.</b></font> <b>Ringkasan Eksekutif &amp; Karakteristik Sistem</b>', h1_style))
    story.append(Paragraph(
        'Server Monitoring Agent adalah platform AIOps Incident Co-Pilot enterprise yang dirancang khusus untuk infrastruktur private cloud <b>Platform Bigdata</b> (Kubernetes v1.26.5 24 node, Longhorn distributed storage, 2x NVIDIA RTX A6000 GPU, HAProxy/Keepalived VIP, dan stack Prometheus/Grafana). Sistem bekerja hibrida: mampu melakukan pemantauan berkala terjadwal, mendengarkan alert real-time Prometheus Alertmanager melalui Webhook Receiver, mendiagnosa kesehatan kluster (Pod CrashLoop, OOMKilled, Storage Degraded) tanpa downtime, menyintesis akar masalah via AI Root Cause Analysis (RCA), serta merespons interaktif melalui Telegram ChatOps Bot (@hlm_alert_bot).',
        body_style
    ))
    story.append(Spacer(1, 2.5*mm))

    # Tabel Komponen Sistem
    komponen_data = [
        [Paragraph('Komponen', cell_header), Paragraph('Modul Source', cell_header), Paragraph('Deskripsi & Tanggung Jawab Operasional', cell_header)],
        [Paragraph('Server Monitor', cell_bold), Paragraph('server_monitor.py', cell_style), Paragraph('Mengumpulkan telemetri CPU, Memory, Disk Partition, dan Uptime sistem via psutil.', cell_style)],
        [Paragraph('Syslog Parser', cell_bold), Paragraph('syslog_parser.py', cell_style), Paragraph('Memindai error log sistem dengan pola regex insiden (Kernel Panic, OOM, crash, disk full).', cell_style)],
        [Paragraph('Knowledge Base', cell_bold), Paragraph('knowledge_base.py', cell_style), Paragraph('Pusat repositori SOP Markdown (K8s/Longhorn/Host), topologi server, serta basis data histori.', cell_style)],
        [Paragraph('Diagnosis Engine', cell_bold), Paragraph('diagnosis_engine.py', cell_style), Paragraph('Menjalankan 12 pemeriksaan read-only: Ping, DNS, port layanan, HTTP endpoint, disk & memory.', cell_style)],
        [Paragraph('K8s Diagnostics', cell_bold), Paragraph('k8s_diagnostics.py', cell_style), Paragraph('Dual-Mode K8s & Longhorn engine: deteksi Pod CrashLoop, ExitCode 137, dan volume replika.', cell_style)],
        [Paragraph('AI RCA Synthesizer', cell_bold), Paragraph('ai_rca_engine.py', cell_style), Paragraph('Menyintesis telemetri & SOP menjadi ringkasan eksekutif akar masalah, dampak, dan aksi mitigasi.', cell_style)],
        [Paragraph('Webhook Receiver', cell_bold), Paragraph('webhook_receiver.py', cell_style), Paragraph('HTTP Ingress port 8080 penerima webhook alert Prometheus Alertmanager, Zabbix, dan Jira.', cell_style)],
        [Paragraph('Feedback Loop', cell_bold), Paragraph('feedback_loop.py', cell_style), Paragraph('Merekam histori audit insiden; membedakan status Triage vs Closed secara aman (tanpa false-close).', cell_style)],
        [Paragraph('Report Generator', cell_bold), Paragraph('report_generator.py', cell_style), Paragraph('Menyusun PDF profesional: Snapshot metrik, tabel diagnosa, kotak AI RCA, dan weekly/monthly report.', cell_style)],
        [Paragraph('Telegram ChatOps', cell_bold), Paragraph('notifier.py (@hlm_alert_bot)', cell_style), Paragraph('Notifikasi alert real-time ke HP engineer dengan tombol aksi (Ack, SOP, Restart Pod) + PDF report.', cell_style)]
    ]
    t_komp = Table(komponen_data, colWidths=[31*mm, 35*mm, 104*mm])
    t_komp.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), C_HEADER_BG),
        ('LINEABOVE', (0,0), (-1,0), 2, colors.HexColor('#F97316')),
        ('LINEBELOW', (0,0), (-1,0), 1, colors.HexColor('#9A3412')),
        ('GRID', (0,0), (-1,-1), 0.5, C_BORDER),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, C_ROW_ALT]),
        ('TOPPADDING', (0,0), (-1,-1), 2.2),
        ('BOTTOMPADDING', (0,0), (-1,-1), 2.2),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))
    story.append(t_komp)

    # PEMISAH KE HALAMAN 2: POIN 2 DIGESER KE HALAMAN 2
    story.append(PageBreak())

    # =========================================================================
    # HALAMAN 2: TIGA WORKFLOW OPERASIONAL UTAMA + DIAGRAM VISUAL 6 TAHAP
    # =========================================================================
    story.append(Paragraph('<font color="#EA580C"><b>▌ 2.</b></font> <b>Tiga Alur Kerja Operasional Utama (System Workflows)</b>', h1_style))
    story.append(Spacer(1, 1*mm))

    # Workflow 1
    story.append(Paragraph('<font color="#EA580C">▶</font> <b>Workflow 1: Monitoring Terjadwal Rutin (Snapshot Polling)</b>', h2_style))
    story.append(Paragraph(
        'Berjalan otomatis berdasarkan interval waktu berkala (default per 30 menit) atau sekali eksekusi sesuai permintaan (on-demand): '
        '<b>Pengumpulan Metrik</b> (CPU, RAM, Disk, Uptime via psutil) &rarr; <b>Evaluasi Threshold</b> (Warning & Critical) &rarr; '
        '<b>Pemindaian Syslog</b> (deteksi error/crash) &rarr; <b>Penyusunan Report PDF</b> di folder output/.',
        body_style
    ))
    story.append(Spacer(1, 1.5*mm))

    # Workflow 2 dengan DIAGRAM VISUAL
    story.append(Paragraph('<font color="#EA580C">▶</font> <b>Workflow 2: Investigasi Insiden Otomatis (Event-Driven Co-Pilot Pipeline)</b>', h2_style))
    story.append(Paragraph(
        'Alur respons cepat 6-tahap yang otomatis aktif ketika alert masuk dari sistem monitoring (Prometheus Alertmanager / Zabbix / Jira):',
        body_style
    ))
    story.append(Spacer(1, 1.5*mm))

    # Sisipkan Gambar Diagram Visual Workflow
    if os.path.exists(diagram_path):
        story.append(RLImage(diagram_path, width=160*mm, height=125*mm))
        story.append(Spacer(1, 2*mm))

    # Workflow 3
    story.append(Paragraph('<font color="#EA580C">▶</font> <b>Workflow 3: Laporan Eksekutif Berkala &amp; ChatOps (Weekly &amp; Monthly Report)</b>', h2_style))
    story.append(Paragraph(
        'Alur analitik berkala yang dijalankan via OS Cron Job (Linux), Task Scheduler (Windows), atau scheduler daemon bawaan: '
        '<b>Agregasi Riwayat</b> (7 hari untuk Weekly / 30 hari untuk Monthly) &rarr; <b>Perhitungan KPI & SLA</b> (rasio penyelesaian insiden, utilisasi resource) &rarr; '
        '<b>Analisis Masalah Berulang</b> (top root causes & SOP yang sering digunakan) &rarr; <b>Penyusunan Executive PDF & ChatOps Delivery</b>.',
        body_style
    ))

    # PEMISAH KE HALAMAN 3: INTEGRASI ARSITEKTUR & CHEATSHEET CLI
    story.append(PageBreak())

    # =========================================================================
    # HALAMAN 3: INTEGRASI ENTERPRISE & CHEATSHEET CLI
    # =========================================================================
    story.append(Paragraph('<font color="#EA580C"><b>▌ 3.</b></font> <b>Integrasi pada Arsitektur Enterprise (Platform Bigdata)</b>', h1_style))
    story.append(Paragraph(
        'Agent monitoring ini dirancang sebagai Co-Pilot lintas layer untuk mempercepat analisis akar masalah dan memitigasi downtime pada infrastruktur Platform Bigdata:',
        body_style
    ))
    story.append(Spacer(1, 1.5*mm))

    infra_map = [
        [Paragraph('Layer Infrastruktur', cell_header), Paragraph('Spesifikasi Platform Bigdata', cell_header), Paragraph('Peran & Integrasi Monitoring Agent', cell_header)],
        [Paragraph('HA Ingress & VIP', cell_bold), Paragraph('HAProxy & Keepalived VIP (10.206.24.12/13) loadbalancing Nginx Ingress.', cell_style), Paragraph('Memeriksa kesehatan endpoint stats HAProxy dan mendeteksi failover VIP.', cell_style)],
        [Paragraph('Kubernetes Cluster', cell_bold), Paragraph('K8s v1.26.5: 3 Master, 15 Worker, 6 Data-Lake Nodes managed by Rancher.', cell_style), Paragraph('Menerima alert Prometheus Alertmanager, query status pod CrashLoop & OOM.', cell_style)],
        [Paragraph('Distributed Storage', cell_bold), Paragraph('Longhorn v1.10.1 (3 replika block storage) + MinIO Object Storage + NFS.', cell_style), Paragraph('Mendiagnosa integritas replika volume Longhorn dan latency storage pool.', cell_style)],
        [Paragraph('Compute & GPU Nodes', cell_bold), Paragraph('Barebone server PH201-GA + 2x NVIDIA RTX A6000 GPU (AI/ML Workload).', cell_style), Paragraph('Memantau utilisasi VRAM GPU, driver status, dan beban compute node.', cell_style)],
        [Paragraph('Network & IPMI', cell_bold), Paragraph('IPMI/BMC segmen 10.206.31.0/24 dan Data Floating 10.206.24.0/22.', cell_style), Paragraph('Mengeksekusi diagnosa konektivitas out-of-band dan link status switch 100G.', cell_style)],
        [Paragraph('AIOps & ChatOps', cell_bold), Paragraph('Prometheus Alertmanager Webhook + Telegram Bot (@hlm_alert_bot).', cell_style), Paragraph('Pengiriman kartu alert real-time ke HP engineer + tombol aksi interaktif & PDF.', cell_style)]
    ]
    t_infra = Table(infra_map, colWidths=[31*mm, 67*mm, 72*mm])
    t_infra.setStyle(TableStyle([
        ('LINEABOVE', (0,0), (-1,0), 2, colors.HexColor('#F97316')),
        ('BACKGROUND', (0,0), (-1,0), C_HEADER_BG),
        ('LINEBELOW', (0,0), (-1,0), 1, colors.HexColor('#9A3412')),
        ('GRID', (0,0), (-1,-1), 0.5, C_BORDER),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, C_ROW_ALT]),
        ('TOPPADDING', (0,0), (-1,-1), 2.2),
        ('BOTTOMPADDING', (0,0), (-1,-1), 2.2),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))
    story.append(t_infra)
    story.append(Spacer(1, 3.5*mm))

    story.append(Paragraph('<font color="#EA580C"><b>▌ 4.</b></font> <b>Panduan Eksekusi CLI, Docker &amp; Kubernetes Deployment</b>', h1_style))
    story.append(Spacer(1, 1*mm))

    cli_data = [
        [Paragraph('Kebutuhan Operasional', cell_header), Paragraph('Perintah CLI / Sintaks Deployment', cell_header)],
        [Paragraph('Pemeriksaan snapshot status server satu kali', cell_style), Paragraph('python src/main.py --config config/config.yaml --once', cell_bold)],
        [Paragraph('Mode Hibrida (Webhook Ingress aktif + Polling berkala)', cell_style), Paragraph('python src/main.py --config config/config.yaml --webhook --loop', cell_bold)],
        [Paragraph('Simulasi Alert Prometheus (K8s CrashLoopBackOff)', cell_style), Paragraph('python scripts/simulate_prometheus_alert.py --scenario crashloop', cell_bold)],
        [Paragraph('Simulasi Alert Prometheus (Longhorn Volume Degraded)', cell_style), Paragraph('python scripts/simulate_prometheus_alert.py --scenario storage', cell_bold)],
        [Paragraph('Test Kirim Alert & PDF ke Telegram HP', cell_style), Paragraph('python scripts/test_telegram_bot.py --token <TOKEN> --chat-id <ID>', cell_bold)],
        [Paragraph('Generate Laporan Mingguan / Bulanan (Executive)', cell_style), Paragraph('python src/main.py --config config/config.yaml --report-period [weekly|monthly]', cell_bold)],
        [Paragraph('Build Image Container (Harbor / Internal Registry)', cell_style), Paragraph('docker build -t harbor.internal/bigdata/monitoring-agent:v1.0.0 .', cell_style)],
        [Paragraph('Deploy ke Kluster Kubernetes (K8s Ready)', cell_style), Paragraph('kubectl apply -f deploy/k8s/', cell_bold)],
        [Paragraph('Cron Job Linux (Weekly: Setiap Senin 08:00)', cell_style), Paragraph('0 8 * * 1 cd /app && python3 src/main.py --report-period weekly', cell_style)],
        [Paragraph('Cron Job Linux (Monthly: Setiap Tgl 1 07:00)', cell_style), Paragraph('0 7 1 * * cd /app && python3 src/main.py --report-period monthly', cell_style)],
    ]
    t_cli = Table(cli_data, colWidths=[65*mm, 105*mm])
    t_cli.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), C_HEADER_BG),
        ('LINEABOVE', (0,0), (-1,0), 2, colors.HexColor('#F97316')),
        ('LINEBELOW', (0,0), (-1,0), 1, colors.HexColor('#9A3412')),
        ('GRID', (0,0), (-1,-1), 0.5, C_BORDER),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, C_ROW_ALT]),
        ('TOPPADDING', (0,0), (-1,-1), 2),
        ('BOTTOMPADDING', (0,0), (-1,-1), 2),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))
    story.append(t_cli)

    doc.build(story, canvasmaker=NumberedCanvas)
    print('PDF successfully generated:', output_pdf)

if __name__ == '__main__':
    build_pdf()

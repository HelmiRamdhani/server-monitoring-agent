"""
PDF report generator module.
Creates a professional PDF report using ReportLab containing:
- Header with timestamp and server info
- Server metrics table
- Threshold alerts table
- Incident summary from syslog parsing
- Detailed incident list (top 10 critical)
- Footer with page numbers
"""

import os
import time
from datetime import datetime
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.platypus import (
    SimpleDocTemplate,
    Table,
    TableStyle,
    Paragraph,
    Spacer,
    PageBreak,
    Image as RLImage,
)
from reportlab.platypus.frames import Frame
from reportlab.platypus.doctemplate import PageTemplate, BaseDocTemplate

import logging

log = logging.getLogger("agent.report")

# Color scheme
COLOR_HEADER = colors.HexColor("#1a1a2e")
COLOR_ACCENT = colors.HexColor("#0F6E56")
COLOR_WARN = colors.HexColor("#EF9F27")
COLOR_CRIT = colors.HexColor("#A32D2D")
COLOR_LIGHT = colors.HexColor("#F1EFE8")
COLOR_BORDER = colors.HexColor("#D3D1C7")


def _severity_color(severity: str) -> colors.Color:
    """Map severity string to a reportlab color."""
    mapping = {
        "critical": COLOR_CRIT,
        "error": COLOR_CRIT,
        "warning": COLOR_WARN,
        "info": COLOR_ACCENT,
    }
    return mapping.get(severity.lower(), COLOR_BORDER)


def _build_styles() -> dict:
    """Create paragraph styles for the report."""
    styles = getSampleStyleSheet()

    styles.add(ParagraphStyle(
        name="ReportTitle",
        parent=styles["Title"],
        fontSize=20,
        textColor=COLOR_HEADER,
        spaceAfter=4,
        alignment=TA_CENTER,
    ))

    styles.add(ParagraphStyle(
        name="ReportSubtitle",
        parent=styles["Normal"],
        fontSize=11,
        textColor=colors.HexColor("#5F5E5A"),
        alignment=TA_CENTER,
        spaceAfter=20,
    ))

    styles.add(ParagraphStyle(
        name="SectionHeader",
        parent=styles["Heading2"],
        fontSize=13,
        textColor=COLOR_ACCENT,
        spaceBefore=14,
        spaceAfter=8,
    ))

    styles.add(ParagraphStyle(
        name="CellText",
        parent=styles["Normal"],
        fontSize=9,
        leading=12,
    ))

    styles.add(ParagraphStyle(
        name="CellTextSmall",
        parent=styles["Normal"],
        fontSize=8,
        leading=10,
    ))

    return styles


def _footer(canvas, doc):
    """Draw footer with page number and timestamp."""
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#888780"))

    page_num = canvas.getPageNumber()
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    footer_text = f"Platform Bigdata — Server Monitoring Agent & Incident Co-Pilot | Generated: {ts} | Page {page_num}"
    canvas.drawCentredString(A4[0] / 2, 15 * mm, footer_text)

    # Line above footer
    canvas.setStrokeColor(COLOR_BORDER)
    canvas.setLineWidth(0.5)
    canvas.line(20 * mm, 20 * mm, A4[0] - 20 * mm, 20 * mm)

    canvas.restoreState()


def generate_report(
    metrics: dict,
    threshold_alerts: list,
    incidents: list,
    incident_summary: dict,
    config: Any,
    diagnosis_results: list = None,
    diagnosis_summary: dict = None,
    kb_match: dict = None,
) -> str:
    """
    Generate a PDF report from monitoring data.

    Args:
        metrics: dict from server_monitor.collect_metrics()
        threshold_alerts: list from server_monitor.check_thresholds()
        incidents: list from syslog_parser.parse_syslog()
        incident_summary: dict from syslog_parser.summarize_incidents()
        config: Config object
        diagnosis_results: list of diagnosis check results (optional, for event-driven mode)
        diagnosis_summary: dict summary of diagnosis checks (optional)
        kb_match: dict with matched SOPs and similar incidents (optional)

    Returns:
        Path to the generated PDF file.
    """
    report_cfg = config.get("report")
    output_dir = report_cfg.get("output_dir", "output") if report_cfg else "output"
    filename_pattern = report_cfg.get("filename_pattern", "report_%Y%m%d_%H%M%S.pdf") if report_cfg else "report_%Y%m%d_%H%M%S.pdf"
    team_name = report_cfg.get("team_name", "Tim Operasional") if report_cfg else "Tim Operasional"

    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)

    filename = time.strftime(filename_pattern)
    filepath = os.path.join(output_dir, filename)

    log.info("Generating PDF report: %s", filepath)

    styles = _build_styles()
    doc = SimpleDocTemplate(
        filepath,
        pagesize=A4,
        topMargin=25 * mm,
        bottomMargin=25 * mm,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
    )

    story = []

    # --- Title ---
    story.append(Paragraph("Server Monitoring Report", styles["ReportTitle"]))
    story.append(Paragraph(
        f"{team_name} | {datetime.now().strftime('%d %B %Y, %H:%M:%S')}",
        styles["ReportSubtitle"],
    ))
    story.append(Spacer(1, 6))

    # --- Server info table ---
    story.append(Paragraph("Informasi Server", styles["SectionHeader"]))

    server_info_data = [
        ["Hostname", metrics.get("hostname", "N/A")],
        ["OS", f"{metrics.get('os', 'N/A')} {metrics.get('os_version', '')[:40]}"],
        ["Uptime", metrics.get("uptime_human", "N/A")],
        ["CPU cores", str(metrics.get("cpu_count", "N/A"))],
        ["Memory total", f"{metrics.get('memory_total_gb', 'N/A')} GB"],
        ["Disk total", f"{metrics.get('disk_total_gb', 'N/A')} GB"],
        ["Load avg", str(metrics.get("load_avg", "N/A"))],
    ]

    t = Table(server_info_data, colWidths=[50 * mm, 120 * mm])
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (0, -1), COLOR_HEADER),
        ("BACKGROUND", (0, 0), (0, -1), COLOR_LIGHT),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(t)
    story.append(Spacer(1, 10))

    # --- Metrics table ---
    story.append(Paragraph("Metrik Server", styles["SectionHeader"]))

    metrics_data = [
        ["Metric", "Current", "Warning", "Critical", "Status"],
    ]

    thresholds = config.get("thresholds")

    metric_rows = [
        ("CPU Usage", f"{metrics.get('cpu_percent', 0)}%",
         f"{thresholds.cpu_warning}%", f"{thresholds.cpu_critical}%",
         metrics.get("cpu_percent", 0)),
        ("Memory Usage", f"{metrics.get('memory_percent', 0)}%",
         f"{thresholds.memory_warning}%", f"{thresholds.memory_critical}%",
         metrics.get("memory_percent", 0)),
        ("Disk Usage", f"{metrics.get('disk_percent', 0)}%",
         f"{thresholds.disk_warning}%", f"{thresholds.disk_critical}%",
         metrics.get("disk_percent", 0)),
    ]

    for label, current, warn, crit, value in metric_rows:
        if isinstance(value, (int, float)):
            if value >= float(crit.replace("%", "")):
                status = "CRITICAL"
                status_color = COLOR_CRIT
            elif value >= float(warn.replace("%", "")):
                status = "WARNING"
                status_color = COLOR_WARN
            else:
                status = "OK"
                status_color = COLOR_ACCENT
        else:
            status = "N/A"
            status_color = COLOR_BORDER

        metrics_data.append([label, current, warn, crit, status])

    t2 = Table(metrics_data, colWidths=[40 * mm, 35 * mm, 30 * mm, 30 * mm, 35 * mm])
    t2.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BACKGROUND", (0, 0), (-1, 0), COLOR_HEADER),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        # Color the status column per row
        ("TEXTCOLOR", (4, 1), (4, 1), COLOR_ACCENT),
        ("TEXTCOLOR", (4, 2), (4, 2), COLOR_ACCENT),
        ("TEXTCOLOR", (4, 3), (4, 3), COLOR_ACCENT),
        ("FONTNAME", (4, 1), (4, -1), "Helvetica-Bold"),
    ]))

    # Adjust status colors based on actual values
    for i, row in enumerate(metric_rows, start=1):
        value = row[4]
        if isinstance(value, (int, float)):
            if value >= float(row[3].replace("%", "")):
                t2.setStyle(TableStyle([("TEXTCOLOR", (4, i), (4, i), COLOR_CRIT)]))
            elif value >= float(row[2].replace("%", "")):
                t2.setStyle(TableStyle([("TEXTCOLOR", (4, i), (4, i), COLOR_WARN)]))

    story.append(t2)
    story.append(Spacer(1, 10))

    # --- Threshold alerts ---
    story.append(Paragraph("Alert Threshold", styles["SectionHeader"]))

    if threshold_alerts:
        alert_data = [["Severity", "Metric", "Value", "Message"]]
        for a in threshold_alerts:
            alert_data.append([
                a["severity"].upper(),
                a["metric"],
                str(a["value"]),
                Paragraph(a["message"], styles["CellTextSmall"]),
            ])

        t3 = Table(alert_data, colWidths=[25 * mm, 30 * mm, 30 * mm, 85 * mm])
        style_cmds = [
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BACKGROUND", (0, 0), (-1, 0), COLOR_HEADER),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("GRID", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]
        for i, a in enumerate(threshold_alerts, start=1):
            style_cmds.append(("TEXTCOLOR", (0, i), (0, i), _severity_color(a["severity"])))
            style_cmds.append(("FONTNAME", (0, i), (0, i), "Helvetica-Bold"))

        t3.setStyle(TableStyle(style_cmds))
        story.append(t3)
    else:
        story.append(Paragraph("Tidak ada alert. Semua metrik dalam batas normal.", styles["CellText"]))

    story.append(Spacer(1, 10))

    # --- Incident summary ---
    story.append(Paragraph("Ringkasan Insiden (dari Syslog)", styles["SectionHeader"]))

    if incident_summary["total"] > 0:
        summary_data = [
            ["Total insiden", str(incident_summary["total"])],
        ]
        for sev, count in incident_summary["by_severity"].items():
            summary_data.append([f"  {sev.upper()}", str(count)])

        t4 = Table(summary_data, colWidths=[60 * mm, 30 * mm])
        t4.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("BACKGROUND", (0, 0), (0, -1), COLOR_LIGHT),
        ]))
        story.append(t4)
        story.append(Spacer(1, 8))

        # Incidents by pattern
        story.append(Paragraph("Insiden per Kategori:", styles["CellText"]))
        pattern_data = [["Pattern", "Jumlah"]]
        for name, count in sorted(incident_summary["by_pattern"].items(), key=lambda x: x[1], reverse=True):
            pattern_data.append([name, str(count)])

        t5 = Table(pattern_data, colWidths=[100 * mm, 30 * mm])
        t5.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BACKGROUND", (0, 0), (-1, 0), COLOR_HEADER),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ALIGN", (1, 0), (1, -1), "CENTER"),
            ("GRID", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(t5)
        story.append(Spacer(1, 8))

        # Top critical incidents detail
        top = incident_summary.get("top_incidents", [])
        if top:
            story.append(PageBreak())
            story.append(Paragraph("Detail Insiden Kritis (Top 10)", styles["SectionHeader"]))

            detail_data = [["Timestamp", "Pattern", "Log Line"]]
            for inc in top:
                detail_data.append([
                    Paragraph(inc.get("timestamp_raw", "N/A"), styles["CellTextSmall"]),
                    Paragraph(inc.get("pattern_name", ""), styles["CellTextSmall"]),
                    Paragraph(inc.get("matched_line", "")[:200], styles["CellTextSmall"]),
                ])

            t6 = Table(detail_data, colWidths=[35 * mm, 35 * mm, 100 * mm])
            t6.setStyle(TableStyle([
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("BACKGROUND", (0, 0), (-1, 0), COLOR_HEADER),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("GRID", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]))
            story.append(t6)
    else:
        story.append(Paragraph("Tidak ada insiden terdeteksi dari syslog.", styles["CellText"]))

    # --- Diagnosis results (event-driven mode) ---
    if diagnosis_results:
        story.append(PageBreak())

        # --- AI & Heuristic Root Cause Analysis (RCA) Callout Box ---
        try:
            try:
                from modules.ai_rca_engine import AIRootCauseEngine
            except ImportError:
                from src.modules.ai_rca_engine import AIRootCauseEngine

            rca_engine = AIRootCauseEngine(config)
            incident_ctx = incidents[0] if incidents else {}
            ctx_for_rca = {
                "server": incident_ctx.get("server", metrics.get("hostname", "cluster")),
                "patterns": [incident_ctx.get("pattern_name")] if incident_ctx.get("pattern_name") else [],
                "text": incident_ctx.get("matched_line", ""),
                "severity": incident_ctx.get("severity", "warning"),
            }
            rca_data = rca_engine.synthesize_rca(
                incident_context=ctx_for_rca,
                diagnosis_results=diagnosis_results,
                kb_match=kb_match,
                metrics=metrics,
            )

            rca_table_data = [
                [Paragraph(f"<b>Analisis Akar Masalah Cerdas (AI RCA)</b> &nbsp; [Confidence: <b>{rca_data['confidence']}</b>]", styles["SectionHeader"])],
                [Paragraph(f"<b>Ringkasan:</b> {rca_data['executive_summary']}", styles["CellText"])],
                [Paragraph(f"<b>Kemungkinan Akar Masalah:</b> {rca_data['probable_root_cause']}", styles["CellText"])],
                [Paragraph(f"<b>Dampak Insiden:</b> {rca_data['immediate_impact']}", styles["CellText"])],
            ]
            actions_text = "<br/>".join([f"• {act}" for act in rca_data["recommended_actions"]])
            rca_table_data.append([Paragraph(f"<b>Rekomendasi Tindakan Cepat:</b><br/>{actions_text}", styles["CellText"])])

            t_rca = Table(rca_table_data, colWidths=[170 * mm])
            t_rca.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
                ("LINEBEFORE", (0, 0), (0, -1), 3, COLOR_ACCENT),
                ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ]))
            story.append(t_rca)
            story.append(Spacer(1, 10))
        except Exception as e:
            log.warning("Could not append AI RCA to report: %s", e)

        story.append(Paragraph("Hasil Diagnosis Otomatis", styles["SectionHeader"]))

        if diagnosis_summary:
            diag_summary_data = [
                ["Total checks", str(diagnosis_summary.get("total_checks", 0))],
            ]
            for status, count in diagnosis_summary.get("by_status", {}).items():
                diag_summary_data.append([f"  {status.upper()}", str(count)])

            t_ds = Table(diag_summary_data, colWidths=[60 * mm, 30 * mm])
            t_ds.setStyle(TableStyle([
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("GRID", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("BACKGROUND", (0, 0), (0, -1), COLOR_LIGHT),
            ]))
            story.append(t_ds)
            story.append(Spacer(1, 8))

        # Detailed diagnosis table
        diag_data = [["Check", "Type", "Status", "Output"]]
        for r in diagnosis_results:
            status_text = r.get("status", "info").upper()
            output_text = r.get("output", "")[:150]
            diag_data.append([
                Paragraph(r.get("check_name", ""), styles["CellTextSmall"]),
                r.get("check_type", ""),
                status_text,
                Paragraph(output_text, styles["CellTextSmall"]),
            ])

        t_diag = Table(diag_data, colWidths=[35 * mm, 25 * mm, 20 * mm, 90 * mm])
        diag_style_cmds = [
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("BACKGROUND", (0, 0), (-1, 0), COLOR_HEADER),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("GRID", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]
        # Color status cells
        for i, r in enumerate(diagnosis_results, start=1):
            s = r.get("status", "info")
            if s == "critical":
                diag_style_cmds.append(("TEXTCOLOR", (2, i), (2, i), COLOR_CRIT))
                diag_style_cmds.append(("FONTNAME", (2, i), (2, i), "Helvetica-Bold"))
            elif s == "warning":
                diag_style_cmds.append(("TEXTCOLOR", (2, i), (2, i), COLOR_WARN))
                diag_style_cmds.append(("FONTNAME", (2, i), (2, i), "Helvetica-Bold"))
            elif s == "ok":
                diag_style_cmds.append(("TEXTCOLOR", (2, i), (2, i), COLOR_ACCENT))

        t_diag.setStyle(TableStyle(diag_style_cmds))
        story.append(t_diag)

    # --- KB / SOP recommendations ---
    if kb_match:
        matched_sops = kb_match.get("matched_sops", [])
        similar_incidents = kb_match.get("similar_incidents", [])

        if matched_sops or similar_incidents:
            story.append(Spacer(1, 10))
            story.append(Paragraph("Rekomendasi dari Knowledge Base", styles["SectionHeader"]))

        if matched_sops:
            story.append(Paragraph("SOP yang Relevan:", styles["CellText"]))
            sop_data = [["SOP ID", "Judul", "Severity", "Skor"]]
            for sop in matched_sops[:5]:
                sop_data.append([
                    sop.get("id", ""),
                    Paragraph(sop.get("title", ""), styles["CellTextSmall"]),
                    sop.get("severity", ""),
                    str(sop.get("relevance_score", 0)),
                ])
            t_sop = Table(sop_data, colWidths=[35 * mm, 75 * mm, 25 * mm, 20 * mm])
            t_sop.setStyle(TableStyle([
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("BACKGROUND", (0, 0), (-1, 0), COLOR_ACCENT),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("GRID", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]))
            story.append(t_sop)
            story.append(Spacer(1, 6))

        if similar_incidents:
            story.append(Paragraph("Insiden Serupa di Masa Lalu:", styles["CellText"]))
            inc_data = [["ID", "Judul", "Resolusi"]]
            for inc in similar_incidents[:3]:
                inc_data.append([
                    inc.get("incident_id", ""),
                    Paragraph(inc.get("title", ""), styles["CellTextSmall"]),
                    Paragraph(inc.get("resolution", "")[:200], styles["CellTextSmall"]),
                ])
            t_inc = Table(inc_data, colWidths=[30 * mm, 55 * mm, 85 * mm])
            t_inc.setStyle(TableStyle([
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("BACKGROUND", (0, 0), (-1, 0), COLOR_ACCENT),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("GRID", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]))
            story.append(t_inc)

    # Build PDF
    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)

    log.info("Report generated successfully: %s", filepath)
    return filepath


def generate_periodic_report(
    period: str,
    metrics: dict,
    analytics: dict,
    config: Any,
) -> str:
    """
    Generate an executive periodic PDF report (Weekly or Monthly).

    Args:
        period: "weekly" or "monthly"
        metrics: current server metrics from server_monitor.collect_metrics()
        analytics: incident analytics from knowledge_base.get_incident_analytics()
        config: Config object

    Returns:
        Path to the generated PDF report
    """
    report_cfg = config.get("report")
    output_dir = report_cfg.get("output_dir", "output") if report_cfg else "output"
    team_name = report_cfg.get("team_name", "Tim Operasional") if report_cfg else "Tim Operasional"

    os.makedirs(output_dir, exist_ok=True)

    period_label = "Weekly" if period.lower() == "weekly" else "Monthly"
    period_title = f"{period_label} Executive IT Health Report"
    days = analytics.get("period_days", 7 if period.lower() == "weekly" else 30)

    filename = f"report_{period.lower()}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    filepath = os.path.join(output_dir, filename)

    log.info("Generating %s report: %s", period_label, filepath)

    styles = _build_styles()
    doc = SimpleDocTemplate(
        filepath,
        pagesize=A4,
        topMargin=25 * mm,
        bottomMargin=25 * mm,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
    )

    story = []

    # --- Title Banner ---
    story.append(Paragraph(period_title, styles["ReportTitle"]))
    date_str = datetime.now().strftime("%d %B %Y")
    cutoff_str = analytics.get("cutoff_date", "")
    story.append(Paragraph(
        f"{team_name} | Periode: {cutoff_str} s/d {date_str} ({days} Hari)",
        styles["ReportSubtitle"],
    ))
    story.append(Spacer(1, 4))

    # --- Section 1: Executive KPI Summary ---
    story.append(Paragraph("Ringkasan Eksekutif & KPI", styles["SectionHeader"]))

    total_inc = analytics.get("total_incidents", 0)
    by_sev = analytics.get("by_severity", {})
    crit_count = by_sev.get("critical", 0)
    warn_count = by_sev.get("warning", 0)
    status_counts = analytics.get("status_counts", {})
    resolved_count = status_counts.get("resolved", 0)
    resolution_rate = f"{(resolved_count / total_inc * 100):.1f}%" if total_inc > 0 else "100%"

    kpi_data = [
        ["Indikator", "Nilai", "Target / Baseline", "Status"],
        ["Total Insiden", str(total_inc), f"< {10 if days == 7 else 30}", "MONITORED"],
        ["Insiden Critical", str(crit_count), "0", "ALERT" if crit_count > 0 else "OK"],
        ["Insiden Warning", str(warn_count), f"< {5 if days == 7 else 15}", "WARNING" if warn_count > 5 else "OK"],
        ["Tingkat Resolusi", resolution_rate, "> 90%", "OK" if resolved_count >= total_inc * 0.9 else "REVIEW"],
        ["CPU Server (Saat Ini)", f"{metrics.get('cpu_percent', 0)}%", "< 75%", "OK" if metrics.get('cpu_percent', 0) < 75 else "HIGH"],
        ["Memori Server (Saat Ini)", f"{metrics.get('memory_percent', 0)}%", "< 80%", "OK" if metrics.get('memory_percent', 0) < 80 else "HIGH"],
        ["Uptime Server", metrics.get("uptime_human", "N/A"), "> 99.5%", "OK"],
    ]

    t_kpi = Table(kpi_data, colWidths=[50 * mm, 35 * mm, 45 * mm, 40 * mm])
    t_kpi_style = [
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BACKGROUND", (0, 0), (-1, 0), COLOR_HEADER),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]

    # Color status cells
    for i in range(1, len(kpi_data)):
        status_val = kpi_data[i][3]
        col = COLOR_ACCENT if status_val == "OK" else COLOR_CRIT if status_val == "ALERT" else COLOR_WARN
        t_kpi_style.append(("TEXTCOLOR", (3, i), (3, i), col))
        t_kpi_style.append(("FONTNAME", (3, i), (3, i), "Helvetica-Bold"))

    t_kpi.setStyle(TableStyle(t_kpi_style))
    story.append(t_kpi)
    story.append(Spacer(1, 10))

    # --- Section 2: Distribusi Insiden per Server & Root Causes ---
    story.append(Paragraph("Analisis Distribusi Insiden", styles["SectionHeader"]))

    by_server = analytics.get("by_server", {})
    if by_server:
        server_table_data = [["Server", "Jumlah Insiden", "Kontribusi (%)"]]
        for srv, count in sorted(by_server.items(), key=lambda x: x[1], reverse=True):
            pct = f"{(count / total_inc * 100):.1f}%" if total_inc > 0 else "0%"
            server_table_data.append([srv, str(count), pct])

        t_srv = Table(server_table_data, colWidths=[70 * mm, 40 * mm, 60 * mm])
        t_srv.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BACKGROUND", (0, 0), (-1, 0), COLOR_HEADER),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ALIGN", (1, 0), (-1, -1), "CENTER"),
            ("GRID", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(t_srv)
        story.append(Spacer(1, 8))

    # Top Root Causes
    top_rc = analytics.get("top_root_causes", [])
    if top_rc:
        story.append(Paragraph("Akar Masalah Terbanyak (Top Recurring Root Causes):", styles["CellText"]))
        rc_table_data = [["Akar Masalah (Root Cause)", "Frekuensi"]]
        for cause, count in top_rc:
            rc_table_data.append([Paragraph(cause, styles["CellTextSmall"]), str(count)])

        t_rc = Table(rc_table_data, colWidths=[130 * mm, 40 * mm])
        t_rc.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BACKGROUND", (0, 0), (-1, 0), COLOR_LIGHT),
            ("TEXTCOLOR", (0, 0), (0, -1), COLOR_HEADER),
            ("ALIGN", (1, 0), (1, -1), "CENTER"),
            ("GRID", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(t_rc)
        story.append(Spacer(1, 8))

    # Top SOPs Used
    top_sops = analytics.get("top_sops_used", [])
    if top_sops:
        story.append(Paragraph("SOP yang Paling Sering Diaplikasikan:", styles["CellText"]))
        sop_table_data = [["SOP ID", "Kali Digunakan"]]
        for sop, count in top_sops:
            sop_table_data.append([sop, str(count)])

        t_sop = Table(sop_table_data, colWidths=[110 * mm, 60 * mm])
        t_sop.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BACKGROUND", (0, 0), (-1, 0), COLOR_LIGHT),
            ("TEXTCOLOR", (0, 0), (0, -1), COLOR_HEADER),
            ("ALIGN", (1, 0), (1, -1), "CENTER"),
            ("GRID", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(t_sop)

    # --- Section 3: Detail Insiden Periode (Page 2) ---
    incidents = analytics.get("incidents", [])
    if incidents:
        story.append(PageBreak())
        story.append(Paragraph(f"Daftar Insiden Terpilih (Periode {period_label})", styles["SectionHeader"]))

        inc_table_data = [["ID", "Tanggal", "Server", "Severity", "Judul / Ringkasan"]]
        for inc in incidents[:15]:
            inc_table_data.append([
                inc.get("incident_id", "N/A"),
                inc.get("date", "N/A"),
                inc.get("server", "N/A"),
                inc.get("severity", "warning").upper(),
                Paragraph(inc.get("title", ""), styles["CellTextSmall"]),
            ])

        t_inc_detail = Table(inc_table_data, colWidths=[35 * mm, 25 * mm, 25 * mm, 25 * mm, 60 * mm])
        inc_style = [
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("BACKGROUND", (0, 0), (-1, 0), COLOR_HEADER),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("GRID", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]
        for i, inc in enumerate(incidents[:15], start=1):
            sev_str = inc.get("severity", "warning").lower()
            inc_style.append(("TEXTCOLOR", (3, i), (3, i), _severity_color(sev_str)))
            inc_style.append(("FONTNAME", (3, i), (3, i), "Helvetica-Bold"))

        t_inc_detail.setStyle(TableStyle(inc_style))
        story.append(t_inc_detail)

    # --- Section 4: Rekomendasi & Tindak Lanjut Tim ---
    story.append(Spacer(1, 10))
    story.append(Paragraph("Rekomendasi Tindak Lanjut Operasional", styles["SectionHeader"]))

    recommendations = [
        "1. Lakukan audit pada server dengan frekuensi insiden tertinggi.",
        "2. Perbarui konfigurasi batas memori / resource limit pada layanan yang sering mengalami OOM.",
        "3. Tinjau dan perbarui SOP jika terdapat insiden berulang dengan waktu resolusi melebihi SLA.",
        "4. Pastikan rotasi log berjalan untuk mencegah partisi disk penuh.",
    ]
    for rec in recommendations:
        story.append(Paragraph(rec, styles["CellText"]))

    # Build PDF
    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)

    log.info("%s report generated successfully: %s", period_label, filepath)
    return filepath

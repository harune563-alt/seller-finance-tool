from io import BytesIO
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter


def safe(value):
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def build_current_workbook(report, person_name, currency, start_date, end_date):
    wb = Workbook()
    summary = wb.active
    summary.title = "Cari Özet"
    summary_rows = [
        ["Cari", person_name or "Tüm cariler"],
        ["Para birimi", currency or "Tümü"],
        ["Başlangıç", start_date or "Tümü"],
        ["Bitiş", end_date or "Tümü"],
        ["Toplam borç", report["totals"]["total_payable"]],
        ["Toplam alacak", report["totals"]["total_receivable"]],
        ["Net bakiye", report["totals"]["net_balance"]],
    ]
    for row in summary_rows:
        summary.append([safe(value) for value in row])
    summary["A1"].font = Font(bold=True)
    summary.column_dimensions["A"].width = 24
    summary.column_dimensions["B"].width = 30
    ws = wb.create_sheet("Cari Ekstre")
    headers = ["Tarih", "Cari", "Hareket", "Tutar", "Bakiye Sonrası", "Kasa Etkisi", "Durum", "Vade", "Vade Durumu", "Mağaza", "Not", "Kayıt ID"]
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="047857")
        cell.alignment = Alignment(wrap_text=True)
    for row in report["rows"]:
        ws.append([safe(value) for value in [
            row["date"], row["person_name"], "Borç" if row["direction"] == "payable" else "Alacak",
            row["amount"], row["balance_after"], {"none": "Kasa etkisi yok", "in": "Kasaya giriş", "out": "Kasadan çıkış"}[row["cash_effect"]],
            "Gerçekleşti" if row["cash_status"] == "completed" else "Bekliyor", row.get("due_date") or "", row.get("due_status", ""),
            row.get("store_name") or "Şirket geneli", row.get("note") or "", row["id"],
        ]])
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    for index, header in enumerate(headers, 1):
        ws.column_dimensions[get_column_letter(index)].width = min(38, max(14, len(header) + 3))
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            if isinstance(cell.value, (int, float)):
                cell.number_format = "#,##0.00;[Red]-#,##0.00"
    output = BytesIO()
    wb.save(output)
    return output.getvalue()


def _register_font():
    path = "/usr/share/fonts/truetype/freefont/FreeSans.ttf"
    try:
        pdfmetrics.getFont("DejaVuSans")
    except KeyError:
        pdfmetrics.registerFont(TTFont("DejaVuSans", path))
    return "DejaVuSans"


def build_current_pdf(report, person_name, currency, start_date, end_date):
    font = _register_font()
    output = BytesIO()
    document = canvas.Canvas(output, pagesize=landscape(A4))
    width, height = landscape(A4)
    margin = 32
    y = height - margin
    document.setFont(font, 16)
    document.drawString(margin, y, "Cari Hesap Ekstresi")
    y -= 24
    document.setFont(font, 9)
    document.drawString(margin, y, f"Cari: {person_name or 'Tüm cariler'}   Döviz: {currency or 'Tümü'}   Tarih: {start_date or '—'} - {end_date or '—'}")
    y -= 18
    document.drawString(margin, y, f"Toplam borç: {report['totals']['total_payable']:.2f}   Toplam alacak: {report['totals']['total_receivable']:.2f}   Net bakiye: {report['totals']['net_balance']:.2f}")
    y -= 22
    headers = ["Tarih", "Cari", "Tür", "Tutar", "Bakiye", "Kasa", "Durum", "Vade", "Vade durumu"]
    widths = [62, 115, 52, 65, 65, 85, 65, 65, 85]
    document.setFont(font, 8)
    def draw_header(current_y):
        x = margin
        document.setFillColorRGB(0.02, 0.47, 0.30)
        document.rect(margin, current_y - 4, sum(widths), 16, fill=1, stroke=0)
        document.setFillColorRGB(1, 1, 1)
        for header, cell_width in zip(headers, widths):
            document.drawString(x + 3, current_y, header)
            x += cell_width
        document.setFillColorRGB(0, 0, 0)
        return current_y - 20
    y = draw_header(y)
    for row in report["rows"]:
        if y < margin + 28:
            document.showPage()
            y = height - margin
            document.setFont(font, 8)
            y = draw_header(y)
        values = [row["date"], row["person_name"], "Borç" if row["direction"] == "payable" else "Alacak", f'{row["amount"]:.2f} {row["currency"]}', f'{row["balance_after"]:.2f}', {"none": "Yok", "in": "Giriş", "out": "Çıkış"}[row["cash_effect"]], "Gerçekleşti" if row["cash_status"] == "completed" else "Bekliyor", row.get("due_date") or "—", row.get("due_status", "—")]
        x = margin
        for value, cell_width in zip(values, widths):
            text = str(value)
            if len(text) > 18:
                text = text[:17] + "…"
            document.setFillColorRGB(0, 0, 0)
            document.drawString(x + 3, y, text)
            x += cell_width
        y -= 17
    document.save()
    return output.getvalue()

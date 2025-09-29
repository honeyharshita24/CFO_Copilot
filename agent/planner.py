from __future__ import annotations

import io

import streamlit as st
from agent.tools import FinanceData, respond, revenue_vs_budget_usd, opex_breakdown_usd, cash_runway_now, plot_revenue_vs_budget_bar, plot_opex_breakdown_bar, plot_cash_trend
import matplotlib.pyplot as plt
from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

def generate_pdf(fin: FinanceData, out_path: str = "export.pdf", answer_text: str | None = None, answer_img_bytes: bytes | None = None) -> str:
    """Generate a tiny PDF with a couple of KPIs and charts.

    If `answer_text` or `answer_img_bytes` are provided, include a page
    with the latest Q&A output (text and optional chart image).
    """
    # Choose latest month for point-in-time views
    latest = sorted(fin.actuals["month"].unique())[-1]
    rvb = revenue_vs_budget_usd(fin, latest)
    opex = opex_breakdown_usd(fin, latest)

    # Create charts to embed
    fig1 = plot_revenue_vs_budget_bar(rvb['actual_usd'], rvb['budget_usd'], title=f"Revenue vs Budget — {latest}")
    img1 = io.BytesIO()
    fig1.savefig(img1, format='png', bbox_inches='tight', dpi=180)
    plt.close(fig1)

    fig2 = plot_opex_breakdown_bar(opex, title=f"Opex Breakdown — {latest}")
    img2 = io.BytesIO()
    fig2.savefig(img2, format='png', bbox_inches='tight', dpi=180)
    plt.close(fig2)

    fig3 = plot_cash_trend(fin, months=6, title="Cash Trend — last 6 months")
    img3 = io.BytesIO()
    fig3.savefig(img3, format='png', bbox_inches='tight', dpi=180)
    plt.close(fig3)

    img1.seek(0); img2.seek(0); img3.seek(0)

    # Write PDF
    c = canvas.Canvas(out_path, pagesize=LETTER)
    width, height = LETTER

    # Page 1: Revenue vs Budget + Opex breakdown
    # c.setFont("Helvetica-Bold", 16)
    # c.drawString(40, height-40, "CFO Copilot — Snapshot")
    # c.setFont("Helvetica", 10)
    # c.drawString(40, height-60, f"As of {latest}")

    # # Revenue block
    # c.setFont("Helvetica-Bold", 12)
    # c.drawString(40, height-90, "Revenue vs Budget")
    # c.setFont("Helvetica", 10)
    # c.drawString(40, height-105, f"Actual: ${rvb['actual_usd']:,.0f} | Budget: ${rvb['budget_usd']:,.0f} | Var: ${rvb['variance_usd']:,.0f} ({rvb['variance_pct']*100:.1f}%)")
    # c.drawImage(ImageReader(img1), 40, height-500, width=220, preserveAspectRatio=True, mask='auto')

    # # Opex block
    # c.setFont("Helvetica-Bold", 12)
    # c.drawString(400, height-90, "Opex Breakdown")
    # c.drawImage(ImageReader(img2), 320, height-500, width=220, preserveAspectRatio=True, mask='auto')

    # c.showPage()

    # # Page 2: Cash trend
    # c.setFont("Helvetica-Bold", 16)
    # c.drawString(40, height-40, "Cash Trend")
    # c.drawImage(ImageReader(img3), 40, 320, width=540, preserveAspectRatio=True, mask='auto')

    # Optional Page 3: include latest Q&A (text + optional chart) so exported
    # PDF reflects the current output the user sees in the app.
    if answer_text or answer_img_bytes:
        # c.showPage()
        c.setFont("Helvetica-Bold", 16)
        c.drawString(40, height-40, "Latest Q&A")
        c.setFont("Helvetica", 10)

        # Wrap text reasonably for the PDF width
        import textwrap
        lines = []
        if answer_text:
            for raw_line in str(answer_text).splitlines():
                wrapped = textwrap.wrap(raw_line, width=90) or [raw_line]
                lines.extend(wrapped)

        text_obj = c.beginText(40, height-80)
        text_obj.setLeading(14)
        text_obj.setFont("Helvetica", 10)
        for ln in lines:
            text_obj.textLine(ln)
        c.drawText(text_obj)

        # If an image was provided (bytes), embed it below the text
        if answer_img_bytes:
            try:
                img_buf = io.BytesIO(answer_img_bytes)
                img_buf.seek(0)
                c.drawImage(ImageReader(img_buf), 40, 120, width=500, preserveAspectRatio=True, mask='auto')
            except Exception:
                # If embedding fails, continue without breaking PDF generation
                pass

    c.save()
    return out_path

def app_ui():
    st.set_page_config(page_title="Mini CFO Copilot", layout="wide")
    st.title("Mini CFO Copilot")
    st.caption("Ask finance questions in plain English. The agent interprets intent, runs data functions, and returns board‑ready answers + charts.")

    with st.sidebar:
        st.header("Settings")
        st.markdown("Sample questions:")
        st.code("""
What was June 2025 revenue vs budget in USD?
Show Gross Margin % trend for the last 3 months.
Break down Opex by category for June 2025.
What is our cash runway right now?
        """)
    export_pdf = st.button("Export PDF (2 pages)")

    fin = FinanceData.from_dir('fixtures')

    # Initialize session state for storing last Q&A so export can capture it
    if 'last_answer_text' not in st.session_state:
        st.session_state['last_answer_text'] = None
    if 'last_answer_img' not in st.session_state:
        st.session_state['last_answer_img'] = None

    if export_pdf:
        # Pass the most recent answer (if any) into the PDF generator so the
        # exported file reflects the current question/answer.
        path = generate_pdf(
            fin,
            out_path="export.pdf",
            answer_text=st.session_state.get('last_answer_text'),
            answer_img_bytes=st.session_state.get('last_answer_img'),
        )
        with open(path, "rb") as f:
            st.download_button("Download export.pdf", data=f, file_name="export.pdf", mime="application/pdf")

    q = st.text_input("Ask a question", value="What was June 2025 revenue vs budget in USD?")
    ask = st.button("Ask" , type="primary")

    if ask and q.strip():
        with st.spinner("Thinking..."):
            text, fig = respond(q, fin)
        st.markdown(f"**Answer**\n\n{text}")
        # Save the latest answer into session_state so Export can include it.
        st.session_state['last_answer_text'] = text
        if fig is not None:
            # Save figure as PNG bytes for embedding into PDF later
            buf = io.BytesIO()
            fig.savefig(buf, format='png', bbox_inches='tight', dpi=180)
            buf.seek(0)
            st.session_state['last_answer_img'] = buf.getvalue()
            st.pyplot(fig, clear_figure=True)
        else:
            st.session_state['last_answer_img'] = None

if __name__ == "__main__":
    app_ui()

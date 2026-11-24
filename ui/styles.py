"""Sistem desain: token warna, tipografi Inter, kartu, badge, dan perilaku responsif."""
import streamlit as st

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
:root{
  --primary:#2563EB; --bg:#F7F8FA; --card:#FFFFFF; --border:#E5E7EB; --text:#111827; --muted:#6B7280;
  --aman:#16A34A; --segera:#D97706; --kritis:#DC2626; --radius:12px; --gap:1rem;
  --shadow:0 1px 2px rgba(16,24,40,.05),0 1px 3px rgba(16,24,40,.06);
}
html, body, [class*="css"], .stApp, button, input, textarea, select{
  font-family:'Inter',-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif !important;}
.stApp{background:var(--bg);}
.block-container{padding-top:2.2rem; padding-bottom:3rem; max-width:1200px;}
[data-testid="stSidebar"]{background:#fff; border-right:1px solid var(--border);}
[data-testid="stDeployButton"], footer, #MainMenu{display:none !important;}
h1,h2,h3{letter-spacing:-0.01em; color:var(--text);}
.page-title{font-size:1.65rem; font-weight:700; margin:0; color:var(--text);}
.page-sub{color:var(--muted); font-size:.95rem; margin:.25rem 0 1.25rem 0;}
.kpi-grid{display:grid; grid-template-columns:repeat(auto-fit,minmax(190px,1fr)); gap:var(--gap); margin-bottom:1.25rem;}
.kpi{background:var(--card); border:1px solid var(--border); border-radius:var(--radius); padding:1rem 1.1rem; box-shadow:var(--shadow);}
.kpi .lbl{font-size:.78rem; color:var(--muted); font-weight:500; text-transform:none;}
.kpi .val{font-size:1.75rem; font-weight:700; line-height:1.25; color:var(--text);}
.kpi .hint{font-size:.76rem; color:var(--muted); margin-top:.1rem;}
.kpi.t-aman{border-left:4px solid var(--aman);} .kpi.t-segera{border-left:4px solid var(--segera);}
.kpi.t-kritis{border-left:4px solid var(--kritis);} .kpi.t-info{border-left:4px solid var(--primary);}
.card{background:var(--card); border:1px solid var(--border); border-radius:var(--radius); padding:1rem 1.2rem; box-shadow:var(--shadow); margin-bottom:var(--gap);}
.card h4{margin:0 0 .4rem 0; font-size:1rem;}
.badge{display:inline-block; padding:.18rem .65rem; border-radius:999px; font-size:.78rem; font-weight:600;}
.b-aman{background:#DCFCE7; color:#166534;} .b-segera{background:#FEF3C7; color:#92400E;}
.b-kritis{background:#FEE2E2; color:#991B1B;} .b-belum{background:#F3F4F6; color:#374151;}
.callout{border-radius:var(--radius); padding:.8rem 1rem; font-size:.88rem; margin:.5rem 0 1rem 0; border:1px solid;}
.c-info{background:#EFF6FF; border-color:#BFDBFE; color:#1E3A8A;}
.c-warn{background:#FFFBEB; border-color:#FDE68A; color:#78350F;}
.c-ok{background:#F0FDF4; border-color:#BBF7D0; color:#14532D;}
.empty{text-align:center; padding:2.2rem 1rem; background:var(--card); border:1px dashed var(--border); border-radius:var(--radius); color:var(--muted);}
.empty b{display:block; color:var(--text); font-size:1.05rem; margin-bottom:.25rem;}
.prio{display:flex; gap:.75rem; align-items:flex-start; padding:.65rem 0; border-bottom:1px solid var(--border);}
.prio:last-child{border-bottom:none;} .prio .n{font-weight:700; color:var(--primary); min-width:1.5rem;}
.prio .t{font-weight:600;} .prio .s{font-size:.82rem; color:var(--muted);}
[data-testid="stMetric"]{background:var(--card); border:1px solid var(--border); border-radius:var(--radius); padding:.8rem 1rem; box-shadow:var(--shadow);}
.stButton>button, .stDownloadButton>button{border-radius:10px; font-weight:600;}
[data-testid="stDataFrame"]{border:1px solid var(--border); border-radius:var(--radius); overflow:hidden;}
.stTabs [data-baseweb="tab-list"]{gap:.25rem; overflow-x:auto;}
.stTabs [data-baseweb="tab"]{font-weight:600;}
@media (max-width:640px){
  .block-container{padding:1.2rem .8rem 2.5rem;}
  .page-title{font-size:1.35rem;} .kpi .val{font-size:1.45rem;}
  .kpi-grid{grid-template-columns:repeat(2,minmax(0,1fr));}
}
</style>
"""


def inject_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)

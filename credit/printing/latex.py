"""Composition PDF institutionnelle via LaTeX (pdflatex, sans shell escape)."""

import base64
import os
from pathlib import Path
import re
import shutil
import subprocess
from tempfile import TemporaryDirectory

from credit.printing.contracts import Presentation


def tex_escape(value):
    value = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", str(value))
    value = value.replace("\u202f", "~").replace("\u00a0", "~")
    replacements = {
        "\\": r"\textbackslash{}",
        "{": r"\{", "}": r"\}", "$": r"\$", "&": r"\&", "%": r"\%",
        "#": r"\#", "_": r"\_", "^": r"\textasciicircum{}",
        "~": r"\textasciitilde{}", "<": r"\textless{}", ">": r"\textgreater{}",
    }
    return "".join(replacements.get(char, char) for char in value).replace("\n", r"\\ ")


def _table(table):
    if not table.rows:
        return ""
    count = len(table.columns)
    if count == 1:
        widths = [r"\dimexpr\linewidth-2\tabcolsep\relax"]
    else:
        first = 0.25 if count == 2 else 0.22
        widths = [f"{first:.4f}\\linewidth"] + [f"{(0.95-first)/(count-1):.4f}\\linewidth"] * (count-1)
    spec = "|" + "|".join(f">{{\\raggedright\\arraybackslash}}p{{{w}}}" for w in widths) + "|"
    head = " & ".join(r"\textbf{" + tex_escape(c) + "}" for c in table.columns) + r" \\ \hline"
    rows = []
    for row in table.rows:
        cells = list(row) + [""] * max(0, count-len(row))
        split = [tex_escape(cell)[i:i+800] for cell in cells[:count] for i in []]
        split = [
            [tex_escape(cell)[i:i+800] for i in range(0, len(tex_escape(cell)) or 1, 800)]
            for cell in cells[:count]
        ]
        for part in range(max(map(len, split))):
            continuation = [values[part] if part < len(values) else "" for values in split]
            rows.append(" & ".join(continuation) + r" \\ \\hline")
    return (
        r"\small\setlength{\tabcolsep}{4pt}\renewcommand{\arraystretch}{1.22}" + "\n"
        + r"\rowcolors{2}{CredixPale}{white}" + "\n"
        + f"\\begin{{longtable}}{{{spec}}}\n\\hline\n{head}\n\\endfirsthead\n"
        + r"\hline " + head + "\n\\endhead\n" + "\n".join(rows)
        + "\n\\end{longtable}\n\\rowcolors{2}{}{}\\normalsize\n"
    )


def latex_source(model, logo_path=None, qr_path=None):
    meta_rows = "\n".join(
        r"\CredixMetaRow{" + tex_escape(k) + "}{" + tex_escape(v) + "}"
        for k, v in model.metadata.items()
    )
    notices = "\n".join(
        r"\begin{CredixNotice}" + tex_escape(item) + r"\end{CredixNotice}"
        for item in model.notices
    )
    sections = []
    for section in model.sections:
        sections.append(r"\section{" + tex_escape(section.title) + "}")
        for paragraph in section.paragraphs:
            sections.append(tex_escape(paragraph) + "\n\\par\\medskip\n")
        sections.extend(_table(table) for table in section.tables)
    logo = (
        r"\includegraphics[width=42mm,height=18mm,keepaspectratio]{" + "logo.png" + "}"
        if logo_path else r"{\sffamily\bfseries\fontsize{20}{22}\selectfont CRÉDIX}"
    )
    verification = ""
    if qr_path:
        verification = (
            r"\section*{Vérification de l’édition}\noindent"
            r"\includegraphics[width=25mm]{" + "verification.pdf" + "}\quad "
            + tex_escape(model.verification_url or "") + "\n"
        )
    signature = ""
    if model.signatures:
        signature = (
            r"\vspace{12mm}\noindent\rule{\linewidth}{0.4pt}"
            r"\par\textbf{Lieu et date :} \dotfill"
            r"\par\vspace{8mm}\textbf{Signature manuscrite éventuelle :} \dotfill"
            r"\par\small Zone volontairement vierge — aucune signature recueillie ni certifiée."
        )
    return r"""\documentclass[10pt,a4paper]{article}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage[french]{babel}
\usepackage{lmodern}
\usepackage{textcomp}
\usepackage{microtype}
\usepackage[a4paper,top=25mm,bottom=23mm,left=19mm,right=19mm,headheight=15pt,headsep=8mm,footskip=12mm]{geometry}
\usepackage{graphicx}
\usepackage[table]{xcolor}
\usepackage{array,longtable,tabularx,booktabs}
\usepackage{fancyhdr}
\usepackage{titlesec}
\usepackage{enumitem}
\usepackage{hyperref}
\usepackage{lastpage}
\usepackage{needspace}
\definecolor{CredixNavy}{HTML}{10243A}
\definecolor{CredixTeal}{HTML}{087E83}
\definecolor{CredixPale}{HTML}{F1F5F8}
\definecolor{CredixMuted}{HTML}{5B6875}
\hypersetup{colorlinks=true,linkcolor=CredixTeal,urlcolor=CredixTeal,pdftitle={""" + tex_escape(model.title) + r"""},pdfauthor={""" + tex_escape(model.platform_name) + r"""}}
\setlength{\parindent}{0pt}
\setlength{\parskip}{5pt}
\setlist{nosep,leftmargin=5mm}
\titleformat{\section}{\Large\bfseries\sffamily\color{CredixNavy}}{\thesection}{0.7em}{}[\color{CredixTeal}\titlerule]
\titlespacing*{\section}{0pt}{15pt}{8pt}
\titleformat{\subsection}{\large\bfseries\sffamily\color{CredixTeal}}{\thesubsection}{0.7em}{}
\pagestyle{fancy}
\fancyhf{}
\fancyhead[L]{\small\sffamily\color{CredixMuted}""" + tex_escape(model.platform_name) + r"""}
\fancyhead[R]{\small\sffamily\color{CredixMuted}Dossier """ + tex_escape(model.metadata.get("Dossier", "—")) + r"""}
\fancyfoot[L]{\small\color{CredixMuted}""" + tex_escape(model.metadata.get("Édition", "Édition")) + r"""}
\fancyfoot[R]{\small\color{CredixMuted}Page \thepage\ sur \pageref{LastPage}}
\renewcommand{\headrulewidth}{0.4pt}
\renewcommand{\headrule}{\hbox to\headwidth{\color{CredixTeal}\leaders\hrule height \headrulewidth\hfill}}
\renewcommand{\footrulewidth}{0.4pt}
\newcommand{\CredixMetaRow}[2]{\textbf{\color{CredixMuted}#1} & #2\\[4pt]\hline}
\newenvironment{CredixNotice}{\par\smallskip\noindent\colorbox{CredixPale}{\parbox{\dimexpr\linewidth-2\fboxsep}{\small\color{CredixNavy}}}}{\par\smallskip}
\begin{document}
\begin{titlepage}
\thispagestyle{empty}
\vspace*{8mm}
""" + logo + r"""
\vfill
{\sffamily\color{CredixTeal}\large DOCUMENT INSTITUTIONNEL\par}
\vspace{7mm}
{\sffamily\bfseries\color{CredixNavy}\fontsize{30}{36}\selectfont """ + tex_escape(model.title) + r"""\par}
\vspace{7mm}
{\sffamily\large\color{CredixMuted}""" + tex_escape(model.status) + r"""\par}
\vspace{15mm}
{\color{CredixTeal}\rule{35mm}{2pt}}
\vfill
\renewcommand{\arraystretch}{1.35}
\begin{tabularx}{\linewidth}{>{\raggedright\arraybackslash\bfseries\color{CredixMuted}}p{45mm}X}
""" + meta_rows + r"""
\end{tabularx}
\vfill
{\small\color{CredixMuted}Document confidentiel — diffusion selon les habilitations applicables.}
\end{titlepage}
\pagenumbering{roman}
\section*{À propos de cette édition}
""" + notices + r"""
\tableofcontents
\clearpage
\pagenumbering{arabic}
""" + "\n".join(sections) + "\n" + verification + signature + r"""
\end{document}
"""


def latex_pdf_document(model: Presentation, max_pages=120):
    compiler = shutil.which("pdflatex")
    if not compiler:
        raise ValueError("latex_engine_unavailable")
    with TemporaryDirectory(prefix="credix-latex-") as tmp:
        root = Path(tmp)
        logo = None
        if model.logo_png:
            logo = root / "logo.png"
            logo.write_bytes(base64.b64decode(model.logo_png, validate=True))
        qr = None
        if model.verification_url:
            from reportlab.graphics import renderPDF
            from credit.printing.render import verification_qr
            qr = root / "verification.pdf"
            renderPDF.drawToFile(verification_qr(model.verification_url), str(qr))
        tex = root / "edition.tex"
        tex.write_text(latex_source(model, logo.name if logo else None, qr.name if qr else None), encoding="utf-8")
        env = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": str(root),
            "LANG": "C.UTF-8",
            "TEXMFOUTPUT": str(root),
            "openin_any": "p",
            "openout_any": "p",
        }
        command = [
            compiler, "-no-shell-escape", "-interaction=nonstopmode",
            "-halt-on-error", "-file-line-error", "-output-directory", str(root), "edition.tex",
        ]
        for _ in range(2):
            try:
                result = subprocess.run(command, cwd=root, env=env, capture_output=True, timeout=25, check=False)
            except subprocess.TimeoutExpired:
                raise ValueError("print_timeout") from None
            if result.returncode:
                raise ValueError("latex_compile_failed") from None
        pdf = root / "edition.pdf"
        if not pdf.exists() or not pdf.read_bytes().startswith(b"%PDF-"):
            raise ValueError("latex_output_invalid")
        import fitz
        with fitz.open(pdf) as document:
            if len(document) > max_pages:
                raise ValueError("print_page_limit")
        return pdf.read_bytes()

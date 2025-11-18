"""
Documentazione interattiva: mostra README e Test Instructions
"""
from pathlib import Path
from fastapi import APIRouter
from fastapi.responses import HTMLResponse
import markdown

router = APIRouter()


def _render_markdown(file_path: str) -> str:
    path = Path(file_path)
    if not path.exists():
        return f"<p>File {file_path} non trovato.</p>"
    text = path.read_text(encoding="utf-8")
    return markdown.markdown(text, extensions=["fenced_code", "tables"])


@router.get("/documentation", response_class=HTMLResponse)
async def documentation_page():
    readme_html = _render_markdown("README.md")
    tests_html = _render_markdown("TEST_INSTRUCTIONS.md")
    
    html_content = f"""
    <!DOCTYPE html>
    <html lang="it">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Documentazione</title>
        <style>
            * {{ box-sizing: border-box; }}
            body {{
                font-family: 'Inter', 'Segoe UI', sans-serif;
                background: #152238;
                padding: 40px;
                margin: 0;
                color: #0f172a;
            }}
            .page {{
                max-width: 1100px;
                margin: 0 auto;
                background: #ffffff;
                border-radius: 18px;
                padding: 40px;
                box-shadow: 0 24px 60px rgba(15,23,42,0.3);
            }}
            h1 {{
                font-size: 2.1rem;
                margin-bottom: 6px;
            }}
            .lead {{
                color: #6b7280;
                margin-bottom: 28px;
            }}
            details {{
                border: 1px solid #e5e7eb;
                border-radius: 14px;
                margin-bottom: 24px;
                background: #f8fafc;
            }}
            summary {{
                cursor: pointer;
                padding: 18px 22px;
                font-weight: 600;
                font-size: 1rem;
            }}
            details[open] summary {{
                border-bottom: 1px solid #e5e7eb;
                background: #eef2ff;
            }}
            article {{
                padding: 20px 24px 28px;
            }}
            article ul {{
                list-style: none;
                padding-left: 0;
            }}
            article ul li {{
                margin-bottom: 10px;
            }}
            article pre {{
                background: #0f172a;
                color: #f8fafc;
                padding: 16px;
                border-radius: 10px;
                overflow-x: auto;
            }}
        </style>
    </head>
    <body>
        <div class="page">
            <h1>Documentazione</h1>
            <p class="lead">Linee guida operative e indicazioni su test e strumenti.</p>
            <details open>
                <summary>README</summary>
                <article>{readme_html}</article>
            </details>
            <details>
                <summary>Test Instructions</summary>
                <article>{tests_html}</article>
            </details>
            <a href="/" style="font-weight:600; text-decoration:none;">Torna alla home</a>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)



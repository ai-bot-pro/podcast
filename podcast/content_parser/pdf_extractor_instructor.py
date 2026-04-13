import re
import logging
import os
import unicodedata
import urllib.request
from typing import List
from urllib.error import URLError
from urllib.parse import urlparse

import typer
import pymupdf
from rich.console import Console

from .table import table


app = typer.Typer()

_USER_AGENT = "gen-podcast/0.1 (arxiv PDF text extraction; +https://github.com)"


def _fetch_pdf_bytes(url: str, timeout: float = 120.0) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _configure_pymupdf_for_text_extraction() -> None:
    """Suppress MuPDF ICC errors (e.g. cmsOpenProfileFromMem failed) on PDFs with bad profiles."""
    try:
        pymupdf.TOOLS.set_icc(False)
    except (AttributeError, TypeError):
        pass
    try:
        pymupdf.TOOLS.mupdf_display_errors(False)
    except (AttributeError, TypeError):
        pass


class PDFExtractor:
    def extract_content(self, file_path: str) -> str:
        try:
            _configure_pymupdf_for_text_extraction()
            if file_path.startswith(("http://", "https://")):
                try:
                    data = _fetch_pdf_bytes(file_path)
                except URLError as e:
                    logging.error(f"Failed to download PDF from {file_path}: {e}")
                    raise
                doc = pymupdf.open(stream=data, filetype="pdf")
            else:
                doc = pymupdf.open(file_path)
            try:
                content = " ".join(page.get_text() for page in doc)
                normalized_content = unicodedata.normalize("NFKD", content)
                return normalized_content
            finally:
                doc.close()
        except Exception as e:
            logging.error(f"Error extracting PDF content: {str(e)}")
            raise


def get_pdf_file_name(file: str):
    if file.startswith(("http://", "https://")):
        tail = urlparse(file).path.rstrip("/").split("/")[-1] or "document"
        if not tail.lower().endswith(".pdf"):
            tail = f"{tail}.pdf"
        return tail
    pattern = r"([^/]+\.pdf)$"
    match = re.search(pattern, file)
    if match:
        pdf_file_name = match.group(1)
        return pdf_file_name
    else:
        raise Exception("must use *.pdf file")


@app.command()
def extract_content(
    ctx: typer.Context,
    pdf_files: List[str],
    output_dir: str = "videos/transcripts/",
) -> None:
    cmd = (ctx.command.name or "").replace("_", "-")
    pdf_files = [p for p in pdf_files if p.replace("_", "-") != cmd]

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    extractor = PDFExtractor()
    for pdf_file in pdf_files:
        try:
            pdf_name = get_pdf_file_name(pdf_file)
            content = extractor.extract_content(pdf_file)
            print(f"PDF {pdf_file} content extracted successfully:")
            print(content[:500] + "..." if len(content) > 500 else content)
            # Save transcript to file
            output_file = os.path.join(output_dir, f"{pdf_name}.txt")
            with open(output_file, "w") as file:
                file.write(content)
        except Exception as e:
            print(f"An error occurred: {str(e)}")


@app.command()
def instruct_content(
    ctx: typer.Context,
    test_urls: List[str],
    language: str = "en",
) -> None:
    cmd = (ctx.command.name or "").replace("_", "-")
    test_urls = [u for u in test_urls if u.replace("_", "-") != cmd]

    console = Console()
    extractor = PDFExtractor()
    for url in test_urls:
        try:
            with console.status("[bold green]Processing URL...") as status:
                content = extractor.extract_content(url)
                status.update("[bold blue]Generating Clips...")
                clips = table.extract_models(content, language=language)
                table.console_table(clips)

            console.print("\nChapter extraction complete!")
        except Exception as e:
            logging.error(f"An error occurred while processing {url}: {str(e)}")


r"""
python -m podcast.content_parser.pdf_extractor_instructor extract-content \
    "/path/to/paper.pdf"

python -m podcast.content_parser.pdf_extractor_instructor instruct-content \
    "/path/to/paper.pdf" \
    --language zh

#TODO: use OCR model extract PDF content e.g.: OCR-GOT2.0 :)
"""
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(pathname)s:%(lineno)d - %(funcName)s - %(message)s",
        handlers=[logging.StreamHandler()],
    )
    app()

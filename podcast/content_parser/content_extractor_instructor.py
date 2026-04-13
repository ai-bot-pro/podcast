import os
import re
import logging
from typing import List
from urllib.parse import urlparse

# Hostnames like "extract-content" become valid-looking https URLs but are almost always CLI typos.
_IPV4_RE = re.compile(
    r"^(?:25[0-5]|2[0-4]\d|[01]?\d\d?)(?:\.(?:25[0-5]|2[0-4]\d|[01]?\d\d?)){3}$"
)

from rich.console import Console
import typer

from .youtube_transcriber_instructor import YouTubeTranscriber
from .website_extractor_instructor import WebsiteExtractor
from .pdf_extractor_instructor import PDFExtractor, get_pdf_file_name

app = typer.Typer()


class ContentExtractor:
    def __init__(self, is_save=False, save_dir=""):
        self.youtube_transcriber = YouTubeTranscriber()
        self.website_extractor = WebsiteExtractor()
        self.pdf_extractor = PDFExtractor()
        self._save_dir = save_dir
        self._is_save = is_save
        self._file_name = ""
        if not os.path.exists(save_dir) and is_save and save_dir:
            os.makedirs(save_dir)

    @staticmethod
    def _expand_source_path(source: str) -> str:
        return os.path.expanduser(source.strip())

    @staticmethod
    def _normalize_http_url(source: str) -> str:
        s = source.strip()
        if not s.startswith(("http://", "https://")):
            s = "https://" + s
        return s

    @staticmethod
    def _is_arxiv_pdf_url(source: str) -> bool:
        """True for arXiv PDF endpoints, e.g. https://arxiv.org/pdf/2604.01161 (.pdf optional)."""
        try:
            u = ContentExtractor._normalize_http_url(source)
            p = urlparse(u.lower())
            host = p.netloc[4:] if p.netloc.startswith("www.") else p.netloc
            if host != "arxiv.org":
                return False
            path = p.path.rstrip("/")
            return path.startswith("/pdf/") and len(path) > len("/pdf/")
        except ValueError:
            return False

    @staticmethod
    def _arxiv_pdf_id_for_filename(source: str) -> str:
        u = ContentExtractor._normalize_http_url(source)
        p = urlparse(u)
        parts = [seg for seg in p.path.split("/") if seg]
        if len(parts) < 2 or parts[0].lower() != "pdf":
            raise ValueError(f"Not a recognized arXiv PDF URL path: {p.path}")
        arxiv_id = "/".join(parts[1:])
        if arxiv_id.lower().endswith(".pdf"):
            arxiv_id = arxiv_id[:-4]
        return arxiv_id

    def is_url(self, source: str) -> bool:
        if os.path.isfile(self._expand_source_path(source)):
            return False
        try:
            raw = source.strip()
            if not raw:
                return False
            has_scheme = raw.startswith(("http://", "https://"))
            candidate = raw if has_scheme else "https://" + raw
            result = urlparse(candidate)
            if result.scheme not in ("http", "https") or not result.netloc:
                return False
            host = result.hostname
            if host is None:
                return False
            # "paper.pdf" -> https://paper.pdf looks like a URL but is usually a local filename.
            if (
                not has_scheme
                and raw.lower().endswith(".pdf")
                and "/" not in raw
                and (result.path in ("", "/"))
            ):
                return False
            # Without an explicit scheme, require a real DNS-like host (avoids Typer args like "extract-content").
            if not has_scheme:
                hl = host.lower()
                if hl == "localhost" or hl.startswith("localhost."):
                    return True
                if _IPV4_RE.match(host):
                    return True
                if "." not in host:
                    return False
            return True
        except ValueError:
            return False

    def extract_content(self, source: str) -> str:
        res = self._extract_content(source)
        if self._is_save:
            output_file = os.path.join(self._save_dir, f"{self._file_name}.txt")
            with open(output_file, "w") as file:
                file.write(res)
                logging.info(f"save to file: {output_file}")
        return res

    def _extract_content(self, source: str) -> str:
        try:
            if self.is_url(source):
                if any(pattern in source for pattern in ["youtube.com", "youtu.be"]):
                    self._file_name = source.split("v=")[-1]
                    return self.youtube_transcriber.extract_transcript(self._file_name)
                if self._is_arxiv_pdf_url(source):
                    url = self._normalize_http_url(source)
                    self._file_name = self._arxiv_pdf_id_for_filename(url)
                    return self.pdf_extractor.extract_content(url)
                else:
                    self._file_name = (
                        source.split("/")[-1] if source.split("/")[-1] else source.split("/")[-2]
                    )
                    return self.website_extractor.extract_content(source)
            elif source.lower().endswith(".pdf"):
                pdf_path = self._expand_source_path(source)
                self._file_name = get_pdf_file_name(pdf_path)
                return self.pdf_extractor.extract_content(pdf_path)
            else:
                raise ValueError(
                    f"Unsupported source: {source!r}. "
                    "Use a full URL (https://...), YouTube link, arXiv /pdf/... link, or a local .pdf path."
                )
        except Exception as e:
            logging.error(f"Error extracting content from {source}: {str(e)}")
            raise

    @property
    def file_name(self):
        return self._file_name


@app.command()
def extract_content(
    ctx: typer.Context,
    sources: List[str],
    is_save: bool = False,
    save_dir: str = "videos/transcripts/",
) -> None:
    # Typer/Click may echo the subcommand name as the first List[str] item (e.g. "extract-content").
    cmd = (ctx.command.name or "").replace("_", "-")
    sources = [s for s in sources if s.replace("_", "-") != cmd]

    extractor = ContentExtractor(is_save=is_save, save_dir=save_dir)

    for source in sources:
        try:
            print(f"Extracting content from: {source}")
            content = extractor.extract_content(source)
            print(f"Extracted content (first 500 characters):\n{content[:500]}...")
            print(f"Total length of extracted content: {len(content)} characters")
            print("-" * 70)

        except Exception as e:
            logging.error(f"An error occurred while processing {source}: {str(e)}", exc_info=True)


r"""
python -m podcast.content_parser.content_extractor_instructor extract-content \
    "https://en.wikipedia.org/wiki/Large_language_model" \
    "https://www.youtube.com/watch?v=aR6CzM0x-g0" \
    "https://arxiv.org/pdf/2604.01161" \
    "/path/to/paper.pdf"
"""
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(pathname)s:%(lineno)d - %(funcName)s - %(message)s",
        handlers=[logging.StreamHandler()],
    )
    app()

"""ResumeEntity — парсинг резюме (PDF, DOCX, TXT)."""
import re
from pathlib import Path

from pypdf import PdfReader


class ResumeEntity:
    SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt", ".rtf"}

    def __init__(self, file_path: str = "resume.pdf"):
        self.file_path = Path(file_path)
        self._cached_text: str | None = None

    def extract_text(self) -> str:
        if self._cached_text:
            return self._cached_text
        if not self.file_path.exists():
            raise FileNotFoundError(f"Файл {self.file_path} не найден.")
        ext = self.file_path.suffix.lower()
        try:
            if ext == ".pdf":
                text = self._read_pdf()
            elif ext in (".docx", ".doc"):
                text = self._read_docx()
            elif ext in (".txt", ".rtf"):
                text = self._read_txt()
            else:
                raise ValueError(f"Неподдерживаемый формат файла: {ext}")
            text = re.sub(r"[ \t]+", " ", text)
            text = re.sub(r"\n\s*\n", "\n", text).strip()
            self._cached_text = text
            return text
        except (FileNotFoundError, ValueError):
            raise
        except Exception as e:
            raise RuntimeError(f"Ошибка при чтении файла: {e}") from e

    def _read_pdf(self) -> str:
        reader = PdfReader(self.file_path)
        return "\n".join(
            page.extract_text() for page in reader.pages if page.extract_text()
        )

    def _read_docx(self) -> str:
        from docx import Document  # python-docx
        doc = Document(self.file_path)
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())

    def _read_txt(self) -> str:
        return self.file_path.read_text(encoding="utf-8", errors="replace")

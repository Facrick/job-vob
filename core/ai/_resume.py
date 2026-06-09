"""ResumeEntity — парсинг PDF-резюме."""
import re
from pathlib import Path

from pypdf import PdfReader


class ResumeEntity:
    def __init__(self, file_path: str = "resume.pdf"):
        self.file_path = Path(file_path)
        self._cached_text: str | None = None

    def extract_text(self) -> str:
        if self._cached_text:
            return self._cached_text
        if not self.file_path.exists():
            raise FileNotFoundError(f"Файл {self.file_path} не найден.")
        try:
            reader = PdfReader(self.file_path)
            text = "\n".join(
                page.extract_text() for page in reader.pages if page.extract_text()
            )
            text = re.sub(r"[ \t]+", " ", text)
            text = re.sub(r"\n\s*\n", "\n", text).strip()
            self._cached_text = text
            return text
        except Exception as e:
            raise RuntimeError(f"Ошибка при чтении PDF: {e}") from e

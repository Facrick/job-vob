"""Работа с файлами: нативный диалог pywebview, загрузка резюме, экспорт."""
import logging
import shutil

import webview
from nicegui import app

from core.paths import user_path


class _FilesMixin:
    """Методы выбора файлов через нативный pywebview-диалог."""

    @staticmethod
    def _native_win():
        """Возвращает NiceGUI-обёртку нативного окна pywebview.

        Важно: используем ТОЛЬКО app.native.main_window (NiceGUI-обёртка),
        а не webview.windows[0] (сырой pywebview-объект). Сырой объект
        не поддерживает await create_file_dialog() — это вызывало ошибку.
        """
        return getattr(app.native, "main_window", None)

    async def _pick_open_file(self, file_types: tuple[str, ...]) -> str | None:
        """Нативный диалог открытия файла через pywebview (awaitable через NiceGUI)."""
        win = self._native_win()
        if win is None:
            self._show_error(
                "Нативное окно недоступно. "
                "Убедитесь что приложение запущено в нативном режиме (не браузер)."
            )
            return None
        try:
            result = await win.create_file_dialog(
                webview.OPEN_DIALOG, allow_multiple=False, file_types=file_types
            )
        except Exception as ex:
            logging.error(f"[FileDialog] open: {ex}")
            self._show_error(f"Не удалось открыть диалог выбора файла: {ex}")
            return None
        if not result:
            return None
        return result[0] if isinstance(result, (list, tuple)) else result

    async def _pick_save_file(self, default_name: str) -> str | None:
        """Нативный диалог сохранения файла через pywebview."""
        win = self._native_win()
        if win is None:
            self._show_error(
                "Нативное окно недоступно. "
                "Убедитесь что приложение запущено в нативном режиме (не браузер)."
            )
            return None
        try:
            result = await win.create_file_dialog(
                webview.SAVE_DIALOG, save_filename=default_name
            )
        except Exception as ex:
            logging.error(f"[FileDialog] save: {ex}")
            self._show_error(f"Не удалось открыть диалог сохранения: {ex}")
            return None
        if not result:
            return None
        return result if isinstance(result, str) else result[0]

    async def handle_resume_upload(self):
        path = await self._pick_open_file(("Резюме PDF (*.pdf)",))
        if not path:
            return
        dest = user_path("resume.pdf")
        try:
            shutil.copyfile(path, dest)
            self.resume.file_path = dest
            self.resume._cached_text = None
            self._refresh_resume_label()
            self._recompute_all_match_scores()
            self._try_autofill_salary()
            self.refresh_table_data()
            self._show_info("Резюме обновлено", f"Загружено: {dest.name}. Match пересчитан.")
        except Exception as ex:
            self._show_error(f"Не удалось загрузить резюме: {ex}")

    async def handle_export(self):
        path = await self._pick_save_file("vacancies_export.csv")
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"
        ok, msg = self.exporter.export_discovered_to_csv(path)
        self._show_info("Экспорт завершён", msg) if ok else self._show_error(msg)

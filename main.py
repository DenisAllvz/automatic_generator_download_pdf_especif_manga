import argparse
import json
import os
import sys
from pathlib import Path
from app.core.config import Settings, data_directory
from app.core.logger import configure_logging
from app.infrastructure.database import Database


def main():
    parser = argparse.ArgumentParser(description="Manga Manager")
    parser.add_argument("--data-dir", type=Path, help="Diretório de dados (testes ou instalação portátil)")
    parser.add_argument("--smoke-test", type=Path, help="Inicializa Qt, grava evidência JSON e encerra")
    parser.add_argument("--screenshot", type=Path, help="Captura Qt no smoke test")
    parser.add_argument("--source-check", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.smoke_test:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QTimer, QLockFile
    from PySide6.QtWidgets import QApplication, QMessageBox
    from app.ui.main_window import MainWindow
    application = QApplication(sys.argv[:1])
    if args.smoke_test and sys.platform == "win32":
        from PySide6.QtGui import QFontDatabase, QFont
        font_path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "segoeui.ttf"
        if font_path.exists():
            QFontDatabase.addApplicationFont(str(font_path))
            application.setFont(QFont("Segoe UI", 10))
    application.setApplicationName("Manga Manager")
    root = args.data_dir or data_directory()
    root.mkdir(parents=True, exist_ok=True)
    instance = QLockFile(str(root / 'instance.lock'))
    instance.setStaleLockTime(0)
    if not instance.tryLock(0):
        if not args.smoke_test:
            QMessageBox.information(None, 'Manga Manager já está aberto', 'Use a janela que já está aberta para estes dados.')
        return 0
    configure_logging(root / "logs")
    try:
        settings = Settings.load(root / "settings.json")
        database = Database(root / "library.sqlite3")
    except (OSError, ValueError, TypeError, RuntimeError) as exc:
        if args.smoke_test:
            raise
        QMessageBox.critical(None, "Configuração indisponível", f"Os dados foram preservados. Corrija configuração ou permissões.\n{exc}")
        return 1
    window = MainWindow(database, settings, root, start_queue=not bool(args.smoke_test))
    window.show()
    if args.smoke_test:
        def smoke():
            result = dict(version=__import__("app").__version__, python=sys.version, platform=sys.platform,
                          screens=window.stack.count(), title=window.windowTitle(), database=root.joinpath("library.sqlite3").exists(),
                          qt=__import__("PySide6").__version__, frozen=bool(getattr(sys, "frozen", False)), features={})
            try:
                from app.smoke import exercise
                result["features"] = exercise(window, root)
                if args.source_check:
                    import asyncio
                    from app.smoke import exercise_source
                    result["features"]["source_check"] = asyncio.run(exercise_source(root, args.source_check))
            except Exception as exc:
                import logging
                logging.getLogger("manga").exception("Falha no teste isolado")
                result.update(error=f"{type(exc).__name__}: {exc}", http_status=getattr(exc, "status", None))
            if args.screenshot:
                window.grab().save(str(args.screenshot))
            args.smoke_test.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            window.close()
            application.quit()
        QTimer.singleShot(400, smoke)
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())

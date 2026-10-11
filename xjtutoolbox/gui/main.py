from __future__ import annotations

import argparse
import signal
import sys
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QEvent, QTimer, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle

from .bridge import ExecutionBridge
from .model import ViewModel


def create_engine(application, app):
    QQuickStyle.setStyle("Basic")
    bridge = ExecutionBridge(application.tasks, app)
    model = ViewModel(
        application.accounts, application.academic, application.downloads, bridge, app
    )
    engine = QQmlApplicationEngine(app)
    engine.rootContext().setContextProperty("controller", model)
    model.quitReady.connect(app.quit)
    engine.load(QUrl.fromLocalFile(str(Path(__file__).with_name("qml") / "Main.qml")))
    return engine, model, bridge


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir")
    args = parser.parse_args(argv)
    from xjtutoolbox.bootstrap import build_application

    application = build_application(Path(args.data_dir) if args.data_dir else None)
    app = QGuiApplication(sys.argv[:1])
    app.setApplicationName("XJTUToolBox")
    engine, model, bridge = create_engine(application, app)
    if not engine.rootObjects():
        bridge.close()
        application.close()
        return 1
    timer = QTimer(app)
    timer.start(200)
    timer.timeout.connect(lambda: None)
    previous = signal.signal(signal.SIGINT, lambda *args: model.requestClose())
    try:
        return app.exec()
    finally:
        signal.signal(signal.SIGINT, previous)
        bridge.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        application.close()

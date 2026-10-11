from PyQt5.QtCore import pyqtSignal

from .ProcessWidget import ProcessThread
from ..utils import accounts, cfg
from ..utils.legacy_academic import run_legacy_scores


class ScoreThread(ProcessThread):
    """Temporary Qt5 entrypoint; delegates the entire workflow to services."""

    scores = pyqtSignal(list, bool)

    def __init__(self, term_number=None, parent=None):
        super().__init__(parent)
        self.term_number = term_number
        self.account = None
        self.allow_qrcode_login = True

    def run(self):
        self.account = accounts.current
        run_legacy_scores(
            self, self.account, False, self.term_number, cfg.useScoreReport.value
        )

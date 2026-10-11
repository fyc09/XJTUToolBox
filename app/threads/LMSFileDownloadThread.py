from ..components.ProgressInfoBar import ProgressBarThread
from ..utils.legacy_download import run_legacy_download


class LMSFileDownloadThread(ProgressBarThread):
    """Qt5 compatibility entrypoint for the shared download workflow."""

    def __init__(
        self, session, url: str, output_path: str, file_label: str, parent=None
    ):
        super().__init__(parent)
        self.session = session
        self.url = url
        self.output_path = output_path
        self.file_label = file_label

    def run(self):
        run_legacy_download(self)

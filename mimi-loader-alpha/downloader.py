import requests
from PySide6.QtCore import QObject, Signal


class Downloader(QObject):

    progress = Signal(int)
    finished = Signal(str)
    error = Signal(str)

    def download(self, url, token, output_file):

        try:

            headers = {
                "Authorization": f"Bearer {token}",
                "Accept": "application/octet-stream"
            }

            response = requests.get(
                url,
                headers=headers,
                stream=True,
                timeout=60
            )

            response.raise_for_status()

            total = int(response.headers.get("content-length", 0))
            downloaded = 0

            with open(output_file, "wb") as f:

                for chunk in response.iter_content(1024 * 1024):

                    if not chunk:
                        continue

                    f.write(chunk)

                    downloaded += len(chunk)

                    if total > 0:
                        percent = int(downloaded * 100 / total)
                        self.progress.emit(percent)

            self.finished.emit(output_file)

        except Exception as e:
            self.error.emit(str(e))

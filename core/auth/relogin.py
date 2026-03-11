from __future__ import annotations

import subprocess
import threading
import time


class ReloginService:
    RELOGIN_COMMAND = 'sudo systemctl restart user@$(id -u $USER).service'

    def trigger_relogin(self, delay_seconds: float = 0.6) -> None:
        delay = max(0.0, float(delay_seconds))
        worker = threading.Thread(
            target=self._run_relogin_command,
            args=(delay,),
            daemon=True,
        )
        worker.start()

    def _run_relogin_command(self, delay_seconds: float) -> None:
        if delay_seconds > 0:
            time.sleep(delay_seconds)

        subprocess.Popen(
            ['/bin/bash', '-lc', self.RELOGIN_COMMAND],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
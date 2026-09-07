import logging
import os
import shutil
import signal
import subprocess
import time

from backend.config import settings
from backend.exceptions.api_exception import ApiException

logger = logging.getLogger(__name__)

# Terraform colourises its output; the escape codes would end up rendered as
# junk in the browser and fed back into the self-repair prompt.
NO_COLOR = "-no-color"


class TerraformValidatorService:

    # `init` downloads and unpacks the provider; measured at ~57s even with a
    # warm plugin cache, so a 60s budget made a valid project fail at random.
    INIT_TIMEOUT_SECONDS = 180

    COMMAND_TIMEOUT_SECONDS = 60

    def __init__(self):
        os.makedirs(settings.TERRAFORM_PLUGIN_CACHE_DIR, exist_ok=True)

    def validate(self, project_path):

        # Best effort: the model aligns attributes inconsistently, so the output
        # is rarely fmt-clean. A failing fmt must never mask the validate error,
        # hence the ignored return code.
        self._run(["terraform", "fmt", "-recursive", NO_COLOR], project_path)

        init_result = self._init(project_path)

        if init_result.returncode != 0:
            return {
                "valid": False,
                "step": "init",
                "stdout": init_result.stdout,
                "stderr": init_result.stderr
            }

        validate_result = self._run(["terraform", "validate", NO_COLOR], project_path)

        return {
            "valid": validate_result.returncode == 0,
            "step": "validate",
            "stdout": validate_result.stdout,
            "stderr": validate_result.stderr
        }

    def _init(self, project_path):
        """Run `terraform init`, healing a stale local cache if needed.

        We keep .terraform/ between runs because reinstalling the provider costs
        ~40s. But it holds symlinks into the shared plugin cache, and a stale one
        makes init fail with "cannot install package into target directory ...
        because it is a symlink". Wiping and retrying recovers automatically.
        """

        command = ["terraform", "init", "-input=false", NO_COLOR]

        result = self._run(command, project_path, timeout=self.INIT_TIMEOUT_SECONDS)

        if result.returncode == 0:
            return result

        cache_dir = os.path.join(project_path, ".terraform")

        if not os.path.isdir(cache_dir):
            return result

        logger.warning(
            "terraform init failed with a local cache present; "
            "clearing %s and retrying once", cache_dir
        )

        shutil.rmtree(cache_dir, ignore_errors=True)

        return self._run(command, project_path, timeout=self.INIT_TIMEOUT_SECONDS)

    def _run(self, command, project_path, timeout=None):

        timeout = timeout or self.COMMAND_TIMEOUT_SECONDS

        env = {
            **os.environ,
            "TF_PLUGIN_CACHE_DIR": settings.TERRAFORM_PLUGIN_CACHE_DIR
        }

        started_at = time.monotonic()

        try:
            # start_new_session puts terraform and its provider plugins in their
            # own process group. Without it, a timeout kills terraform but leaves
            # the plugin children running: they hold the provider binary open and
            # every later `terraform init` fails with "text file busy" through the
            # shared plugin cache. Observed for real, 17 minutes after the fact.
            process = subprocess.Popen(
                command,
                cwd=project_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
                start_new_session=True
            )

        except FileNotFoundError:
            raise ApiException(
                message="Terraform CLI is not installed or not found on the server.",
                status_code=500
            )

        except OSError as e:
            raise ApiException(
                message=f"Unable to run Terraform: {e}",
                status_code=500
            )

        try:
            stdout, stderr = process.communicate(timeout=timeout)

        except subprocess.TimeoutExpired:
            self._terminate(process)

            logger.error("terraform %s timed out after %ss", command[1], timeout)

            raise ApiException(
                message=(
                    f"Terraform command '{' '.join(command)}' timed out "
                    f"after {timeout}s."
                ),
                status_code=504
            )

        logger.info(
            "terraform %s finished in %.1fs (exit=%d)",
            command[1], time.monotonic() - started_at, process.returncode
        )

        return subprocess.CompletedProcess(
            command, process.returncode, stdout, stderr
        )

    @staticmethod
    def _terminate(process):
        """Kill terraform *and* the provider plugins it spawned."""

        try:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)

        except (ProcessLookupError, PermissionError, OSError):
            process.kill()

        try:
            process.communicate(timeout=5)

        except subprocess.TimeoutExpired:
            pass

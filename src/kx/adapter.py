"""KaggleAdapter: every Kaggle call kx makes, in-process through the SDK.

Rules this module enforces (all verified against kaggle 2.2.3):

* ``kaggle`` is imported lazily. Importing it runs ``authenticate()``, which with
  no credential prints help on stdout and calls ``exit(1)``; ``load()`` catches
  that and raises ``CredentialUnavailable`` instead.
* The SDK's HTTP client has no timeout, so every call runs under a SIGALRM
  ``deadline``. Library chatter is swallowed by ``quiet``.
* Push builds its own ``ApiSaveKernelRequest`` so every flag is explicit
  (``kernels_push`` defaults a missing ``enable_internet`` to True).
* Output is pulled by our own loop with ``safe_join`` (``kernels_output`` in
  2.2.3 writes server-supplied names without a traversal check).
* Server text (error bodies, URLs, signed download links) is never returned in
  an error: callers get an op name and an HTTP status code only.

Tests pass a fake with the same method names; nothing here is a module global.
"""

from __future__ import annotations

import contextlib
import enum
import io
import json
import signal
from pathlib import Path

from kx.util import KxError


class KxTimeout(Exception):
    pass


class CredentialUnavailable(Exception):
    pass


@contextlib.contextmanager
def deadline(seconds: float):
    """Raise KxTimeout if the block runs longer than ``seconds`` (POSIX, main thread)."""

    def _raise(signum, frame):
        raise KxTimeout(f"deadline {seconds}s")

    old = signal.signal(signal.SIGALRM, _raise)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old)


@contextlib.contextmanager
def quiet():
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        yield


def plain(obj, depth: int = 0):
    """KaggleObject / enum / datetime -> plain JSON-able structure."""
    if depth > 8:
        return None
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if isinstance(obj, enum.Enum):
        return obj.name
    if isinstance(obj, (list, tuple)):
        return [plain(x, depth + 1) for x in obj]
    if isinstance(obj, dict):
        return {k: plain(v, depth + 1) for k, v in obj.items()}
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    fields = getattr(obj, "_fields", None)
    if fields:
        out = {}
        for f in fields:
            name = getattr(f, "field_name", None) or getattr(f, "name", None)
            if not name:
                continue
            try:
                out[name] = plain(getattr(obj, name), depth + 1)
            except Exception:  # noqa: BLE001 - a broken optional field is recorded as None
                out[name] = None
        return out
    return str(obj)


def safe_join(root: Path, name: str) -> Path:
    """Resolve a server-supplied file name under root, refusing any escape."""
    if (not name or "\x00" in name or "\\" in name or Path(name).is_absolute()
            or ".." in Path(name).parts):
        raise ValueError("unsafe output file name")
    root_r = root.resolve()
    p = (root_r / name).resolve()
    if root_r not in p.parents:
        raise ValueError("unsafe output file name")
    return p


def _is_network_error(exc) -> bool:
    names = {type(e).__name__ for e in (exc, exc.__cause__, exc.__context__) if e is not None}
    return bool(names & {"ConnectionError", "Timeout", "ReadTimeout", "ConnectTimeout",
                         "NameResolutionError", "MaxRetryError", "ChunkedEncodingError",
                         "gaierror", "OSError"})


def _http_status(exc) -> int | None:
    resp = getattr(exc, "response", None)
    code = getattr(resp, "status_code", None)
    return code if isinstance(code, int) else None


class KaggleAdapter:
    """Real adapter. Construct cheaply; ``load()`` happens on first use."""

    def __init__(self, timeout: float = 60):
        self.timeout = timeout
        self._api = None
        self.username: str | None = None

    # -- loading ---------------------------------------------------------- #
    def load(self):
        if self._api is not None:
            return self._api
        try:
            with quiet(), deadline(self.timeout):
                from kaggle.api.kaggle_api_extended import KaggleApi  # noqa: PLC0415

                api = KaggleApi()
                api.authenticate()
        except SystemExit as exc:
            raise CredentialUnavailable("no_valid_credential") from exc
        except KxTimeout as exc:
            raise KxError("error", "timed out loading the Kaggle SDK",
                          errors=["kaggle_timeout:authenticate"]) from exc
        except Exception as exc:  # noqa: BLE001 - token introspection failure etc.
            code = _http_status(exc)
            if code in (401, 403) or (code is None and not _is_network_error(exc)):
                raise CredentialUnavailable(type(exc).__name__) from exc
            # A network outage or a 5xx is not a bad credential: retryable error.
            label = f"http_{code}" if code else type(exc).__name__
            raise KxError("error", f"could not reach Kaggle to check the credential ({label})",
                          errors=[f"{label}:authenticate"],
                          next_action={"kind": "run", "command": "kx status",
                                       "instruction": "Check the network, then retry."}) from exc
        self._api = api
        self.username = api.get_config_value("username")
        return api

    def _call(self, op: str, fn, timeout: float | None = None, retries: int = 2):
        """Run fn(api) under a deadline. Idempotent reads retry transient failures
        (connection errors, 429, 5xx) with backoff; pushes pass retries=0."""
        import time

        for attempt in range(retries + 1):
            try:
                return self._call_once(op, fn, timeout)
            except KxError as exc:
                transient = exc.status == "error" and any(
                    e.startswith(("ConnectionError", "ChunkedEncodingError", "http_429", "http_5",
                                  "ReadTimeout", "kaggle_timeout")) for e in exc.errors)
                if not transient or attempt == retries:
                    raise
                time.sleep(2 * (attempt + 1) ** 2)
        raise AssertionError("unreachable")

    def _call_once(self, op: str, fn, timeout: float | None = None):
        api = self.load()
        try:
            with quiet(), deadline(timeout or self.timeout):
                return fn(api)
        except KxTimeout as exc:
            raise KxError("error", f"Kaggle call timed out ({op})",
                          errors=[f"kaggle_timeout:{op}"]) from exc
        except KxError:
            raise
        except Exception as exc:  # noqa: BLE001 - mapped, never echoed
            code = _http_status(exc)
            if code in (401, 403):
                raise KxError("needs_user", f"Kaggle refused {op} (HTTP {code})",
                              errors=[f"http_{code}:{op}"], data={"http_status": code}) from exc
            if code == 404:
                raise KxError("invalid", f"Kaggle has no such resource ({op}, HTTP 404)",
                              errors=[f"http_404:{op}"], data={"http_status": 404}) from exc
            label = f"http_{code}" if code else type(exc).__name__
            raise KxError("error", f"Kaggle call failed ({op}: {label})",
                          errors=[f"{label}:{op}"]) from exc

    # -- account ---------------------------------------------------------- #
    def validate(self) -> str:
        """One authenticated live call (a legacy key is not checked by authenticate)."""
        self._call("competitions_list",
                   lambda api: api.competitions_list(search="titanic", page_size=1))
        return self.username or ""

    # -- competitions ----------------------------------------------------- #
    def competition(self, slug: str) -> dict:
        from kagglesdk.competitions.types.competition_api_service import ApiGetCompetitionRequest

        def fn(api):
            with api.build_kaggle_client() as client:
                r = ApiGetCompetitionRequest()
                r.competition_name = slug
                return plain(client.competitions.competition_api_client.get_competition(r))

        return self._call("get_competition", fn)

    def files_summary(self, slug: str) -> dict:
        from kagglesdk.competitions.types.competition_api_service import (
            ApiGetCompetitionDataFilesSummaryRequest,
        )

        def fn(api):
            with api.build_kaggle_client() as client:
                r = ApiGetCompetitionDataFilesSummaryRequest()
                r.competition_name = slug
                cc = client.competitions.competition_api_client
                return plain(cc.get_competition_data_files_summary(r))

        return self._call("get_competition_data_files_summary", fn)

    def list_tree(self, slug: str, path: str | None = None, max_pages: int = 20) -> dict:
        """Files and directories at one level (root, or ``path`` after joining)."""
        from kagglesdk.competitions.types.competition_api_service import ApiListDataTreeFilesRequest

        def fn(api):
            files, dirs, token = [], [], None
            with api.build_kaggle_client() as client:
                cc = client.competitions.competition_api_client
                for _ in range(max_pages):
                    r = ApiListDataTreeFilesRequest()
                    r.competition_name = slug
                    r.page_size = 200
                    if path:
                        r.path = path
                    if token:
                        r.page_token = token
                    resp = plain(cc.list_data_tree_files(r)) or {}
                    files += resp.get("files") or []
                    dirs += resp.get("directories") or []
                    token = resp.get("next_page_token")
                    if not token:
                        break
            return {"files": files, "directories": dirs, "truncated": bool(token)}

        return self._call("list_data_tree_files", fn)

    def download_bundle(self, slug: str, dest_dir: Path, timeout: float) -> Path:
        """Download the competition's data as ONE bundle (never a per-file loop,
        which hits HTTP 429). Returns the archive path."""

        def fn(api):
            dest_dir.mkdir(parents=True, exist_ok=True)
            api.competition_download_files(slug, path=str(dest_dir), force=True, quiet=True)
            found = sorted(dest_dir.glob(f"{slug}.*"))
            if not found:
                raise FileNotFoundError("bundle not written")
            return found[0]

        return self._call("download_data_files", fn, timeout=timeout)

    def download_file(self, slug: str, name: str, dest_dir: Path, timeout: float) -> Path:
        """One named competition file (Kaggle may serve it zipped). Only for a
        handful of files: per-file loops over many files hit HTTP 429."""

        def fn(api):
            dest_dir.mkdir(parents=True, exist_ok=True)
            base = Path(name).name
            api.competition_download_file(slug, name, path=str(dest_dir), force=True, quiet=True)
            for cand in (dest_dir / base, dest_dir / f"{base}.zip"):
                if cand.exists():
                    return cand
            raise FileNotFoundError("file not written")

        return self._call("download_data_file", fn, timeout=timeout)

    # -- submissions (submit: the user-confirmed path only; read-back) ------ #
    def submissions(self, slug: str, page_size: int = 50) -> list[dict]:
        return self._call("list_submissions", lambda api: plain(
            api.competition_submissions(slug, page_size=page_size)) or [])

    def episodes(self, submission_id: int) -> list[dict]:
        return self._call("list_submission_episodes", lambda api: plain(
            api.competition_list_episodes(int(submission_id))) or [])

    def replay(self, episode_id: int, dest_dir: Path) -> dict:
        def fn(api):
            dest_dir.mkdir(parents=True, exist_ok=True)
            api.competition_episode_replay(int(episode_id), path=str(dest_dir), quiet=True)
            return json.loads((dest_dir / f"episode-{int(episode_id)}-replay.json").read_text())

        return self._call("get_episode_replay", fn, timeout=120)

    # -- research (all readable without joining) --------------------------- #
    def pages(self, slug: str) -> list[dict]:
        """Competition pages (overview, evaluation, rules, data...): untrusted text."""
        return self._call("list_competition_pages",
                          lambda api: plain(api.competition_list_pages(slug)) or [])

    def topics(self, slug: str, sort_by: str = "top", page: int = 1) -> list[dict]:
        def fn(api):
            resp = plain(api.competition_list_topics(slug, sort_by=sort_by, page=page)) or {}
            return resp.get("topics") or []

        return self._call("list_competition_topics", fn)

    def topic_messages(self, slug: str, topic_id: int) -> list[dict]:
        """Full thread incl. the original post (the CLI's `topics show` drops it)."""
        from kagglesdk.competitions.types.competition_api_service import ApiListTopicMessagesRequest

        def fn(api):
            with api.build_kaggle_client() as client:
                r = ApiListTopicMessagesRequest()
                r.competition_name = slug
                r.topic_id = int(topic_id)
                r.page_size = -1
                resp = plain(client.competitions.competition_api_client.list_topic_messages(r)) or {}
            return resp.get("messages") or resp.get("topic_messages") or []

        return self._call("list_topic_messages", fn)

    def kernels_list(self, **kw) -> list[dict]:
        return self._call("list_kernels", lambda api: plain(api.kernels_list(**kw)) or [])

    def kernel_source(self, owner: str, slug: str) -> dict:
        """A kernel's code + metadata, returned in memory (never written by the SDK)."""
        from kagglesdk.kernels.types.kernels_api_service import ApiGetKernelRequest

        def fn(api):
            with api.build_kaggle_client() as client:
                r = ApiGetKernelRequest()
                r.user_name = owner
                r.kernel_slug = slug
                resp = plain(client.kernels.kernels_api_client.get_kernel(r)) or {}
            blob = resp.get("blob") or {}
            return {"source": blob.get("source") or "", "language": blob.get("language"),
                    "kernel_type": blob.get("kernel_type"), "metadata": resp.get("metadata") or {}}

        return self._call("get_kernel", fn)

    # -- kernels ---------------------------------------------------------- #
    def push(self, metadata: dict, code_text: str, timeout_s: int | None = None) -> dict:
        from kagglesdk.kernels.types.kernels_api_service import ApiSaveKernelRequest

        def fn(api):
            with api.build_kaggle_client() as client:
                r = ApiSaveKernelRequest()
                r.slug = metadata["id"]
                r.new_title = metadata["title"]
                r.text = code_text
                r.language = metadata["language"]
                r.kernel_type = metadata["kernel_type"]
                r.is_private = bool(metadata["is_private"])
                r.enable_gpu = bool(metadata["enable_gpu"])
                r.enable_tpu = bool(metadata["enable_tpu"])
                r.enable_internet = bool(metadata["enable_internet"])
                r.dataset_data_sources = list(metadata.get("dataset_sources") or [])
                r.competition_data_sources = list(metadata.get("competition_sources") or [])
                r.kernel_data_sources = list(metadata.get("kernel_sources") or [])
                r.model_data_sources = list(metadata.get("model_sources") or [])
                r.category_ids = []
                if metadata.get("machine_shape"):
                    r.machine_shape = metadata["machine_shape"]
                if metadata.get("docker_image"):
                    r.docker_image = metadata["docker_image"]
                if metadata.get("docker_image_pinning_type"):
                    r.docker_image_pinning_type = metadata["docker_image_pinning_type"]
                if timeout_s:
                    r.session_timeout_seconds = int(timeout_s)
                return plain(client.kernels.kernels_api_client.save_kernel(r))

        return self._call("save_kernel", fn, timeout=180, retries=0)

    def submit(self, slug: str, message: str, *, file: str | None = None,
               kernel: str | None = None, version: int | None = None,
               file_name: str | None = None) -> dict:
        """One competition submission: a file upload, or a code-competition kernel
        version (`kernel` + `version` + the output `file_name`). Never retried: a
        failure after the request reached Kaggle may still have created it."""

        def fn(api):
            if kernel:
                r = api.competition_submit_code(file_name, message, slug, kernel, int(version),
                                                quiet=True)
            else:
                r = api.competition_submit(file, message, slug, quiet=True)
            return {"ref": getattr(r, "ref", None), "message": getattr(r, "message", None)}

        return self._call("create_submission", fn, timeout=600, retries=0)

    def kernel_status(self, owner: str, slug: str) -> dict:
        from kagglesdk.kernels.types.kernels_api_service import ApiGetKernelSessionStatusRequest

        def fn(api):
            with api.build_kaggle_client() as client:
                r = ApiGetKernelSessionStatusRequest()
                r.user_name = owner
                r.kernel_slug = slug
                return plain(client.kernels.kernels_api_client.get_kernel_session_status(r))

        return self._call("get_kernel_session_status", fn)

    def dataset_state(self, ref: str) -> dict:
        """{"status", "current_version_number"} of a dataset; HTTP 404 when it does not exist."""
        def fn(api):
            return json.loads(api.dataset_status(ref, format="json(status,current_version_number)"))

        return self._call("dataset_status", fn)

    def my_kernel_refs(self, search: str) -> list[str]:
        """Refs of this account's kernels (private included) matching search."""
        def fn(api):
            return [str(getattr(k, "ref", "")) for k in
                    api.kernels_list(mine=True, search=search, page_size=50) or []]

        return self._call("kernels_list", fn)

    def my_datasets(self, search: str) -> list[dict]:
        """This account's datasets (private included) matching search: ref + is_private."""
        def fn(api):
            return [{"ref": str(getattr(d, "ref", "")),
                     "is_private": getattr(d, "is_private", None)}
                    for d in api.dataset_list(mine=True, search=search) or []]

        return self._call("dataset_list", fn)

    def dataset_push(self, folder: str, *, new: bool, notes: str) -> dict:
        """Create a private dataset from folder (its dataset-metadata.json names it), or add a
        version. Never retried: a failure after Kaggle received it may have created it."""
        def fn(api):
            if new:
                r = api.dataset_create_new(folder, public=False, quiet=True,
                                           convert_to_csv=False, dir_mode="zip")
            else:
                r = api.dataset_create_version(folder, notes, quiet=True, convert_to_csv=False,
                                               dir_mode="zip")
            return {"ref": getattr(r, "ref", None), "status": getattr(r, "status", None),
                    "error": getattr(r, "error", None)}

        return self._call("dataset_push", fn, timeout=3600, retries=0)

    def accelerator_quota(self) -> dict:
        """This account's weekly GPU/TPU quota: seconds used, reserved by running sessions,
        and allowed, plus the refresh time (live-verified 2026-10-04)."""
        from kagglesdk.kernels.types.kernels_api_service import (
            ApiGetAcceleratorQuotaStatisticsRequest,
        )

        def secs(td):
            return td.total_seconds() if hasattr(td, "total_seconds") else None

        def fn(api):
            with api.build_kaggle_client() as client:
                r = client.kernels.kernels_api_client.get_accelerator_quota_statistics(
                    ApiGetAcceleratorQuotaStatisticsRequest())
                out = {"refresh": plain(r.quota_refresh_time)}
                for name in ("gpu", "tpu"):
                    q = getattr(r, f"{name}_quota")
                    out[name] = {"used_s": secs(q.time_used), "reserved_s": secs(q.time_reserved),
                                 "allowed_s": secs(q.total_time_allowed)}
                return out

        return self._call("get_accelerator_quota_statistics", fn)

    def get_kernel(self, owner: str, slug: str) -> dict:
        from kagglesdk.kernels.types.kernels_api_service import ApiGetKernelRequest

        def fn(api):
            with api.build_kaggle_client() as client:
                r = ApiGetKernelRequest()
                r.user_name = owner
                r.kernel_slug = slug
                resp = plain(client.kernels.kernels_api_client.get_kernel(r)) or {}
                return resp.get("metadata") or {}

        return self._call("get_kernel", fn)

    def list_output(self, owner: str, slug: str) -> dict:
        from kagglesdk.kernels.types.kernels_api_service import ApiListKernelSessionOutputRequest

        def fn(api):
            files, log, token = [], None, None
            with api.build_kaggle_client() as client:
                kc = client.kernels.kernels_api_client
                for _ in range(50):
                    r = ApiListKernelSessionOutputRequest()
                    r.user_name = owner
                    r.kernel_slug = slug
                    r.page_size = 100
                    if token:
                        r.page_token = token
                    resp = plain(kc.list_kernel_session_output(r)) or {}
                    if log is None:
                        log = resp.get("log")
                    files += [{"file_name": f.get("file_name"), "url": f.get("url")}
                              for f in resp.get("files") or []]
                    token = resp.get("next_page_token")
                    if not token:
                        break
            return {"files": files, "log": log}

        return self._call("list_kernel_session_output", fn)

    def download(self, url: str, dest: Path, timeout: float = 600) -> int:
        """Stream one output file to dest. The URL is signed: never logged."""
        import requests

        def fn(_api):
            dest.parent.mkdir(parents=True, exist_ok=True)
            n = 0
            with requests.get(url, stream=True, timeout=(15, 120)) as r:
                r.raise_for_status()
                with open(dest, "wb") as fh:
                    for chunk in r.iter_content(1 << 20):
                        fh.write(chunk)
                        n += len(chunk)
            return n

        return self._call("download_output", fn, timeout=timeout)

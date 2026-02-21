"""Prime contractor module for Startd8.

Provides the core PrimeContractor class for seed-based code generation,
along with manifest management (F-010) and staleness detection (F-011).

Features:
    F-001: Seed-based generation and contractor framework
    F-002: Seed input parsing and contractor instantiation
    F-010: Generation manifest with checksum support
    F-011: Staleness detection via source checksum comparison
    F-015: Cross-platform state file management
"""

import hashlib
import json
import logging
import pathlib
import subprocess
import sys
import tempfile
from typing import Any, Dict, Optional, Union

# ============================================================================
# Guarded platform imports (F-015)
# ============================================================================

if sys.platform == "win32":
    import msvcrt
else:
    import fcntl

# ============================================================================
# Module logger
# ============================================================================

logger = logging.getLogger(__name__)

# ============================================================================
# F-001 constants (Seed-based generation)
# ============================================================================

DEFAULT_CONTRACTOR_TIMEOUT: float = 300.0
DEFAULT_CONTRACTOR_RETRIES: int = 3
CONTRACTOR_READY_TIMEOUT: float = 10.0

# ============================================================================
# F-015 constants (Cross-platform state)
# ============================================================================

STATE_FILE_ENCODING: str = "utf-8"
STATE_FILE_LOCK_TIMEOUT: float = 30.0

# ============================================================================
# F-010 constants (Generation manifest)
# ============================================================================

GENERATION_MANIFEST_FILENAME: str = "generation-manifest.json"
GENERATION_MANIFEST_VERSION: str = "1.0"

# ============================================================================
# F-011 constants (Staleness Detection)
# ============================================================================

MANIFEST_FILENAME: str = "generation-manifest.json"
CHECKSUM_ALGORITHM: str = "sha256"
MANIFEST_CHECKSUM_KEY: str = "source_checksum"
FORCE_REGENERATE_FLAG: str = "--force-regenerate"
_CHECKSUM_LOG_PREFIX_LEN: int = 12

# ============================================================================
# Custom exceptions (F-015)
# ============================================================================


class StateFileError(Exception):
    """Raised when state file operations fail."""

    pass


class StateFileLockTimeout(StateFileError):
    """Raised when acquiring a state file lock times out."""

    pass


# ============================================================================
# F-015 private helpers (Cross-platform state)
# ============================================================================


def _acquire_file_lock(
    file_handle: Any, timeout: float = STATE_FILE_LOCK_TIMEOUT
) -> None:
    """Acquire a cross-platform file lock with timeout.

    Args:
        file_handle: Open file object to lock.
        timeout: Maximum time in seconds to wait for lock acquisition.

    Raises:
        StateFileLockTimeout: If lock cannot be acquired within timeout.
    """
    import time

    deadline = time.monotonic() + timeout
    while True:
        try:
            if sys.platform == "win32":
                msvcrt.locking(file_handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                fcntl.flock(file_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        except (OSError, IOError):
            if time.monotonic() > deadline:
                raise StateFileLockTimeout(
                    f"Could not acquire lock within {timeout} seconds"
                )
            time.sleep(0.05)


def _release_file_lock(file_handle: Any) -> None:
    """Release a cross-platform file lock.

    Args:
        file_handle: Open file object to unlock.
    """
    try:
        if sys.platform == "win32":
            msvcrt.locking(file_handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            fcntl.flock(file_handle.fileno(), fcntl.LOCK_UN)
    except (OSError, IOError) as exc:
        logger.warning("Failed to release file lock: %s", exc)


# ============================================================================
# F-015 public utility functions (Cross-platform state)
# ============================================================================


def read_state_file(
    state_file_path: pathlib.Path,
    timeout: float = STATE_FILE_LOCK_TIMEOUT,
) -> Optional[Dict[str, Any]]:
    """Read and parse a JSON state file with file locking.

    Args:
        state_file_path: Path to the state file.
        timeout: Lock acquisition timeout in seconds.

    Returns:
        Parsed JSON dict, or None if file does not exist or cannot be read.

    Raises:
        StateFileLockTimeout: If lock cannot be acquired within timeout.
    """
    if not state_file_path.is_file():
        return None

    try:
        with open(state_file_path, "r", encoding=STATE_FILE_ENCODING) as f:
            _acquire_file_lock(f, timeout=timeout)
            try:
                return json.load(f)
            finally:
                _release_file_lock(f)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Failed to read state file %s: %s", state_file_path, exc)
        return None


def write_state_file(
    state_file_path: pathlib.Path,
    state: Dict[str, Any],
    timeout: float = STATE_FILE_LOCK_TIMEOUT,
) -> None:
    """Write a dict as JSON to a state file with file locking.

    Args:
        state_file_path: Path to the state file.
        state: Dict to serialize and write.
        timeout: Lock acquisition timeout in seconds.

    Raises:
        StateFileLockTimeout: If lock cannot be acquired within timeout.
        StateFileError: If write fails.
    """
    try:
        state_file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(state_file_path, "w", encoding=STATE_FILE_ENCODING) as f:
            _acquire_file_lock(f, timeout=timeout)
            try:
                json.dump(state, f, indent=2)
            finally:
                _release_file_lock(f)
    except (OSError, TypeError) as exc:
        raise StateFileError(
            f"Failed to write state file {state_file_path}: {exc}"
        )


# ============================================================================
# F-011 private helpers (Staleness Detection)
# ============================================================================


def _safe_checksum_prefix(value: Any) -> str:
    """Return a safe, fixed-length prefix of a checksum for logging.

    Handles non-string types gracefully to avoid ``TypeError`` in log
    formatting.

    Args:
        value: The value to format (typically a checksum string).

    Returns:
        A string slice of at most ``_CHECKSUM_LOG_PREFIX_LEN`` characters.
    """
    if isinstance(value, str):
        return value[:_CHECKSUM_LOG_PREFIX_LEN]
    return repr(value)[:_CHECKSUM_LOG_PREFIX_LEN]


# ============================================================================
# F-010 / F-011 public utility functions (Checksum & manifest)
# ============================================================================


def compute_source_checksum(data: Union[str, Dict[str, Any]]) -> str:
    """Compute a SHA-256 hex digest of the given data.

    If *data* is a ``str``, it is treated as raw seed content and hashed
    directly after UTF-8 encoding (F-011 staleness detection path).

    If *data* is a ``dict``, it is serialized to canonical JSON (sorted
    keys, compact separators) and then hashed (F-010 manifest path).

    Args:
        data: Either a seed content string or a state dict to checksum.

    Returns:
        Lowercase hex-encoded SHA-256 digest string (64 characters).

    Raises:
        TypeError: If *data* is neither ``str`` nor ``dict``.
    """
    if isinstance(data, str):
        return hashlib.sha256(data.encode("utf-8")).hexdigest()
    if isinstance(data, dict):
        canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    raise TypeError(
        f"compute_source_checksum expects str or dict, got {type(data).__name__}"
    )


class GenerationManifest:
    """Typed representation of generation-manifest.json.

    Attributes:
        version: Manifest schema version.
        source_checksum: SHA-256 hex digest of seed content.
        metadata: Optional free-form metadata dict.
    """

    def __init__(
        self,
        version: str = GENERATION_MANIFEST_VERSION,
        source_checksum: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.version = version
        self.source_checksum = source_checksum
        self.metadata = metadata or {}

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a dict suitable for JSON encoding."""
        return {
            "version": self.version,
            "source_checksum": self.source_checksum,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GenerationManifest":
        """Deserialize from a dict (e.g. parsed JSON)."""
        return cls(
            version=data.get("version", GENERATION_MANIFEST_VERSION),
            source_checksum=data.get("source_checksum", ""),
            metadata=data.get("metadata", {}),
        )


def write_generation_manifest(
    manifest_path: pathlib.Path,
    manifest: GenerationManifest,
) -> None:
    """Write a :class:`GenerationManifest` to a JSON file.

    Args:
        manifest_path: Path to the manifest file.
        manifest: GenerationManifest instance to write.

    Raises:
        OSError: If file write fails.
    """
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest.to_dict(), f, indent=2)


def read_generation_manifest(manifest_path: pathlib.Path) -> GenerationManifest:
    """Read and parse a :class:`GenerationManifest` from JSON.

    Args:
        manifest_path: Path to the manifest file.

    Returns:
        Deserialized GenerationManifest.

    Raises:
        FileNotFoundError: If the file does not exist.
        json.JSONDecodeError: If JSON is invalid.
        ValueError: If manifest structure is invalid.
    """
    with open(manifest_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("Manifest root must be a JSON object")
        return GenerationManifest.from_dict(data)


# ============================================================================
# F-011 public utility functions (Staleness Detection)
# ============================================================================


def read_manifest(manifest_path: pathlib.Path) -> Optional[dict]:
    """Read and parse generation-manifest.json for staleness checks.

    Returns ``None`` if the file is missing, unreadable, or contains
    invalid JSON.  Logs an ``INFO`` message for missing files and a
    ``WARNING`` for corrupt files (file exists but cannot be parsed).

    Args:
        manifest_path: Path to the manifest file.

    Returns:
        The parsed manifest as a dict, or ``None``.
    """
    if not manifest_path.is_file():
        logger.info("No manifest found at %s", manifest_path)
        return None
    try:
        text = manifest_path.read_text(encoding="utf-8")
        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError("Manifest root is not a JSON object")
        return data
    except (json.JSONDecodeError, ValueError, OSError) as exc:
        logger.warning("Corrupt manifest at %s: %s", manifest_path, exc)
        return None


def should_regenerate(
    manifest_path: pathlib.Path,
    current_checksum: str,
    force: bool = False,
) -> bool:
    """Decide whether to regenerate output.

    Returns ``True`` if regeneration is needed, ``False`` to reuse
    existing output.

    Decision logic (evaluated in order):

    1. ``force=True`` (``--force-regenerate``) → ``True``
    2. No manifest / corrupt manifest → ``True``
    3. ``source_checksum`` missing or wrong type → ``True``
    4. ``source_checksum`` mismatch → ``True``
    5. ``source_checksum`` match → ``False`` (reuse)

    Args:
        manifest_path:    Path to the generation manifest file.
        current_checksum: SHA-256 hex digest of the current seed content.
        force:            If ``True``, unconditionally return ``True``.

    Returns:
        ``True`` if regeneration should proceed, ``False`` to reuse.
    """
    if force:
        logger.info("Force regenerate requested, bypassing staleness check")
        return True

    manifest = read_manifest(manifest_path)
    if manifest is None:
        # read_manifest already logged the reason (missing vs corrupt)
        return True

    stored_checksum = manifest.get("source_checksum")
    if stored_checksum is None:
        logger.warning(
            "Corrupt manifest at %s: missing 'source_checksum' key",
            manifest_path,
        )
        return True

    if not isinstance(stored_checksum, str):
        logger.warning(
            "Corrupt manifest at %s: 'source_checksum' is not a string (got %s)",
            manifest_path,
            type(stored_checksum).__name__,
        )
        return True

    if stored_checksum == current_checksum:
        logger.info(
            "Reusing existing generation (checksum %s matches)",
            _safe_checksum_prefix(current_checksum),
        )
        return False

    logger.info(
        "Source changed, regenerating (stored=%s, current=%s)",
        _safe_checksum_prefix(stored_checksum),
        _safe_checksum_prefix(current_checksum),
    )
    return True


# ============================================================================
# F-001 utility functions (Seed parsing & validation)
# ============================================================================


def parse_seed_input(seed_input: str) -> Dict[str, Any]:
    """Parse a seed input string as JSON.

    Args:
        seed_input: A JSON string representing the seed.

    Returns:
        Parsed JSON object as a dict.

    Raises:
        json.JSONDecodeError: If *seed_input* is not valid JSON.
        ValueError: If the root is not a JSON object.
    """
    data = json.loads(seed_input)
    if not isinstance(data, dict):
        raise ValueError("Seed must be a JSON object at root level")
    return data


def validate_contractor_config(config: Dict[str, Any]) -> None:
    """Validate contractor configuration dict.

    Args:
        config: Configuration dict from seed.

    Raises:
        ValueError: If required fields are missing or invalid.
    """
    if "contractor_class" not in config:
        raise ValueError("Seed must specify 'contractor_class'")


# ============================================================================
# F-001 configuration class
# ============================================================================


class ContractorConfig:
    """Configuration for a contractor instance.

    Attributes:
        contractor_class: Fully qualified class name.
        timeout: Execution timeout in seconds.
        retries: Number of execution retries.
        extra_args: Additional arguments for contractor init.
    """

    def __init__(
        self,
        contractor_class: str,
        timeout: float = DEFAULT_CONTRACTOR_TIMEOUT,
        retries: int = DEFAULT_CONTRACTOR_RETRIES,
        extra_args: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.contractor_class = contractor_class
        self.timeout = timeout
        self.retries = retries
        self.extra_args = extra_args or {}

    @classmethod
    def from_seed(cls, seed: Dict[str, Any]) -> "ContractorConfig":
        """Construct from parsed seed data.

        Args:
            seed: Parsed seed dict.

        Returns:
            ContractorConfig instance.

        Raises:
            ValueError: If seed is missing required fields.
        """
        validate_contractor_config(seed)
        return cls(
            contractor_class=seed["contractor_class"],
            timeout=seed.get("timeout", DEFAULT_CONTRACTOR_TIMEOUT),
            retries=seed.get("retries", DEFAULT_CONTRACTOR_RETRIES),
            extra_args=seed.get("extra_args", {}),
        )


# ============================================================================
# F-002 PrimeContractor (Seed-based contractor execution)
# ============================================================================


class PrimeContractor:
    """Base contractor for seed-based code generation.

    Executes contractor subprocesses that receive seed data and produce
    generated code.  Handles timeout, retries, and manifest management.

    Attributes:
        config: ContractorConfig instance.
    """

    def __init__(self, config: ContractorConfig) -> None:
        """Initialize a PrimeContractor.

        Args:
            config: ContractorConfig instance specifying behaviour.
        """
        self.config = config

    @classmethod
    def from_seed_string(cls, seed_input: str) -> "PrimeContractor":
        """Construct a contractor from a seed JSON string.

        Args:
            seed_input: JSON string containing contractor config.

        Returns:
            PrimeContractor instance.

        Raises:
            json.JSONDecodeError: If *seed_input* is not valid JSON.
            ValueError: If seed structure is invalid.
        """
        seed = parse_seed_input(seed_input)
        config = ContractorConfig.from_seed(seed)
        return cls(config)

    def execute(
        self,
        seed_data: Dict[str, Any],
        output_dir: pathlib.Path,
    ) -> str:
        """Execute the contractor with seed data.

        Runs the contractor subprocess with the given seed, writing
        output to the specified directory.

        Args:
            seed_data: Seed dict to pass to contractor.
            output_dir: Directory for generated output.

        Returns:
            Contractor subprocess output (stdout).

        Raises:
            subprocess.TimeoutExpired: If execution exceeds timeout.
            subprocess.CalledProcessError: If subprocess returns non-zero.
        """
        seed_json = json.dumps(seed_data)
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".json",
            delete=False,
            encoding="utf-8",
        ) as tmp:
            tmp.write(seed_json)
            tmp_path = tmp.name

        try:
            cmd = [
                sys.executable,
                "-m",
                self.config.contractor_class,
                tmp_path,
                str(output_dir),
            ]
            result = subprocess.run(
                cmd,
                timeout=self.config.timeout,
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout
        finally:
            pathlib.Path(tmp_path).unlink(missing_ok=True)


# ============================================================================
# F-011 PrimeContractorWorkflow (Staleness-aware generation orchestration)
# ============================================================================


class PrimeContractorWorkflow:
    """Staleness-aware generation workflow orchestrator.

    Wraps the generation pipeline with staleness detection: before
    regenerating output, computes a SHA-256 checksum of the seed content
    and compares it against the stored ``source_checksum`` in
    ``generation-manifest.json``.  If they match (and ``--force-regenerate``
    is not set), existing output is reused.  Otherwise, regeneration
    proceeds.

    This class is a coordination point for PI-007 integration.  The
    ``_run_generation`` and ``_load_existing_output`` methods are
    extension points to be wired by downstream features.
    """

    def execute(
        self,
        seed_content: str,
        output_dir: pathlib.Path,
        force: bool = False,
    ) -> Any:
        """Run the generation workflow with staleness detection.

        Args:
            seed_content: The seed content string to generate from.
            output_dir:   Directory for generated output and manifest.
            force:        If ``True``, bypass staleness checks and always
                          regenerate (equivalent to ``--force-regenerate``).

        Returns:
            The generation result (type defined by downstream integration).

        Raises:
            ValueError: If path traversal is detected (manifest path
                        escapes *output_dir*).
            NotImplementedError: If ``_run_generation`` or
                                 ``_load_existing_output`` have not been
                                 overridden by downstream features.
        """
        manifest_path = (output_dir / MANIFEST_FILENAME).resolve()
        resolved_output = output_dir.resolve()

        # Path traversal guard — security boundary.
        # Uses relative_to() rather than str.startswith() to avoid the
        # "/foo/bar" vs "/foo/bar-evil" class of false positives.
        try:
            manifest_path.relative_to(resolved_output)
        except ValueError:
            raise ValueError(
                f"Path traversal detected: {manifest_path} is not under "
                f"{resolved_output}"
            )

        current_checksum = compute_source_checksum(seed_content)

        if not should_regenerate(manifest_path, current_checksum, force=force):
            return self._load_existing_output(output_dir)

        # Proceed with generation pipeline.
        # After successful generation, the manifest writer (PI-009 or the
        # generation pipeline) writes source_checksum into the manifest.
        # If generation succeeds but manifest writing fails, the next run
        # will unnecessarily regenerate — safe by design (fail-open).
        result = self._run_generation(seed_content, output_dir)
        return result

    def _load_existing_output(self, output_dir: pathlib.Path) -> Any:
        """Load and return previously generated output.

        Called when staleness detection determines existing output is
        current and can be reused.

        Args:
            output_dir: Directory containing previously generated artifacts.

        Returns:
            The loaded generation result.

        Raises:
            NotImplementedError: Stub — must be overridden by downstream
                                 integration (PI-007).
        """
        raise NotImplementedError(
            "_load_existing_output must be implemented by downstream integration"
        )

    def _run_generation(
        self, seed_content: str, output_dir: pathlib.Path
    ) -> Any:
        """Execute the generation pipeline.

        Called when staleness detection determines regeneration is needed.

        Args:
            seed_content: The seed content string.
            output_dir:   Directory for generated output.

        Returns:
            The generation result.

        Raises:
            NotImplementedError: Stub — must be overridden by downstream
                                 integration (PI-007).
        """
        raise NotImplementedError(
            "_run_generation must be implemented by downstream integration"
        )
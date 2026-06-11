# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""
Local secrets backend — the default, always-on, no-network backend.

It hydrates nothing: the existing env-var + ``~/.startd8/config.json`` resolution
already covers credentials, so ``get_all_secrets()`` returns ``{}`` (FR-9, FR-5a).
``get_secret()`` still answers from the live environment for callers that want a
uniform interface, mirroring today's ``ConfigManager.get_api_key()`` behavior.
"""

import os
from typing import Dict, List, Optional


class LocalSecretsProvider:
    """No-op backend: env/config file remain the source of truth."""

    @property
    def name(self) -> str:
        return "local"

    def get_all_secrets(self) -> Dict[str, str]:
        # Hydrates nothing — env + config file already apply. (FR-9 / FR-5a)
        return {}

    def get_secret(self, key: str) -> Optional[str]:
        # Resolve from the live environment (config-file fallback is handled by
        # ConfigManager for provider keys; this keeps the interface uniform).
        return os.environ.get(key)

    def validate_config(self) -> bool:
        return True

    def get_required_env_vars(self) -> List[str]:
        return []

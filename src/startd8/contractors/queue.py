"""
Feature Queue - Manages the ordered list of features to develop and integrate.

The feature queue ensures:
1. Features are processed in dependency order
2. Each feature's status is tracked (pending, developing, integrating, complete)
3. Failed integrations block dependent features
4. The queue can be persisted and resumed

This module is now part of startd8-sdk and works without ContextCore.
"""

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional


class FeatureStatus(Enum):
    """Status of a feature in the queue."""

    PENDING = "pending"  # Not yet started
    DEVELOPING = "developing"  # Lead contractor is generating code
    GENERATED = "generated"  # Code generated, ready for integration
    INTEGRATING = "integrating"  # Integration in progress
    CHECKPOINT = "checkpoint"  # Running integration checkpoints
    COMPLETE = "complete"  # Fully integrated and validated
    FAILED = "failed"  # Integration failed, needs attention
    BLOCKED = "blocked"  # Blocked by failed dependency


@dataclass
class FeatureSpec:
    """Specification for a feature to be developed."""

    id: str
    name: str
    description: str = ""
    dependencies: List[str] = field(default_factory=list)
    target_files: List[str] = field(default_factory=list)
    status: FeatureStatus = FeatureStatus.PENDING
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error_message: Optional[str] = None
    integration_attempts: int = 0
    generated_files: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, d: Dict) -> "FeatureSpec":
        """Create from dictionary."""
        d = d.copy()
        d["status"] = FeatureStatus(d.get("status", "pending"))
        return cls(**d)


class FeatureQueue:
    """
    Manages the ordered queue of features to develop and integrate.

    Key responsibilities:
    1. Track feature status through the pipeline
    2. Enforce dependency ordering
    3. Block dependent features when integration fails
    4. Persist state for resume capability

    Example:
        queue = FeatureQueue()
        queue.add_feature("feat-1", "Add auth", description="OAuth2 implementation")
        queue.add_feature("feat-2", "Add logout", dependencies=["feat-1"])

        feature = queue.get_next_feature()
        queue.start_feature(feature.id)
        # ... do work ...
        queue.complete_feature(feature.id)
    """

    def __init__(
        self,
        state_file: Optional[Path] = None,
        auto_save: bool = True,
        project_root: Optional[Path] = None,
    ):
        """
        Initialize the feature queue.

        Args:
            state_file: Path to state file for persistence
            auto_save: Whether to auto-save on changes
            project_root: Project root for default state file location
        """
        self.features: Dict[str, FeatureSpec] = {}
        self.order: List[str] = []  # Processing order
        self.auto_save = auto_save

        # Determine state file location
        if state_file:
            self.state_file = state_file
        elif project_root:
            self.state_file = project_root / ".prime_contractor_state.json"
        else:
            self.state_file = Path.cwd() / ".prime_contractor_state.json"

        # Load existing state if available
        if self.state_file.exists():
            self.load_state()

    def add_feature(
        self,
        feature_id: str,
        name: str,
        description: str = "",
        dependencies: Optional[List[str]] = None,
        target_files: Optional[List[str]] = None,
    ) -> FeatureSpec:
        """Add a feature to the queue."""
        spec = FeatureSpec(
            id=feature_id,
            name=name,
            description=description,
            dependencies=dependencies or [],
            target_files=target_files or [],
        )

        self.features[feature_id] = spec
        if feature_id not in self.order:
            self.order.append(feature_id)

        if self.auto_save:
            self.save_state()

        return spec

    def add_features_from_plan(self, plan: Dict) -> List[FeatureSpec]:
        """
        Add features from an integration plan.

        This allows importing features from the lead contractor's
        generated backlog.

        Args:
            plan: Integration plan with "files" list

        Returns:
            List of added features
        """
        added = []

        for item in plan.get("files", []):
            feature_name = item.get("feature", "unknown")
            feature_id = feature_name.replace(" ", "_").lower()

            if feature_id not in self.features:
                spec = self.add_feature(
                    feature_id=feature_id,
                    name=feature_name,
                    target_files=[item.get("target", "")],
                )
                spec.generated_files = [item.get("source", "")]
                spec.status = FeatureStatus.GENERATED
                added.append(spec)

        return added

    def get_next_feature(self) -> Optional[FeatureSpec]:
        """
        Get the next feature to process.

        Returns the first feature that:
        1. Is in PENDING or GENERATED status
        2. Has all dependencies completed
        """
        for feature_id in self.order:
            feature = self.features.get(feature_id)
            if not feature:
                continue

            # Skip completed or failed features
            if feature.status in (
                FeatureStatus.COMPLETE,
                FeatureStatus.FAILED,
                FeatureStatus.BLOCKED,
            ):
                continue

            # Check dependencies
            deps_met = True
            for dep_id in feature.dependencies:
                dep = self.features.get(dep_id)
                if not dep or dep.status != FeatureStatus.COMPLETE:
                    deps_met = False
                    break

            if deps_met and feature.status in (
                FeatureStatus.PENDING,
                FeatureStatus.GENERATED,
            ):
                return feature

        return None

    def start_feature(self, feature_id: str) -> bool:
        """Mark a feature as started (developing)."""
        feature = self.features.get(feature_id)
        if not feature:
            return False

        feature.status = FeatureStatus.DEVELOPING
        feature.started_at = datetime.now().isoformat()

        if self.auto_save:
            self.save_state()

        return True

    def mark_generated(self, feature_id: str, generated_files: List[str]) -> bool:
        """Mark a feature as having generated code."""
        feature = self.features.get(feature_id)
        if not feature:
            return False

        feature.status = FeatureStatus.GENERATED
        feature.generated_files = generated_files

        if self.auto_save:
            self.save_state()

        return True

    def start_integration(self, feature_id: str) -> bool:
        """Mark a feature as being integrated."""
        feature = self.features.get(feature_id)
        if not feature:
            return False

        feature.status = FeatureStatus.INTEGRATING
        feature.integration_attempts += 1

        if self.auto_save:
            self.save_state()

        return True

    def complete_feature(self, feature_id: str) -> bool:
        """Mark a feature as complete."""
        feature = self.features.get(feature_id)
        if not feature:
            return False

        feature.status = FeatureStatus.COMPLETE
        feature.completed_at = datetime.now().isoformat()

        if self.auto_save:
            self.save_state()

        return True

    def fail_feature(self, feature_id: str, error_message: str) -> bool:
        """Mark a feature as failed."""
        feature = self.features.get(feature_id)
        if not feature:
            return False

        feature.status = FeatureStatus.FAILED
        feature.error_message = error_message

        # Block dependent features
        self._block_dependents(feature_id)

        if self.auto_save:
            self.save_state()

        return True

    def _block_dependents(self, failed_feature_id: str):
        """Block all features that depend on a failed feature."""
        for feature_id, feature in self.features.items():
            if failed_feature_id in feature.dependencies:
                if feature.status == FeatureStatus.PENDING:
                    feature.status = FeatureStatus.BLOCKED
                    feature.error_message = (
                        f"Blocked by failed dependency: {failed_feature_id}"
                    )

    def get_status_summary(self) -> Dict[str, int]:
        """Get a summary of feature statuses."""
        summary = {status.value: 0 for status in FeatureStatus}

        for feature in self.features.values():
            summary[feature.status.value] += 1

        return summary

    def get_progress(self) -> float:
        """Get overall progress as a percentage."""
        if not self.features:
            return 0.0

        completed = sum(
            1 for f in self.features.values() if f.status == FeatureStatus.COMPLETE
        )

        return (completed / len(self.features)) * 100

    def save_state(self):
        """Save queue state to file."""
        state = {
            "features": {fid: f.to_dict() for fid, f in self.features.items()},
            "order": self.order,
            "saved_at": datetime.now().isoformat(),
        }

        with open(self.state_file, "w") as f:
            json.dump(state, f, indent=2)

    def load_state(self) -> bool:
        """Load queue state from file."""
        try:
            with open(self.state_file, "r") as f:
                state = json.load(f)

            self.features = {
                fid: FeatureSpec.from_dict(fd)
                for fid, fd in state.get("features", {}).items()
            }
            self.order = state.get("order", [])

            return True
        except (json.JSONDecodeError, IOError):
            return False

    def reset(self):
        """Reset the queue to initial state."""
        for feature in self.features.values():
            feature.status = FeatureStatus.PENDING
            feature.started_at = None
            feature.completed_at = None
            feature.error_message = None
            feature.integration_attempts = 0

        if self.auto_save:
            self.save_state()

    def print_status(self):
        """Print current queue status."""
        print("\n" + "=" * 70)
        print("FEATURE QUEUE STATUS")
        print("=" * 70)

        summary = self.get_status_summary()
        progress = self.get_progress()

        print(
            f"\nProgress: {progress:.1f}% ({summary['complete']}/{len(self.features)} features)"
        )
        print(f"  Pending: {summary['pending']}")
        print(f"  Developing: {summary['developing']}")
        print(f"  Generated: {summary['generated']}")
        print(f"  Integrating: {summary['integrating']}")
        print(f"  Complete: {summary['complete']}")
        print(f"  Failed: {summary['failed']}")
        print(f"  Blocked: {summary['blocked']}")

        print("\nFeature Details:")
        for feature_id in self.order:
            feature = self.features.get(feature_id)
            if not feature:
                continue

            icon = {
                FeatureStatus.PENDING: "○",
                FeatureStatus.DEVELOPING: "◐",
                FeatureStatus.GENERATED: "◑",
                FeatureStatus.INTEGRATING: "◕",
                FeatureStatus.CHECKPOINT: "◔",
                FeatureStatus.COMPLETE: "●",
                FeatureStatus.FAILED: "✗",
                FeatureStatus.BLOCKED: "⊘",
            }.get(feature.status, "?")

            print(f"  {icon} {feature.name} ({feature.status.value})")
            if feature.error_message:
                print(f"      Error: {feature.error_message}")
            if feature.dependencies:
                print(f"      Depends on: {', '.join(feature.dependencies)}")

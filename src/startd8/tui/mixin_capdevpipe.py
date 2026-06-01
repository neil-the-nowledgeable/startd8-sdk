"""CapDevPipeMixin: extracted from tui_improved.py ImprovedTUI (Pass B)."""

from ._shared import *  # noqa: F401,F403

class CapDevPipeMixin:
    def install_capdevpipe_flow(self, config: Optional[Dict[str, Any]] = None):
        """Install & configure cap-dev-pipe into a project (FR-1).

        Standalone-callable: pass a ``config`` dict to run **headless** (no prompts) for the
        future workflow registry and tests (NFR-7 / S8); omit it for the interactive TUI
        flow. All file/shell work is delegated to the TUI-agnostic ``CapDevPipeInstaller``;
        this method only gathers inputs (or accepts them) and renders results. In headless
        mode it returns the ``ExecuteResult`` (or the apply-mode ``VerifyResult``).
        """
        from ..capdevpipe_installer import CapDevPipeInstaller, ReRunMode
        from ..exceptions import Startd8Error

        installer = CapDevPipeInstaller()
        headless = config is not None
        try:
            cfg = (
                self._capdevpipe_cfg_from_dict(config, installer)
                if headless
                else self._capdevpipe_configure(installer)
            )
            if cfg is None:
                return None  # cancelled

            state = installer.detect_existing(cfg.target_root)
            # Existing-install re-run (FR-12). Interactive always prompts for a mode;
            # headless applies an explicitly-requested ``cfg.rerun_mode`` (the registry /
            # library surface, NFR-7). Headless with no rerun_mode falls through to
            # ``execute()``, which is an idempotent "ensure installed" replay.
            if state.exists and (not headless or cfg.rerun_mode is not None):
                mode = cfg.rerun_mode if headless else self._capdevpipe_choose_mode(state)
                if mode is None:
                    return None
                # doctor (FR-17) is a read-only health check: call it directly so its
                # richer dangling-source diagnostic is what we render, not verify()'s.
                if mode is ReRunMode.DOCTOR:
                    vr = installer.doctor(cfg.target_root)
                else:
                    installer.apply_mode(cfg.target_root, mode, cfg)
                    vr = installer.verify(cfg.target_root)
                if not headless:
                    self._capdevpipe_render_verify(cfg, vr, mode=mode)
                self._persist_capdevpipe_prefs(cfg)
                return vr

            actions = installer.plan_actions(cfg)
            if not headless and not self._capdevpipe_preview_confirm(cfg, actions):
                return None

            # FR-13/FR-16 (R4-F5): execute consumes the *previewed* action list, so the list
            # the user confirmed is byte-for-byte the list applied — not an independent recompute.
            result = installer.execute(cfg, actions=actions)
            if not result.success:
                self._capdevpipe_render_failure(result)
                return result

            vr = installer.verify(cfg.target_root)
            if not vr.passed:
                # Verify-failure branch (R3-S4): never present a red verify as success.
                self._capdevpipe_verify_failed(installer, cfg, vr, headless)
                return result
            if not headless:
                self._capdevpipe_render_summary(cfg, vr)
            self._persist_capdevpipe_prefs(cfg)
            return result
        except Startd8Error as exc:
            # Actionable SDK errors (NFR-5): show the message, not a traceback.
            self.console.print(
                Panel(str(exc), title="cap-dev-pipe install", border_style="red")
            )
            if not headless:
                questionary.press_any_key_to_continue().ask()
            if headless:
                raise
            return None

    def _capdevpipe_cfg_from_dict(self, config: Dict[str, Any], installer):
        """Build an InstallConfig from a plain dict for headless runs (S8/NFR-7)."""
        from ..capdevpipe_installer import (
            InstallConfig,
            InstallMethod,
            ProfileSpec,
            ReRunMode,
        )

        source = installer.locate_source(
            Path(config["source_path"]) if config.get("source_path") else None
        )
        profiles = [
            ProfileSpec(
                lang=p["lang"],
                plan=Path(p["plan"]) if p.get("plan") else None,
                reqs=Path(p["reqs"]) if p.get("reqs") else None,
            )
            for p in config.get("profiles", [])
        ]
        cfg = InstallConfig(
            source_path=source,
            target_root=Path(config["target_root"]).expanduser(),
            method=InstallMethod(config.get("method", "symlink")),
            pipeline_env=dict(config.get("pipeline_env", {})),
            default_lang=config.get("default_lang", "python"),
            profiles=profiles,
        )
        # FR-12 via the headless surface: honor an explicitly-requested re-run mode so the
        # workflow registry can drive upgrade/repair/reconfigure/replace-env on an existing
        # install (previously the field was silently dropped — a dark feature).
        if config.get("rerun_mode"):
            cfg.rerun_mode = ReRunMode(config["rerun_mode"])
        cfg.pipeline_env = installer.detect_pipeline_env(cfg)
        return cfg

    def _capdevpipe_configure(self, installer):
        """Interactive prompts → InstallConfig, or None on cancel (FR-2/3/4/7/8/9)."""
        from ..capdevpipe_installer import (
            DEFAULT_SOURCE,
            InstallConfig,
            InstallMethod,
            PREF_INSTALL_METHOD,
            PREF_SOURCE_PATH,
        )
        from ..config import get_config_manager

        prefs = get_config_manager()
        default_source = prefs.get_preference(PREF_SOURCE_PATH) or str(DEFAULT_SOURCE)
        source_str = self._safe_path_input(
            "cap-dev-pipe source checkout:", default=default_source, only_directories=True
        )
        if not source_str:
            return None
        source = installer.locate_source(Path(source_str))  # validates (FR-2)

        target_str = self._safe_path_input(
            "Target project root:", default=str(Path.cwd()), only_directories=True
        )
        if not target_str:
            return None
        target = Path(target_str).expanduser()

        default_method = prefs.get_preference(PREF_INSTALL_METHOD) or "symlink"
        method_choice = questionary.select(
            "Install method:",
            choices=[
                "symlink (single source of truth; recommended)",
                "copy (self-contained; drifts)",
            ],
            default=(
                "symlink (single source of truth; recommended)"
                if default_method == "symlink"
                else "copy (self-contained; drifts)"
            ),
            style=custom_style,
        ).ask()
        if not method_choice:
            return None
        method = InstallMethod.SYMLINK if "symlink" in method_choice else InstallMethod.COPY

        default_lang = questionary.text(
            "Default language for the wrapper:", default="python", style=custom_style
        ).ask()
        if default_lang is None:
            return None

        cfg = InstallConfig(
            source_path=source,
            target_root=target,
            method=method,
            pipeline_env={},
            default_lang=default_lang or "python",
            profiles=[],
        )
        # Detect + confirm pipeline.env (FR-7).
        cfg.pipeline_env = self._capdevpipe_confirm_env(installer, cfg)
        if cfg.pipeline_env is None:
            return None
        # Profiles from detected docs (FR-9).
        cfg.profiles = self._capdevpipe_select_profiles(installer, target)
        return cfg

    def _capdevpipe_confirm_env(self, installer, cfg):
        """Detect the four managed keys and let the user confirm/edit each (FR-7)."""
        detected = installer.detect_pipeline_env(cfg)
        confirmed: Dict[str, str] = {}
        for key in ("CONTEXTCORE_ROOT", "SDK_ROOT", "PROJECT_ROOT", "PROJECT_NAME"):
            value = questionary.text(
                f"{key}:", default=detected.get(key, ""), style=custom_style
            ).ask()
            if value is None:
                return None
            confirmed[key] = value
        return confirmed

    def _capdevpipe_select_profiles(self, installer, target):
        """Let the user wire detected plan/requirements docs into language profiles (FR-9)."""
        from ..capdevpipe_installer import ProfileSpec

        candidates = installer.detect_doc_candidates(target)
        profiles = []
        while True:
            add = questionary.confirm(
                "Add a language profile (wire plan/requirements docs)?",
                default=not profiles,
                style=custom_style,
            ).ask()
            if not add:
                break
            lang = questionary.text("Language name (e.g. python):", style=custom_style).ask()
            if not lang:
                break
            plan = self._capdevpipe_pick_doc("plan", candidates.plans)
            reqs = self._capdevpipe_pick_doc("requirements", candidates.reqs)
            profiles.append(ProfileSpec(lang=lang, plan=plan, reqs=reqs))
        return profiles

    def _capdevpipe_pick_doc(self, kind, docs):
        """Pick one detected doc (or skip)."""
        if not docs:
            return None
        choices = [str(d) for d in docs] + ["← skip"]
        picked = questionary.select(
            f"Choose the {kind} doc:", choices=choices, style=custom_style
        ).ask()
        if not picked or picked == "← skip":
            return None
        return Path(picked)

    def _capdevpipe_choose_mode(self, state):
        """Choose a re-run mode for an existing install (FR-12)."""
        from ..capdevpipe_installer import ReRunMode

        note = " [pending — prior run may have crashed]" if state.pending else ""
        self.console.print(
            Panel(
                f"An existing .cap-dev-pipe/ install was detected{note}.",
                title="cap-dev-pipe re-run",
                border_style="yellow",
            )
        )
        mapping = {
            "repair (recreate missing/broken, then verify)": ReRunMode.REPAIR,
            "upgrade (refresh scripts; prune orphans)": ReRunMode.UPGRADE,
            "reconfigure (rewrite config/profiles)": ReRunMode.RECONFIGURE,
            "replace-pipeline.env (rewrite managed keys)": ReRunMode.REPLACE_PIPELINE_ENV,
            "doctor (check for a moved/deleted source)": ReRunMode.DOCTOR,
            "← cancel": None,
        }
        picked = questionary.select(
            "How would you like to proceed?",
            choices=list(mapping.keys()),
            style=custom_style,
        ).ask()
        return mapping.get(picked) if picked else None

    def _capdevpipe_preview_confirm(self, cfg, actions) -> bool:
        """Render the planned action list (FR-13) and require confirmation (NFR-2)."""
        lines = "\n".join(f"  • {a.describe()}" for a in actions)
        self.console.print(
            Panel(
                f"[bold]Target:[/bold] {cfg.target_root}\n"
                f"[bold]Method:[/bold] {cfg.method.value}\n"
                f"[bold]Planned actions ({len(actions)}):[/bold]\n{lines}",
                title="cap-dev-pipe install — preview",
                border_style="cyan",
            )
        )
        return bool(
            questionary.confirm("Proceed with these actions?", default=True, style=custom_style).ask()
        )

    def _capdevpipe_render_failure(self, result):
        """Render an execute() failure (FR-16 rollback / repairable states)."""
        tail = (
            "Rolled back cleanly."
            if result.rolled_back
            else "Left repairable — re-run and choose 'repair'."
            if result.repairable
            else ""
        )
        self.console.print(
            Panel(
                f"[red]Install failed:[/red] {result.error}\n{tail}",
                title="cap-dev-pipe install",
                border_style="red",
            )
        )
        questionary.press_any_key_to_continue().ask()

    def _capdevpipe_verify_failed(self, installer, cfg, vr, headless):
        """Verify-failure branch (R3-S4): surface the failure, offer repair (manifest-driven)."""
        from ..capdevpipe_installer import ReRunMode

        self.console.print(
            Panel(
                f"[yellow]Install wrote files but verification failed:[/yellow]\n{vr.message}",
                title="cap-dev-pipe verify",
                border_style="yellow",
            )
        )
        if headless:
            return
        if questionary.confirm("Attempt repair now?", default=True, style=custom_style).ask():
            installer.apply_mode(cfg.target_root, ReRunMode.REPAIR, cfg)
            vr2 = installer.verify(cfg.target_root)
            self._capdevpipe_render_verify(cfg, vr2, mode=ReRunMode.REPAIR)
        else:
            questionary.press_any_key_to_continue().ask()

    def _capdevpipe_render_verify(self, cfg, vr, mode=None):
        """Render a verify result after an apply-mode/repair (FR-11/FR-12)."""
        colour = "green" if vr.passed else "red"
        status = "PASSED" if vr.passed else "FAILED"
        label = f" ({mode.value})" if mode else ""
        self.console.print(
            Panel(
                f"[{colour}]Verify {status}{label}[/{colour}]\n{vr.message}",
                title="cap-dev-pipe",
                border_style=colour,
            )
        )
        questionary.press_any_key_to_continue().ask()

    def _capdevpipe_render_summary(self, cfg, vr):
        """Render the success summary + the exact next command (FR-14)."""
        wrapper = f"./.cap-dev-pipe/{cfg.target_root.name}-cap-dlv-pipe.sh"
        table = Table(title="cap-dev-pipe installed")
        table.add_column("What", style="cyan")
        table.add_column("Value", style="white")
        table.add_row("Method", cfg.method.value)
        table.add_row("Target", str(cfg.target_root))
        table.add_row("Profiles", ", ".join(vr.expected_langs) or "(none)")
        table.add_row("Verify", vr.message)
        self.console.print(table)
        self.console.print(
            Panel(
                f"[bold]Run the pipeline with:[/bold]\n  {wrapper}",
                title="Next steps",
                border_style="green",
            )
        )
        questionary.press_any_key_to_continue().ask()

    def _persist_capdevpipe_prefs(self, cfg):
        """Remember source path + install method for next time (FR-15)."""
        from ..capdevpipe_installer import PREF_INSTALL_METHOD, PREF_SOURCE_PATH
        from ..config import get_config_manager

        try:
            prefs = get_config_manager()
            prefs.set_preference(PREF_SOURCE_PATH, str(cfg.source_path))
            prefs.set_preference(PREF_INSTALL_METHOD, cfg.method.value)
        except Exception:  # pragma: no cover - pref persistence is best-effort
            pass

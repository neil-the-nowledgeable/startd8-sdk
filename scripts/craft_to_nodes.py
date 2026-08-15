#!/usr/bin/env python3
"""craft_to_nodes — READ-ONLY projector: renders the user's KNOWLEDGE corpus through the
startd8-sdk navigator as a node graph.

Three regions → three layer nodes under a "Craft" root:
  · Design Principles  (craft/design_principles/*.md)
  · Lessons_Learned    (domain dirs → domain nodes → topic files)
  · Skills             (~/.claude/skills/*/SKILL.md)

Emits a self-contained HTML tree to /tmp/craft-node-graph.html. Zero writes to craft/.

    python3 scripts/craft_to_nodes.py
    python3 scripts/craft_to_nodes.py --out /tmp/my-graph.html
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import List, Optional

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from startd8.navigator.models import Node, NodeEvidence, NodeStatus  # noqa: E402
from startd8.navigator.render_tree import render_navigator_tree_html  # noqa: E402

# ── paths ──────────────────────────────────────────────────────────────────────
CRAFT_ROOT = Path.home() / "Documents" / "craft"
PRINCIPLES_DIR = CRAFT_ROOT / "design_principles"
LESSONS_DIR = CRAFT_ROOT / "Lessons_Learned"
SKILLS_DIR = Path.home() / ".claude" / "skills"

# ── helpers ────────────────────────────────────────────────────────────────────

def _first_h1(path: Path) -> Optional[str]:
    """Return the first # heading text from a Markdown file, or None."""
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if line.startswith("# "):
                return line[2:].strip()
    except OSError:
        pass
    return None


def _first_sentence(text: str) -> str:
    """Return the first sentence (up to first . / ! / ?), truncated to 140 chars."""
    text = text.strip()
    m = re.search(r"[.!?]", text)
    if m:
        text = text[: m.end()].strip()
    return text[:140] if len(text) > 140 else text


def _in_one_sentence(path: Path) -> Optional[str]:
    """Find the 'In one sentence' section value in a principle file."""
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
        # Look for a heading "In one sentence" and grab the next non-blank line
        m = re.search(r"##\s+In one sentence\s*\n+(.+)", content)
        if m:
            return m.group(1).strip()[:200]
    except OSError:
        pass
    return None


def _yaml_field(path: Path, field: str) -> Optional[str]:
    """Extract a YAML frontmatter field (handles multi-line > folded scalars)."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    # Find frontmatter block
    m = re.match(r"---\n(.*?)\n---", text, re.DOTALL)
    if not m:
        return None
    fm = m.group(1)
    # Try simple single-line value
    single = re.search(rf"^{re.escape(field)}:\s*(.+)$", fm, re.MULTILINE)
    if single:
        val = single.group(1).strip()
        if val.startswith(">"):
            # folded scalar — grab indented continuation lines
            idx = fm.find(single.group(0))
            rest = fm[idx + len(single.group(0)):]
            lines = []
            for ln in rest.splitlines():
                if ln.startswith("  "):
                    lines.append(ln.strip())
                elif ln.strip() == "":
                    continue
                else:
                    break
            return " ".join(lines)
        if val not in ('|', '>'):
            return val
    # Multi-line key: field: |\n  ...
    block = re.search(rf"^{re.escape(field)}:\s*[|>]\s*\n((?:  .+\n?)+)", fm, re.MULTILINE)
    if block:
        lines = [ln.strip() for ln in block.group(1).splitlines() if ln.strip()]
        return " ".join(lines)
    return None


def _node(key: str, does: str, *, status: str, ref: str, ref_type: str = "doc",
          layer: str, children: tuple = (), **attrs) -> Node:
    attributes = {"layer": layer}
    attributes.update(attrs)
    return Node(
        key=key,
        does=does,
        status=status,
        category=layer,
        lives=(NodeEvidence(type=ref_type, ref=ref),),
        children=children,
        attributes=attributes,
    )


# ── region projectors ──────────────────────────────────────────────────────────

def project_principles() -> List[Node]:
    """One Node per *.md file in craft/design_principles/."""
    nodes: List[Node] = []
    if not PRINCIPLES_DIR.is_dir():
        return nodes
    for md in sorted(PRINCIPLES_DIR.glob("*.md")):
        # Extract name from filename: KAGAMI_DESIGN_PRINCIPLE.md → Kagami
        stem = md.stem  # e.g. KAGAMI_DESIGN_PRINCIPLE
        name_part = stem.replace("_DESIGN_PRINCIPLE", "").replace("_", " ").title()
        # Try to get "In one sentence" paragraph
        does = _in_one_sentence(md)
        if not does:
            # Fall back to H1 text
            h1 = _first_h1(md)
            does = h1 or name_part
        # Truncate
        does = does[:200]
        nodes.append(_node(
            key=f"principle.{stem.lower()}",
            does=does,
            status=NodeStatus.BUILT,
            ref=str(md),
            layer="principle",
        ))
    return nodes


def _project_topic_files(lessons_subdir: Path, domain_key: str) -> List[Node]:
    """Project lesson topic files from <domain>/lessons/ into child nodes."""
    lessons_subpath = lessons_subdir / "lessons"
    if not lessons_subpath.is_dir():
        return []
    nodes: List[Node] = []
    for md in sorted(lessons_subpath.glob("*.md")):
        h1 = _first_h1(md)
        # Extract a short topic name from filename (e.g. 01-benchmarking.md → benchmarking)
        stem = md.stem  # e.g. 01-benchmarking
        topic_slug = re.sub(r"^\d+-", "", stem)  # strip numeric prefix
        if h1:
            # Strip "Leg N: " prefix if present
            h1_clean = re.sub(r"^Leg\s+\d+:\s*", "", h1).strip()
            does = h1_clean
        else:
            does = topic_slug.replace("-", " ").title()
        nodes.append(_node(
            key=f"lesson.{domain_key}.{topic_slug}",
            does=does[:200],
            status=NodeStatus.BUILT,
            ref=str(md),
            layer="lesson-topic",
            topic=topic_slug,
        ))
    return nodes


def project_lessons() -> List[Node]:
    """One domain Node per subdir that contains a *LESSONS_LEARNED.md index file.
    Design_Docs_LESSONS_LEARNED siblings are folded under their parent domain."""
    if not LESSONS_DIR.is_dir():
        return []

    domain_nodes: List[Node] = []

    for domain_dir in sorted(LESSONS_DIR.iterdir()):
        if not domain_dir.is_dir():
            continue
        # Skip utility dirs
        if domain_dir.name in ("archive", "commands", "index", "design", "untitled folder"):
            continue

        # Find the primary LESSONS_LEARNED.md (not Design_Docs_*)
        primary_index: Optional[Path] = None
        design_docs_index: Optional[Path] = None
        for md in domain_dir.glob("*LESSONS_LEARNED.md"):
            if "Design_Docs" in md.name:
                design_docs_index = md
            else:
                primary_index = md

        if not primary_index:
            continue  # No primary index — skip

        # Extract domain title from H1
        h1 = _first_h1(primary_index)
        # Fall back to dir name formatted
        domain_title = h1 or domain_dir.name.replace("_", " ").title()
        # Shorten: "SDK Developer Lessons Learned" → "SDK Developer Lessons Learned"
        does_raw = h1 or domain_title
        # Get the first sentence / short summary from the file
        try:
            body = primary_index.read_text(encoding="utf-8", errors="replace")
            # Find first meaningful paragraph after the heading
            lines = [ln.strip() for ln in body.splitlines() if ln.strip() and not ln.startswith("#")]
            does = _first_sentence(lines[0]) if lines else does_raw
        except OSError:
            does = does_raw

        domain_key = domain_dir.name.lower().replace(" ", "_")

        # Project topic files as children
        topic_children = tuple(_project_topic_files(domain_dir, domain_key))

        # Optionally add Design Docs child node
        design_child: tuple = ()
        if design_docs_index:
            dd_h1 = _first_h1(design_docs_index)
            dd_does = dd_h1 or "Design documentation craft lessons for this domain"
            design_child = (
                _node(
                    key=f"lesson.{domain_key}.design-docs",
                    does=dd_does[:200],
                    status=NodeStatus.BUILT,
                    ref=str(design_docs_index),
                    layer="lesson-topic",
                    topic="design-docs",
                ),
            )

        all_children = topic_children + design_child

        domain_nodes.append(_node(
            key=f"lesson.{domain_key}",
            does=does[:200],
            status=NodeStatus.BUILT,
            ref=str(primary_index),
            layer="lesson-domain",
            domain=domain_dir.name,
            topic_count=str(len(all_children)),
            children=all_children,
        ))

    return domain_nodes


def project_skills() -> List[Node]:
    """One Node per skill dir that contains a SKILL.md with name + description frontmatter."""
    if not SKILLS_DIR.is_dir():
        return []
    nodes: List[Node] = []
    for skill_dir in sorted(SKILLS_DIR.iterdir()):
        if not skill_dir.is_dir():
            continue
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.is_file():
            continue  # workspace dirs, etc.

        name = _yaml_field(skill_md, "name") or skill_dir.name
        description_raw = _yaml_field(skill_md, "description") or ""
        does = _first_sentence(description_raw) if description_raw else f"Skill: {name}"

        # Determine status: check tags for "draft" indicators
        tags_raw = _yaml_field(skill_md, "tags") or ""
        version_raw = _yaml_field(skill_md, "version") or ""
        is_draft = "draft" in tags_raw.lower() or version_raw.startswith("0.0")
        status = NodeStatus.THIN if is_draft else NodeStatus.BUILT

        nodes.append(_node(
            key=f"skill.{name}",
            does=does[:200],
            status=status,
            ref=str(skill_md),
            layer="skill",
            invoke=_yaml_field(skill_md, "invoke") or "",
        ))

    return nodes


# ── assembly ───────────────────────────────────────────────────────────────────

def build_craft_tree() -> List[Node]:
    principle_nodes = project_principles()
    lesson_domain_nodes = project_lessons()
    skill_nodes = project_skills()

    # Count sub-artifacts for each layer
    n_principles = len(principle_nodes)
    n_lesson_domains = len(lesson_domain_nodes)
    n_skills = len(skill_nodes)

    principles_layer = Node(
        key="craft.design-principles",
        does="Cross-repo design principles — named operating rules for human+agent work",
        status=NodeStatus.BUILT,
        category="layer",
        children=tuple(principle_nodes),
        attributes={
            "layer": "layer",
            "count": str(n_principles),
            "readiness": f"{n_principles} principles",
        },
        lives=(NodeEvidence(type="doc", ref=str(PRINCIPLES_DIR)),),
    )

    lessons_layer = Node(
        key="craft.lessons-learned",
        does="Accumulated domain lessons — indexed by domain, drillable to topic files",
        status=NodeStatus.BUILT,
        category="layer",
        children=tuple(lesson_domain_nodes),
        attributes={
            "layer": "layer",
            "count": str(n_lesson_domains),
            "readiness": f"{n_lesson_domains} domains",
        },
        lives=(NodeEvidence(type="doc", ref=str(LESSONS_DIR)),),
    )

    skills_layer = Node(
        key="craft.skills",
        does="Packaged agent skills (~/.claude/skills/) — named, versioned, invocable capabilities",
        status=NodeStatus.BUILT,
        category="layer",
        children=tuple(skill_nodes),
        attributes={
            "layer": "layer",
            "count": str(n_skills),
            "readiness": f"{n_skills} skills",
        },
        lives=(NodeEvidence(type="doc", ref=str(SKILLS_DIR)),),
    )

    total_nodes = 1 + 3 + n_principles + n_lesson_domains + n_skills
    # Count topic children too
    for dn in lesson_domain_nodes:
        total_nodes += len(dn.children)

    root = Node(
        key="craft",
        does="The knowledge corpus — design principles · accumulated lessons · packaged skills",
        status=NodeStatus.BUILT,
        category="root",
        children=(principles_layer, lessons_layer, skills_layer),
        attributes={
            "layer": "root",
            "kind": "intro",
            "description": (
                "Three knowledge regions projected to NODE-SCHEMA: design principles (cross-repo "
                "operating rules), lessons learned (domain-indexed accumulated wisdom), and skills "
                "(invocable packaged capabilities). Browse by layer or search across all nodes."
            ),
            "readiness": (
                f"{n_principles} principles · {n_lesson_domains} lesson-domains · {n_skills} skills"
            ),
        },
        lives=(NodeEvidence(type="doc", ref=str(CRAFT_ROOT)),),
    )
    return [root]


# ── main ───────────────────────────────────────────────────────────────────────

def _count_tree(nodes: List[Node]) -> int:
    return sum(1 + _count_tree(list(n.children)) for n in nodes)


def main(argv) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=Path("/tmp/craft-node-graph.html"))
    args = ap.parse_args(argv[1:])

    roots = build_craft_tree()
    total = _count_tree(roots)

    out = render_navigator_tree_html(
        roots,
        args.out,
        title="Craft — the knowledge corpus as a node graph",
        subtitle="principles · lessons · skills, projected to NODE-SCHEMA",
        open_depth=2,
    )

    # Report counts
    craft_root = roots[0]
    layers = {child.key: child for child in craft_root.children}
    n_principles = int(layers.get("craft.design-principles", Node(key="", does="", attributes={"count": "0"})).attributes.get("count", 0))
    n_lesson_domains = int(layers.get("craft.lessons-learned", Node(key="", does="", attributes={"count": "0"})).attributes.get("count", 0))
    n_skills = int(layers.get("craft.skills", Node(key="", does="", attributes={"count": "0"})).attributes.get("count", 0))

    print(f"wrote {out}")
    print(f"total nodes: {total}")
    print(f"  principles: {n_principles}")
    print(f"  lesson-domains: {n_lesson_domains}")
    print(f"  skills: {n_skills}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

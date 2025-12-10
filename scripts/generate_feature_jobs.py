#!/usr/bin/env python3
"""
Generate Job Files for Flower Defense V2 Features

This script reads the master plan and generates job files for the startd8
job queue to process features sequentially.

Usage:
    # Generate just Feature 1 (to start)
    python scripts/generate_feature_jobs.py --feature 1
    
    # Generate all features (Feature 9 last as requested)
    python scripts/generate_feature_jobs.py --all
    
    # Generate specific features
    python scripts/generate_feature_jobs.py --features 1 2 3
"""

import argparse
import json
import uuid
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Any


# Paths from master plan
AGENT_PLANS_DIR = Path("/Users/neilyashinsky/Documents/FMLs/dev/play/version2/plan/agent_plans")
GAME_REPO = Path("/Users/neilyashinsky/Documents/FMLs/dev/reface/repo/forcemultiplierlabs")
DEFAULT_OUTPUT_DIR = Path.home() / "startd8-jobs" / "flower-defense-v2"

# Feature metadata (from master plan)
FEATURES = {
    1: {
        "file": "1_feature_1_high_score.md",
        "title": "Session High Score Storage",
        "effort": "2-3 hrs",
        "disruption": "low",
        "depends_on": [9],
        "priority": 8  # High priority, but after Feature 9
    },
    2: {
        "file": "1_feature_2_initials_entry.md",
        "title": "Initials Entry",
        "effort": "4-6 hrs",
        "disruption": "low",
        "depends_on": [1],
        "priority": 7
    },
    3: {
        "file": "1_feature_3_pink_trebuchet.md",
        "title": "Pink Trebuchet Style",
        "effort": "3-4 hrs",
        "disruption": "low",
        "depends_on": [],
        "priority": 6
    },
    8: {
        "file": "1_feature_8_game_messages.md",
        "title": "Periodic Game Messages",
        "effort": "4-6 hrs",
        "disruption": "low",
        "depends_on": [],
        "priority": 5
    },
    4: {
        "file": "2_feature_4_style_selector.md",
        "title": "Trebuchet Style Selector",
        "effort": "6-8 hrs",
        "disruption": "medium",
        "depends_on": [3],
        "priority": 4
    },
    5: {
        "file": "2_feature_5_level_5_ammo.md",
        "title": "Level 5 Limited Ammo",
        "effort": "4-6 hrs",
        "disruption": "medium",
        "depends_on": [],
        "priority": 3
    },
    6: {
        "file": "2_feature_6_continue_progress.md",
        "title": "Continue from Last Level",
        "effort": "3-4 hrs",
        "disruption": "medium",
        "depends_on": [1],
        "priority": 2
    },
    7: {
        "file": "3_feature_7_cat_powerup.md",
        "title": "Cat Power-Up System",
        "effort": "8-12 hrs",
        "disruption": "high",
        "depends_on": [],
        "priority": 1
    },
    9: {
        "file": "4_feature_9_arcade_mode.md",
        "title": "Arcade Mode Architecture",
        "effort": "12-16 hrs",
        "disruption": "critical",
        "depends_on": [],
        "priority": 10  # HIGHEST - do first
    }
}

# Correct implementation order (Feature 9 first, Feature 7 last)
IMPLEMENTATION_ORDER = [9, 1, 2, 3, 8, 4, 5, 6, 7]


def read_feature_plan(feature_num: int) -> str:
    """Read the feature plan file content"""
    metadata = FEATURES[feature_num]
    file_path = AGENT_PLANS_DIR / metadata["file"]
    
    if not file_path.exists():
        raise FileNotFoundError(f"Feature plan not found: {file_path}")
    
    return file_path.read_text(encoding='utf-8')


def create_job_file_content(
    feature_num: int,
    agent: str = "claude"
) -> Dict[str, Any]:
    """Create job file content for a feature"""
    
    metadata = FEATURES[feature_num]
    plan_content = read_feature_plan(feature_num)
    
    # Build the prompt for the agent
    prompt_content = f"""# Development Task: {metadata['title']}

## Context

You are implementing Feature {feature_num} for Flower Defense V2, a TypeScript/React game.

**Game Repository:** {GAME_REPO}

**Important:** This is feature development work. You will need to:
1. Read and understand the feature plan below
2. Examine the existing codebase structure
3. Implement the feature according to the specifications
4. Ensure all code follows TypeScript best practices
5. Test the implementation

## Dependencies

{f"This feature depends on: Feature(s) {', '.join(map(str, metadata['depends_on']))}" if metadata['depends_on'] else "This feature has no dependencies"}

## Feature Plan

{plan_content}

## Implementation Requirements

1. **Follow the Implementation Steps** exactly as outlined in the plan
2. **Maintain TypeScript Types** - All code must be properly typed
3. **Follow Existing Patterns** - Match the style of the existing codebase
4. **Test Thoroughly** - Verify the feature works on desktop and mobile
5. **No Console Errors** - Ensure clean console output
6. **Performance** - Maintain 60 FPS performance
7. **Accessibility** - Include ARIA attributes where applicable

## File Locations

- Source code: `{GAME_REPO}/src/`
- Components: `{GAME_REPO}/src/components/`
- Utilities: `{GAME_REPO}/src/utils/`
- Hooks: `{GAME_REPO}/src/hooks/`
- Styles: `{GAME_REPO}/src/styles/`

## Output Format

Please provide:
1. All file changes needed (full file contents)
2. Brief explanation of what was implemented
3. Any edge cases or considerations
4. Testing steps to verify the feature works

## Begin Implementation

Please implement this feature now.
"""
    
    # Create job file structure
    job_data = {
        "job_id": f"feature-{feature_num}-{uuid.uuid4().hex[:8]}",
        "prompt": {
            "content": prompt_content,
            "version": "1.0.0",
            "tags": [
                "flower-defense",
                "v2",
                f"feature-{feature_num}",
                metadata['disruption'],
                "implementation"
            ],
            "metadata": {
                "feature_num": feature_num,
                "feature_title": metadata['title'],
                "effort_estimate": metadata['effort'],
                "disruption_level": metadata['disruption'],
                "depends_on": metadata['depends_on'],
                "game_repo": str(GAME_REPO)
            }
        },
        "agents": [agent],
        "priority": metadata['priority'],
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "metadata": {
            "feature_num": feature_num,
            "project": "flower-defense-v2",
            "plan_file": metadata['file']
        }
    }
    
    return job_data


def save_job_file(job_data: Dict[str, Any], output_dir: Path) -> Path:
    """Save job file to disk"""
    output_dir.mkdir(parents=True, exist_ok=True)
    
    feature_num = job_data['metadata']['feature_num']
    job_id = job_data['job_id']
    
    # Create filename: feature_N_title.json
    filename = f"feature_{feature_num:02d}_{FEATURES[feature_num]['title'].lower().replace(' ', '_')}.json"
    file_path = output_dir / filename
    
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(job_data, f, indent=2, ensure_ascii=False)
    
    return file_path


def generate_feature_jobs(
    feature_nums: List[int],
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    agent: str = "claude"
) -> List[Path]:
    """Generate job files for specified features"""
    
    created_files = []
    
    for feature_num in feature_nums:
        if feature_num not in FEATURES:
            print(f"⚠️  Warning: Unknown feature number {feature_num}, skipping")
            continue
        
        try:
            job_data = create_job_file_content(feature_num, agent)
            file_path = save_job_file(job_data, output_dir)
            created_files.append(file_path)
            
            metadata = FEATURES[feature_num]
            print(f"✓ Created: {file_path.name}")
            print(f"  Feature {feature_num}: {metadata['title']}")
            print(f"  Priority: {metadata['priority']} | Effort: {metadata['effort']}")
            print()
            
        except Exception as e:
            print(f"✗ Error creating job for Feature {feature_num}: {e}")
            print()
    
    return created_files


def generate_readme(output_dir: Path, feature_nums: List[int]):
    """Generate README for the job files"""
    
    readme_content = f"""# Flower Defense V2 - Feature Development Jobs

Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Overview

This directory contains job files for implementing Flower Defense V2 features
using the startd8 agent framework.

## Features to Implement

"""
    
    for i, feature_num in enumerate(feature_nums, 1):
        metadata = FEATURES[feature_num]
        deps = f" (depends on: {', '.join(map(str, metadata['depends_on']))})" if metadata['depends_on'] else ""
        readme_content += f"{i}. **Feature {feature_num}**: {metadata['title']} - {metadata['effort']}{deps}\n"
    
    readme_content += f"""
## Implementation Order

Jobs should be processed in priority order (highest first):

"""
    
    sorted_features = sorted(feature_nums, key=lambda f: FEATURES[f]['priority'], reverse=True)
    for i, feature_num in enumerate(sorted_features, 1):
        metadata = FEATURES[feature_num]
        readme_content += f"{i}. Feature {feature_num}: {metadata['title']} (priority: {metadata['priority']})\n"
    
    readme_content += f"""
## How to Use

### Option 1: Using startd8 TUI

1. Launch startd8 TUI:
   ```bash
   startd8
   ```

2. Navigate to: **📥 Job Queue**

3. Configure queue folder to: `{output_dir}`

4. Process queue:
   - **Process Queue** - Process all jobs in priority order
   - **Process Single Job** - Process one job at a time

### Option 2: Using startd8 Job Queue API

```python
from startd8 import JobQueue, JobQueueConfig
from pathlib import Path

# Configure queue
config = JobQueueConfig(
    watch_folder=Path("{output_dir}"),
    poll_interval_seconds=5.0,
    default_agents=["claude"]
)

# Create queue
queue = JobQueue(config, framework)

# Process all jobs
results = queue.process_all()

# Check results
for result in results:
    print(f"Job {{result.job_id}}: {{result.status}}")
```

### Option 3: Manual Processing

1. Open each job file
2. Copy the prompt content
3. Send to your preferred AI agent
4. Apply the generated code to the game repository

## File Structure

Each job file contains:
- `job_id`: Unique identifier
- `prompt`: The full development task with context
- `agents`: Which agent(s) to use
- `priority`: Processing order (higher = first)
- `status`: Current status (pending/processing/completed/failed)
- `metadata`: Feature information

## Game Repository

**Location:** `{GAME_REPO}`

Make sure the agent has access to this repository to implement features.

## Notes

- Feature 9 (Arcade Mode Architecture) should be done FIRST as it's foundational
- Feature 7 (Cat Power-Up) should be done LAST as it's high disruption
- Some features depend on others - check the `depends_on` field
- All implementations must maintain TypeScript types and existing patterns
- Test thoroughly on both desktop and mobile

## Quality Standards

All implementations must:
- ✓ Follow existing code patterns
- ✓ Include TypeScript types
- ✓ Work on desktop and mobile
- ✓ Have no console errors
- ✓ Maintain 60 FPS performance
- ✓ Include accessibility attributes

---

*Generated by startd8 feature job generator*
"""
    
    readme_path = output_dir / "README.md"
    readme_path.write_text(readme_content, encoding='utf-8')
    print(f"✓ Created README: {readme_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Generate job files for Flower Defense V2 features",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate just Feature 1
  python scripts/generate_feature_jobs.py --feature 1
  
  # Generate all features (correct order: 9 first, 7 last)
  python scripts/generate_feature_jobs.py --all
  
  # Generate specific features
  python scripts/generate_feature_jobs.py --features 1 2 3
  
  # Use different agent
  python scripts/generate_feature_jobs.py --all --agent gpt4
  
  # Custom output directory
  python scripts/generate_feature_jobs.py --all --output ~/my-jobs
        """
    )
    
    parser.add_argument(
        '--feature',
        type=int,
        help='Generate job for a single feature (e.g., 1, 2, 3)'
    )
    
    parser.add_argument(
        '--features',
        type=int,
        nargs='+',
        help='Generate jobs for multiple features (e.g., 1 2 3)'
    )
    
    parser.add_argument(
        '--all',
        action='store_true',
        help='Generate jobs for all features (correct order: 9 first, 7 last)'
    )
    
    parser.add_argument(
        '--agent',
        default='claude',
        help='Agent to use (default: claude)'
    )
    
    parser.add_argument(
        '--output',
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f'Output directory (default: {DEFAULT_OUTPUT_DIR})'
    )
    
    args = parser.parse_args()
    
    # Determine which features to generate
    if args.all:
        feature_nums = IMPLEMENTATION_ORDER
        print("Generating job files for ALL features (Feature 9 first, Feature 7 last)...\n")
    elif args.features:
        feature_nums = args.features
        print(f"Generating job files for features: {', '.join(map(str, feature_nums))}...\n")
    elif args.feature:
        feature_nums = [args.feature]
        print(f"Generating job file for Feature {args.feature}...\n")
    else:
        parser.print_help()
        return
    
    # Generate job files
    created_files = generate_feature_jobs(
        feature_nums=feature_nums,
        output_dir=args.output,
        agent=args.agent
    )
    
    if created_files:
        # Generate README
        generate_readme(args.output, feature_nums)
        
        print("\n" + "=" * 60)
        print(f"✓ Successfully created {len(created_files)} job file(s)")
        print(f"✓ Output directory: {args.output}")
        print("=" * 60)
        print("\nNext steps:")
        print("1. Review the job files in the output directory")
        print("2. Configure startd8 job queue to watch this directory")
        print("3. Process the queue to implement features")
        print(f"\n  startd8 → Job Queue → Configure → {args.output}")
    else:
        print("\n⚠️  No job files were created")


if __name__ == "__main__":
    main()






#!/usr/bin/env python3
"""
Git integration example for startd8 SDK

This example demonstrates:
- Creating model-specific branches
- Tracking work across branches
- Recording branch metadata
- Comparing implementations from different branches
"""

import subprocess
from pathlib import Path
from startd8 import AgentFramework
from startd8.models import GitBranchInfo


def run_git_command(args):
    """Run a git command and return output"""
    try:
        result = subprocess.run(
            ["git"] + args,
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Git command failed: {e}")
        return None


def main():
    print("🌿 startd8 SDK - Git Integration Example\n")
    
    # Initialize framework
    framework = AgentFramework(Path("./.startd8"))
    
    # Check if we're in a git repository
    git_root = run_git_command(["rev-parse", "--show-toplevel"])
    if not git_root:
        print("❌ Not in a git repository. Please run from a git repo.")
        return
    
    print(f"✓ Git repository: {git_root}\n")
    
    # Get current branch
    current_branch = run_git_command(["branch", "--show-current"])
    print(f"Current branch: {current_branch}\n")
    
    # Create a feature prompt
    print("Creating feature prompt...")
    prompt = framework.create_prompt(
        content="Implement a user profile page with avatar upload and bio editing",
        version="1.0.0",
        tags=["feature", "ui", "profile"],
        metadata={
            "base_branch": current_branch,
            "feature": "user-profile-page"
        }
    )
    print(f"✓ Created prompt: {prompt.id}\n")
    
    # Define models and their branches
    model_branches = {
        "claude-sonnet": "feature/profile-claude",
        "gpt4-turbo": "feature/profile-gpt4",
        "gemini-pro": "feature/profile-gemini"
    }
    
    print(f"Setting up {len(model_branches)} model branches...\n")
    
    branch_info_list = []
    
    for model, branch_name in model_branches.items():
        print(f"📝 {model} → {branch_name}")
        
        # Check if branch exists
        existing = run_git_command(["branch", "--list", branch_name])
        
        if existing:
            print(f"  ⚠️  Branch already exists, skipping creation")
        else:
            # Create branch
            result = run_git_command(["checkout", "-b", branch_name])
            if result is not None:
                print(f"  ✓ Created branch")
                
                # Switch back to original branch
                run_git_command(["checkout", current_branch])
        
        # Create branch info
        branch_info = GitBranchInfo(
            branch_name=branch_name,
            agent_name=model,
            model=model,
            base_branch=current_branch,
            status="active"
        )
        branch_info_list.append(branch_info)
        
        # Store in prompt metadata
        if "branches" not in prompt.metadata:
            prompt.metadata["branches"] = []
        
        prompt.metadata["branches"].append({
            "agent": model,
            "branch": branch_name,
            "status": "ready"
        })
        
        print()
    
    # Update prompt with branch information
    framework.storage.save_prompt(prompt)
    print("✓ Updated prompt with branch information\n")
    
    print("="*60 + "\n")
    
    # Show workflow instructions
    print("📋 Next Steps:\n")
    print("1. For each model/branch:")
    print("   a. Checkout the branch:")
    for model, branch in model_branches.items():
        print(f"      git checkout {branch}")
    print()
    print("   b. Implement the feature using that model/agent")
    print("   c. Commit the changes:")
    print("      git add .")
    print(f"      git commit -m 'Implement profile page with {{model}}'")
        print()
        print("   d. Record the response:")
        print("      startd8 record-response <prompt-id> \\")
        print("        --agent <agent-name> \\")
        print("        --model <model-name> \\")
        print("        --response 'Implementation complete' \\")
        print("        --time <response-time-ms>")
        print()
        print("2. Compare implementations:")
        print(f"   startd8 compare {prompt.id}")
    print()
    print("3. Review and select best approach or merge components")
    print()
    print("4. Merge selected implementation to main:")
    print(f"   git checkout {current_branch}")
    print("   git merge <selected-branch>")
    
    print("\n" + "="*60 + "\n")
    
    # Show branch summary
    print("🌳 Branch Summary:\n")
    for branch_info in branch_info_list:
        print(f"  • {branch_info.branch_name}")
        print(f"    Agent: {branch_info.agent_name}")
        print(f"    Model: {branch_info.model}")
        print(f"    Base: {branch_info.base_branch}")
        print(f"    Status: {branch_info.status}")
        print()
    
    print("✅ Git integration setup complete!")
    print(f"\n💡 Tip: Use 'git branch' to see all branches")


if __name__ == "__main__":
    main()


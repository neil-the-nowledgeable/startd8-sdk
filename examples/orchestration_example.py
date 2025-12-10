#!/usr/bin/env python3
"""
Orchestration example for startd8

Demonstrates the new pipeline functionality that combines
benchmarking with sequential LLM workflows.
"""

from startd8 import AgentFramework, Pipeline, WorkflowTemplates
from startd8.agents import MockAgent
from startd8.orchestration import PipelineComparison
from pathlib import Path


def main():
    print("🔗 startd8 Pipeline Orchestration Example\n")
    print("="*60)
    
    # Initialize framework
    framework = AgentFramework(Path("./orchestration-demo"))
    print(f"✓ Initialized framework\n")
    
    # ============================================================
    # Example 1: Simple Sequential Pipeline
    # ============================================================
    print("Example 1: Basic Pipeline")
    print("-"*60)
    
    # Create a pipeline manually
    pipeline = Pipeline(name="design-implement", framework=framework)
    
    # Add steps
    pipeline.add_step(
        name="designer",
        agent=MockAgent(name="designer", model="mock-designer"),
    )
    
    pipeline.add_step(
        name="developer",
        agent=MockAgent(name="developer", model="mock-developer"),
        transform=lambda spec: f"Implement this design:\n\n{spec}"
    )
    
    # Run it
    result = pipeline.run("Design a user authentication system")
    
    print(f"✓ Pipeline completed in {result.total_time_ms}ms")
    print(f"  Total tokens: {result.total_tokens}")
    print(f"  Total cost: ${result.total_cost:.4f}")
    print(f"  Steps: {len(result.steps)}")
    
    # Show each step's output
    for step in result.steps:
        print(f"\n  Step {step['step_number']}: {step['step_name']}")
        print(f"    Agent: {step['agent']}")
        print(f"    Time: {step['response_time_ms']}ms")
        preview = step['output'][:100] + "..." if len(step['output']) > 100 else step['output']
        print(f"    Output: {preview}")
    
    print("\n" + "="*60 + "\n")
    
    # ============================================================
    # Example 2: Using Workflow Templates
    # ============================================================
    print("Example 2: Workflow Templates")
    print("-"*60)
    
    # Use pre-built template
    planner_impl = WorkflowTemplates.planner_implementer(
        planner_agent=MockAgent(name="planner", model="gpt-4-planner"),
        implementer_agent=MockAgent(name="implementer", model="gpt-4-mini")
    )
    planner_impl.framework = framework
    
    result2 = planner_impl.run("Create a password reset feature")
    
    print(f"✓ Planner→Implementer pipeline completed")
    print(f"  Design step: {result2.steps[0]['response_time_ms']}ms")
    print(f"  Implementation step: {result2.steps[1]['response_time_ms']}ms")
    print(f"  Total: ${result2.total_cost:.4f}")
    
    print("\n" + "="*60 + "\n")
    
    # ============================================================
    # Example 3: Comparing Pipeline Configurations
    # ============================================================
    print("Example 3: Pipeline Comparison")
    print("-"*60)
    
    # Create multiple pipeline configurations
    comparison = PipelineComparison(framework)
    
    # Config A: Fast models
    fast_pipeline = WorkflowTemplates.planner_implementer(
        MockAgent(name="fast-planner", model="gpt-4-mini"),
        MockAgent(name="fast-impl", model="gpt-4-mini")
    )
    fast_pipeline.framework = framework
    result_fast = fast_pipeline.run("Design API endpoints")
    comparison.add_result(result_fast)
    
    # Config B: Quality models
    quality_pipeline = WorkflowTemplates.planner_implementer(
        MockAgent(name="quality-planner", model="gpt-4"),
        MockAgent(name="quality-impl", model="claude-3-5")
    )
    quality_pipeline.framework = framework
    result_quality = quality_pipeline.run("Design API endpoints")
    comparison.add_result(result_quality)
    
    # Compare
    comp_results = comparison.compare()
    
    print("Pipeline Comparison:")
    print(f"  Total pipelines tested: {comp_results['total_pipelines']}")
    print(f"  Average time: {comp_results['averages']['time_ms']:.2f}ms")
    print(f"  Average cost: ${comp_results['averages']['cost']:.4f}")
    
    print("\n  Fastest:")
    for p in comp_results['rankings']['by_speed']:
        print(f"    - {p['pipeline_id']}: {p['total_time_ms']}ms")
    
    print("\n  Cheapest:")
    for p in comp_results['rankings']['by_cost']:
        print(f"    - {p['pipeline_id']}: ${p['total_cost']:.4f}")
    
    print("\n" + "="*60 + "\n")
    
    # ============================================================
    # Example 4: Pipeline with Benchmarking
    # ============================================================
    print("Example 4: Hybrid Benchmark + Pipeline")
    print("-"*60)
    
    # First, benchmark to find the best planner
    print("Step 1: Benchmark planner candidates...")
    
    prompt = framework.create_prompt(
        content="Design a caching system",
        version="1.0.0",
        tags=["benchmark", "planner"]
    )
    
    planners = [
        MockAgent(name="planner-a", model="gpt-4"),
        MockAgent(name="planner-b", model="claude-3-5"),
        MockAgent(name="planner-c", model="gpt-4-mini"),
    ]
    
    for planner in planners:
        response = planner.create_response(prompt.id, prompt.content)
        framework.storage.save_response(response)
    
    # Compare planners
    planner_comparison = framework.compare_responses(prompt.id)
    best_planner_name = planner_comparison['rankings']['by_speed'][0]['agent']
    
    print(f"✓ Best planner: {best_planner_name}")
    
    # Now use best planner in a pipeline
    print("\nStep 2: Use best planner in production pipeline...")
    
    best_planner = next(p for p in planners if p.name == best_planner_name)
    
    prod_pipeline = WorkflowTemplates.planner_implementer(
        planner_agent=best_planner,
        implementer_agent=MockAgent(name="implementer", model="gpt-4-mini")
    )
    prod_pipeline.framework = framework
    
    final_result = prod_pipeline.run("Design a caching system")
    
    print(f"✓ Production pipeline completed")
    print(f"  Used benchmarked best planner: {best_planner_name}")
    print(f"  Total cost: ${final_result.total_cost:.4f}")
    
    print("\n" + "="*60 + "\n")
    
    # ============================================================
    # Summary
    # ============================================================
    print("✅ All examples completed!\n")
    print("Key Takeaways:")
    print("  1. Pipelines enable sequential agent chaining")
    print("  2. All pipeline steps are tracked with full metrics")
    print("  3. Workflow templates provide common patterns")
    print("  4. Can compare different pipeline configurations")
    print("  5. Benchmarking + pipelines = optimal production workflows")
    print()
    print(f"📁 Data stored in: {framework.storage.base_dir}")


if __name__ == "__main__":
    main()


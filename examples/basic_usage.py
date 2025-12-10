#!/usr/bin/env python3
"""
Basic usage example for startd8 SDK

This example demonstrates:
- Creating a versioned prompt
- Running multiple agents
- Recording responses
- Comparing results
"""

from startd8 import AgentFramework
from startd8.agents import MockAgent
from pathlib import Path


def main():
    print("🚀 startd8 SDK - Basic Usage Example\n")
    
    # Initialize framework with custom storage location
    storage_dir = Path("./example-data")
    framework = AgentFramework(storage_dir)
    print(f"✓ Initialized framework at: {storage_dir}\n")
    
    # Create a versioned prompt
    print("Creating prompt...")
    prompt = framework.create_prompt(
        content="Write a Python function to calculate the Fibonacci sequence up to n terms",
        version="1.0.0",
        tags=["python", "algorithms", "fibonacci"],
        metadata={
            "difficulty": "easy",
            "language": "python"
        }
    )
    print(f"✓ Created prompt: {prompt.id}")
    print(f"  Version: {prompt.version}")
    print(f"  Tags: {', '.join(prompt.tags)}\n")
    
    # Create multiple mock agents (simulating different models)
    agents = [
        MockAgent(name="agent-alpha", model="model-alpha-v1"),
        MockAgent(name="agent-beta", model="model-beta-v2"),
        MockAgent(name="agent-gamma", model="model-gamma-v3"),
    ]
    
    # Generate responses from each agent
    print("Generating responses from agents...")
    for agent in agents:
        response = agent.create_response(
            prompt_id=prompt.id,
            prompt=prompt.content
        )
        framework.storage.save_response(response)
        print(f"✓ {agent.name}: {response.response_time_ms}ms, {response.token_usage.total} tokens")
    
    print("\n" + "="*60 + "\n")
    
    # Compare responses
    print("📊 Comparison Results:\n")
    comparison = framework.compare_responses(prompt.id)
    
    print(f"Total Responses: {comparison['total_responses']}")
    print(f"Average Response Time: {comparison['avg_response_time_ms']:.2f}ms")
    print(f"Total Tokens: {comparison['total_tokens']}")
    
    print("\n🏆 Rankings:")
    print("\nBy Speed:")
    for i, entry in enumerate(comparison['rankings']['by_speed'], 1):
        print(f"  {i}. {entry['agent']}: {entry['time_ms']}ms")
    
    print("\nBy Token Efficiency:")
    for i, entry in enumerate(comparison['rankings']['by_token_efficiency'], 1):
        print(f"  {i}. {entry['agent']}: {entry['tokens']} tokens")
    
    # Create a benchmark
    print("\n" + "="*60 + "\n")
    print("Creating benchmark...")
    benchmark = framework.create_benchmark(
        name="Fibonacci Implementation Comparison",
        prompt_id=prompt.id,
        metadata={"example": True}
    )
    print(f"✓ Created benchmark: {benchmark.id}")
    
    # Complete the benchmark
    framework.complete_benchmark(
        benchmark_id=benchmark.id,
        summary=f"Compared {len(agents)} agents on Fibonacci implementation task"
    )
    print(f"✓ Completed benchmark\n")
    
    # Export report
    report_path = Path("./example-data/reports/comparison.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    
    report = framework.export_benchmark_report(
        benchmark_id=benchmark.id,
        output_file=report_path
    )
    print(f"✓ Exported report to: {report_path}")
    
    print("\n✅ Example complete!")
    print(f"\nData stored in: {storage_dir}")
    print("You can inspect the JSON files to see the stored data.")


if __name__ == "__main__":
    main()


#!/usr/bin/env python3
"""
Advanced benchmarking example for startd8 SDK

This example demonstrates:
- Running multiple prompts in sequence
- Using the BenchmarkRunner
- Generating detailed comparison reports
- Tracking metrics across multiple tests
"""

from startd8 import AgentFramework
from startd8.agents import MockAgent
from startd8.benchmark import BenchmarkRunner, ComparisonReport
from pathlib import Path


def main():
    print("🚀 startd8 SDK - Advanced Benchmarking Example\n")
    
    # Initialize
    storage_dir = Path("./advanced-example-data")
    framework = AgentFramework(storage_dir)
    print(f"✓ Initialized framework at: {storage_dir}\n")
    
    # Create benchmark runner
    runner = BenchmarkRunner(framework)
    report_gen = ComparisonReport(framework)
    
    # Define test prompts
    test_cases = [
        {
            "content": "Design a RESTful API for a todo list application with CRUD operations",
            "version": "1.0.0",
            "tags": ["api-design", "rest", "backend"],
            "name": "Todo API Design"
        },
        {
            "content": "Implement error handling middleware for Express.js application",
            "version": "1.0.0",
            "tags": ["error-handling", "middleware", "nodejs"],
            "name": "Express Error Handling"
        },
        {
            "content": "Write database migration for adding user roles and permissions",
            "version": "1.0.0",
            "tags": ["database", "migration", "security"],
            "name": "User Roles Migration"
        },
    ]
    
    # Create agents simulating different models
    agents = [
        MockAgent(name="fast-model", model="fast-v1"),
        MockAgent(name="balanced-model", model="balanced-v2"),
        MockAgent(name="thorough-model", model="thorough-v3"),
    ]
    
    print(f"Running {len(test_cases)} benchmarks with {len(agents)} agents each...\n")
    print("="*60 + "\n")
    
    benchmark_results = []
    
    # Run each benchmark
    for i, test_case in enumerate(test_cases, 1):
        print(f"Benchmark {i}/{len(test_cases)}: {test_case['name']}")
        print("-" * 60)
        
        # Run the benchmark
        results = runner.run_benchmark(
            prompt_content=test_case['content'],
            agents=agents,
            benchmark_name=test_case['name'],
            version=test_case['version'],
            tags=test_case['tags']
        )
        
        benchmark_results.append(results)
        
        # Show quick stats
        comparison = results['comparison']
        print(f"✓ Completed: {comparison['total_responses']} responses")
        print(f"  Avg Time: {comparison['avg_response_time_ms']:.2f}ms")
        print(f"  Total Tokens: {comparison['total_tokens']}")
        
        # Show winner
        if comparison['rankings']['by_speed']:
            fastest = comparison['rankings']['by_speed'][0]
            print(f"  🏆 Fastest: {fastest['agent']} ({fastest['time_ms']}ms)")
        
        print()
    
    print("="*60 + "\n")
    
    # Generate detailed reports for each benchmark
    print("Generating detailed reports...\n")
    
    reports_dir = storage_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    
    for i, result in enumerate(benchmark_results, 1):
        benchmark_id = result['benchmark']['id']
        test_name = result['benchmark']['name']
        
        # Generate markdown report
        report_file = reports_dir / f"benchmark-{i}-{test_name.lower().replace(' ', '-')}.md"
        report_gen.generate_markdown_report(
            prompt_id=result['prompt']['id'],
            output_file=report_file
        )
        print(f"✓ Report {i}: {report_file.name}")
        
        # Generate metrics
        metrics = report_gen.generate_metrics(result['prompt']['id'])
        print(f"  - Fastest: {metrics.fastest_agent}")
        print(f"  - Most Efficient: {metrics.most_efficient_agent}")
        print(f"  - Total Cost: ${metrics.total_cost_estimate:.4f}")
        print()
    
    # Generate aggregate statistics
    print("="*60 + "\n")
    print("📊 Aggregate Statistics:\n")
    
    total_responses = sum(r['comparison']['total_responses'] for r in benchmark_results)
    avg_time_overall = sum(r['comparison']['avg_response_time_ms'] for r in benchmark_results) / len(benchmark_results)
    total_tokens_all = sum(r['comparison']['total_tokens'] for r in benchmark_results)
    
    print(f"Total Benchmarks: {len(benchmark_results)}")
    print(f"Total Responses: {total_responses}")
    print(f"Overall Avg Time: {avg_time_overall:.2f}ms")
    print(f"Total Tokens Used: {total_tokens_all}")
    
    # Agent performance summary
    print("\n🏆 Agent Performance Summary:\n")
    
    agent_wins = {agent.name: 0 for agent in agents}
    
    for result in benchmark_results:
        rankings = result['comparison']['rankings']['by_speed']
        if rankings:
            winner = rankings[0]['agent']
            if winner in agent_wins:
                agent_wins[winner] += 1
    
    for agent_name, wins in sorted(agent_wins.items(), key=lambda x: x[1], reverse=True):
        print(f"  {agent_name}: {wins} wins")
    
    print("\n✅ Advanced benchmarking complete!")
    print(f"\n📁 All data and reports saved to: {storage_dir}")
    print(f"📊 View detailed reports in: {reports_dir}")


if __name__ == "__main__":
    main()


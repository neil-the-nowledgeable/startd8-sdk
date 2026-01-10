"""
Job Queue Example for startd8

This example demonstrates how to use the job queue feature programmatically.

Usage:
    1. Configure a queue folder:
       startd8 queue configure --folder ~/startd8-jobs
    
    2. Run this script to create and process jobs
    
    3. Or use the CLI:
       startd8 queue status
       startd8 queue run
       startd8 queue watch
"""

from pathlib import Path
from startd8 import (
    AgentFramework,
    JobQueue,
    JobQueueConfig,
    JobStatus,
    create_job_file,
)


def main():
    # Define a watch folder for jobs
    watch_folder = Path.home() / "startd8-jobs-example"
    watch_folder.mkdir(parents=True, exist_ok=True)
    
    print(f"📁 Watch folder: {watch_folder}")
    
    # Create queue configuration
    config = JobQueueConfig(
        watch_folder=watch_folder,
        poll_interval_seconds=5.0,
        default_agents=["mock"],  # Use mock for testing
        archive_completed=True,
        archive_folder=watch_folder / "completed"
    )
    
    # Create framework and queue
    framework = AgentFramework()
    queue = JobQueue(config, framework)
    
    # Create some sample jobs
    print("\n📝 Creating sample jobs...")
    
    job1 = create_job_file(
        output_path=watch_folder / "fibonacci_task",
        content="Write a Python function to calculate fibonacci numbers recursively.",
        version="1.0.0",
        agents=["mock"],
        priority=1,
        tags=["coding", "python"]
    )
    print(f"  ✓ Created: {job1.name}")
    
    job2 = create_job_file(
        output_path=watch_folder / "sorting_task",
        content="Explain the differences between quicksort, mergesort, and heapsort.",
        version="1.0.0",
        agents=["mock"],
        priority=2,
        tags=["algorithms", "sorting"]
    )
    print(f"  ✓ Created: {job2.name}")
    
    job3 = create_job_file(
        output_path=watch_folder / "design_task",
        content="Design a simple REST API for a todo list application.",
        version="1.0.0",
        agents=["mock"],
        priority=3,  # Highest priority
        tags=["design", "api"]
    )
    print(f"  ✓ Created: {job3.name}")
    
    # Show queue status
    print("\n📊 Queue Status:")
    status = queue.get_queue_status()
    print(f"  Total jobs: {status['total_jobs']}")
    print(f"  Pending: {status['status_counts']['pending']}")
    
    # List pending jobs
    print("\n📋 Pending Jobs (sorted by priority):")
    pending = queue.get_pending_jobs()
    for job in pending:
        preview = job.prompt.content[:50] + "..." if len(job.prompt.content) > 50 else job.prompt.content
        print(f"  [{job.priority}] {job.job_id[:12]}... - {preview}")
    
    # Process jobs with progress callback
    print("\n🚀 Processing jobs...")
    
    def on_progress(current, total, job, result):
        status_icon = "✓" if result.status == JobStatus.COMPLETED else "✗"
        print(f"  [{current}/{total}] {status_icon} {job.job_id[:12]}... - {result.status.value}")
    
    results = queue.process_all(on_progress=on_progress)
    
    # Summary
    success = sum(1 for r in results if r.status == JobStatus.COMPLETED)
    print(f"\n✅ Completed: {success}/{len(results)} jobs")
    
    # Show results
    print("\n📄 Results:")
    for result in results:
        print(f"  Job {result.job_id[:12]}...")
        print(f"    Status: {result.status.value}")
        print(f"    Responses: {len(result.response_ids)}")
        if result.prompt_id:
            print(f"    Prompt ID: {result.prompt_id}")
    
    print(f"\n📁 Completed jobs archived to: {watch_folder / 'completed'}")


if __name__ == "__main__":
    main()












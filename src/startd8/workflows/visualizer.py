"""
WorkflowVisualizer — Mermaid diagram export for pipeline structure and execution results.

FR-420: Structure visualization (Pipeline → Mermaid)
FR-421: Post-execution visualization (WorkflowResult → Mermaid with status colors)
"""

from typing import List, Union

from ..orchestration import (
    Pipeline,
    PipelineStep,
    ConditionalStep,
    ParallelStep,
    WorkflowStep,
)
from .models import WorkflowResult


class WorkflowVisualizer:
    """Generate Mermaid flowcharts from Pipeline definitions or WorkflowResult execution data."""

    @staticmethod
    def to_mermaid(pipeline_or_result: Union["Pipeline", "WorkflowResult"]) -> str:
        """Generate Mermaid flowchart from a Pipeline or WorkflowResult."""
        if isinstance(pipeline_or_result, Pipeline):
            return WorkflowVisualizer._pipeline_to_mermaid(pipeline_or_result)
        elif isinstance(pipeline_or_result, WorkflowResult):
            return WorkflowVisualizer._result_to_mermaid(pipeline_or_result)
        raise TypeError(f"Expected Pipeline or WorkflowResult, got {type(pipeline_or_result)}")

    @staticmethod
    def _pipeline_to_mermaid(pipeline: "Pipeline") -> str:
        """FR-420: Generate Mermaid flowchart from Pipeline structure."""
        lines = ["graph TD"]
        lines.append("    start([Start])")
        prev_id = "start"

        for i, step in enumerate(pipeline.steps):
            step_id = f"step{i}"

            if isinstance(step, PipelineStep):
                lines.append(f"    {step_id}[{step.name}]")
                lines.append(f"    {prev_id} --> {step_id}")
                prev_id = step_id

            elif isinstance(step, ConditionalStep):
                lines.append(f"    {step_id}{{{{{step.name}}}}}")
                lines.append(f"    {prev_id} --> {step_id}")
                # True branch
                if_id = f"{step_id}_if"
                lines.append(f"    {if_id}[{step.if_step.name}]")
                lines.append(f"    {step_id} -->|True| {if_id}")
                # False branch
                if step.else_step:
                    else_id = f"{step_id}_else"
                    lines.append(f"    {else_id}[{step.else_step.name}]")
                    lines.append(f"    {step_id} -->|False| {else_id}")
                    # Merge point
                    merge_id = f"{step_id}_merge"
                    lines.append(f"    {merge_id}(( ))")
                    lines.append(f"    {if_id} --> {merge_id}")
                    lines.append(f"    {else_id} --> {merge_id}")
                    prev_id = merge_id
                else:
                    prev_id = if_id

            elif isinstance(step, ParallelStep):
                fork_id = f"{step_id}_fork"
                join_id = f"{step_id}_join"
                lines.append(f"    {fork_id}{{{{Fork}}}}")
                lines.append(f"    {prev_id} --> {fork_id}")
                for j, sub in enumerate(step.steps):
                    sub_id = f"{step_id}_p{j}"
                    lines.append(f"    {sub_id}[{sub.name}]")
                    lines.append(f"    {fork_id} --> {sub_id}")
                lines.append(f"    {join_id}{{{{Join}}}}")
                for j in range(len(step.steps)):
                    lines.append(f"    {step_id}_p{j} --> {join_id}")
                prev_id = join_id

            elif isinstance(step, WorkflowStep):
                wf_name = getattr(step.workflow, 'metadata', None)
                wf_label = wf_name.name if wf_name else step.name
                lines.append(f"    subgraph {step_id}_sub[{step.name}]")
                lines.append(f"        {step_id}_wf[{wf_label}]")
                lines.append(f"    end")
                lines.append(f"    {prev_id} --> {step_id}_sub")
                prev_id = f"{step_id}_sub"

        lines.append(f"    {prev_id} --> finish([End])")
        return "\n".join(lines)

    @staticmethod
    def _result_to_mermaid(result: "WorkflowResult") -> str:
        """FR-421: Generate Mermaid flowchart from execution result with status colors."""
        lines = ["graph TD"]

        for i, step in enumerate(result.steps):
            step_id = f"step{i}"
            if step.success:
                style = ":::success"
            else:
                style = ":::failure"

            label = f"{step.step_name}<br/>{step.time_ms}ms"
            if step.error:
                err_preview = step.error[:30].replace('"', "'")
                label += f"<br/>ERROR: {err_preview}"

            lines.append(f'    {step_id}["{label}"]{style}')
            if i > 0:
                lines.append(f"    step{i-1} --> step{i}")

        # Class definitions for coloring
        lines.append("    classDef success fill:#2ecc71,color:#fff")
        lines.append("    classDef failure fill:#e74c3c,color:#fff")
        return "\n".join(lines)

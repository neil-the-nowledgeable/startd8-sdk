"""
Improvement Tracking Workflow

Tracks improvements made between document updates to evaluate workflow effectiveness,
model performance, and prompt quality. Stores improvement metrics persistently in
project-index-local.yaml.
"""

import yaml
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict


@dataclass
class ImprovementDelta:
    """Represents improvement in a quality category"""
    category: str
    before_score: float
    after_score: float
    delta: float
    improvement_percent: float


@dataclass
class ImprovementRecord:
    """Complete record of an improvement session"""
    session_id: str
    date: str
    workflow_name: str
    agent_name: str
    prompt_id: Optional[str]
    document_path: str
    before_version: str
    after_version: str
    overall_score_before: float
    overall_score_after: float
    overall_improvement: float
    category_deltas: List[ImprovementDelta]
    strengths_added: List[str]
    gaps_resolved: List[str]
    notes: Optional[str]


class ImprovementTracker:
    """Tracks document improvements and stores metrics in project index"""
    
    CATEGORIES = [
        "Completeness",
        "Clarity",
        "Consistency",
        "Testability",
        "Maintainability",
        "Developer Experience"
    ]
    
    def __init__(self, index_file_path: Path):
        """
        Initialize improvement tracker
        
        Args:
            index_file_path: Path to project-index-local.yaml
        """
        self.index_file_path = Path(index_file_path)
        self.index_data = None
        self.load_index()
    
    def load_index(self):
        """Load the YAML index file"""
        if not self.index_file_path.exists():
            # Create empty structure
            self.index_data = {
                'metadata': {},
                'design_documents': {
                    'quality_tracking': {
                        'documents': []
                    }
                },
                'improvement_history': []
            }
            return
        
        try:
            with open(self.index_file_path, 'r') as f:
                self.index_data = yaml.safe_load(f) or {}
            
            # Ensure improvement_history exists
            if 'improvement_history' not in self.index_data:
                self.index_data['improvement_history'] = []
        except Exception as e:
            raise ValueError(f"Failed to load index file: {e}")
    
    def save_index(self):
        """Save the updated index file"""
        self.index_file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.index_file_path, 'w') as f:
            yaml.dump(
                self.index_data,
                f,
                default_flow_style=False,
                sort_keys=False,
                allow_unicode=True
            )
    
    def get_document_scores(self, document_path: str) -> Optional[Dict[str, Any]]:
        """
        Get quality scores for a document from the index
        
        Args:
            document_path: Path to the document
            
        Returns:
            Dictionary with scores and assessment data, or None if not found
        """
        if 'design_documents' not in self.index_data:
            return None
        
        quality_tracking = self.index_data['design_documents'].get('quality_tracking', {})
        documents = quality_tracking.get('documents', [])
        
        # Try to find document by path
        doc_name = Path(document_path).name
        
        # First pass: look for exact or partial matches with quality scores
        best_match = None
        for doc in documents:
            # Check primary_doc field
            primary_doc = doc.get('primary_doc', '')
            
            # Also check current_version.file field (V2 index format)
            current_version = doc.get('current_version', {})
            current_file = current_version.get('file', '') if isinstance(current_version, dict) else ''
            
            # Check if document path matches either field
            matches_primary = doc_name in primary_doc or primary_doc in document_path if primary_doc else False
            matches_current = doc_name in current_file or current_file in document_path if current_file else False
            
            if matches_primary or matches_current:
                # Prefer entries with quality scores
                has_score = doc.get('quality_score') is not None
                current_has_score = current_version.get('quality_score') is not None if isinstance(current_version, dict) else False
                
                if has_score or current_has_score:
                    # If current_version has the score but top-level doesn't, merge them
                    if not has_score and current_has_score:
                        # Return a merged view with scores from current_version
                        merged_doc = dict(doc)
                        merged_doc['quality_score'] = current_version.get('quality_score')
                        # Copy categories_assessed if not present at top level
                        if not merged_doc.get('categories_assessed') and current_version.get('categories_assessed'):
                            merged_doc['categories_assessed'] = current_version.get('categories_assessed')
                        return merged_doc
                    return doc
                elif best_match is None:
                    # Keep as fallback if no scored match found
                    best_match = doc
        
        return best_match
    
    def calculate_improvement_deltas(
        self,
        before_scores: Dict[str, float],
        after_scores: Dict[str, float]
    ) -> List[ImprovementDelta]:
        """
        Calculate improvement deltas for each category
        
        Args:
            before_scores: Dictionary of category -> score before
            after_scores: Dictionary of category -> score after
            
        Returns:
            List of ImprovementDelta objects
        """
        deltas = []
        
        for category in self.CATEGORIES:
            before = before_scores.get(category, 0.0)
            after = after_scores.get(category, 0.0)
            delta = after - before
            
            # Calculate improvement percentage (avoid division by zero)
            if before > 0:
                improvement_percent = (delta / before) * 100
            elif after > 0:
                improvement_percent = 100.0  # Went from 0 to positive
            else:
                improvement_percent = 0.0
            
            deltas.append(ImprovementDelta(
                category=category,
                before_score=before,
                after_score=after,
                delta=delta,
                improvement_percent=improvement_percent
            ))
        
        return deltas
    
    def extract_category_scores(self, document_data: Dict[str, Any]) -> Dict[str, float]:
        """
        Extract category scores from document assessment data
        
        Handles both V1 format (categories_assessed at top level) and 
        V2 format (categories_assessed may be in current_version).
        
        Args:
            document_data: Document entry from quality_tracking
            
        Returns:
            Dictionary of category -> score
        """
        scores = {}
        
        # Try top-level categories_assessed first
        categories_assessed = document_data.get('categories_assessed', [])
        
        # If empty, try current_version.categories_assessed (V2 format)
        if not categories_assessed:
            current_version = document_data.get('current_version', {})
            if isinstance(current_version, dict):
                categories_assessed = current_version.get('categories_assessed', [])
        
        # If still empty, the document may not have category assessments
        if not categories_assessed:
            return scores
        
        for cat_data in categories_assessed:
            if not isinstance(cat_data, dict):
                continue
            category_name = cat_data.get('name', '')
            score = cat_data.get('score', 0.0)
            if isinstance(score, (int, float)):
                scores[category_name] = float(score)
        
        return scores
    
    def record_improvement(
        self,
        document_path: str,
        before_version: str,
        after_version: str,
        workflow_name: str,
        agent_name: str,
        prompt_id: Optional[str] = None,
        strengths_added: Optional[List[str]] = None,
        gaps_resolved: Optional[List[str]] = None,
        notes: Optional[str] = None
    ) -> ImprovementRecord:
        """
        Record an improvement between two document versions
        
        Args:
            document_path: Path to the document
            before_version: Path/identifier for before version
            after_version: Path/identifier for after version
            workflow_name: Name of workflow used (e.g., "Design Polish Pipeline")
            agent_name: Name of agent used
            prompt_id: Optional prompt ID used
            strengths_added: List of strengths added
            gaps_resolved: List of gaps resolved
            notes: Optional notes about the improvement
            
        Returns:
            ImprovementRecord object
        """
        # Get before and after scores
        before_data = self.get_document_scores(before_version)
        after_data = self.get_document_scores(after_version)
        
        if not before_data or not after_data:
            raise ValueError(
                f"Could not find assessment data for one or both versions. "
                f"Before: {before_data is not None}, After: {after_data is not None}"
            )
        
        before_scores = self.extract_category_scores(before_data)
        after_scores = self.extract_category_scores(after_data)
        
        # Calculate overall scores
        overall_before = before_data.get('quality_score', 0.0)
        overall_after = after_data.get('quality_score', 0.0)
        overall_improvement = overall_after - overall_before
        
        # Calculate category deltas
        category_deltas = self.calculate_improvement_deltas(before_scores, after_scores)
        
        # Create improvement record
        current_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        session_id = f"{current_date}-improvement-{Path(document_path).stem}"
        
        record = ImprovementRecord(
            session_id=session_id,
            date=current_date,
            workflow_name=workflow_name,
            agent_name=agent_name,
            prompt_id=prompt_id,
            document_path=document_path,
            before_version=before_version,
            after_version=after_version,
            overall_score_before=float(overall_before),
            overall_score_after=float(overall_after),
            overall_improvement=overall_improvement,
            category_deltas=category_deltas,
            strengths_added=strengths_added or [],
            gaps_resolved=gaps_resolved or [],
            notes=notes
        )
        
        # Store in index file
        if 'improvement_history' not in self.index_data:
            self.index_data['improvement_history'] = []
        
        # Convert to dict for YAML storage
        record_dict = {
            'session_id': record.session_id,
            'date': record.date,
            'workflow_name': record.workflow_name,
            'agent_name': record.agent_name,
            'prompt_id': record.prompt_id,
            'document_path': record.document_path,
            'before_version': record.before_version,
            'after_version': record.after_version,
            'overall_score_before': record.overall_score_before,
            'overall_score_after': record.overall_score_after,
            'overall_improvement': record.overall_improvement,
            'category_deltas': [
                {
                    'category': d.category,
                    'before_score': d.before_score,
                    'after_score': d.after_score,
                    'delta': d.delta,
                    'improvement_percent': d.improvement_percent
                }
                for d in record.category_deltas
            ],
            'strengths_added': record.strengths_added,
            'gaps_resolved': record.gaps_resolved,
            'notes': record.notes
        }
        
        self.index_data['improvement_history'].append(record_dict)
        self.save_index()
        
        return record
    
    def get_improvement_statistics(
        self,
        workflow_name: Optional[str] = None,
        agent_name: Optional[str] = None,
        document_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get improvement statistics filtered by criteria
        
        Args:
            workflow_name: Filter by workflow name
            agent_name: Filter by agent name
            document_path: Filter by document path
            
        Returns:
            Dictionary with statistics
        """
        history = self.index_data.get('improvement_history', [])
        
        # Filter records
        filtered = history
        if workflow_name:
            filtered = [r for r in filtered if r.get('workflow_name') == workflow_name]
        if agent_name:
            filtered = [r for r in filtered if r.get('agent_name') == agent_name]
        if document_path:
            filtered = [r for r in filtered if document_path in r.get('document_path', '')]
        
        if not filtered:
            return {
                'total_improvements': 0,
                'average_overall_improvement': 0.0,
                'category_averages': {},
                'workflow_performance': {},
                'agent_performance': {}
            }
        
        # Calculate statistics
        total = len(filtered)
        avg_overall = sum(r.get('overall_improvement', 0) for r in filtered) / total
        
        # Category averages
        category_totals = {cat: {'delta': 0.0, 'count': 0} for cat in self.CATEGORIES}
        for record in filtered:
            for delta in record.get('category_deltas', []):
                cat = delta.get('category')
                if cat in category_totals:
                    category_totals[cat]['delta'] += delta.get('delta', 0)
                    category_totals[cat]['count'] += 1
        
        category_averages = {
            cat: (data['delta'] / data['count'] if data['count'] > 0 else 0.0)
            for cat, data in category_totals.items()
        }
        
        # Workflow performance
        workflow_stats = {}
        for record in filtered:
            wf_name = record.get('workflow_name', 'Unknown')
            if wf_name not in workflow_stats:
                workflow_stats[wf_name] = {'count': 0, 'total_improvement': 0.0}
            workflow_stats[wf_name]['count'] += 1
            workflow_stats[wf_name]['total_improvement'] += record.get('overall_improvement', 0)
        
        workflow_performance = {
            wf: {
                'count': stats['count'],
                'average_improvement': stats['total_improvement'] / stats['count']
            }
            for wf, stats in workflow_stats.items()
        }
        
        # Agent performance
        agent_stats = {}
        for record in filtered:
            agent = record.get('agent_name', 'Unknown')
            if agent not in agent_stats:
                agent_stats[agent] = {'count': 0, 'total_improvement': 0.0}
            agent_stats[agent]['count'] += 1
            agent_stats[agent]['total_improvement'] += record.get('overall_improvement', 0)
        
        agent_performance = {
            agent: {
                'count': stats['count'],
                'average_improvement': stats['total_improvement'] / stats['count']
            }
            for agent, stats in agent_stats.items()
        }
        
        return {
            'total_improvements': total,
            'average_overall_improvement': avg_overall,
            'category_averages': category_averages,
            'workflow_performance': workflow_performance,
            'agent_performance': agent_performance
        }


"""
Document Importer for Project Index

Scans directories for design documents and imports them into the project index
for tracking. Supports rescanning to find new documents.
"""

import yaml
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set, Tuple
import re


class DocumentImporter:
    """Import design documents into project index for tracking"""
    
    # Common design document patterns
    DESIGN_DOC_PATTERNS = [
        r'.*design.*\.md$',
        r'.*spec.*\.md$',
        r'.*architecture.*\.md$',
        r'.*plan.*\.md$',
    ]
    
    # Feature group patterns (e.g., 01-core-types, 02-tools)
    FEATURE_GROUP_PATTERN = r'(\d{2}-[a-z-]+)'
    
    def __init__(self, index_file_path: Path):
        """
        Initialize document importer
        
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
                }
            }
            return
        
        try:
            with open(self.index_file_path, 'r') as f:
                self.index_data = yaml.safe_load(f) or {}
            
            # Ensure structure exists
            if 'design_documents' not in self.index_data:
                self.index_data['design_documents'] = {}
            if 'quality_tracking' not in self.index_data['design_documents']:
                self.index_data['design_documents']['quality_tracking'] = {'documents': []}
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
    
    def is_design_document(self, file_path: Path) -> bool:
        """
        Check if a file is a design document
        
        Args:
            file_path: Path to check
            
        Returns:
            True if file matches design document patterns
        """
        if not file_path.suffix == '.md':
            return False
        
        name_lower = file_path.name.lower()
        
        # Check against patterns
        for pattern in self.DESIGN_DOC_PATTERNS:
            if re.match(pattern, name_lower, re.IGNORECASE):
                return True
        
        # Also check if it's in a design-related directory
        path_str = str(file_path).lower()
        if 'design' in path_str or 'spec' in path_str or 'architecture' in path_str:
            return True
        
        return False
    
    def extract_feature_group(self, file_path: Path) -> Optional[str]:
        """
        Extract feature group from file path
        
        Args:
            file_path: Path to extract feature group from
            
        Returns:
            Feature group string (e.g., "01-core-types") or None
        """
        path_str = str(file_path)
        
        # Look for pattern like 01-core-types, 02-tools, etc.
        match = re.search(self.FEATURE_GROUP_PATTERN, path_str)
        if match:
            return match.group(1)
        
        # Check parent directories
        for parent in file_path.parents:
            parent_name = parent.name.lower()
            match = re.search(self.FEATURE_GROUP_PATTERN, parent_name)
            if match:
                return match.group(1)
        
        return None
    
    def get_tracked_documents(self) -> Set[str]:
        """
        Get set of currently tracked document paths
        
        Returns:
            Set of document paths (normalized)
        """
        tracked = set()
        
        if 'design_documents' not in self.index_data:
            return tracked
        
        quality_tracking = self.index_data['design_documents'].get('quality_tracking', {})
        documents = quality_tracking.get('documents', [])
        
        for doc in documents:
            primary_doc = doc.get('primary_doc', '')
            if primary_doc:
                # Normalize path for comparison
                tracked.add(str(Path(primary_doc).resolve()))
        
        return tracked
    
    def create_document_entry(self, doc_path: Path, feature_group: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> Dict:
        """
        Create a document entry for the index
        
        Args:
            doc_path: Path to the document
            feature_group: Optional feature group (will be extracted if not provided)
            metadata: Optional metadata dict with quality_score, analysis_date, status, etc.
            
        Returns:
            Document entry dictionary
        """
        if not feature_group:
            feature_group = self.extract_feature_group(doc_path)
        
        # Extract name from path or use metadata name
        if metadata and metadata.get('name'):
            doc_name = metadata['name']
        else:
            doc_name = doc_path.stem.replace('_', ' ').replace('-', ' ').title()
        
        # Calculate relative path if possible
        try:
            if self.index_file_path.parent in doc_path.parents:
                primary_doc = str(doc_path.relative_to(self.index_file_path.parent))
            else:
                primary_doc = str(doc_path.resolve())
        except ValueError:
            primary_doc = str(doc_path.resolve())
        
        current_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        # Use metadata if provided, otherwise use defaults
        quality_score = metadata.get('quality_score') if metadata else None
        analysis_date = metadata.get('analysis_date') if metadata else None
        status = metadata.get('status', 'not_analyzed') if metadata else 'not_analyzed'
        polishing_status = metadata.get('polishing_status', 'pending_analysis') if metadata else 'pending_analysis'
        created = metadata.get('created') if metadata else None
        created_by = metadata.get('created_by') if metadata else None
        
        return {
            'feature_group': feature_group or 'unknown',
            'name': doc_name,
            'primary_doc': primary_doc,
            'quality_score': quality_score,
            'status': status,
            'analysis_date': analysis_date,
            'analysis_file': None,
            'polishing_status': polishing_status,
            'polishing_priority': 'medium',
            'strengths': [],
            'critical_gaps': [],
            'categories_assessed': [],
            'improvements_made': [],
            'improvements_pending': [],
            'last_updated': analysis_date or current_date,
            'last_polished': None,
            'created': created,
            'created_by': created_by
        }
    
    def scan_directory(
        self,
        directory: Path,
        recursive: bool = True,
        exclude_patterns: Optional[List[str]] = None
    ) -> List[Path]:
        """
        Scan directory for design documents
        
        Args:
            directory: Directory to scan
            recursive: Whether to scan recursively
            exclude_patterns: List of patterns to exclude (e.g., ['node_modules', '.git'])
            
        Returns:
            List of design document paths found
        """
        directory = Path(directory).resolve()
        
        if not directory.exists() or not directory.is_dir():
            return []
        
        exclude_patterns = exclude_patterns or ['.git', 'node_modules', '__pycache__', '.startd8']
        
        documents = []
        
        if recursive:
            for file_path in directory.rglob('*.md'):
                # Check if excluded
                if any(pattern in str(file_path) for pattern in exclude_patterns):
                    continue
                
                if self.is_design_document(file_path):
                    documents.append(file_path)
        else:
            for file_path in directory.glob('*.md'):
                if self.is_design_document(file_path):
                    documents.append(file_path)
        
        return sorted(documents)
    
    def import_documents(
        self,
        document_paths: List[Path],
        skip_existing: bool = True,
        metadata_map: Optional[Dict[Path, Dict[str, Any]]] = None
    ) -> Tuple[int, int, List[str]]:
        """
        Import documents into the index
        
        Args:
            document_paths: List of document paths to import
            skip_existing: Whether to skip documents already in index
            metadata_map: Optional dict mapping Path -> metadata dict for documents
            
        Returns:
            Tuple of (imported_count, skipped_count, imported_paths)
        """
        if 'design_documents' not in self.index_data:
            self.index_data['design_documents'] = {}
        if 'quality_tracking' not in self.index_data['design_documents']:
            self.index_data['design_documents']['quality_tracking'] = {'documents': []}
        
        quality_tracking = self.index_data['design_documents']['quality_tracking']
        documents = quality_tracking.get('documents', [])
        
        tracked = self.get_tracked_documents()
        imported_count = 0
        skipped_count = 0
        imported_paths = []
        
        metadata_map = metadata_map or {}
        
        for doc_path in document_paths:
            doc_path = Path(doc_path).resolve()
            doc_str = str(doc_path)
            
            # Get metadata for this document if available
            metadata = metadata_map.get(doc_path)
            
            # Check if already tracked
            if skip_existing and doc_str in tracked:
                skipped_count += 1
                continue
            
            # Check if already in documents list (by primary_doc)
            already_exists = False
            for existing_doc in documents:
                existing_path = existing_doc.get('primary_doc', '')
                # Try to resolve and compare
                try:
                    if self.index_file_path.parent.exists():
                        existing_resolved = (self.index_file_path.parent / existing_path).resolve()
                        if existing_resolved == doc_path:
                            already_exists = True
                            break
                except (ValueError, OSError):
                    # If resolution fails, compare strings
                    if existing_path in doc_str or doc_str in existing_path:
                        already_exists = True
                        break
            
            if already_exists:
                skipped_count += 1
                continue
            
            # Create entry with metadata if available
            feature_group = metadata.get('feature_group') if metadata else None
            doc_entry = self.create_document_entry(doc_path, feature_group=feature_group, metadata=metadata)
            documents.append(doc_entry)
            imported_count += 1
            imported_paths.append(doc_str)
        
        # Update the index
        quality_tracking['documents'] = documents
        
        # Update metadata
        if 'metadata' not in self.index_data:
            self.index_data['metadata'] = {}
        self.index_data['metadata']['last_imported'] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        self.save_index()
        
        return imported_count, skipped_count, imported_paths
    
    def rescan_directory(
        self,
        directory: Path,
        recursive: bool = True,
        exclude_patterns: Optional[List[str]] = None
    ) -> Tuple[int, int, List[str]]:
        """
        Rescan directory and import new documents
        
        Args:
            directory: Directory to rescan
            recursive: Whether to scan recursively
            exclude_patterns: List of patterns to exclude
            
        Returns:
            Tuple of (imported_count, skipped_count, imported_paths)
        """
        # Scan for all documents
        found_docs = self.scan_directory(directory, recursive, exclude_patterns)
        
        # Import new ones
        return self.import_documents(found_docs, skip_existing=True)
    
    def get_document_count(self) -> int:
        """Get total number of tracked documents"""
        if 'design_documents' not in self.index_data:
            return 0
        
        quality_tracking = self.index_data['design_documents'].get('quality_tracking', {})
        documents = quality_tracking.get('documents', [])
        return len(documents)
    
    def extract_documents_from_current_version(self) -> List[Tuple[Path, Dict[str, Any]]]:
        """
        Extract document paths from current_version fields in the YAML index.
        Returns only the most recent document per feature group.
        
        Returns:
            List of tuples: (document_path, document_metadata)
            where document_metadata contains feature_group, name, quality_score, etc.
            Only one document per feature_group (most recent by analysis_date or created date)
        """
        documents_by_feature_group = {}
        
        if 'design_documents' not in self.index_data:
            return []
        
        quality_tracking = self.index_data['design_documents'].get('quality_tracking', {})
        documents = quality_tracking.get('documents', [])
        
        for doc_entry in documents:
            # Check if this entry has a current_version field
            current_version = doc_entry.get('current_version')
            if not current_version:
                continue
            
            # Get the file path from current_version
            file_path_str = current_version.get('file')
            if not file_path_str:
                continue
            
            # Resolve the path relative to index file's parent directory
            try:
                # Try relative path first
                doc_path = (self.index_file_path.parent / file_path_str).resolve()
            except (ValueError, OSError):
                # If that fails, try as absolute path
                doc_path = Path(file_path_str).resolve()
            
            # Extract metadata from the document entry
            feature_group = doc_entry.get('feature_group', 'unknown')
            analysis_date = current_version.get('analysis_date')
            created_date = current_version.get('created')
            
            # Determine date for comparison (prefer analysis_date, fallback to created)
            comparison_date = analysis_date or created_date or ''
            
            metadata = {
                'feature_group': feature_group,
                'name': doc_entry.get('name', doc_path.stem),
                'quality_score': current_version.get('quality_score'),
                'analysis_date': analysis_date,
                'status': current_version.get('status', 'not_analyzed'),
                'polishing_status': current_version.get('polishing_status', 'pending_analysis'),
                'created': created_date,
                'created_by': current_version.get('created_by'),
                '_comparison_date': comparison_date  # For sorting
            }
            
            # Keep only the most recent document per feature group
            if feature_group not in documents_by_feature_group:
                documents_by_feature_group[feature_group] = (doc_path, metadata)
            else:
                # Compare dates - keep the one with the latest date
                existing_date = documents_by_feature_group[feature_group][1].get('_comparison_date', '')
                if comparison_date > existing_date:
                    documents_by_feature_group[feature_group] = (doc_path, metadata)
        
        # Convert to list and remove internal comparison_date field
        result = []
        for doc_path, metadata in documents_by_feature_group.values():
            # Remove internal field
            metadata.pop('_comparison_date', None)
            result.append((doc_path, metadata))
        
        # Sort by feature_group for consistent ordering
        result.sort(key=lambda x: x[1].get('feature_group', ''))
        
        return result


"""
Tests for document chunking functionality.

This module tests the large document detection and chunking utilities
that enable processing of documents too large for single-pass LLM operations.
"""

import pytest
from startd8.document_chunking import (
    detect_large_document,
    split_document_by_sections,
    split_document_hybrid,
    reassemble_chunks,
    create_chunk_context,
    get_chunk_instructions,
    LargeDocumentConfig,
    LargeDocumentDetectionResult,
    DocumentChunk,
    ChunkedDocument,
    ChunkingStrategy,
)


class TestDetectLargeDocument:
    """Tests for large document detection."""
    
    def test_small_document_not_large(self):
        """Small documents should not be flagged as large."""
        config = LargeDocumentConfig(max_chars_single_pass=50_000)
        result = detect_large_document("A" * 10_000, config)
        
        assert not result.is_large
        assert result.recommended_chunks == 1
    
    def test_large_document_detected(self):
        """Documents exceeding threshold should be detected."""
        config = LargeDocumentConfig(max_chars_single_pass=50_000)
        result = detect_large_document("A" * 60_000, config)
        
        assert result.is_large
        assert result.recommended_chunks > 1
        assert "exceeds" in result.reason.lower()
    
    def test_token_estimate_threshold(self):
        """Token estimate threshold should also trigger detection."""
        config = LargeDocumentConfig(
            max_chars_single_pass=100_000,  # High char limit
            max_tokens_single_pass=5_000  # Low token limit
        )
        # 25,000 chars ≈ 6,250 tokens (exceeds 5,000)
        result = detect_large_document("A" * 25_000, config)
        
        assert result.is_large
        assert "token" in result.reason.lower()
    
    def test_result_is_truthy_when_large(self):
        """LargeDocumentDetectionResult should be truthy when large."""
        config = LargeDocumentConfig(max_chars_single_pass=1_000)
        result = detect_large_document("A" * 5_000, config)
        
        assert bool(result) is True
    
    def test_result_is_falsy_when_small(self):
        """LargeDocumentDetectionResult should be falsy when not large."""
        config = LargeDocumentConfig(max_chars_single_pass=50_000)
        result = detect_large_document("A" * 1_000, config)
        
        assert bool(result) is False
    
    def test_recommended_chunks_calculation(self):
        """Recommended chunks should be based on target chunk size."""
        config = LargeDocumentConfig(
            max_chars_single_pass=10_000,
            target_chunk_chars=5_000
        )
        # 25,000 chars / 5,000 per chunk = 5 chunks
        result = detect_large_document("A" * 25_000, config)
        
        assert result.is_large
        assert result.recommended_chunks >= 5


class TestSplitDocumentBySections:
    """Tests for section-based document splitting."""
    
    def test_document_with_sections(self):
        """Document with headers should be split by sections."""
        doc = """# Title

## Section 1

Content for section 1.

## Section 2

Content for section 2.
"""
        config = LargeDocumentConfig(target_chunk_chars=50)
        result = split_document_by_sections(doc, config)
        
        assert result.total_chunks >= 1
        assert result.strategy == ChunkingStrategy.SECTION
    
    def test_document_without_sections(self):
        """Document without headers should be single chunk."""
        doc = "Just some plain text without any headers."
        result = split_document_by_sections(doc)
        
        assert result.total_chunks == 1
        assert result.chunks[0].content == doc
    
    def test_section_path_tracking(self):
        """Chunks should track their section hierarchy."""
        doc = """# Main Title

## Parent Section

### Child Section

Content here.
"""
        result = split_document_by_sections(doc)
        
        # At least one chunk should have section path
        has_path = any(len(c.section_path) > 0 for c in result.chunks)
        assert has_path


class TestSplitDocumentHybrid:
    """Tests for hybrid document splitting."""
    
    def test_combines_section_and_size_limits(self):
        """Hybrid strategy should respect both sections and size limits."""
        # Create a document with one very large section
        large_section = "Content. " * 1000  # ~9000 chars
        doc = f"""# Title

## Small Section

Short content.

## Large Section

{large_section}

## Another Small Section

More short content.
"""
        config = LargeDocumentConfig(
            target_chunk_chars=2000,
            max_chunk_chars=3000
        )
        result = split_document_hybrid(doc, config)
        
        assert result.strategy == ChunkingStrategy.HYBRID
        # Large section should be split into multiple chunks
        assert result.total_chunks > 2
    
    def test_preserves_small_sections(self):
        """Small sections should remain intact."""
        doc = """# Title

## Section A

Short content A.

## Section B

Short content B.
"""
        config = LargeDocumentConfig(target_chunk_chars=10000)
        result = split_document_hybrid(doc, config)
        
        # With large target, sections should be grouped together
        assert result.total_chunks <= 2


class TestReassembleChunks:
    """Tests for chunk reassembly."""
    
    def test_basic_reassembly(self):
        """Processed chunks should be reassembled correctly."""
        original = ChunkedDocument(
            original_content="Original",
            chunks=[
                DocumentChunk(index=0, content="Part 1", start_line=1, end_line=5, section_path=[]),
                DocumentChunk(index=1, content="Part 2", start_line=6, end_line=10, section_path=[]),
            ],
            strategy=ChunkingStrategy.SECTION
        )
        
        processed = ["Polished Part 1", "Polished Part 2"]
        result = reassemble_chunks(processed, original)
        
        assert "Polished Part 1" in result
        assert "Polished Part 2" in result
    
    def test_chunk_count_mismatch_raises_error(self):
        """Mismatched chunk counts should raise ValueError."""
        original = ChunkedDocument(
            original_content="Original",
            chunks=[
                DocumentChunk(index=0, content="Part 1", start_line=1, end_line=5, section_path=[]),
            ],
            strategy=ChunkingStrategy.SECTION
        )
        
        processed = ["Part 1", "Part 2", "Part 3"]  # Too many
        
        with pytest.raises(ValueError, match="mismatch"):
            reassemble_chunks(processed, original)


class TestCreateChunkContext:
    """Tests for chunk context generation."""
    
    def test_includes_position_info(self):
        """Context should include chunk position."""
        chunk = DocumentChunk(index=1, content="Content", start_line=10, end_line=20, section_path=["Section A"])
        chunked_doc = ChunkedDocument(
            original_content="Full doc",
            chunks=[
                DocumentChunk(index=0, content="First", start_line=1, end_line=9, section_path=[]),
                chunk,
                DocumentChunk(index=2, content="Third", start_line=21, end_line=30, section_path=[]),
            ],
            strategy=ChunkingStrategy.SECTION
        )
        
        context = create_chunk_context(chunk, chunked_doc)
        
        assert "CHUNK 2 OF 3" in context
        assert "Section A" in context


class TestGetChunkInstructions:
    """Tests for chunk-specific instructions."""
    
    def test_first_chunk_instructions(self):
        """First chunk should have beginning-specific instructions."""
        chunk = DocumentChunk(index=0, content="First", start_line=1, end_line=10, section_path=[])
        chunked_doc = ChunkedDocument(
            original_content="Full",
            chunks=[chunk, DocumentChunk(index=1, content="Second", start_line=11, end_line=20, section_path=[])],
            strategy=ChunkingStrategy.SECTION
        )
        
        instructions = get_chunk_instructions(chunk, chunked_doc, task="polish")
        
        assert "BEGINNING" in instructions
        assert "title" in instructions.lower() or "introduction" in instructions.lower()
    
    def test_last_chunk_instructions(self):
        """Last chunk should have ending-specific instructions."""
        first = DocumentChunk(index=0, content="First", start_line=1, end_line=10, section_path=[])
        last = DocumentChunk(index=1, content="Last", start_line=11, end_line=20, section_path=[])
        chunked_doc = ChunkedDocument(
            original_content="Full",
            chunks=[first, last],
            strategy=ChunkingStrategy.SECTION
        )
        
        instructions = get_chunk_instructions(last, chunked_doc, task="polish")
        
        assert "END" in instructions
        assert "conclusion" in instructions.lower()
    
    def test_middle_chunk_instructions(self):
        """Middle chunks should have continuity instructions."""
        chunks = [
            DocumentChunk(index=i, content=f"Chunk {i}", start_line=i*10+1, end_line=(i+1)*10, section_path=[])
            for i in range(3)
        ]
        chunked_doc = ChunkedDocument(
            original_content="Full",
            chunks=chunks,
            strategy=ChunkingStrategy.SECTION
        )
        
        instructions = get_chunk_instructions(chunks[1], chunked_doc, task="polish")
        
        assert "MIDDLE" in instructions
        assert "continuity" in instructions.lower()


class TestDocumentChunk:
    """Tests for DocumentChunk dataclass."""
    
    def test_char_count_property(self):
        """char_count should return content length."""
        chunk = DocumentChunk(
            index=0,
            content="Hello World",
            start_line=1,
            end_line=1,
            section_path=[]
        )
        assert chunk.char_count == 11
    
    def test_estimated_tokens_property(self):
        """estimated_tokens should be approximately chars/4."""
        chunk = DocumentChunk(
            index=0,
            content="A" * 400,  # 400 chars
            start_line=1,
            end_line=1,
            section_path=[]
        )
        assert chunk.estimated_tokens == 100  # 400 / 4


class TestLargeDocumentConfig:
    """Tests for LargeDocumentConfig defaults."""
    
    def test_default_values(self):
        """Default config should have sensible values."""
        config = LargeDocumentConfig()
        
        assert config.max_chars_single_pass == 50_000
        assert config.max_tokens_single_pass == 12_000
        assert config.target_chunk_chars == 20_000
        assert config.preserve_sections is True
    
    def test_custom_values(self):
        """Custom config values should be respected."""
        config = LargeDocumentConfig(
            max_chars_single_pass=100_000,
            target_chunk_chars=10_000
        )
        
        assert config.max_chars_single_pass == 100_000
        assert config.target_chunk_chars == 10_000


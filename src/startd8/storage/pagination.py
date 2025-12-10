"""
Pagination utilities for storage operations
"""

from typing import List, TypeVar, Generic, Iterator
from math import ceil

from ..models import PaginatedResult

T = TypeVar('T')


def paginate(items: List[T], page: int = 1, page_size: int = 50) -> PaginatedResult:
    """
    Paginate a list of items
    
    Args:
        items: List of items to paginate
        page: Page number (1-indexed)
        page_size: Number of items per page
    
    Returns:
        PaginatedResult with paginated items
    
    Raises:
        ValueError: If page or page_size is invalid
    """
    if page < 1:
        raise ValueError("Page must be >= 1")
    if page_size < 1:
        raise ValueError("Page size must be >= 1")
    
    total = len(items)
    total_pages = ceil(total / page_size) if total > 0 else 1
    
    # Clamp page to valid range
    if page > total_pages:
        page = total_pages
    
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    
    paginated_items = items[start_idx:end_idx]
    
    return PaginatedResult(
        items=paginated_items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )


def paginate_generator(
    items: Iterator[T],
    total: int,
    page: int = 1,
    page_size: int = 50
) -> PaginatedResult:
    """
    Paginate items from a generator/iterator
    
    Args:
        items: Iterator of items
        total: Total number of items (must be known)
        page: Page number (1-indexed)
        page_size: Number of items per page
    
    Returns:
        PaginatedResult with paginated items
    """
    if page < 1:
        raise ValueError("Page must be >= 1")
    if page_size < 1:
        raise ValueError("Page size must be >= 1")
    
    total_pages = ceil(total / page_size) if total > 0 else 1
    
    # Clamp page to valid range
    if page > total_pages:
        page = total_pages
    
    # Skip items before the requested page
    skip = (page - 1) * page_size
    for _ in range(skip):
        try:
            next(items)
        except StopIteration:
            break
    
    # Collect items for the requested page
    page_items = []
    for _ in range(page_size):
        try:
            page_items.append(next(items))
        except StopIteration:
            break
    
    return PaginatedResult(
        items=page_items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )










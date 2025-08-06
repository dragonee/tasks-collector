import re
from django.db.models import Q
from ..models import Event, Statistics


def count_words_in_text(text):
    """Count words in a text string, excluding empty strings"""
    if not text or not isinstance(text, str):
        return 0
    # Split by whitespace and count non-empty strings
    return len([word for word in re.split(r'\s+', text.strip()) if word])


def calculate_total_word_count(year=None):
    """Calculate total word count from all events with text content
    
    Args:
        year (int, optional): Filter events by year. If None, includes all events.
    """
    total_words = 0
    
    # Get all events, optionally filtered by year
    events = Event.objects.all()
    if year:
        events = events.filter(published__year=year)
    
    for event in events:
        # Check for text fields in different event types
        text_fields = []
        
        # Common text fields across event types
        if hasattr(event, 'comment') and event.comment:
            text_fields.append(event.comment)
        
        if hasattr(event, 'note') and event.note:
            text_fields.append(event.note)
            
        if hasattr(event, 'situation') and event.situation:
            text_fields.append(event.situation)
            
        if hasattr(event, 'interpretation') and event.interpretation:
            text_fields.append(event.interpretation)
            
        if hasattr(event, 'approach') and event.approach:
            text_fields.append(event.approach)
            
        if hasattr(event, 'description') and event.description:
            text_fields.append(event.description)
            
        if hasattr(event, 'name') and event.name:
            text_fields.append(event.name)
            
        if hasattr(event, 'success_criteria') and event.success_criteria:
            text_fields.append(event.success_criteria)
        
        # Count words in all text fields for this event
        for text in text_fields:
            total_words += count_words_in_text(text)
    
    return total_words


def update_word_count_statistic(year=None):
    """Update or create the word count statistic
    
    Args:
        year (int, optional): Year to calculate for. If None, calculates for all events.
    """
    total_words = calculate_total_word_count(year)
    
    # Create key based on year
    key = f'total_word_count_{year}' if year else 'total_word_count'
    
    # Update or create the statistic
    stat, created = Statistics.objects.get_or_create(
        key=key,
        defaults={'value': total_words}
    )
    
    if not created:
        stat.value = total_words
        stat.save()
    
    return total_words


def get_all_years_in_database():
    """Get all years that have events in the database"""
    years = Event.objects.dates('published', 'year').values_list('published__year', flat=True)
    return list(set(years))


def get_word_count_statistic(year=None):
    """Get the current word count statistic
    
    Args:
        year (int, optional): Year to get statistic for. If None, gets overall statistic.
    """
    key = f'total_word_count_{year}' if year else 'total_word_count'
    
    try:
        stat = Statistics.objects.get(key=key)
        return stat.value, stat.last_updated
    except Statistics.DoesNotExist:
        return None, None
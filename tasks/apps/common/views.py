from django.http import JsonResponse


def health_check(request):
    """Health check endpoint for Docker container health monitoring."""
    return JsonResponse({"status": "healthy"})

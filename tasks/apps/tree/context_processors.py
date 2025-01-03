from datetime import datetime

def menu(request):
    return {
        'current_year': datetime.now().year
    }
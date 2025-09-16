# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Frontend Development
- `docker compose -f docker/development/docker-compose.yml exec tasks-frontend npm run dev` - Start webpack in watch mode for development
- `docker compose -f docker/development/docker-compose.yml exec tasks-frontend npm run build` - Build assets for development
- `docker compose -f docker/development/docker-compose.yml exec tasks-frontend npm run build-dist` - Build production-ready assets

### Backend Development
- `docker compose -f docker/development/docker-compose.yml exec tasks-backend python manage.py runserver` - Start Django development server
- `docker compose -f docker/development/docker-compose.yml exec tasks-backend python manage.py migrate` - Run database migrations
- `docker compose -f docker/development/docker-compose.yml exec tasks-backend python manage.py createsuperuser` - Create admin user
- `docker compose -f docker/development/docker-compose.yml exec tasks-backend python manage.py test` - Run Django tests
- `docker compose -f docker/development/docker-compose.yml exec tasks-backend pytest` - Run tests with pytest (configured in pytest.ini)
- `docker compose -f docker/development/docker-compose.yml exec tasks-backend python manage.py loaddata tasks/fixtures/dev/initial_state.json` - Load development fixtures

### Docker Development
- `docker-compose up` (from docker/development/) - Start full development environment
- `docker-compose exec tasks-backend bash` - Access running container

## Architecture Overview

### Core Structure
This is a Django-based personal productivity application with a Vue.js frontend. The system uses an **event-driven architecture** where all user activities are tracked as events with stream IDs.

### Django Apps

1. **Common App** (`tasks.apps.common`)
   - Provides shared functionality and custom User model
   - Contains template tags and management commands

2. **Quests App** (`tasks.apps.quests`)
   - Quest-based goal tracking with journaling
   - Models: Quest, QuestJournal

3. **Rewards App** (`tasks.apps.rewards`)
   - Gamification system with nested reward tables
   - Models: Reward, RewardTableItem, Claim, Claimed
   - Uses probability-based reward distribution

4. **Tree App** (`tasks.apps.tree`) - **Main Application**
   - Core productivity system with comprehensive life tracking
   - **Thread-based organization**: Daily, Weekly, Monthly threads
   - **Event sourcing**: All activities tracked as polymorphic events
   - Key models: Thread, Event, Board, Habit, Observation, Plan, Reflection, JournalAdded, QuickNote, Breakthrough

### Key Architectural Patterns

- **Event Sourcing**: All changes tracked as events with stream IDs
- **Polymorphic Events**: Different event types share common Event base class
- **Thread-Based Organization**: Activities organized into Daily/Weekly/Monthly threads
- **API-First Design**: Full REST API coverage alongside traditional Django views

### Frontend Architecture
- **Vue.js 2.x** with Vuex for state management
- **Webpack** for asset bundling
- **Bootstrap 4** for UI components

### Database
- **PostgreSQL** for production
- Uses Django migrations for schema management
- Event streams for tracking all user activities

### Development Environment
- Supports both traditional Python/Django setup and Docker development
- Auto-reloading for both backend and frontend changes
- Separate configurations for local/development/production environments

## Important Notes

- Settings are environment-specific (local.py, dist.py)
- Database and email configurations use separate .py files (db.py, email.py)
- All user activities are tracked through the event system
- The system is designed around personal productivity and development workflows
- Uses Django Polymorphic for event inheritance

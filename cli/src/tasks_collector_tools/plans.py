import requests
import aiohttp
import asyncio
from datetime import date, datetime, timedelta
from calendar import monthrange

from dataclasses import dataclass

from .utils import itemize_string, SHORT_TIMEOUT

from requests.exceptions import ConnectionError


FOCUS_TEMPLATE = "Focus: {focus}"

PLAN_TEMPLATE = """
{focus}
"""

@dataclass
class Plan:
    id: int
    pub_date: date
    focus: str

    def __str__(self):
        if not self.focus:
            return ""

        focus = itemize_string(self.focus, prepend="\n", prefix="- [ ] ")

        if focus.strip():
            focus = FOCUS_TEMPLATE.format(focus=focus)

        return PLAN_TEMPLATE.format(focus=focus).strip() + "\n"


def get_plan_for_today(config):
    try:
        url = '{}/plans/?pub_date={}&thread=Daily'.format(config.url, date.today().isoformat())

        response = requests.get(
            url, 
            auth=(config.user, config.password), 
            timeout=SHORT_TIMEOUT
        )
        response.raise_for_status()

        data = response.json()

        if data['count'] == 0:
            return Plan(id=None, pub_date=date.today(), focus="")

        return Plan(**data['results'][0])
    except ConnectionError:
        return Plan(id=None, pub_date=date.today(), focus='')

def get_end_of_week(dt: date) -> date:
    """Get the date of the end of the week (Sunday) for the given date."""
    days_until_sunday = 6 - dt.weekday()
    return dt + timedelta(days=days_until_sunday)

def get_end_of_month(dt: date) -> date:
    """Get the last day of the month for the given date."""
    _, last_day = monthrange(dt.year, dt.month)
    return date(dt.year, dt.month, last_day)

async def fetch_plan(session: aiohttp.ClientSession, config, target_date: date, thread: str) -> Plan:
    """Fetch a single plan asynchronously."""
    try:
        url = f'{config.url}/plans/?pub_date={target_date.isoformat()}&thread={thread}'
        
        async with session.get(
            url,
            auth=aiohttp.BasicAuth(config.user, config.password),
            timeout=SHORT_TIMEOUT
        ) as response:
            response.raise_for_status()
            data = await response.json()
            
            if data['count'] == 0:
                return Plan(id=None, pub_date=target_date, focus="")
            
            return Plan(**data['results'][0])
    except (aiohttp.ClientError, asyncio.TimeoutError):
        return Plan(id=None, pub_date=target_date, focus='')

async def get_plans_for_today(config):
    """Fetch three plans in parallel:
    1. Daily plan for today
    2. Weekly plan for the end of the week
    3. Big-picture plan for the end of the month
    """
    today = date.today()
    end_of_week = get_end_of_week(today)
    end_of_month = get_end_of_month(today)
    
    async with aiohttp.ClientSession() as session:
        daily_plan, weekly_plan, monthly_plan = await asyncio.gather(
            fetch_plan(session, config, today, 'Daily'),
            fetch_plan(session, config, end_of_week, 'Weekly'),
            fetch_plan(session, config, end_of_month, 'Big-picture')
        )
        
        return {
            'daily': daily_plan,
            'weekly': weekly_plan,
            'monthly': monthly_plan
        }

def get_plans_for_today_sync(config):
    """Synchronous wrapper for get_plans_for_today."""
    return asyncio.run(get_plans_for_today(config))
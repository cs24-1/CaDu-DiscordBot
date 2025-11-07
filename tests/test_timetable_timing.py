"""Test suite for timetable task timing functionality."""
import asyncio
import unittest
from datetime import datetime, timedelta
import pytz
from unittest.mock import MagicMock, patch, AsyncMock
from discord.ext import commands
from cogs.timetable import Timetable

class TestTimetableTaskTiming(unittest.TestCase):
    def setUp(self):
        """Set up test environment before each test."""
        self.bot = MagicMock(spec=commands.Bot)
        self.bot.wait_until_ready = AsyncMock()
        self.channel = MagicMock()
        self.bot.get_channel.return_value = self.channel
        self.cog = Timetable(self.bot)

    async def test_wait_until_6am(self):
        """Test that the task waits correctly until 6 AM."""
        berlin = pytz.timezone("Europe/Berlin")
        
        # Mock current time as 5 AM
        current_time = datetime.now(berlin).replace(
            hour=5, minute=0, second=0, microsecond=0
        )
        expected_target = current_time.replace(hour=6)  # 6 AM same day
        expected_wait = 3600  # One hour in seconds

        with patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep, \
             patch('datetime.datetime') as mock_datetime:
            
            # Setup datetime mock
            mock_datetime.now.return_value = current_time
            
            # Run the task
            await self.cog.daily_timetable_task()
            
            # Verify sleep was called with correct wait time (1 hour)
            mock_sleep.assert_awaited_with(expected_wait)

    async def test_correct_schedule_time(self):
        """Test that the task is scheduled for the correct time (6 AM Berlin time)."""
        with patch('datetime.datetime') as mock_datetime:
            # Mock time as midnight
            berlin = pytz.timezone("Europe/Berlin")
            midnight = datetime.now(berlin).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            mock_datetime.now.return_value = midnight
            
            # Calculate expected wait time (6 hours)
            expected_wait = 6 * 3600  # 6 hours in seconds
            
            with patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
                await self.cog.daily_timetable_task()
                mock_sleep.assert_awaited_with(expected_wait)

    @patch('utils.timetableUtils.get_timetable')
    async def test_no_wait_after_6am(self, mock_get_timetable):
        """Test that task executes immediately if started after 6 AM."""
        berlin = pytz.timezone("Europe/Berlin")
        test_time = datetime.now(berlin).replace(
            hour=7, minute=0, second=0, microsecond=0
        )

        with patch('datetime.datetime') as mock_datetime, \
             patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
            
            mock_datetime.now.return_value = test_time
            mock_get_timetable.return_value = "Test timetable"
            
            await self.cog.daily_timetable_task()
            
            # Verify sleep was not called (no waiting needed)
            mock_sleep.assert_not_awaited()

    @patch('utils.timetableUtils.get_timetable')
    async def test_24h_loop_timing(self, mock_get_timetable):
        """Test that the task repeats every 24 hours."""
        # This test verifies the @tasks.loop(hours=24) decorator
        self.assertEqual(
            self.cog.daily_timetable_task.hours,
            24,
            "Task should be configured to run every 24 hours"
        )

def async_test(coro):
    """Helper to run async tests."""
    def wrapper(*args, **kwargs):
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(coro(*args, **kwargs))
    return wrapper

if __name__ == '__main__':
    unittest.main()
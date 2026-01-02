from django.test import TestCase

from ..commit import calculate_changes_per_board


class CommitTestCase(TestCase):
    """Test cases for board commit functionality."""

    def test_item_cannot_stay_on_board_for_more_than_5_weeks(self):
        """Test that an item cannot stay on a board for more than 5 weeks by progressing it through 6 transitions."""

        # Start with a single item at week 0
        board_state = [
            {
                "text": "Test item",
                "data": {
                    "text": "Test item",
                    "state": "active",
                    "meaningfulMarkers": {
                        "weeksInList": 0,
                        "canBePostponed": False,
                        "postponedFor": 0,
                        "important": False,
                        "finalizing": False,
                        "canBeDoneOutsideOfWork": False,
                        "madeProgress": False,
                    },
                },
                "state": {"checked": False},
                "children": [],
            }
        ]

        # Progress through 6 weeks (transitions)
        for week in range(6):
            result = calculate_changes_per_board(board_state)

            if week < 5:  # Weeks 0-4 (transitions 1-5)
                # Item should still be present in current board (None key)
                self.assertIn(
                    None, result, f"Current board should exist at week {week}"
                )
                current_board = result[None]
                self.assertEqual(
                    len(current_board), 1, f"Item should be present at week {week}"
                )
                self.assertEqual(current_board[0]["text"], "Test item")

                # Verify weeksInList is incremented correctly
                expected_weeks = week + 1
                actual_weeks = current_board[0]["data"]["meaningfulMarkers"][
                    "weeksInList"
                ]
                self.assertEqual(
                    actual_weeks,
                    expected_weeks,
                    f"weeksInList should be {expected_weeks} at transition {week + 1}",
                )

                # Update board_state for next iteration
                board_state = current_board
            else:  # Week 5 (6th transition)
                # Item should be removed (either no current board or empty current board)
                if None in result:
                    current_board = result[None]
                    self.assertEqual(
                        len(current_board),
                        0,
                        "Item should be removed after 6th week (weeksInList=5)",
                    )
                else:
                    # No current board means no items
                    self.assertTrue(
                        True, "No current board means item was filtered out"
                    )

    def test_postponed_item_exempt_from_5_week_rule(self):
        """Test that a postponed item survives beyond 5 weeks."""

        # Start with a postponed item
        board_state = [
            {
                "text": "Postponed item",
                "data": {
                    "text": "Postponed item",
                    "state": "active",
                    "meaningfulMarkers": {
                        "weeksInList": 4,  # Start at week 4
                        "canBePostponed": False,
                        "postponedFor": 2,  # Postponed for 2 weeks
                        "important": False,
                        "finalizing": False,
                        "canBeDoneOutsideOfWork": False,
                        "madeProgress": False,
                    },
                },
                "state": {"checked": False},
                "children": [],
            }
        ]

        # Progress through 3 more transitions (should reach weeksInList=5 but stay postponed)
        for week in range(3):
            result = calculate_changes_per_board(board_state)

            # Item should always be present because it's postponed
            self.assertIn(None, result)
            current_board = result[None]
            self.assertEqual(
                len(current_board), 1, f"Postponed item should survive week {week + 4}"
            )

            # Update for next iteration
            board_state = current_board

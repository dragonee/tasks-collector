package org.polybrain.tasks.health.data

import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class TripDetailTest {

    // As TasksClient configures it.
    private val json = Json {
        ignoreUnknownKeys = true
        encodeDefaults = true
    }

    @Test
    fun `a trip's events carry where they were made, or no place`() {
        val detail = json.decodeFromString<TripDetailResponse>(
            """
            {"story": {"id": 3, "type": "trip", "title": "Walk",
                       "started": "2026-06-06T09:00:00+00:00", "stopped": null},
             "events": [
               {"id": 1, "type": "journal", "published": "2026-06-06T10:00:00+00:00",
                "location": {"lat": 40.7128, "lng": -74.006, "acc": 5.0},
                "comment": "Coffee at the corner"},
               {"id": 2, "type": "photo", "published": "2026-06-06T10:05:00+00:00",
                "location": {"lat": 1.5, "lng": 2.5, "acc": null},
                "comment": "", "thumbnail_url": null, "ready": false},
               {"id": 3, "type": "journal", "published": "2026-06-06T10:10:00+00:00",
                "location": null, "comment": "no place"},
               {"id": 4, "type": "habit", "published": "2026-06-06T10:15:00+00:00",
                "habit_slug": "walk", "habit_name": "Walk", "occured": true, "note": ""}
             ],
             "share": null}
            """,
        )

        val (coffee, photo, plain, habit) = detail.events
        assertEquals(EventLocation(40.7128, -74.006, 5f), coffee.location)
        assertEquals("Coffee at the corner", coffee.comment)
        assertEquals(EventLocation(1.5, 2.5, null), photo.location)
        assertNull(plain.location)
        assertNull(habit.location)
    }
}

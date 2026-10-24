from collections import Counter

from sqlalchemy import func, select

from ayda.core.db import Database
from ayda.modules import habits, quests
from ayda.modules.quests import Template


def test_catalog_has_150_to_200_quests_and_15_per_category() -> None:
    catalog = quests.load_catalog()

    assert 150 <= len(catalog.quests) <= 200
    per_category = Counter(q.category for q in catalog.quests)
    assert set(per_category) == set(quests.CATEGORIES)
    assert min(per_category.values()) >= 15


def test_catalog_interests_exist_and_the_main_ones_have_quests() -> None:
    catalog = quests.load_catalog()
    used = {i for q in catalog.quests for i in q.interests}

    assert used <= habits.INTEREST_CODES
    # Interests such as music or theatre are served by events, not by catalog quests.
    assert {"sport", "outdoors", "city", "learning", "rest", "project", "friends", "home"} <= used


def test_rest_quests_cover_the_same_durations_as_sport() -> None:
    catalog = quests.load_catalog()

    def buckets(category: str) -> set[int]:
        return {
            0
            if q.duration_min <= 15
            else 1
            if q.duration_min <= 30
            else 2
            if q.duration_min <= 60
            else 3
            for q in catalog.quests
            if q.category == category
        }

    assert buckets("rest") == buckets("sport") == {0, 1, 2, 3}


async def test_migration_seeded_the_catalog_and_sync_is_idempotent(database: Database) -> None:
    async with database.sessionmaker() as session:
        count = await session.scalar(select(func.count()).select_from(Template))
        assert count == len(quests.load_catalog().quests)

        assert await quests.sync_catalog(session) == count
        await session.rollback()

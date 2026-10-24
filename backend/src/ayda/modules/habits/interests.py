"""Interests (ADR 0018): what the user likes, from a catalog in code plus their own words.

An interest says which quest and event categories it serves and which words of an event title
point at it, so one pick feeds quest selection, event ranking and the assistant.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Interest:
    code: str
    title: str
    # Quest and event categories this interest serves.
    categories: tuple[str, ...]
    # Word stems (lower case, "е" for "ё") found in the titles of events of this interest.
    words: tuple[str, ...] = ()


# Codes are stable: quest templates and saved choices refer to them.
INTERESTS: tuple[Interest, ...] = (
    Interest(
        "sport",
        "Спорт и тренировки",
        ("sport",),
        ("спорт", "футбол", "забег", "марафон", "турнир", "фитнес", "трениров", "баскетбол"),
    ),
    Interest(
        "outdoors",
        "Прогулки и природа",
        ("walk",),
        ("прогулк", "природ", "поход", "пляж", "экскурс", "парк"),
    ),
    Interest(
        "city",
        "Город и история",
        ("city",),
        ("истори", "музе", "форт", "архитектур", "краевед", "экскурс"),
    ),
    Interest(
        "music",
        "Музыка и концерты",
        ("city",),
        ("концерт", "джаз", "рок", "оркестр", "музык", "хор", "опен эйр", "open air"),
    ),
    Interest(
        "theatre",
        "Театр и кино",
        ("city",),
        ("спектакл", "театр", "кино", "балет", "опер", "мюзикл"),
    ),
    Interest(
        "art",
        "Искусство и выставки",
        ("city",),
        ("выставк", "галере", "искусств", "фотограф", "арт"),
    ),
    Interest(
        "humor",
        "Стендап и юмор",
        ("city", "social"),
        ("стендап", "юмор", "комеди", "импров"),
    ),
    Interest(
        "learning",
        "Лекции и учёба",
        ("learning",),
        ("лекци", "мастер-класс", "курс", "воркшоп", "обучен"),
    ),
    Interest(
        "books",
        "Книги и чтение",
        ("learning",),
        ("книг", "чтени", "писател", "поэзи", "литератур"),
    ),
    Interest(
        "cooking",
        "Еда и готовка",
        ("home",),
        ("гастро", "дегустац", "кулинар", "фуд", "ярмарк"),
    ),
    Interest(
        "games",
        "Игры и настолки",
        ("social",),
        ("квиз", "настол", "киберспорт", "квест"),
    ),
    Interest(
        "friends",
        "Встречи с людьми",
        ("social",),
        ("встреч", "клуб", "нетворкинг", "вечеринк", "разговорн"),
    ),
    Interest(
        "family",
        "Семья и дети",
        ("social",),
        ("детск", "семейн", "малыш"),
    ),
    Interest(
        "rest",
        "Спокойный отдых",
        ("rest",),
        ("спа", "медитац", "релакс", "йога"),
    ),
    Interest("project", "Свой проект", ("project",), ("стартап", "хакатон", "предпринимат")),
    Interest("home", "Порядок и уют дома", ("home",)),
)

INTEREST_CODES = frozenset(i.code for i in INTERESTS)
BY_CODE = {i.code: i for i in INTERESTS}
MAX_INTERESTS = 8
MAX_TAGS = 5
MAX_TAG_LENGTH = 30


def categories_of(codes: list[str] | tuple[str, ...]) -> set[str]:
    return {c for code in codes if code in BY_CODE for c in BY_CODE[code].categories}


def words_of(codes: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(w for code in codes if code in BY_CODE for w in BY_CODE[code].words))

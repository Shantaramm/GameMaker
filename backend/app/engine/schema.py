"""Примитивы движка: документ Game и всё, из чего он состоит (SPEC §5).

Модели проверяют только форму данных. Ссылки между объектами, достижимость
и прочие смысловые правила проверяет validator.py.

Объединения (события, условия, эффекты, внешность врага) размечены тегами
с префиксом "~". Validator убирает эти теги из пути ошибки, чтобы путь
выглядел как `scenes[3].events[1].nodes[4].next`.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Discriminator, Field, Tag

TAG_PREFIX = "~"

Id = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]*$", max_length=64)]
Stat = Literal["hp", "attack", "defense", "focus"]
Emotion = Literal["neutral", "angry", "sad", "happy", "scared", "surprised"]
Role = Literal["hero", "companion", "npc", "antagonist"]
PaletteName = Id
PartId = Id


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


def _tag(name: str) -> Tag:
    return Tag(TAG_PREFIX + name)


def _key_discriminator(keys: tuple[str, ...]):
    """Тег варианта по первому найденному ключу (для объектов вида {set_flag: ...})."""

    def pick(value: Any) -> str | None:
        if isinstance(value, dict):
            present = value.keys()
        else:
            present = {
                f.alias or name for name, f in type(value).model_fields.items()
            }
        for key in keys:
            if key in present:
                return TAG_PREFIX + key
        return None

    return Discriminator(pick)


# --- Условия (§5.5) ---------------------------------------------------------


class CondAll(Strict):
    all: list[Condition] = Field(min_length=1)


class CondAny(Strict):
    any: list[Condition] = Field(min_length=1)


class CondNot(Strict):
    not_: Condition = Field(alias="not")


class CondFlag(Strict):
    flag: Id
    is_: bool = Field(alias="is")


class CondItem(Strict):
    has_item: Id


class CondStat(Strict):
    stat: Stat
    op: Literal[">=", "<="]
    value: int


_COND_KEYS = ("all", "any", "not", "flag", "has_item", "stat")

Condition = Annotated[
    Union[
        Annotated[CondAll, _tag("all")],
        Annotated[CondAny, _tag("any")],
        Annotated[CondNot, _tag("not")],
        Annotated[CondFlag, _tag("flag")],
        Annotated[CondItem, _tag("has_item")],
        Annotated[CondStat, _tag("stat")],
    ],
    _key_discriminator(_COND_KEYS),
]


# --- Эффекты (§5.5) ---------------------------------------------------------


class EffSetFlag(Strict):
    set_flag: Id
    value: bool


class EffGiveItem(Strict):
    give_item: Id


class EffTakeItem(Strict):
    take_item: Id


class EffLearnSkill(Strict):
    learn_skill: Id


class EffModStat(Strict):
    mod_stat: Stat
    delta: int


class EffHeal(Strict):
    heal: int = Field(ge=1)


class EffDamage(Strict):
    damage: int = Field(ge=1)


class EffGoto(Strict):
    goto: Id


_EFFECT_KEYS = (
    "set_flag", "give_item", "take_item", "learn_skill",
    "mod_stat", "heal", "damage", "goto",
)

Effect = Annotated[
    Union[
        Annotated[EffSetFlag, _tag("set_flag")],
        Annotated[EffGiveItem, _tag("give_item")],
        Annotated[EffTakeItem, _tag("take_item")],
        Annotated[EffLearnSkill, _tag("learn_skill")],
        Annotated[EffModStat, _tag("mod_stat")],
        Annotated[EffHeal, _tag("heal")],
        Annotated[EffDamage, _tag("damage")],
        Annotated[EffGoto, _tag("goto")],
    ],
    _key_discriminator(_EFFECT_KEYS),
]


# --- Внешность (§5.7). id деталей сверяются с библиотекой в validator.py ----


class PortraitSpec(Strict):
    head: PartId
    skin: PaletteName
    hair: PartId  # "none" — лысый
    hair_color: PaletteName
    eyes: PartId
    eye_color: PaletteName
    brows: PartId
    mouth: PartId
    facial_hair: PartId | None = None
    outfit: PartId
    outfit_color: PaletteName
    accent_color: PaletteName
    accessory: list[PartId] = Field(default_factory=list, max_length=2)
    bg_color: PaletteName


class CreatureSpec(Strict):
    body: PartId
    color: PaletteName
    accent_color: PaletteName
    features: list[PartId] = Field(default_factory=list, max_length=3)
    size: Literal["small", "medium", "large"]


class BackgroundProp(Strict):
    id: PartId
    x: int = Field(ge=0, le=160)


class BackgroundSpec(Strict):
    setting: Literal["indoor", "outdoor"]
    time: Literal["day", "dusk", "night"]
    sky: PartId | None = None
    far: PartId
    props: list[BackgroundProp] = Field(default_factory=list, max_length=5)
    ground: PartId
    overlay: Literal["rain", "fog", "snow", "dust", "none"] = "none"
    mood_palette: PaletteName


def _appearance_tag(value: Any) -> str:
    if isinstance(value, dict):
        is_creature = "body" in value
    else:
        is_creature = isinstance(value, CreatureSpec)
    return TAG_PREFIX + ("creature" if is_creature else "portrait")


EnemyAppearance = Annotated[
    Union[
        Annotated[PortraitSpec, _tag("portrait")],
        Annotated[CreatureSpec, _tag("creature")],
    ],
    Discriminator(_appearance_tag),
]


# --- Персонажи и бой (§5.2, §5.3) --------------------------------------------


class Meta(Strict):
    title: str = Field(min_length=1, max_length=120)
    logline: str = Field(max_length=500)
    tone: str = Field(max_length=200)
    art_style: str = Field(max_length=200)
    language: Literal["ru"] = "ru"
    est_minutes: int = Field(ge=1, le=120)


class Character(Strict):
    id: Id
    name: str = Field(min_length=1, max_length=60)
    role: Role
    description: str = Field(max_length=1000)
    appearance: PortraitSpec


class Stats(Strict):
    """Стартовые статы героя. hp и focus — максимумы; текущие значения живут в рантайме."""

    hp: int = Field(ge=1)
    attack: int = Field(ge=0)
    defense: int = Field(ge=0)
    focus: int = Field(ge=0)


class Skill(Strict):
    id: Id
    name: str = Field(min_length=1, max_length=60)
    description: str = Field(max_length=300)
    cost_focus: int = Field(ge=0)
    effect: list[Effect] = Field(min_length=1)
    target: Literal["enemy", "self"]


class Item(Strict):
    id: Id
    name: str = Field(min_length=1, max_length=60)
    description: str = Field(max_length=300)
    consumable: bool
    effect: list[Effect] = Field(default_factory=list)


class EnemyAbility(Strict):
    name: str = Field(min_length=1, max_length=60)
    effect: list[Effect] = Field(min_length=1)
    every_n_turns: int = Field(ge=1)


class Enemy(Strict):
    id: Id
    name: str = Field(min_length=1, max_length=60)
    description: str = Field(max_length=500)
    tier: int = Field(ge=1, le=5)
    appearance: EnemyAppearance
    # Заполняет balance.py, не LLM.
    hp: int | None = Field(default=None, ge=1)
    attack: int | None = Field(default=None, ge=0)
    defense: int | None = Field(default=None, ge=0)
    abilities: list[EnemyAbility] = Field(default_factory=list, max_length=2)


class FlagDef(Strict):
    id: Id
    description: str = Field(default="", max_length=300)


# --- Сцены и события (§5.4) ------------------------------------------------


class DialogueChoice(Strict):
    text: str = Field(min_length=1)
    condition: Condition | None = None
    effects: list[Effect] = Field(default_factory=list)
    next: Id  # node_id или "end"


class DialogueNode(Strict):
    id: Id
    speaker: Id  # character_id или "narrator"
    text: str = Field(min_length=1)
    emotion: Emotion | None = None
    choices: list[DialogueChoice] = Field(default_factory=list)
    next: Id | None = None  # node_id или "end"; нужен, когда choices пусто


class Dialogue(Strict):
    type: Literal["dialogue"]
    id: Id
    nodes: list[DialogueNode] = Field(min_length=1)
    start_node: Id


def _on_lose_tag(value: Any) -> str:
    return TAG_PREFIX + ("game_over" if isinstance(value, str) else "effects")


OnLose = Annotated[
    Union[
        Annotated[Literal["game_over"], _tag("game_over")],
        Annotated[list[Effect], _tag("effects")],
    ],
    Discriminator(_on_lose_tag),
]


class Battle(Strict):
    type: Literal["battle"]
    id: Id
    enemies: list[Id] = Field(min_length=1, max_length=3)
    on_win: list[Effect] = Field(default_factory=list)
    on_lose: OnLose = "game_over"
    can_flee: bool = False


class ChoiceOption(Strict):
    text: str = Field(min_length=1)
    condition: Condition | None = None
    effects: list[Effect] = Field(default_factory=list)


class Choice(Strict):
    type: Literal["choice"]
    id: Id
    prompt: str = Field(min_length=1)
    options: list[ChoiceOption] = Field(min_length=1)


class Narration(Strict):
    type: Literal["narration"]
    id: Id
    text: str = Field(min_length=1)


class Transition(Strict):
    type: Literal["goto"]
    to: Id  # scene_id или ending_id
    condition: Condition | None = None


def _event_tag(value: Any) -> str | None:
    kind = value.get("type") if isinstance(value, dict) else getattr(value, "type", None)
    return TAG_PREFIX + kind if isinstance(kind, str) else None


Event = Annotated[
    Union[
        Annotated[Dialogue, _tag("dialogue")],
        Annotated[Battle, _tag("battle")],
        Annotated[Choice, _tag("choice")],
        Annotated[Narration, _tag("narration")],
        Annotated[Transition, _tag("goto")],
    ],
    Discriminator(_event_tag),
]


class Scene(Strict):
    id: Id
    title: str = Field(min_length=1, max_length=120)
    background: BackgroundSpec
    intro: str = Field(min_length=1)
    events: list[Event] = Field(min_length=1)


class Ending(Strict):
    id: Id
    title: str = Field(min_length=1, max_length=120)
    text: str = Field(min_length=1)
    kind: Literal["good", "neutral", "bad"]


class Game(Strict):
    schema_version: Literal["1"] = "1"
    meta: Meta
    hero: Character
    characters: list[Character] = Field(default_factory=list)
    stats_template: Stats | None = None  # заполняет balance.py
    start_skills: list[Id] = Field(default_factory=list)
    start_items: list[Id] = Field(default_factory=list)
    skills: list[Skill] = Field(default_factory=list)
    items: list[Item] = Field(default_factory=list)
    enemies: list[Enemy] = Field(default_factory=list)
    flags: list[FlagDef] = Field(default_factory=list)
    scenes: list[Scene] = Field(min_length=1)
    start_scene: Id
    endings: list[Ending] = Field(min_length=1)

    def dump(self) -> dict[str, Any]:
        return self.model_dump(mode="json", by_alias=True, exclude_none=True)


for _model in (CondAll, CondAny, CondNot):
    _model.model_rebuild()


def game_json_schema() -> dict[str, Any]:
    return Game.model_json_schema(by_alias=True)

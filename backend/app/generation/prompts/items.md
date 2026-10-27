Ты — геймдизайнер RPG. Опиши предметы, навыки, магазины и тактики боя так, чтобы они подходили её жанру и тону: в фэнтези — посох и мантия, в детективе — револьвер и плащ, в космосе — бластер и скафандр.

Бриф:
{{brief}}

Упомянуты в локациях и должны быть описаны:
{{referenced}}

{{profile}}

Правила:
- Опиши каждый упомянутый предмет, навык и магазин. Можно добавить товары в магазины.
- kind: consumable (используется, есть effect: heal / damage / mod_stat), equipment (надевается, есть equip: slot hand / body / trinket и bonus), key (ключ, без effect), misc (сюжетный предмет, без effect).
- Слоты экипировки нейтральны к жанру: hand — то, что в руке (оружие, инструмент), body — одежда или броня, trinket — аксессуар.
- Бой тактический, на клетках. У предмета в руке есть equip.range — дальность атаки: 1 — вплотную (нож, меч, дубинка), 2 — копьё или кнут, 3–4 — лук, ружьё, револьвер, посох мага. Хотя бы одно оружие дальнего боя (range ≥ 3) — в магазине или в сундуке.
- value_tier 1–5 — насколько ценен предмет. Цену и пределы бонусов посчитает код.
- icon — только из каталога иконок.
- Навыки героя: target enemy (damage, mod_stat attack/defense) или self (heal, mod_stat attack/defense), cost_focus 2–4.
- start_skills — 1 навык героя с начала игры; start_equipment — что надето с начала (по желанию).
- tactics — 2–4 тактических приёма, которые игрок покупает прямо в бою. Они должны вытекать из сюжета и жанра: «Свисток Тимофея» после того, как друг присоединился, «Соляная граната» после разговора с алхимиком. currency: points (за кураж, который копится ударами) или gold (за золото, раз за бой). target: unit (тот, кто применяет), party (весь отряд) или enemies (все враги). effect: heal или mod_stat attack/defense для unit и party; damage или mod_stat attack/defense с минусом для enemies. duration 1–3 хода, move_bonus 0–3 клетки. unlock — условие из сюжета (флаг, предмет, побеждённый враг, уровень); без unlock тактика доступна сразу. tier 1–3 — сила; цену посчитает код. Базовые тактики («Сосредоточиться», «Рывок», «Сомкнуть ряды», «Второе дыхание») добавит код — не повторяй их.

Каталог деталей:
{{catalog}}

Схема ответа (JSON Schema):
{{schema}}

Пример фрагмента (сокращён):
{"items": [{"id": "tonic", "name": "Бабушкина настойка", "description": "Горькая, но ставит на ноги.", "icon": "potion", "kind": "consumable", "effect": [{"heal": 20}], "value_tier": 1}, {"id": "fishing_knife", "name": "Разделочный нож", "description": "…", "icon": "knife", "kind": "equipment", "equip": {"slot": "hand", "bonus": {"attack": 2}, "range": 1}, "value_tier": 1}], "skills": [{"id": "sharp_strike", "name": "Точный удар", "description": "…", "cost_focus": 3, "effect": [{"damage": 14}], "target": "enemy"}], "shops": [{"id": "marfa_stall", "name": "Прилавок Марфы", "items": ["tonic", "fishing_knife"], "buys": true}], "tactics": [{"id": "tim_whistle", "name": "Свисток Тимофея", "description": "Тим свистит — враги на миг теряют строй.", "icon": "feather", "currency": "points", "tier": 2, "target": "enemies", "effect": [{"mod_stat": "defense", "delta": -2}], "duration": 2, "unlock": {"flag": "tim_joined", "is": true}}], "start_skills": ["sharp_strike"], "start_items": [], "start_equipment": {}}

Ответ — только JSON по схеме, без пояснений и без markdown.

Ты — геймдизайнер RPG. Опиши предметы, навыки и магазины игры так, чтобы они подходили её жанру и тону: в фэнтези — посох и мантия, в детективе — револьвер и плащ, в космосе — бластер и скафандр.

Бриф:
{{brief}}

Упомянуты в локациях и должны быть описаны:
{{referenced}}

Правила:
- Опиши каждый упомянутый предмет, навык и магазин. Можно добавить товары в магазины.
- kind: consumable (используется, есть effect: heal / damage / mod_stat), equipment (надевается, есть equip: slot hand / body / trinket и bonus), key (ключ, без effect), misc (сюжетный предмет, без effect).
- Слоты экипировки нейтральны к жанру: hand — то, что в руке (оружие, инструмент), body — одежда или броня, trinket — аксессуар.
- value_tier 1–5 — насколько ценен предмет. Цену и пределы бонусов посчитает код.
- icon — только из каталога иконок.
- Навыки героя: target enemy (damage, mod_stat attack/defense) или self (heal, mod_stat attack/defense), cost_focus 2–4.
- start_skills — 1 навык героя с начала игры; start_equipment — что надето с начала (по желанию).

Каталог деталей:
{{catalog}}

Схема ответа (JSON Schema):
{{schema}}

Пример фрагмента (сокращён):
{"items": [{"id": "tonic", "name": "Бабушкина настойка", "description": "Горькая, но ставит на ноги.", "icon": "potion", "kind": "consumable", "effect": [{"heal": 20}], "value_tier": 1}, {"id": "fishing_knife", "name": "Разделочный нож", "description": "…", "icon": "knife", "kind": "equipment", "equip": {"slot": "hand", "bonus": {"attack": 2}}, "value_tier": 1}], "skills": [{"id": "sharp_strike", "name": "Точный удар", "description": "…", "cost_focus": 3, "effect": [{"damage": 14}], "target": "enemy"}], "shops": [{"id": "marfa_stall", "name": "Прилавок Марфы", "items": ["tonic", "fishing_knife"], "buys": true}], "start_skills": ["sharp_strike"], "start_items": [], "start_equipment": {}}

Ответ — только JSON по схеме, без пояснений и без markdown.

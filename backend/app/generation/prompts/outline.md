Ты — геймдизайнер и художник по персонажам. По брифу составь каркас RPG с видом сбоку: персонажи с внешностью, флаги, квесты, список локаций и концовки. Диалогов и объектов на карте здесь нет — их добавят позже по каждой локации.

Бриф:
{{brief}}

Правила:
- 5–8 локаций, 1–3 концовки, минимум 2 будущих боя, минимум 1 торговец, минимум 1 значимый выбор, который влияет на концовку через флаг.
- Ровно один основной квест (main: true) и 0–3 побочных. Этапы квеста — условия над флагами, предметами (has_item), золотом и побеждёнными врагами ({"defeated": "<id объекта-врага>"}). Id объектов-врагов придумай сейчас и используй их потом.
- Связи локаций (links) образуют связный граф: из start_location можно дойти до любой локации и хотя бы до одной концовки. В links можно указывать и id концовок.
- У локации 1–3 этажа (floors); зоны (zones) — именованные участки по порядку слева направо, у каждой этаж от 0 до floors−1.
- Внешность, тайлсеты (theme) и фоны (background) — только из каталога ниже. Внешность соответствует описанию: детектив — плащ, старик — седые волосы, маг — мантия. У героя, компаньона и антагониста не совпадают одновременно причёска, цвет волос и наряд.
- background.setting совпадает с назначением тайлсета (indoor/outdoor из каталога).
- Описания флагов пиши как условие, которое игрок увидит в подсказке: «Тимофей идёт вместе с героем», «Журнал найден».
- Id — латиница в snake_case. Тексты — по-русски.

Каталог деталей:
{{catalog}}

Схема ответа (JSON Schema):
{{schema}}

Пример фрагмента (сокращён):
{"meta": {"title": "Погасший маяк", "logline": "…", "tone": "мрачная сказка", "art_style": "пиксель-арт", "language": "ru", "est_minutes": 20}, "hero": {"id": "arina", "name": "Арина", "role": "hero", "description": "…", "appearance": {"head": "oval", "skin": "fair", "hair": "long_braid", "hair_color": "chestnut", "eyes": "sharp", "eye_color": "green", "brows": "straight", "mouth": "thin", "outfit": "detective_coat", "outfit_color": "slate", "accent_color": "brass", "bg_color": "navy"}}, "characters": [], "flags": [{"id": "tim_joined", "description": "Тимофей идёт вместе с Ариной"}], "quests": [{"id": "light_the_lamp", "title": "Зажечь маяк", "main": true, "stages": [{"text": "Пробиться к двери маяка", "done": {"defeated": "guardians"}}]}], "locations": [{"id": "pier", "title": "Пристань", "theme": "town_street", "background": {"setting": "outdoor", "time": "night", "sky": "moon", "far": "sea_cliffs", "ground": "planks", "overlay": "fog", "mood_palette": "cold_sea"}, "size": "medium", "floors": 1, "zones": [{"id": "ferry", "floor": 0, "name": "у парома"}], "summary": "Встреча с другом детства.", "links": ["alley"]}], "start_location": "pier", "endings": [{"id": "ending_dawn", "title": "Рассвет", "text": "…", "kind": "good"}]}

Ответ — только JSON по схеме, без пояснений и без markdown.

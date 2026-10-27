# Генератор RPG по брифу

Пользователь пишет идею — ИИ (GigaChat) превращает её в пиксельную RPG с видом сбоку, в которую можно сыграть в браузере и поделиться ссылкой. Требования — `SPEC.md`, решения и отклонения — `NOTES.md`, устройство кода — `CLAUDE.md`.

## Запуск

```bash
# бэкенд
cd backend
python -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/uvicorn app.main:app --reload          # http://127.0.0.1:8000

# фронтенд (в другом терминале)
cd frontend
npm install
npm run dev                                      # http://localhost:5173
```

- `http://localhost:5173/` — создать игру по идее;
- `http://localhost:5173/play/demo` — демо-игра «Погасший маяк» (работает и без бэкенда);
- `http://localhost:5173/lab` — PixelLab, просмотр графики (для разработки).

Без ключа GigaChat сайт работает в **демо-режиме**: любая идея превращается в демо-игру, но весь путь — бриф, генерация, игра, ссылка — настоящий. Чтобы подключить GigaChat, скопируйте `.env.example` в `.env`, впишите `GIGACHAT_AUTH_KEY`, положите корневой сертификат НУЦ Минцифры в `certs/russian_trusted_root_ca.cer` и проверьте доступ: `cd backend && .venv/bin/python -m app.gigachat.client --smoke`.

## Проверки

```bash
cd backend && .venv/bin/python -m pytest          # движок, графика, пайплайн, API
cd frontend && npm run typecheck && npm run e2e   # демо-игра проходится кликами до обеих концовок
cd frontend && npm run e2e:site                   # идея → бриф → генерация → игра → ссылка
```

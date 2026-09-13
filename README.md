# OVOZ GIFT — Working rebuild

Bu ZIP oldingi statik loyihani qayta tuzilgan, ishlaydigan FastAPI + SQLite + Telegram Mini App bazasi bilan almashtiradi.

## Ishga tushirish
1. `backend` ichida: `python -m venv .venv && pip install -r requirements.txt`
2. Environment: `BOT_TOKEN=...`, `BOT_USERNAME=Ovoz_giftbot`, `OWNER_IDS=8884758319,7891819965`
3. `cd backend && uvicorn main:app --host 0.0.0.0 --port 8000`
4. `frontend`ni HTTPS hostingga joylang va `window.OVOZ_API` orqali API manzilini ko‘rsating.

## Muhim
- Telegram initData HMAC tekshiruvi backendda bor.
- Ownerlar faqat `OWNER_IDS` orqali aniqlanadi.
- Admin qo‘shish faqat Owner uchun.
- Balance, referral, task, free spin, history, withdrawal, ranking va audit log API mavjud.
- Real Telegram Stars/Gift to‘lovlari uchun BotFather/payment konfiguratsiyasi va server webhooklari alohida ulanishi kerak.
- Pul/Stars tikib tasodifiy real qiymatdagi yutuq olish mexanizmi kiritilmagan; bepul promo spin mavjud.

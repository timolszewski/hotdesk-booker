# 🪑 Hotdesk Auto-Booker

Automatyczne rezerwowanie biurka w Speednet codziennie o 00:01.

## 👉 [KLIKNIJ TUTAJ ABY SKONFIGUROWAĆ](https://timolszewski.github.io/hotdesk-booker/)

Konfiguracja zajmuje około 5-10 minut.

---

## Co to robi?

- ✅ Rezerwuje Twoje ulubione biurko automatycznie każdego dnia roboczego
- ✅ Jeśli ulubione jest zajęte, wybiera następne z listy
- ✅ Pomija weekendy
- ✅ Działa w tle - nie musisz nic robić

## Wymagania

- Konto GitHub (darmowe)
- Konto w hotdesk.speednet.pl

---

## 🔄 Token wygasł?

Jeśli rezerwacje przestały działać:

1. Otwórz [hotdesk.speednet.pl](https://hotdesk.speednet.pl) i zaloguj się
2. Kliknij zakładkę "📋 Kopiuj Token" na pasku zakładek
3. Wejdź na GitHub → Twoje repo → **Settings** → **Secrets and variables** → **Actions**
4. Przy `HOTDESK_REFRESH_TOKEN` kliknij ✏️ → wklej nowy token → **Update secret**

[Szczegółowa instrukcja z obrazkami](https://timolszewski.github.io/hotdesk-booker/)

---

## ⏸️ Chcesz wyłączyć?

**Tymczasowo:**
1. GitHub → Twoje repo → **Actions** → **Daily Hotdesk Booking**
2. Kliknij **"..."** → **"Disable workflow"**

**Na stałe:** Usuń repozytorium (Settings → Danger Zone → Delete)

---

## ⚙️ Zmiana preferencji

Edytuj plik `.github/workflows/daily-booking.yml`:

```yaml
env:
  PREFERRED_DESKS: S05,S15,S10,S14  # Twoje ulubione biurka
  BOOKING_SUBJECT: "Twoje Imię"     # Opis rezerwacji
```

Dostępne biurka: S01, S02, S03... S18

---

## ❓ Pytania?

Napisz do @timolszewski lub sprawdź [instrukcję konfiguracji](https://timolszewski.github.io/hotdesk-booker/)

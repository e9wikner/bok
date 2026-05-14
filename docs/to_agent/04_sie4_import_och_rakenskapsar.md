# SIE4-import och räkenskapsår

Detta dokument beskriver hur systemet hanterar import av SIE4-filer och
räkenskapsår. Informationen är systemkritisk och används för att förstå hur
verifikationer placeras vid import.

## SIE4-formatet

SIE4 (Standardiserad Import/Export) är ett svenskt filformat för
redovisningsdata. Varje fil innehåller transaktioner för ett specifikt
räkenskapsår.

## Räkenskapsårsidentifiering (`#RAR`)

SIE4-filer använder taggen `#RAR` för att ange räkenskapsår:

```
#RAR <årindex> <startdatum> <slutdatum>
```

Exempel:
```
#RAR 0 20250101 20251231    ; Aktuellt räkenskapsår 2025
#RAR -1 20240101 20241231   ; Föregående räkenskapsår 2024
```

- `#RAR 0` anger filens aktuella räkenskapsår.
- Systemet tolkar datum för att placera verifikationer i rätt period.
- Verifikationer placeras i period baserat på verifikationsdatum inom rätt
  räkenskapsår.

## Ingående balans (`#IB`)

Taggen `#IB` anger ingående balans för konton:

```
#IB <årindex> <kontonummer> <belopp>
```

- `#IB 0` = Ingående balans för filens aktuella räkenskapsår.
- Systemet kan skapa en IB-verifikation baserat på dessa värden.
- Beloppen måste balansera (debet = kredit) för att vara giltiga.

Exempel från verklig data:
```
#IB 0 1920 166166177        ; Ingående balans konto 1920: 1 661 661,77 kr
```

## Utgående balans (`#UB`)

Taggen `#UB` anger utgående balans:

```
#UB <årindex> <kontonummer> <belopp>
```

- `#UB -1` = Ingående balans för aktuellt år (föregående års ingående).
- `#UB 0` = Utgående balans för filens räkenskapsår.

**Viktigt:** Föregående års utgående balans (`#UB 0` för år N) blir nästa års
ingående balans (`#IB 0` för år N+1).

Systemet importerar normalt inte `#UB`-värden som verifikationer, men de är
viktiga för att förstå sambandet mellan år.

## Multi-period import

Systemet stödjer import av flera SIE4-filer med olika räkenskapsår:

1. Varje fil behandlas separat baserat på sin `#RAR`-tagg.
2. Verifikationer placeras i rätt period baserat på verifikationsdatum.
3. Verifikationsnummer fortsätter i serie inom varje räkenskapsår.

### Exempel från produktionsdata

**SIE4 2025** (155 verifikationer: A1-A155):
```
#RAR 0 20250101 20251231
#UB -1 1920 166166177       ; IB 2025 = 1 661 661,77 kr
#UB 0 1920 119113902        ; UB 2025 = 1 191 139,02 kr
                              ; Skillnad = -470 522 kr (resultatet för 2025)
```

**SIE4 2026** (31 verifikationer: A156-A186):
```
#RAR 0 20260101 20261231
#IB 0 1920 119113902        ; IB 2026 = samma som UB 2025
```

Verifikationerna fortsätter i A-serien från föregående import.

## IB-verifikationer vid import

Vid import kan systemet skapa IB-verifikationer automatiskt:

- Format: `A<år>` där `<år>` är räkenskapsåret (t.ex. A190 för IB 2025).
- Belopp måste balansera exakt: D = K.
- Endast konton med saldo > 0 inkluderas.

## Viktiga principer

1. **Datum är avgörande:** Verifikationer placeras alltid i den period som
   motsvarar verifikationsdatumet.
2. **Räkenskapsår från `#RAR`:** Filens `#RAR 0` bestämmer vilket räkenskapsår
   verifikationerna tillhör.
3. **Seriefortsättning:** Verifikationsnummer fortsätter automatiskt när flera
   filer importeras för samma räkenskapsår.
4. **Inga dubbletter:** Systemet hanterar import så att samma verifikation inte
   skapas flera gånger.

## Filhantering

SIE4-filer kan innehålla:
- Verifikationer med fullständiga konteringsrader
- Ingående balanser (`#IB`)
- Utgående balanser (`#UB`)
- Kontoplan (`#KONTO`)
- Dimensionsinformation (`#DIM`, `#OBJ`)

Systemet importerar främst verifikationer och balanser. Kontoplan och
dimensioner används som referens vid import men påverkar inte systemets egen
kontoplan.

## Källa

- SIE4-standard: https://www.sie.se/
- BAS-kontoplanen: https://www.bas.se/

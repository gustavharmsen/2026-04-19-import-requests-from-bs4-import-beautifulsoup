# Professional Lead Engine

Et Python-script der finder potentielle kunder, scanner deres website og laver en prioriteret leadliste med kontaktdata, salgs-signaler, CRM-status og outreach-udkast.

## Hvad den kan

- finde virksomheder via Google-sogning
- hente website-signaler som kontakt-side, email, telefon, sociale links og teknologier
- analysere billeder pa siden for kvalitet
- score leads i `A`, `B` og `C`
- gemme leads i en lokal `SQLite` database
- foresla naeste handling pr. lead
- eksportere resultater til `CSV` og en `Markdown`-rapport
- generere et email-udkast til hver virksomhed

## Installation

```bash
pip install -r requirements.txt
```

## Brug

Standardkorsel:

```bash
python lead_engine.py
```

Eksempel med egne vaerdier:

```bash
python lead_engine.py \
  --city Esbjerg \
  --query restaurant \
  --max-businesses 20 \
  --max-images 5 \
  --service-offer "webdesign, billeder og lokal SEO" \
  --min-score 55 \
  --output-csv leads.csv \
  --output-md lead_report.md \
  --output-db lead_engine.db
```

Hvis sogemaskinerne ikke giver resultater, kan du scanne websites direkte:

```bash
python lead_engine.py \
  --websites "https://example.com,https://example.org" \
  --service-offer "webdesign, billeder og lokal SEO" \
  --min-score 55
```

Eller via fil med et website per linje:

```bash
python lead_engine.py --input-websites websites.txt
```

Du kan ogsa indlaese en CSV fra fx Google Maps-arbejde eller andre lister:

```bash
python lead_engine.py \
  --maps-csv maps_leads.csv \
  --service-offer "webdesign, billeder og lokal SEO" \
  --min-score 55
```

Eksempel pa CSV-kolonner:

```csv
name,website,rating,review_count,image_count,maps_url
Restaurant A,https://example-a.dk,4.5,187,1,https://maps.google.com/...
Restaurant B,https://example-b.dk,4.2,96,0,https://maps.google.com/...
```

Hvis en virksomhed har fa eller ingen billeder pa Maps, vil det nu trakke lead-scoren op, isaer hvis rating og anmeldelser ellers ser staerke ud.

## Output

Scriptet genererer som standard:

- `lead_results.csv`
- `lead_report.md`
- `lead_engine.db`

CSV-filen er god til sortering og import i et CRM.
Markdown-rapporten er god til manuel opfolgning, gennemgang og outreach.
SQLite-databasen er god, hvis du vil gemme, opdatere og genbruge leads lokalt over tid.

## Vigtige noter

- Google-scraping kan vaere ustabilt og blive blokeret.
- Ikke alle websites viser kontaktoplysninger tydeligt.
- Lead-scoren er heuristisk og bor bruges som prioritering, ikke som sandhed.

## Naeste forbedringer

- skifte fra Google-scraping til en mere stabil datakilde
- integrere med rigtigt CRM
- tilfoje niche-specifik scoring
- lave automatisk outreach-sekvenser

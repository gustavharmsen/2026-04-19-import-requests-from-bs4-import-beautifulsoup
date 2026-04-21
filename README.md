# Professional Lead Engine

Et lokalt leadværktøj der samler website-scanning, Maps-signaler, social presence, niche-scoring og outreach-udkast i samme flow.

## Hvad den kan

- finde virksomheder via Google/Bing nar det virker
- importere fleksibel CSV med websites, Maps-felter og sociale links
- hente website-signaler som kontakt-side, email, telefon, sociale links og teknologier
- analysere billeder pa websitet for kvalitet
- vaegte Maps-billeddaekning og anmeldelser
- score leads i `A`, `B` og `C`
- gemme leads i en lokal `SQLite` database
- foresla naeste handling pr. lead
- eksportere resultater til `CSV` og en `Markdown`-rapport
- generere et email-udkast til hver virksomhed
- koere via terminal eller en lille lokal web-app

## Installation

```bash
pip install -r requirements.txt
```

Hvis du vil bruge web-appen:

```bash
python3 app.py
```

Og aabn derefter:

```text
http://127.0.0.1:5050
```

## Brug

Standardkorsel:

```bash
python3 lead_engine.py
```

Eksempel med egne vaerdier:

```bash
python3 lead_engine.py \
  --city Esbjerg \
  --query restaurant \
  --niche restaurant \
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
python3 lead_engine.py \
  --websites "https://example.com,https://example.org" \
  --service-offer "webdesign, billeder og lokal SEO" \
  --min-score 55
```

Eller via fil med et website per linje:

```bash
python3 lead_engine.py --input-websites websites.txt
```

Du kan ogsa indlaese en CSV fra fx Google Maps-arbejde eller andre lister:

```bash
python3 lead_engine.py \
  --source-csv sample_leads.csv \
  --niche restaurant \
  --service-offer "webdesign, billeder og lokal SEO" \
  --min-score 55
```

Eksempel pa CSV-kolonner:

```csv
name,website,city,query,rating,review_count,image_count,maps_url,instagram,facebook
Restaurant A,https://example-a.dk,Esbjerg,restaurant,4.5,187,1,https://maps.google.com/...,https://instagram.com/examplea,https://facebook.com/examplea
Restaurant B,https://example-b.dk,Esbjerg,restaurant,4.2,96,0,https://maps.google.com/...,,
```

Kolonnenavne er fleksible. Værktøjet forstår fx ogsa `business_name`, `domain`, `reviews`, `photos`, `instagram_url` og lignende.

## Output

Scriptet genererer som standard:

- `lead_results.csv`
- `lead_report.md`
- `lead_engine.db`

CSV-filen er god til sortering og import i et CRM.
Markdown-rapporten er god til manuel opfolgning, gennemgang og outreach.
SQLite-databasen er god, hvis du vil gemme, opdatere og genbruge leads lokalt over tid.
Web-appen gemmer resultater i mappen `runtime/`.

## Vigtige noter

- Google-scraping kan vaere ustabilt og blive blokeret.
- Ikke alle websites viser kontaktoplysninger tydeligt.
- Lead-scoren er heuristisk og bor bruges som prioritering, ikke som sandhed.
- Den mest stabile arbejdsgang er ofte at bruge en CSV fra din egen research eller et Maps-udtraek.

## Naeste forbedringer

- integrere med rigtigt CRM
- tilfoje flere nicheprofiler
- lave automatisk outreach-sekvenser

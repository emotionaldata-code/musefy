# Musefy

Catalogo asincrono: Python 3.13+, TMDB (film/TV), schema Jikan v4 (anime e manga),
PostgreSQL, CLI, API FastAPI di sola lettura e frontend React/TypeScript Vite + shadcn.
Nessuna autenticazione.
Scaffold creato con `uv init` (workspace) e `alembic init -t async`.

## Struttura

- `packages/core`: schemi Pydantic condivisi, configurazione, database e repository concreti.
- `packages/scraper`: HTTP/rate limit, adattatori delle fonti, discovery e ingestion.
- `packages/backend`: composizione FastAPI, dipendenze e routing.
- `packages/cli`: argparse e composizione dei comandi.
- `packages/frontend`: client API tipizzato da OpenAPI, componenti shadcn, catalogo e dettaglio.
- `migrations`: migrazione iniziale e ampliamento dei namespace manga; nessun `create_all`.

HTTP usa `httpx.AsyncClient`; API, ingestion e repository usano async/await e
SQLAlchemy 2 con asyncpg. Nessuna coda esterna o richiesta alle fonti nelle route.

## Configurazione e Docker

```bash
cp .env.example .env
# Modificare .env: password PostgreSQL e TMDB_READ_ACCESS_TOKEN.
docker compose up --build -d
curl http://127.0.0.1:8000/health
```

Usare una password locale URL-safe, oppure codificarla correttamente nella URL
PostgreSQL. Il token TMDB è un **Read Access Token Bearer**, senza API key aggiuntiva.
Jikan non richiede credenziali. Le credenziali sono lette a runtime; `.env` è escluso
da Git e dal contesto Docker. API e migrazioni non ricevono il token TMDB.

Compose avvia PostgreSQL con volume/healthcheck, poi `alembic upgrade head`, poi
l'API e il frontend. **`docker compose up` non avvia ingestion.** Il servizio `cli` è nel profilo
`manual`; API/CLI/scraper condividono la stessa immagine Python non-root.
Il frontend ha una build Node e un runtime nginx separati, con proxy `/api` verso FastAPI.
Tutte le porte sono locali: frontend http://127.0.0.1:5173, API :8000, PostgreSQL :5432.
I dati restano nel volume PostgreSQL anche dopo `docker compose down` (senza `-v`).

## Produzione EDIA

- Frontend: https://musefy.edia-company.com
- FastAPI: https://api-musefy.edia-company.com/docs
- Repository: https://github.com/emotionaldata-code/musefy (`main`).
- Dokploy: progetto **Musefy**, ambiente **production**, Compose `musefy-production-6pe27w`.

Dokploy usa `compose.production.yaml`, separato dal Compose locale. Nessuna porta
dei container viene pubblicata sul server. PostgreSQL appartiene soltanto alla
rete Docker privata `database` (`internal: true`), accessibile ad API, migrazioni
e scraper; frontend e rete condivisa del reverse proxy non vi appartengono.
Il volume PostgreSQL persiste tra i deploy. Il tunnel Cloudflare e il routing
Dokploy espongono esclusivamente i due domini HTTP/HTTPS, secondo `/home/freed/info.md`.
Il frontend chiama direttamente il dominio API; CORS autorizza soltanto il frontend.

Ogni push su `main` avvia la CI GitHub Actions (PostgreSQL di test, Alembic,
pytest con HTTP simulato, mypy strict, Ruff, build TypeScript/Vite, Playwright e
build delle immagini). L'app GitHub già collegata a Dokploy avvia automaticamente
il deploy dello stesso ramo. **CI e deploy sono paralleli**: il deploy nativo non
attende l'esito dei test. Non sono necessari token GitHub o chiavi SSH nei workflow.
Il checkout locale usa la chiave SSH `id_ed25519_emotionaldata` tramite configurazione
Git del solo repository; le chiavi non sono committate.

Il comando di deploy Dokploy include `--force-recreate`, per rieseguire sempre il
servizio `migrate`: **`alembic upgrade head` deve terminare con successo prima di
API e scraper**. Una migrazione fallita impedisce il loro nuovo avvio. Si applicano
le revisioni Alembic committate, senza autogenerarle in produzione. Questo deploy
ricrea i container e può causare una breve indisponibilità; non è un deploy senza
interruzioni. Non usare `down -v`, `freshVolumes` o volumi casuali nei redeploy.

Due servizi permanenti eseguono `musefy worker --source tmdb` e `--source jikan`.
Ogni fonte ha il proprio processo, limiter e lock PostgreSQL. Una passata percorre
progressivamente il catalogo senza limite di schede; completata o interrotta,
attende 3600 secondi prima di ripartire. Il client e il limiter vengono riutilizzati;
checkpoint, step parziali, upsert e skip sono quelli della CLI. Un SIGTERM cancella
il lavoro async e chiude client/connessioni, permettendo la ripresa dal DB. Nessun
refresh automatico delle schede complete. Film/TV e anime/manga sono percorsi
sequenzialmente **all'interno** della fonte; le due fonti avanzano indipendentemente.
Il caricamento iniziale completo richiede tempo e dipende dalla disponibilità remota.

Segreti di produzione configurati a runtime in Dokploy, conservati localmente solo
nel workspace `self-hosting/.secrets/` ignorato da Git. Il token TMDB è passato
esclusivamente al suo scraper. I log Docker ruotano a 3 file da 10 MB per servizio.

Diagnostica sulla VM (directory di checkout Dokploy):

```bash
cd /etc/dokploy/compose/musefy-production-6pe27w/code
docker compose -p musefy-production-6pe27w -f compose.production.yaml ps
docker compose -p musefy-production-6pe27w -f compose.production.yaml logs --tail 50 scraper-tmdb scraper-jikan
docker compose -p musefy-production-6pe27w -f compose.production.yaml exec postgres psql -U musefy -d musefy -c 'SELECT source_type, count(*) FROM titles GROUP BY source_type;'
```

Per fermare o riavviare una fonte, usare `stop scraper-tmdb` / `start scraper-tmdb`
(oppure `scraper-jikan`) con lo stesso prefisso Compose. Queste operazioni non
eliminano checkpoint o schede. Non avviare una seconda copia della stessa fonte
su un altro database: i lock sono coordinati soltanto dal DB condiviso.

## Disponibilità della fonte anime/manga

Il maintainer ha [dismesso l'istanza pubblica Jikan il 1° ottobre 2026](https://github.com/jikan-me/jikan-rest/issues/613).
Il connettore conserva lo schema Jikan v4 e accetta `JIKAN_BASE_URL`:

- una propria istanza Jikan (`https://…/v4`);
- [Tenrai](https://api.tenrai.org/documentation), alternativa indicata dal maintainer,
  compatibile con gli endpoint usati (`https://api.tenrai.org/v1`).

`.env.example` propone Tenrai; senza override il codice conserva l'URL originale Jikan.
La configurazione locale usa Tenrai per i 20 titoli MAL importati. `source=jikan`
identifica il connettore/namespace; `metadata.api_base_url` registra il provider
HTTP effettivo, visibile nella provenienza della scheda. I voti restano MyAnimeList.
Nessun fallback nascosto tra provider. Restano i limiti prudenti 1,1 s e 60/min.
Tenrai è in beta: disponibilità e dati possono variare. Non fornisce diritti di
redistribuzione sui dati MAL.

## Frontend

Aprire **http://127.0.0.1:5173** dopo `docker compose up --build -d`.
Ricerca sul titolo, categorie, fonte, anno e genere interrogano FastAPI;
scroll continuo con caricamento progressivo di 15 schede per richiesta.
Le card mostrano copertina, titolo, anno e formato. Il dettaglio mostra sinossi e
generi; cast, autori, rating distinti per fonte e provenienza sono espandibili.
Filtri e dettaglio sono condivisibili tramite URL. Cambiare filtro riparte dall'inizio;
chiudere una scheda conserva i titoli caricati e la posizione. Un errore nelle
richieste successive lascia visibili le card e permette di ritentare.
I poster sono caricati dai CDN delle fonti: senza rete compare un'alternativa testuale.
Il frontend non riceve il token TMDB. Nessuna traduzione automatica.
Tema chiaro/scuro dal pulsante accanto al titolo: segue inizialmente il sistema,
poi conserva la scelta in localStorage, applicandola prima del rendering.
Font di sistema, feedback immediato sui controlli e rispetto di reduced motion.
Stile True-black flat (seed 1722118383), con equivalente chiaro e locandine reali:
il catalogo mette in primo piano le copertine, con attribuzione raccolta in basso.
Verificato a 1440, 768 e 390 px; nessun dato dimostrativo nel catalogo locale.

Scaffold eseguito da CLI con `npm create vite@latest packages/frontend -- --template react-ts --no-interactive`,
poi `npx shadcn@latest init --base radix --preset nova --yes --no-monorepo`
e `npx shadcn@latest add button input badge dialog skeleton --yes`.
Filtri e scorrimento aggiunti con `npx shadcn@latest add select scroll-area --yes`: componenti
Radix/shadcn in `components/ui`, toolbar e crediti separati, stile Tailwind.
Menu utilizzabili da tastiera, scrollbar sottili, chiusura sempre accessibile e reduced motion.

Sviluppo con Node 24 (API Compose già attiva):

```bash
docker compose stop frontend
cd packages/frontend
npm ci
npm run dev
npm run build
npm run lint
npm run api:types # rigenera i tipi dall'OpenAPI locale
npm test # API simulate; richiede Google Chrome installato
npm test -- --headed # include verifica layout con scrollbar classiche; richiede un display
```

In CI Chrome usa un display virtuale Xvfb: controlla anche che aprire e chiudere i
filtri non cambi la larghezza del catalogo, su desktop e mobile.

Per tornare alla build Docker, terminare Vite e lanciare `docker compose up -d frontend`
dalla root. Per ricostruire dopo modifiche: `docker compose up --build -d frontend`.

## Popolare 10 schede per categoria

Importazione per ID, idempotente e senza modificare i checkpoint di discovery.
Schede già complete vengono saltate prima di qualunque richiesta di dettaglio;
`--force` le aggiorna. Errori e passaggi incompleti sono riprendibili.
Questi comandi fanno richieste reali; nessun import parte automaticamente.

```bash
docker compose run --rm cli import-titles --source tmdb --type movie --ids 550 603 27205 157336 680 13 155 238 120 129
docker compose run --rm cli import-titles --source tmdb --type tv --ids 1396 1399 66732 1398 100088 60625 1402 82856 42009 60059
docker compose run --rm cli import-titles --source jikan --type anime --ids 1 20 21 1535 16498 5114 9253 11061 38000 40748
docker compose run --rm cli import-titles --source jikan --type manga --ids 2 13 11 21 1 1706 44347 96792 116778 121496
```

## CLI

I comandi di acquisizione contattano le fonti reali solo quando avviati manualmente:

```bash
docker compose run --rm cli preview --source tmdb --type movie --id 550
docker compose run --rm cli preview --source jikan --type anime --id 1
docker compose run --rm cli scrape --source all --max-items 20
docker compose run --rm cli scrape --source tmdb --refresh-after 30
docker compose run --rm cli scrape --source jikan --force
```

Consultazione locale del catalogo:

```bash
docker compose run --rm cli list --source tmdb --type movie --year 2020 --genre Drama --q storia --limit 20 --offset 0
docker compose run --rm cli get 1
```

`--max-items` limita i tentativi di scheda **per fonte**, inclusi i fallimenti;
la discovery può registrare anticipatamente un batch limitato di ID. Senza limite
si percorrono i pendenti e una passata del catalogo disponibile. Con `all` le fonti
hanno worker, code e limiter indipendenti; un errore di una fonte non ferma l'altra.
JSON va su stdout, log e avanzamento su stderr. Exit code 1 indica un fallimento
(o `get` inesistente), 2 argomenti/configurazione invalidi.

`preview` non scrive schede/checkpoint; richiede comunque PostgreSQL per il lock
condiviso con ingestion. Nessuna modalità aggira i limiti della fonte.

## API

```bash
curl 'http://127.0.0.1:8000/titles?source=tmdb&source_type=movie&year=2020&genre=Drama&q=storia&limit=20&offset=0'
curl http://127.0.0.1:8000/titles/1
```

`GET /health` verifica PostgreSQL (503 se indisponibile). `GET /titles` restituisce
`items`, `total`, `offset`, `limit`; ordine crescente per ID interno, limite 1–100.
`source_type` è `movie`, `tv`, `anime` o `manga`; il formato anime (Movie, TV, OVA, …) resta
nei metadati. Il genere è esatto, la ricerca sul titolo è case-insensitive e tratta
`%`/`_` letteralmente. `GET /titles/{id}` restituisce 404 se assente.
`GET /titles/facets` restituisce conteggi globali per tipo, anni e generi dal DB.
Schemi e documentazione interattiva: `/docs`. Nessun endpoint di ingestion.

## Ripresa, aggiornamenti e limiti

Tre tabelle: `titles` con identità/filtri e metadati JSONB validati da Pydantic;
`ingestion_items` con ID scoperti e passaggi parziali; `checkpoints` con cursori/versioni.
ID e checkpoint sono salvati nella stessa transazione prima dei dettagli;
upsert della scheda e completamento sono anch'essi atomici. Il vincolo univoco è
`(source, source_type, source_id)`: movie e TV TMDB rimangono distinti.

- Le schede complete sono saltate interrogando il DB **prima** dei dettagli.
  `--refresh-after DAYS` e `--force` richiedono un nuovo recupero. I fallimenti,
  anche durante refresh, sono ritentabili alla successiva esecuzione; la scheda
  precedente resta consultabile. I passaggi già riusciti vengono riutilizzati.
- TMDB: export ufficiali gzip/JSONL letti in streaming, batch da 100, versione e
  numero di riga persistiti; prima si chiude lo stream, poi si recuperano i dettagli
  dagli ID nel DB (anche con concorrenza 1). Con `--max-items` la discovery si
  ferma quando ha scoperto abbastanza pendenti. Details con append di credits, keyword, titoli
  alternativi e ID esterni. Sinossi italiana, fallback inglese solo se manca.
  Si usa l'ultimo giorno pubblicato (entro le 08:00 UTC). Per riprendere un gzip
  si rileggono le righe precedenti senza richiederne i dettagli. Export più vecchi
  di 85 giorni vengono sostituiti con uno recente (la fonte li conserva 3 mesi).
  Sono inclusi gli export standard movie/TV, esclusi gli export adult separati.
- Jikan: pagine da 25 ordinate per `mal_id`, lista salvata come seed; `full` serve
  per relazioni/ID esterni, poi `characters` e `staff`, senza richiedere anche la
  scheda base. Una passata conclusa riparte da pagina 1 alla prossima esecuzione,
  per trovare nuovi ID anche inferiori. Il catalogo remoto non è uno snapshot:
  inserimenti/rimozioni durante una passata sono recuperabili nelle successive.
  I manga usano `/manga`, `full` e `characters`; autori e date di pubblicazione
  provengono da `full`. Nessuna chiamata al percorso staff, che non esiste per i manga.
- Concorrenza limitata, code di dimensione `2 × CONCURRENCY`, nessun task per
  l'intero catalogo. TMDB: 10 richieste/s configurabili. Jikan: almeno 1,1 s tra
  richieste, senza burst, più finestra mobile di 60/min (quindi anche sotto 3/s).
  Timeout espliciti, massimo `HTTP_RETRIES` retry dopo il primo tentativo, backoff
  esponenziale con jitter, `Retry-After` numerico/data HTTP. Un 429 sospende la
  fonte. I 4xx permanenti non sono ritentati nella stessa esecuzione; l'elemento
  resta fallito e verrà riprovato in una successiva. Un export interrotto durante
  lo streaming riprende dal checkpoint alla successiva esecuzione.
- Lock advisory PostgreSQL per fonte, anche per preview, con connessione dedicata.
  Coordinano i processi che usano **lo stesso database**; i limiti Jikan possono
  applicarsi anche ad altri utilizzatori dello stesso IP.
- Nessuna fusione automatica tra fonti, nemmeno per titoli identici: si conservano
  schede, rating e identificatori esterni separati. Non è implementato un resolver
  di identità incrociate; nessun dato di un'altra fonte sovrascrive la scheda.
  I campi non disponibili restano null/vuoti; la lingua della sinossi Jikan non è
  dichiarata dalla fonte e rimane null. Nessuna traduzione automatica.

## Sviluppo e verifiche

```bash
uv sync --all-packages --frozen
# Con il PostgreSQL Compose già pronto, .env contiene la URL locale corretta:
uv run alembic upgrade head
uv run uvicorn musefy_backend.app:app --reload
uv run musefy list --limit 10
uv run mypy
uv run ruff check packages tests migrations
uv run ruff format --check packages tests migrations
```

Database di test **dedicato e distruttibile**, separato dal catalogo:

```bash
docker run --rm -d --name musefy-test-postgres \
  -e POSTGRES_USER=musefy -e POSTGRES_PASSWORD=test-only -e POSTGRES_DB=musefy_test \
  -p 127.0.0.1:55432:5432 postgres:17-alpine
# Attendere che: docker exec musefy-test-postgres pg_isready -U musefy -d musefy_test
TEST_DATABASE_URL=postgresql+asyncpg://musefy:test-only@127.0.0.1:55432/musefy_test uv run pytest -q
docker stop musefy-test-postgres
```

La suite ricrea lo schema del database di test, applica Alembic su schema vuoto e
controlla l'assenza di drift. La URL deve terminare in `_test`; senza
`TEST_DATABASE_URL` i test PostgreSQL sono esplicitamente saltati.
HTTP esterno è bloccato dai test; tutte le fonti usano MockTransport e i limiter
un clock simulato. Coperti upsert/rollback/namespace, lock, ripresa/cancellazione,
step falliti, skip, refresh, nuovi ID inferiori, export streaming, timeout/429,
limiti e indipendenza delle fonti, API/filtri/paginazione/404.
I test non contattano le fonti. Su richiesta esplicita sono state importate in locale
40 schede reali (10 per tipo), senza avviare la discovery completa.

## Fonti e attribuzione

Documentazione verificata durante l'implementazione:
[TMDB](https://developer.themoviedb.org/docs/),
[daily ID exports](https://developer.themoviedb.org/docs/daily-id-exports),
[rate limiting](https://developer.themoviedb.org/docs/rate-limiting),
[append](https://developer.themoviedb.org/docs/append-to-response),
[Jikan v4](https://docs.api.jikan.moe/) e relativo
[OpenAPI ufficiale](https://github.com/jikan-me/jikan-rest/blob/master/storage/api-docs/api-docs.json).
La soglia TMDB pubblicata è circa 40 richieste/s e può cambiare; il default locale
è volutamente inferiore.

This product uses the TMDB API but is not endorsed or certified by TMDB.

TMDB è gratuito per uso non commerciale con attribuzione; l'uso commerciale deve
essere concordato con TMDB. Per distribuire un'applicazione includere l'avviso e
il [logo ufficiale approvato](https://www.themoviedb.org/about/logos-attribution)
nei crediti, rispettando le [condizioni e l'attribuzione](https://developer.themoviedb.org/docs/faq).
L'accesso gratuito a Jikan e la licenza del suo software non concedono
automaticamente diritti sui dati MyAnimeList. Verificare le condizioni dei titolari:
questo progetto **non dichiara il dataset liberamente redistribuibile**.

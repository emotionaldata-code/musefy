# Musefy

Catalogo asincrono: Python 3.13+, TMDB (film/TV), schema Jikan v4 (anime e manga),
PostgreSQL, CLI, API FastAPI di sola lettura e frontend React/TypeScript Vite + shadcn.
Accesso con Google SSO, account provisionati al primo login e sessioni JWT in cookie HttpOnly.
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
# Configurare anche Google OAuth e AUTH_JWT_SECRET come descritto sotto.
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

Due servizi nel profilo manuale `ingestion` possono eseguire `musefy worker --source tmdb` e `--source jikan`.
Compose senza servizi espliciti avvia solo PostgreSQL, migrazioni, API e frontend.
In produzione il comando Dokploy include anche `scraper-tmdb scraper-jikan`:
entrambi sono attivi e vengono aggiornati insieme all'applicazione nei deploy successivi.
I due processi ospitano **quattro runner async in memoria**, uno per film, serie TV,
anime e manga. Ogni runner ha client HTTP, slot di concorrenza, coda limitata,
checkpoint e ciclo di ripartenza propri: nessuno attende il completamento degli altri.
I due runner dello stesso provider condividono soltanto il limiter e il lock PostgreSQL.
Una passata percorre progressivamente il catalogo del proprio tipo senza limite di
schede; completata o interrotta, quel runner attende 3600 secondi prima di ripartire,
mentre gli altri continuano. Client e limiter vengono riutilizzati;
checkpoint, step parziali, upsert e skip sono quelli della CLI. Un SIGTERM cancella
il lavoro async e chiude client/connessioni, permettendo la ripresa dal DB. Nessun
refresh automatico delle schede complete. Il lock resta acquisito durante i cicli
indipendenti; una verifica della sua connessione ogni 30 secondi rileva le interruzioni
del DB, cancella i due runner del provider e permette di riacquisire il lock alla
ripartenza. Gli errori di una singola passata restano isolati al proprio runner.
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

## Accesso Google

Il browser avvia `GET /auth/google`; FastAPI gestisce redirect e callback Google,
scambia il codice con PKCE e verifica firma RS256, issuer, audience, scadenza, nonce
ed email verificata. Sono richiesti solo `openid email profile`. Il primo accesso
crea un account con Google `sub`, email, nome, avatar e timestamp. L'identità è il
`sub`, non l'email: un cambio email aggiorna lo stesso account senza unirlo ad altri.
Non vengono conservati access token o refresh token Google.
L'immagine API disattiva gli access log Uvicorn per evitare di registrare il codice
OAuth temporaneo nella query della callback; gli errori applicativi restano nei log.

Creare un client OAuth **Applicazione web** in Google Cloud. Per una beta scegliere
pubblico **Esterno**, con i soli scope di identità. Configurare gli URI esatti:

- locale: `http://127.0.0.1:8000/auth/callback`;
- produzione: `https://api-musefy.edia-company.com/auth/callback`.

Usare preferibilmente progetti/client distinti per sviluppo e produzione. Impostare
`GOOGLE_CLIENT_ID` e `GOOGLE_CLIENT_SECRET` solo nel `.env` backend/Compose; non
aggiungere variabili `VITE_` con segreti. Il frontend non richiede credenziali OAuth.
Generare `AUTH_JWT_SECRET` diverso per ciascun ambiente con
`python3 -c 'import secrets; print(secrets.token_urlsafe(48))'` e proteggerlo come
le credenziali del database. `.env.example` contiene tutti i nomi delle variabili.

Locale: `AUTH_FRONTEND_URL=http://127.0.0.1:5173`,
`GOOGLE_REDIRECT_URI=http://127.0.0.1:8000/auth/callback`,
`AUTH_COOKIE_SECURE=false`. Aprire il frontend con **127.0.0.1**, coerentemente
con il callback: non alternare `localhost` e `127.0.0.1` nella stessa sessione.
Produzione: `AUTH_FRONTEND_URL=https://musefy.edia-company.com`,
`GOOGLE_REDIRECT_URI=https://api-musefy.edia-company.com/auth/callback`;
Compose impone `AUTH_COOKIE_SECURE=true`. Salvare i segreti anche nell'ambiente
Dokploy, sorgente del `.env` generato sulla VM a ogni deploy.

La sessione dura `AUTH_SESSION_TTL_SECONDS` (default 7 giorni). Il JWT rimane in un
cookie host-only HttpOnly, SameSite=Lax, Secure e con prefisso `__Host-` in produzione.
Non compare in URL, risposte JSON o localStorage. Ogni richiesta verifica sia il JWT
sia l'esistenza di sessione e account nel database. `POST /auth/logout` richiede
l'Origin del frontend e revoca la sessione nel DB. Cambiare la chiave JWT invalida
le sessioni esistenti. Le risposte API non vengono memorizzate in cache.

`GET /auth/me` restituisce `id`, `email`, `name`, `picture`. Catalogo, ricerca, docs
e OpenAPI richiedono un account autenticato. Restano pubblici solo avvio/callback
del login e `GET /health`, necessario al monitoraggio. Il frontend controlla la
sessione prima di caricare chat o catalogo, mostra avatar/email e permette di uscire.
Credenziali OAuth assenti: il login restituisce 503; non esiste un accesso anonimo
di ripiego. Applicare `alembic upgrade head` prima di avviare la nuova API.

Riferimenti: [Google OpenID Connect](https://developers.google.com/identity/openid-connect/openid-connect),
[OAuth per applicazioni web](https://developers.google.com/identity/protocols/oauth2/web-server).

## Frontend

La prima schermata è **Musefy**, una chat dimostrativa che ripete ogni messaggio.
I messaggi rimangono nel browser mentre si cambia sezione e si cancellano al reload;
non sono inviati al backend né salvati nel database. Invio per spedire, Shift+Invio
per andare a capo. Su desktop la sidebar è aperta all’avvio e richiudibile.
Su telefono e tablet (fino a 1000 px) il pulsante accanto al titolo apre un menu
laterale shadcn, chiuso all’avvio: si richiude scegliendo una sezione, toccando fuori
o premendo Escape. La chat rispetta le safe area e lo spazio visibile della tastiera.
Il catalogo è accessibile dalle altre voci e direttamente con `/?view=catalog`; i link filtrati esistenti restano validi.
Chat e toggle usano `textarea` e `collapsible`, aggiunti con
`npx shadcn@latest add collapsible textarea --yes`; menu mobile aggiunto con
`npx shadcn@latest add sheet --yes`.

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
npm run api:types # genera OpenAPI dal codice Python, senza sessione HTTP né DB
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
docker compose run --rm cli worker --source all --interval 3600
```

Consultazione locale del catalogo:

```bash
docker compose run --rm cli list --source tmdb --type movie --year 2020 --genre Drama --q storia --limit 20 --offset 0
docker compose run --rm cli get 1
```

`--max-items` limita i tentativi di scheda **per tipo**, inclusi i fallimenti
(con `all --max-items 20`, fino a 20 film, 20 serie TV, 20 anime e 20 manga);
la discovery può registrare anticipatamente un batch limitato di ID. Senza limite
si percorrono i pendenti e una passata del catalogo disponibile per ciascun tipo.
`scrape` esegue una passata per tipo in parallelo; `worker` ripete ciascuna passata
indipendentemente. Con `--source all` entrambi avviano i quattro runner.
L'entrypoint è `packages/cli/src/musefy_cli/main.py:execute`; in
`packages/scraper/src/musefy_scraper/runner.py`, `run_source` orchestra le passate,
`work` i cicli continui e `ingest` discovery e dettagli di un solo tipo. Le query dei
pendenti in `packages/core/src/musefy_core/db/ingestion.py` filtrano provider e tipo.
Il JSON di `scrape` espone contatori o classe di errore per provider e tipo, per
esempio `{"tmdb":{"movie":{"attempted":1,"completed":1,"failed":0},"tv":…},"jikan":…}`.
JSON va su stdout, log e avanzamento su stderr. Exit code 1 indica un fallimento
(o `get` inesistente), 2 argomenti/configurazione invalidi.

`preview` non scrive schede/checkpoint; richiede comunque PostgreSQL per il lock
condiviso con ingestion. Nessuna modalità aggira i limiti della fonte.

## API

Esempi per una sessione autenticata (cookie in `cookies.txt`, da proteggere e non committare):

```bash
curl -b cookies.txt 'http://127.0.0.1:8000/titles?source=tmdb&source_type=movie&year=2020&genre=Drama&q=storia&limit=20&offset=0'
curl -b cookies.txt http://127.0.0.1:8000/titles/1
```

`GET /health` verifica PostgreSQL (503 se indisponibile). `GET /titles` restituisce
`items`, `total`, `offset`, `limit`; ordine crescente per ID interno, limite 1–100.
`source_type` è `movie`, `tv`, `anime` o `manga`; il formato anime (Movie, TV, OVA, …) resta
nei metadati. Il genere è esatto, la ricerca sul titolo è case-insensitive e tratta
`%`/`_` letteralmente. `GET /titles/{id}` restituisce 404 se assente.
`GET /titles/facets` restituisce conteggi globali per tipo, anni e generi dal DB.
Schemi e documentazione interattiva: `/docs`. Nessun endpoint di ingestion.

## Embeddings e ricerca semantica

Baseline: **una sinossi → un vettore**, richiesta → vettore → cosine similarity in
PostgreSQL/pgvector. Modello MIT `intfloat/multilingual-e5-small`, revisione fissa
`614241f622f53c4eeff9890bdc4f31cfecc418b3`, 384 dimensioni; prefissi `passage: ` e
`query: `, mean pooling con attention mask, normalizzazione L2. Tokenizzazione
con `truncation=True` a 512 token, inclusi prefisso e token speciali: la coda della
sinossi può essere persa. Nessun enrichment, reranking o traduzione automatica.

La migrazione `0ff20b5a3271` abilita `vector` e crea `title_embeddings`, separata dalle
schede. Memorizza ID del titolo, vettore, fingerprint della configurazione, hash SHA256 della
sinossi esatta e timestamp. Sinossi vuote escluse. Batch limitati, keyset pagination,
commit per batch e upsert idempotente: rilanciare salta ciò che è già corrente.
Sinossi modificate durante il calcolo non vengono salvate; quelle modificate dopo
sono escluse dalla ricerca fino al prossimo batch. `--force` ricalcola esplicitamente.
I nuovi titoli acquisiti vengono indicizzati al batch successivo, anche con `--watch`.

`--batch-size` limita il batch DB (default 32, massimo 1024); l’inferenza resta
suddivisa in blocchi massimi di 128. Da 128 elementi l’upload usa `COPY BINARY`
su una tabella temporanea e upsert nella stessa transazione, riducendo il traffico
dei vettori sul tunnel. Il recheck delle sinossi trasferisce solo gli hash.
Per un catalogo ampio: `uv run musefy embed --batch-size 1024 --threads 8`.
Con una wheel CUDA locale usare `uv run --no-sync musefy embed --device cuda
--batch-size 1024 --threads 4`: `--no-sync` evita di ripristinare la wheel CPU del lockfile.

```bash
uv sync --all-packages --frozen
uv run musefy embedding-model # scarica e verifica una volta il modello fissato
uv run musefy embed --batch-size 32 --threads 2
uv run musefy embed --max-items 100 --batch-size 16
uv run musefy embed --force --batch-size 32
uv run musefy embed --watch --interval 60 --batch-size 1024 --threads 4
curl -b cookies.txt --get 'http://127.0.0.1:8000/search' \
  --data-urlencode 'q=indagine psicologica con misteri e colpi di scena' \
  --data-urlencode 'source_type=anime' --data-urlencode 'limit=10'
```

`GET /search` accetta `q` (1–200 caratteri non vuoti), `source`, `source_type`, `year`,
`genre`, `offset` e `limit` (1–100). Risposta `items: [{title, score}], offset, limit`;
score è cosine similarity, non una probabilità. Ordine per distanza e ID in caso di
parità. Per ora ricerca esatta, senza indice ANN: misurare la latenza al crescere del
catalogo prima di aggiungere HNSW. I filtri sono espliciti, non estratti dal testo.

API: un solo modello lazy condiviso, due thread CPU e inferenza serializzata fuori
dall’event loop. Non scarica nulla nelle route: usa soltanto la cache locale;
cache assente o modello indisponibile → 503. La build Docker preinstalla e verifica
il modello in `/opt/models`; a runtime non servono API key né servizi di embedding.
L’immagine contiene PyTorch **CPU**; il batch può usare `--device cuda` solo in un
ambiente locale con PyTorch CUDA compatibile installato separatamente. Nessuno
scraper viene avviato dai comandi di embedding.

Sul server applicare prima lo schema, senza avviare ingestion:

```bash
docker compose -p musefy-production-6pe27w -f compose.production.yaml run --rm migrate
```

PostgreSQL di produzione resta su rete privata. Per un batch dal PC, aprire un
forward SSH verso l’IP Docker corrente di PostgreSQL sulla rete `database`:

```bash
ssh -N -L 127.0.0.1:55433:IP_POSTGRES_CONTAINER:5432 ssh.edia-company.com
# In un altro terminale: impostare DATABASE_URL con host 127.0.0.1:55433
# usando le credenziali PostgreSQL locali protette, senza inserirle nella history.
uv run musefy embed --batch-size 32 --threads 8
```

L’IP Docker può cambiare a ogni deploy: rilevarlo nuovamente con `docker inspect`.
Nessuna porta PostgreSQL pubblica e nessun endpoint HTTP per generare o caricare embeddings.

Per mantenere l’indice aggiornato dal PC, `embed --watch` riparte dagli ID iniziali
a ogni passata, salta hash/profili correnti e attende 60 secondi dopo il completamento.
Non accetta `--force` o `--max-items`. Un errore interrompe il processo senza perdere
i batch già committati; il servizio locale lo riavvia ricreando il tunnel e rilevando
l’IP corrente del container PostgreSQL.

Template in `infra/embeddings/`: copiare `embeddings.env.example` in
`~/.config/musefy/embeddings.env` (directory 700, file 600), configurare i percorsi
assoluti, le credenziali DB e l’accesso SSH non interattivo. `MUSEFY_RUNTIME` deve
contenere il comando `bin/musefy` con questi pacchetti installati e il modello già
scaricato. Per CUDA usare un venv separato con PyTorch CUDA compatibile, mantenendo
lo stesso modello/revisione; il lockfile dell’app rimane CPU. Nessun segreto va nei
template o nella repository.

```bash
mkdir -p ~/.config/systemd/user
cp infra/embeddings/musefy-embeddings.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now musefy-embeddings.service
systemctl --user status musefy-embeddings.service
journalctl --user -u musefy-embeddings.service -f
systemctl --user stop musefy-embeddings.service
```

Il servizio gira sul PC: quando è spento, sospeso o senza rete il recupero riprende
al ritorno. `loginctl enable-linger "$USER"` permette al servizio utente di continuare
dopo il logout. Non calcola embeddings sul server e non avvia scraper.

## Ripresa, aggiornamenti e limiti

Il catalogo usa quattro tabelle, inclusa `title_embeddings` descritta sopra: `titles` con identità/filtri
e metadati JSONB validati da Pydantic;
`ingestion_items` con ID scoperti e passaggi parziali; `checkpoints` con cursori/versioni.
Gli account e le sessioni aggiungono le tabelle `users` e `auth_sessions`.

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
- Concorrenza limitata **per tipo**, code di dimensione `2 × CONCURRENCY`, nessun task per
  l'intero catalogo. TMDB: 10 richieste/s configurabili. Jikan: almeno 1,1 s tra
  richieste, senza burst, più finestra mobile di 60/min (quindi anche sotto 3/s).
  Questi limiti di frequenza e le pause 429 sono condivisi fra i due tipi dello stesso
  provider; quattro runner non moltiplicano le richieste/s consentite.
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
uv run uvicorn musefy_backend.app:app --reload --no-access-log
uv run musefy list --limit 10
uv run mypy
uv run ruff check packages tests migrations
uv run ruff format --check packages tests migrations
```

Costruire anche l’immagine PostgreSQL compatibile con il volume Alpine esistente:

```bash
docker build -t musefy-postgres:17-pgvector infra/postgres
```

Database di test **dedicato e distruttibile**, separato dal catalogo:

```bash
docker run --rm -d --name musefy-test-postgres \
  -e POSTGRES_USER=musefy -e POSTGRES_PASSWORD=test-only -e POSTGRES_DB=musefy_test \
  -p 127.0.0.1:55432:5432 musefy-postgres:17-pgvector
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

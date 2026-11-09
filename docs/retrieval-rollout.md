# Rilascio retrieval, healer e nuovi embeddings

Il modello resta `intfloat/multilingual-e5-small`, 384 dimensioni. Il documento
include titolo, formato, generi, temi/keyword e sinossi effettiva. Il nuovo profilo
viene preparato in `title_embedding_profiles`; `title_embeddings` conserva i
vettori precedenti. Il deploy **non attiva automaticamente il nuovo profilo**.

## Schema e deploy

Il deploy consueto applica `alembic upgrade head`. Le revisioni nuove sono:

1. `f84a31cd297b`: documento, policy, overlay, hash e tre flag generati.
2. `c29e14b78a05`: coda persistente del healer.
3. `19e20a75b9c1`: vettori paralleli e profilo attivo.
4. `6f230a11b064`: indice cosine HNSW creato `CONCURRENTLY`.
5. `7b8c62d10ae4`: pacing HTTP condiviso tra processi.

La prima revisione calcola hash e flag (`semantic_eligible`, `needs_healing`,
`recommendation_eligible`) in una sola riscrittura di `titles` con
lock esclusivo: pianificare una finestra di manutenzione e spazio per la riscrittura.
La durata va misurata su una copia del catalogo; il benchmark ridotto non la
predice. Dopo lo schema, **il lungo backfill resta separato e mantiene disponibile
la ricerca sui vettori precedenti**. Un titolo modificato dal healer può diventare
temporaneamente privo di un vettore corrente.

HNSW viene costruito inizialmente sulla tabella nuova vuota, poi aggiornato dal
backfill. Per una procedura manuale con caricamento prima della costruzione:
applicare fino a `19e20a75b9c1`, eseguire il batch, quindi `alembic upgrade head`
prima di avviare scraper/healer aggiornati. Il pacing richiede l'ultima revisione.
Un'interruzione della costruzione concorrente lascia eventualmente un indice
invalido; rieseguire la migrazione lo ricrea.

## PC che calcola i vettori

Il servizio utente esistente usa un runtime separato dal checkout: un `git pull`
da solo non aggiorna i pacchetti installati. Dopo il deploy dello schema:

```bash
systemctl --user stop musefy-embeddings.service
uv pip install \
  --python /home/francesco/.local/share/musefy/embedding-runtime/bin/python \
  --no-deps ./packages/core ./packages/scraper ./packages/cli
systemctl --user start musefy-embeddings.service
journalctl --user -u musefy-embeddings.service -f
```

Adattare il percorso al valore `MUSEFY_RUNTIME` del proprio ambiente. `--no-deps`
mantiene la wheel PyTorch CUDA eventualmente installata: le dipendenze non sono
cambiate. Il servizio usa già `embed --watch`: prepara automaticamente tutti i
documenti mancanti/obsoleti e riprende dai batch committati. **Non serve `--force`,
né esportare o caricare file di vettori**. Il batch scrive direttamente nel DB
privato attraverso il tunnel. Verificare prima che SSH/Cloudflare funzioni:
`websocket: bad handshake` impedisce sia il batch sia i comandi di controllo.

Con il watcher e il suo tunnel attivi, lo script seguente usa lo stesso
EnvironmentFile senza stampare credenziali o aprire un secondo forward:

```bash
./infra/embeddings/command.sh embedding-status
./infra/embeddings/command.sh embedding-benchmark \
  --queries "$PWD/benchmarks/retrieval.json" --threads 4
./infra/embeddings/command.sh embedding-activate
```

`embedding-status` espone profilo attivo, titoli semanticamente idonei, vettori
correnti e pendenti. `embedding-activate` rifiuta un profilo vuoto o con pendenti;
il cambio viene committato atomicamente. Con ingestion continua può esserci un
piccolo arretrato: attendere il watcher e ritentare; se non si azzera, fermare
brevemente ingestion/healer durante l'ultimo recupero e il passaggio, poi riavviarli.

Rollback del solo profilo, senza cancellare i nuovi vettori:

```bash
./infra/embeddings/command.sh embedding-activate --profile legacy
```

I vecchi vettori non vengono più aggiornati dal nuovo watcher: la copertura del
rollback diminuisce nel tempo. Non eliminare la tabella precedente durante la
prima verifica del rilascio.

## Benchmark e indice

`embedding-benchmark` misura il **profilo nuovo prima dell'attivazione**, confrontando
ANN e ricerca esatta senza mascherare pagine incomplete con il fallback. Il JSON
contiene ID, recall e tempi per query, media/minimo del recall e p50/p95 dei tempi.
La generazione del vettore della query è esclusa da questi tempi.

`benchmarks/retrieval.json` contiene 32 query italiane sui quattro tipi. Aggiungere
query reali e filtri selettivi per anno/genere; ripetere le misure a cache calda.
Prima del passaggio verificare recall@20, cardinalità, p95 e piano effettivo sul
catalogo completo. Non interpretare il recall ANN come giudizio di pertinenza:
misura quanto i risultati approssimati coincidono con quelli esatti.

HNSW usa `vector_cosine_ops`, `m=16`, `ef_construction=128`. Ogni ricerca del nuovo
profilo imposta localmente `hnsw.iterative_scan=strict_order`, `ef_search` almeno 400
e un budget di scansione limitato. Policy, hash e filtri precedono la selezione
dei risultati; pagine ANN insufficienti ricadono sulla ricerca esatta. Il planner
può scegliere la ricerca esatta per insiemi piccoli o molto selettivi.

## Healer

Avvio limitato, dal checkout sulla VM dopo il deploy:

```bash
docker compose -p musefy-production-6pe27w -f compose.production.yaml \
  run --rm healer musefy heal --max-items 100
```

Servizio continuo:

```bash
docker compose -p musefy-production-6pe27w -f compose.production.yaml up -d healer
```

Il servizio è nel profilo `healing`: aggiungere `healer` alla lista esplicita del
comando di deploy Dokploy per mantenerlo tra i servizi gestiti nei deploy futuri.
Il solo push non avvia un servizio assente da quella lista. Il ciclo elabora fino
a 1000 schede, poi attende 300 secondi; un errore di processo viene riavviato da Docker.

TMDB usa il Bearer esistente; TVmaze non richiede chiavi. `TMDB_RPS=10` (massimo 30)
e `TVMAZE_RPS=1` (massimo 2) sono coordinati tramite PostgreSQL anche tra ingestion
e healer; `429`/`Retry-After` sospendono il provider condiviso. Non avviare processi
con limiti diversi sullo stesso provider. I limiti non coordinano altri programmi
che usino lo stesso IP fuori da Musefy.

Priorità: sinossi assente/placeholder/note, poi trame brevi. TMDB tenta italiano e,
se ancora scarso, inglese. Per le serie, TVmaze usa soltanto ID IMDb/TheTVDB esatti
e verificati; nessuna associazione per somiglianza del titolo. Si conserva solo
un testo narrativo che migliori quello disponibile, con provenienza. Un successivo
refresh della fonte può prevalere se restituisce un testo migliore, senza cancellare
l'overlay conservato. I confronti fra trame valide usano la quantità di parole:
è una preferenza deterministica, non una valutazione semantica della fonte.

Coda, lease e passaggi TMDB riusciti sono persistiti. Errori temporanei usano
backoff esponenziale; un risultato negativo scade dopo 30 giorni. Per ritentare
prima usare `musefy heal --max-items 100 --retry-not-found` (incompatibile con watch).
Anime e manga ricevono le policy di qualità, ma questo healer recupera solo titoli
TMDB; non associa automaticamente anime/manga a serie TVmaze.

La sinossi originale resta in `titles.details`; l'overlay separato include fonte,
ID, endpoint, URL e data. API e dettaglio mostrano la provenienza effettivamente
usata. TVmaze richiede attribuzione e [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/):
il testo viene conservato con tale provenienza e l'interfaccia segnala la rimozione
del markup HTML. Riferimenti: [TVmaze API](https://www.tvmaze.com/api),
[TMDB rate limiting](https://developer.themoviedb.org/docs/rate-limiting).

## Policy delle raccomandazioni

- Film TMDB con voto TMDB `<5/10` e almeno 100 voti: esclusi dalle raccomandazioni.
- Sinossi assente, placeholder riconosciuto o sole note di stagione/franchise:
  esclusione temporanea dalla ricerca semantica e priorità al healer.
- Trama breve ma informativa: resta idonea. Per italiano/inglese, meno di 40 parole
  assegna priorità al healer; nessuna soglia universale per altre lingue.
- Pochi generi, voto assente o meno di 100 voti: nessuna esclusione per questo motivo.

Il catalogo e la ricerca per titolo restano completi. I voti non fanno parte del
documento: aggiornarli cambia subito il filtro senza richiedere un nuovo vettore.
Anche i flag sono aggiornati automaticamente da PostgreSQL: regex e rating non
vengono rivalutati per ogni candidato a ogni ricerca.

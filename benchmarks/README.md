# Retrieval benchmark

`retrieval.json` contiene 32 query italiane, otto per film, TV, anime e manga.
Sono descrizioni di trame note senza il titolo nella query; non sono traffico utente.

Dopo il backfill del profilo nuovo, prima del passaggio:

```bash
./infra/embeddings/command.sh embedding-benchmark \
  --queries "$PWD/benchmarks/retrieval.json" --threads 4
```

Il comando confronta risultati approssimati ed esatti del profilo nuovo anche
quando quello precedente è ancora attivo. Non attiva il profilo e non esegue
healing. Riporta ID, recall e tempi per ogni caso, media/minimo recall e p50/p95.
Il tempo di embedding della query è escluso. Ripetere a cache calda e aggiungere
filtri selettivi anno/genere e richieste reali prima del passaggio in produzione.
Il planner può scegliere un ordinamento esatto su insiemi piccoli: verificare
`EXPLAIN` per attribuire correttamente i risultati a HNSW.

Il benchmark locale iniziale sui documenti, 2.917 titoli reali e 32 positivi noti,
ha portato Hit@2 da 19/32 a 24/32 e Hit@10 da 24/32 a 29/32 rispetto alla sola sinossi.
È una verifica esplorativa su un campione, non una misura di precisione né una
prova di miglioramento per ogni query. Dati grezzi, vettori e report sono negli
artifacts locali ignorati da Git; non vengono pubblicati payload dei provider.

Procedura operativa: [retrieval-rollout.md](../docs/retrieval-rollout.md).

Validazione HNSW locale (PostgreSQL 17/pgvector 0.8.7): 128 combinazioni di query
con tipo, genere e anno, 2.910 vettori idonei sui 2.917 titoli. Il planner sul
campione sceglieva la ricerca esatta: il suo recall 1.0 non dimostra uso di HNSW.
Forzando il percorso HNSW e confrontando `ef_search=100/200/400`, il valore 400 ha
ottenuto recall@20 medio 0,9996, minimo 0,95 e cardinalità corretta in 128/128 casi.
È il minimo scelto per la ricerca; le latenze sul campione non predicono quelle
sul catalogo completo. Il test di freschezza ha escluso 40 vettori resi obsoleti.

Il benchmark ha anche individuato il costo delle policy calcolate durante ogni
scansione: spostarle in flag generati ha portato il p50 SQL della ricerca esatta
globale sul nuovo profilo da circa 1.079 ms a 4,9 ms nel campione. Include macchine,
cache e carico locali, senza garanzie sul tempo di produzione. Il confronto va
ripetuto dopo il backfill reale con il comando sopra.

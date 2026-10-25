# AeroControlQwen — aero-ecosystem

**Ecosistema aerospaziale per simulazione di volo, controllo e calibrazione automatica.**

Un ambiente integrato che comprende un simulatore di volo a sei gradi di libertà, una Ground Control Station con strumenti di cockpit, un flight controller con sintesi automatica dei guadagni, e un'infrastruttura di comunicazione real-time. Progettato per essere estendibile a diverse configurazioni di velivolo.

---

## Principi guida

| Principio | Descrizione |
|---|---|
| **Nessun numero indovinato** | I guadagni del controllore sono derivati dalla fisica del velivolo tramite una catena deterministica, non impostati a mano |
| **Verifica oggettiva** | Ogni sintesi è valutata da un gate numerico configurabile, non da un giudizio soggettivo |
| **Calibrazione per velivolo** | Cambiando le tavole aerodinamiche e le inerzie, i guadagni si ricalcolano automaticamente senza modifiche al codice |
| **Calibrazione per requisiti** | L'utente specifica le prestazioni desiderate; il sistema produce i guadagni coerenti |
| **Modularità** | Il flight controller è un modulo indipendente, riusabile su hardware futuro senza dipendenze dal simulatore |
| **Trasparenza** | Ogni passaggio della catena di calibrazione è verificabile e documentato |

---

## Architettura

```
┌─────────────────────────────────────────────────────────────┐
│                    GCS (Ground Control Station)              │
│   Strumenti cockpit · Telemetria · Comandi · Lancio sim     │
└──────────────────┬───────────────────────┬──────────────────┘
                   │ Telemetria (ZMQ)      │ Comandi (ZMQ)
                   ▼                       ▼
┌─────────────────────────────────────────────────────────────┐
│                    Simulatore di volo 6-DoF                  │
│   Dinamica corpo rigido · Aerodinamica · Propulsione        │
│   Flight controller integrato                                │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│              flight_controller (modulo indipendente)          │
│   Gate di accettazione · Trim · Estrazione pianta           │
│   Sintesi guadagni · Gain scheduling · System ID            │
│   Rate loop · Attitude loop · Anelli esterni (pianificati)  │
└─────────────────────────────────────────────────────────────┘
```

### Catena di calibrazione

```
Tavole aerodinamiche + inerzie + geometria
        ↓ Trim (equilibrio forze e momenti)
Condizione di volo di riferimento
        ↓ Estrazione derivate
Modello della pianta per asse
        ↓ Sintesi guidata da specifica di prestazione
Guadagni del controllore
        ↓ Gate di accettazione
Verifica / iterazione conservativa
        ↓ System identification (opzionale)
Confronto con il simulatore non lineare
```

### Flusso di volo

```
Input GCS → comandi normalizzati → ZMQ
    → Simulatore → Flight controller → superfici
    → Dinamica 6-DoF → telemetria → ZMQ → strumenti GCS
```

---

## Stack tecnologico

| Componente | Tecnologia |
|---|---|
| Linguaggio | Python |
| GUI | PySide6 (Qt) |
| Comunicazione | ZeroMQ |
| Calcolo numerico | NumPy |
| Piattaforme | Windows, Linux |

Tutte le dipendenze sono open-source e compatibili con uso commerciale.

---

## Vincoli di progetto

### Architetturali

- I guadagni del controllore sono **calcolati**, mai impostati a mano
- Il "se OK" è un **confronto numerico** con una specifica configurabile
- Il flight controller è un **modulo indipendente** dal simulatore
- I controlli devono rispettare i **limiti fisici degli attuatori**

### Di workflow

- **Ala fissa**: sintesi automatica → gate → verifica in simulatore → correzioni → fallback manuale come eccezione
- **Configurazioni complesse** (multirotore, transizione): domini di tuning separati, con la transizione come dominio autonomo
- **Approcci neurali**: solo come supervisore o compensazione residua, mai come anello primario di controllo

### Tecnici

- Solo Python, nessuna dipendenza proprietaria
- Windows e Linux
- Simulazione a corpo rigido a sei gradi di libertà
- Simulatore e GCS come processi separati
- Test autonomi per ogni componente del flight controller

---

## Struttura del repository

```
aero-ecosystem/
├── simulator/                  # Simulatore di volo
│   ├── run_sim.py              # Entry point
│   ├── sim_engine.py           # Integrazione 6-DoF
│   ├── dynamics/               # Equazioni del moto, atmosfera, aero, propulsione
│   ├── aircraft/               # Configurazioni velivolo
│   ├── flight_controller/      # FC modulare
│   └── test_*.py               # Test autonomi
│
├── gcs_ui/                     # Ground Control Station
│   └── sim_ui/
│       ├── main.py             # Entry point
│       ├── sim_manager.py      # Gestione processo simulatore
│       └── ui/                 # Finestra, strumenti, dialog
│
├── ipc_bus/                    # Protocollo ZMQ (telemetria + comandi)
└── control_input/              # Input tastiera configurabile
```

---

## Il Flight Controller

Il pacchetto `flight_controller/` implementa una catena di calibrazione completa.

### Gate di accettazione

Definisce i requisiti di prestazione in modo numerico e configurabile: banda passante, smorzamento, overshoot, tempo di assestamento, errore a regime, margini di stabilità, saturazione degli attuatori. Ogni sintesi viene valutata contro questa specifica.

### Trim e estrazione della pianta

Risolve la condizione di equilibrio per una data condizione di volo e ricava le derivate aerodinamiche rilevanti per il controllo. Il risultato è un modello della pianta per ciascun asse, espresso in termini di guadagno e costante di tempo.

### Sintesi dei guadagni

Calcola i guadagni del controllore a partire dal modello della pianta e dalla specifica di prestazione, usando un metodo di piazzamento dei poli. Se il gate non è soddisfatto, il sistema itera in modo conservativo riducendo o aumentando la banda passante a seconda del tipo di fallimento.

### Gain scheduling

Estende la validità dei guadagni a più condizioni di volo costruendo una griglia di punti di trim e interpolando i guadagni in base alla condizione corrente. Include un meccanismo di smoothing per evitare transizioni brusche.

### System identification

Verifica che il modello lineare usato per la sintesi corrisponda al comportamento del simulatore non lineare. Eccita il sistema ad anello aperto con segnali noti e confronta la risposta con il modello analitico.

### Anelli di controllo

| Anello | Stato | Descrizione |
|---|---|---|
| Rate (inner) | Integrato | Stabilizza le velocità angolari. Comanda le superfici a partire dal rate desiderato |
| Attitude (middle) | Implementato, non integrato | Comanda il rate a partire dall'angolo desiderato |
| Altitude / Speed (outer) | Pianificato | Comanda l'assetto a partire da quota e velocità desiderate |

Il rate loop stabilizza l'assetto del velivolo. Gli anelli esterni, necessari per il mantenimento autonomo di quota e velocità, sono pianificati.

---

## La GCS

La Ground Control Station fornisce:

- **Strumenti di cockpit** configurabili, con temi e layout salvabili
- **Telemetria unificata**: mock, esterna, ZeroMQ, traiettorie di test, pausa
- **Comandi di volo** da tastiera con mappatura configurabile e persistente
- **Lancio del simulatore** con configurazione delle condizioni iniziali
- **Log del simulatore** con visibilità persistente

Il simulatore viene lanciato come processo separato e comunicato via ZeroMQ. La GCS può avviare, fermare e monitorare la simulazione.

---

## Stato attuale

### Implementato

- Simulatore di volo 6-DoF con aerodinamica e propulsione
- Flight controller con catena di calibrazione completa (gate, trim, pianta, sintesi, scheduling, sysid)
- Integrazione del rate loop nel simulatore
- GCS con strumenti, telemetria, comandi, temi, preset
- Lancio del simulatore dalla GCS con configurazione
- Mappatura tasti configurabile e persistente
- Test autonomi per tutti i componenti del flight controller

### In sviluppo

- GUI di tuning per la calibrazione interattiva
- Integrazione dell'attitude loop nel simulatore
- Anelli esterni per quota e velocità
- Test di regressione dinamica end-to-end

### Pianificato

- Visuale 3D del velivolo
- Supporto per configurazioni multi-velivolo
- Estensione a configurazioni multirotore e transizione
- Profili di tuning persistenti per velivolo

---

## Roadmap

| Fase | Contenuto |
|---|---|
| **Chiusura integrazione** | Auto-connect telemetria, test di regressione, preferenze coerenti |
| **GUI di tuning** | Interfaccia per calibrazione interattiva con report del gate |
| **Anelli esterni** | Attitude loop integrato, altitude e airspeed hold |
| **Estensione velivoli** | Configurazioni aggiuntive, profili di tuning per velivolo |
| **Visuale 3D** | Rappresentazione del velivolo in volo |
| **Configurazioni complesse** | Multirotore, transizione, gain scheduling avanzato |

---

## Test

Ogni componente del flight controller ha test autonomi che verificano proprietà strutturali e comportamentali. I test non richiedono framework esterni e stampano un esito leggibile.

```bash
python simulator/test_rate_controller.py
python simulator/test_attitude_controller.py
python simulator/test_performance_spec.py
python simulator/test_trim_plant.py
python simulator/test_synthesis.py
python simulator/test_gain_scheduler.py
python simulator/test_sysid.py
```

---

## Convenzioni

| Regola | Dettaglio |
|---|---|
| Test autonomi | Ogni test aggiunge i percorsi necessari e stampa PASS/FAIL |
| Nessun guadagno hardcoded | I guadagni sono il risultato della sintesi, non un input |
| Dataclass per i contratti | Telemetria, comandi, specifiche, metriche sono dataclass |
| Segni di direzione espliciti | Il segno fisico delle derivate è catturato e applicato dal controllore |
| Stop non bloccante | La gestione dei processi usa segnali e watchdog, non chiamate bloccanti |
| Output non bufferizzato | I processi figli sono lanciati con buffering disabilitato |

---

## Licenza e dipendenze

Tutte le dipendenze sono open-source e compatibili con uso commerciale. Nessuna componente proprietaria è richiesta.

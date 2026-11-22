"""
Dry-run fixtures for public sales: two real notices from the Gazzetta Ufficiale
5a serie (texts reproduced from the public record, July 2026). Used instead of
network calls when the ingestion runs in dry_run mode, and by the tests.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from app.ingestion.public_sales.sources import RawNotice

_TZ = ZoneInfo("Europe/Rome")

GENZANO_BODY = " Asta pubblica per l'alienazione di immobili di proprieta' comunale \n  Si rende noto che il giorno 4 settembre 2026 alle ore 10.00  presso\nla sede del Comune di Genzano in via Italo Belardi  81,  avra'  luogo\nl'asta pubblica, in un  unico  e  definitivo  esperimento,  ai  sensi\ndell'art. 73, lett c) e art. 76 del R.D. 23 maggio  1924,  n.827  per\nl'alienazione dei seguenti immobili: \n  Lotto 1, LOCALE COMMERCIALE CHIOSCO BAR sito in Via Luigi Longo 8 -\nfg.2 particella 1537 Cat C/1; \n  Importo a base di gara: € 80.000,00 non soggetto ad IVA. \n  Lotto 2, LOCALE COMMERCIALE sito in Largo Dott. Nicola Ottavio snc-\nfg.3 particella 1906 sub 2 Cat C/1; \n  Importo a base di gara: € 58.750,20 non soggetto ad IVA. \n  Lotto 3, Magazzino cantina- fg.2 particella 942 sub 501 Cat. C/2; \n  Importo a base di gara: € 8.363,70 non soggetto ad IVA. \n  Lotto 4, Magazzino tettoia - fg.11 particella 454 sub 10 Cat. A/5; \n  Importo a base di gara: € 8.570,70 non soggetto ad IVA. \n  Lotto 5, Magazzino fabbricato rurale - fg.2 particella 972; \n  Importo a base di gara: € 31.816,00 non soggetto ad IVA. \n  Lotto 6, Magazzino - fg.11 particella 640 sub 1 Cat. C/2; \n  Importo a base di gara: € 28.050,00 non soggetto ad IVA. \n  Lotto 7, Magazzino grotta - fg.11 particella 463 Cat B/8; \n  Importo a base di gara: € 4.582,00 non soggetto ad IVA. \n  Lotto 8, Terreno - fg.8 particella 24 area verde; \n  Importo a base di gara: € 5.600,00 non soggetto ad IVA. \n  Scadenza: 02 settembre 2026 ore 12.00. \n  Informazioni ed esame della documentazione  completa:  c/o  Ufficio\nPatrimonio con appuntamento \n  Il responsabile del procedimento Dott.ssa Daniela Virciglio \n                            Il dirigente \n                    dott.ssa Daniela Bastianelli \nTX26BIA353\n"

MOMO_BODY = '                 Asta pubblica - Vendita immobiliare \n  Estratto di avviso di asta pubblica ad unico e  definitivo  incanto\ncon il metodo delle offerte segrete di cui all\'art. 73 lettera c) del\nRegio Decreto 23/05/1924, n. 827 e smi per la vendita di  terreno  di\nproprieta\' del Comune di Momo. \n  Il Responsabile del Servizio  Tecnico  con  Determina  n.  181  del\n01/07/2026 rende noto che il giorno 04/08/2026 con  inizio  alle  ore\n09:00 avra\' luogo nella  sala  giunta  del  Comune  di  Momo  in  via\nSquarini 2 un esperimento di  asta  pubblica  a  unico  e  definitivo\nincanto con il metodo delle offerte segrete da  confrontarsi  con  il\nprezzo base d\'asta di € 92.750,00, per l\'alienazione di  un  immobile\nappartenente al patrimonio comunale. \n  L\'offerta deve pervenire in plico chiuso all\'ufficio protocollo del\nComune di Momo entro le  ore  12:00  del  giorno  03/08/2026  recante\nall\'esterno il nominativo del mittente e la seguente  dicitura:  "Non\naprire - Offerta asta pubblica alienazione immobile". \n  Il bando e la relativa documentazione  relativa  all\'immobile  sono\nintegralmente pubblicati sull\' Albo on-line e sul sito del Comune  di\nMomo. \n                    Il responsabile del servizio \n                         geom. Marco Bordin \nTX26BIA326\n'

FIXTURE_NOTICES = [
    RawNotice(
        notice_id="TX26BIA353",
        source="gu",
        title="Asta pubblica per l'alienazione di immobili di proprieta' comunale",
        body=GENZANO_BODY,
        ente="COMUNE DI GENZANO DI ROMA",
        sede="via Italo Belardi, 81 - 00045 Genzano di Roma (RM), Italia",
        url="https://www.gazzettaufficiale.it/atto/contratti/caricaDettaglioAtto/originario?atto.dataPubblicazioneGazzetta=2026-07-27&atto.codiceRedazionale=TX26BIA353",
        published=datetime(2026, 7, 27, tzinfo=_TZ),
    ),
    RawNotice(
        notice_id="TX26BIA326",
        source="gu",
        title="Asta pubblica - Vendita immobiliare",
        body=MOMO_BODY,
        ente="COMUNE DI MOMO",
        sede="via Squarini n. 2 - 28015 Momo",
        url="https://www.gazzettaufficiale.it/eli/id/2026/07/08/TX26BIA326/S5",
        published=datetime(2026, 7, 8, tzinfo=_TZ),
    ),
]

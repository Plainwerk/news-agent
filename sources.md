# Nachrichtenquellen

Zentrale Konfiguration aller RSS-Feeds. Hier Quellen ergänzen oder entfernen —
das Fetch-Skript liest diese Datei automatisch ein.

**Labels:** `links` | `mitte-links` | `mitte` | `mitte-rechts` | `rechts` | `öRR` | `agentur`

---

## Quellen

| Name                  | Feed-URL                                                        | Label      |
|-----------------------|-----------------------------------------------------------------|------------|
| Tagesschau            | https://www.tagesschau.de/xml/rss2                              | öRR        |
| ZDF heute             | https://www.zdf.de/rss/zdf/nachrichten                         | öRR        |
| Der Spiegel           | https://www.spiegel.de/schlagzeilen/index.rss                   | mitte-links |
| Zeit Online           | https://newsfeed.zeit.de/index                                  | mitte-links |
| Süddeutsche Zeitung   | https://rss.sueddeutsche.de/rss/Topthemen                      | mitte-links |
| FAZ                   | https://www.faz.net/rss/aktuell/                                | mitte      |
| NZZ                   | https://www.nzz.ch/recent.rss                                   | mitte      |
| Handelsblatt          | https://www.handelsblatt.com/contentexport/feed/schlagzeilen    | mitte      |
| Die Welt              | https://www.welt.de/feeds/topnews.rss                          | mitte-rechts |
| Cicero                | https://www.cicero.de/rss.xml                                   | mitte-rechts |
| taz                   | https://taz.de/!p4608;rss                                       | links      |
| Neues Deutschland     | https://www.nd-aktuell.de/rss/aktuell.php                       | links      |
| Junge Freiheit        | https://jungefreiheit.de/feed/                                  | rechts     |
| Tichys Einblick       | https://www.tichyseinblick.de/feed/                             | rechts     |
| n-tv (dpa)            | https://www.n-tv.de/rss                                         | agentur    |

---

## Hinweise

- Alle URLs beim ersten Testlauf prüfen — Feed-Strukturen ändern sich gelegentlich.
- Reuters hat seine RSS-Feeds 2020 eingestellt. Als Ersatz dient n-tv, das primär
  dpa-Agenturmeldungen sendet.
- Themen-Scope: Politik, Wirtschaft, Gesellschaft. Sport/Kultur/Boulevard wird
  im Fetch-Skript per Kategorie-Filter ausgeblendet (konfigurierbar).

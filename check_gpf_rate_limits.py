#!/usr/bin/env python3
"""Compare le tableau des limites d'usage de la Géoplateforme aux limites annoncées par Kong.

Pour chaque ligne du tableau de DOC_URL, envoie une requête légère (jamais de
rafale) et compare la limite documentée à l'en-tête RateLimit-Limit de Kong.
Bibliothèque standard uniquement ; le proxy est pris dans HTTPS_PROXY.
Code de sortie : 0 si toutes les lignes concordent, 1 sinon.
"""

import re
import sys
from urllib.error import HTTPError
from urllib.request import Request, urlopen

DOC_URL = "https://cartes.gouv.fr/aide/fr/guides-utilisateur/utiliser-les-services-de-la-geoplateforme/limites-d-usage/"
HEADERS = {"User-Agent": "gpf-rate-limit-check"}
GPF = "https://data.geopf.fr"
COPC = "LiDARHD-NUALID/NUALHD_1-0__LAZ_LAMB93_AE_2025-07-22/LHD_FXX_0098_6847_PTS_LAMB93_IGN69.copc.laz"

# Fragment du libellé (en minuscules) -> URL de test. La première correspondance
# gagne : « téléchargement copc », « au vol » et « partiel » passent donc avant
# « téléchargement ». Si un fichier disparaît, Kong répond quand même (404 avec
# ses en-têtes) ; un fichier à jour se trouve sous
# https://data.geopf.fr/chunk/telechargement/resource/LiDARHD-NUALID
PROBES = {
    "téléchargement copc": f"{GPF}/telechargement/download/{COPC}",
    "au vol": f"{GPF}/chunk/telechargement/download/{COPC}",
    "vraie pyramide": f"{GPF}/chunk/telechargement/download/lidarhd_fxx_ept/AE_EPT/ept.json",
    "partiel": f"{GPF}/chunk/telechargement/capabilities?limit=1",
    "téléchargement": f"{GPF}/telechargement/capabilities?limit=1",
    "wms-raster": f"{GPF}/wms-r?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetMap&LAYERS=ORTHOIMAGERY.ORTHOPHOTOS"
                  "&STYLES=&CRS=EPSG:4326&BBOX=48.85,2.35,48.851,2.351&WIDTH=1&HEIGHT=1&FORMAT=image/png",
    "wms-vecteur": f"{GPF}/wms-v/ows?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities",
    "wfs": f"{GPF}/wfs/ows?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature&TYPENAMES=ADMINEXPRESS-COG.LATEST:region"
           "&COUNT=1&PROPERTYNAME=nom_officiel&OUTPUTFORMAT=application/json",
    "csw": f"{GPF}/csw?SERVICE=CSW&REQUEST=GetCapabilities&VERSION=2.0.2",
    "autocomplétion": f"{GPF}/geocodage/completion?text=paris&maximumResponses=1",
    "géocodage": f"{GPF}/geocodage/search?q=paris&limit=1",
    "altimétrique": f"{GPF}/altimetrie/1.0/calcul/alti/rest/elevation.json?lon=2.35&lat=48.85&resource=ign_rge_alti_wld",
    "itinéraire": f"{GPF}/navigation/itineraire?resource=bdtopo-valhalla&profile=pedestrian&start=2.35,48.85&end=2.36,48.86",
    "isochrone": f"{GPF}/navigation/isochrone?resource=bdtopo-valhalla&profile=pedestrian&point=2.35,48.85"
                 "&costType=time&costValue=1&timeUnit=minute",
    "recherche": f"{GPF}/recherche/api/indexes/geoplateforme/suggest?text=orthophoto",
    "pg_tileserv": f"{GPF}/vector-tms/1.0.0/cartes.dataset/18/0/0.pbf",  # tuile vide
}


def kong_limit(url):
    """Renvoie (statut HTTP, en-tête RateLimit-Limit) sans lire le corps de la réponse."""
    # Pour un fichier, 8 octets suffisent.
    headers = {**HEADERS, "Range": "bytes=0-7"} if "/download/" in url else HEADERS
    try:
        with urlopen(Request(url, headers=headers), timeout=20) as response:
            return response.status, response.headers.get("RateLimit-Limit")
    except HTTPError as error:  # Kong pose aussi ses en-têtes sur les erreurs (404, 429...)
        return error.code, error.headers.get("RateLimit-Limit")


def main():
    page = urlopen(Request(DOC_URL, headers=HEADERS), timeout=20).read().decode()
    rows = re.findall(r"<td>([^<]+)</td><td>(\d+) requêtes/s</td>", page)
    if not rows:
        sys.exit(f"Tableau des limites introuvable dans {DOC_URL}")

    print(f"{'API':45} {'Doc':>4} {'Kong':>5} {'HTTP':>5}  Verdict")
    ok = 0
    for label, doc in rows:
        url = next((url for key, url in PROBES.items() if key in label.lower()), None)
        status, kong = "-", None
        if url is None:
            verdict = "pas d'URL de test"
        else:
            try:
                status, kong = kong_limit(url)
                verdict = "OK" if kong == doc else "ÉCART" if kong else "pas d'en-tête"
            except OSError as error:  # réseau, DNS, TLS, délai dépassé
                verdict = f"erreur : {error}"
        ok += verdict == "OK"
        print(f"{label:45} {doc:>4} {kong or '-':>5} {status:>5}  {verdict}")

    print(f"\n{ok}/{len(rows)} lignes concordent avec Kong.")
    return 0 if ok == len(rows) else 1

if __name__ == "__main__":
    sys.exit(main())

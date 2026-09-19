import os
import re
import requests
from bs4 import BeautifulSoup
from github import Github, Auth

# --- RECUPERO DATI SENSIBILI DAI SECRETS DI GITHUB ---
GITHUB_TOKEN = os.getenv("GH_PAT")
REPO_NAME = os.getenv("REPO_NAME", "Truii24/list.m3u")  # Valore di default se non impostato
TMDB_API_TOKEN = os.getenv("TMDB_API_TOKEN")

# Controllo di sicurezza sui Secret obbligatori
if not GITHUB_TOKEN or not TMDB_API_TOKEN:
    raise ValueError("ERRORE: Mancano le variabili d'ambiente obbligatorie (GH_PAT o TMDB_API_TOKEN).")

headers = {
    "accept": "application/json",
    "Authorization": f"Bearer {TMDB_API_TOKEN}"
}

default_headers = {
    "User-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "Host": "vixsrc.to",
    "Cookie": "cf_clearance=9jeXHIzCTq30OXj51jCT7lkbJjG3PE_Jyxp1ZeJaW2M-1789843009-1.2.1.1-L4B9MHNk.CJFA_UafMYT4fsV1CFgf5H9sXQQwxhvrIiMg9m8azwiCJKuZd9sPnh._347ot18__tQj1VauNPecClnEq3S1Ds4duSiK9qikhCfhKJzMu0Qz23W5xttzJvBn7jY7uZs4jMniLw1g4cSHkuRwgqYKlMOGHHReLZKYLAod2F1YBie7cgS.1kQW4prs9_BTV.d6MhL8RYjKwBKwY94pznHYzyUdvalwTgzYYwouDYtPYIDvroZVRqCt0y.uNNAJBW7L4vti1tjFFW1rVcKyrrdPIVR2yB.KyXfIHBktgSuQRCJKgmhX.vLETqbDrjEWIKE7ZXcZb8vUyer1bKf_fEkZGASvSFKKvhM4Ze9XPUxD1rao0s12ynTR8R3FvaHRCMa_np0QG9F3bMuNRYDf__voy1oyR5zo.vYB.zvZWdF22NmjgbSnymABGTeDYticcZf7d4HjKxCAvQh4waXF4c4.GL67ztCR6e7MQ2ALEQOB3PzRO48XJ9lbA0NJRN2nOJ3jy6FrXghwi47vQ"
}

default_link_dove_rubo = "https://vixsrc.to/api/{}/{}"
default_vix = "https://vixsrc.to"

# I due formati di URL (con b=1 e senza b=1)
url_with_b = "https://vixcloud.co/playlist/{}?b=1&token={}&expires={}&h=1&scz=1&lang=it"
url_without_b = "https://vixcloud.co/playlist/{}?token={}&expires={}&h=1&scz=1&lang=it"


def get_token(html_text) -> tuple:
    soup = BeautifulSoup(html_text, "html.parser")

    token = None
    expires = None
    video_id = None

    script_playlist = soup.find("script", string=re.compile("masterPlaylist"))
    if script_playlist and script_playlist.string:
        match_playlist = re.search(
            r"'token':\s*'([^']+)'.*?'expires':\s*'([^']+)'", 
            script_playlist.string, 
            re.DOTALL
        )
        if match_playlist:
            token, expires = match_playlist.groups()

    script_video = soup.find("script", string=re.compile(r"window\.video"))
    if script_video and script_video.string:
        match_video = re.search(r"id:\s*'([^']+)'", script_video.string)
        if match_video:
            video_id = match_video.group(1)

    return token, expires, video_id


def verify_and_clean_hls_url(video_id: str, token: str, expires: str) -> str:
    """
    Testa prima il formato con ?b=1 e, in caso di errore (es. 403),
    prova il formato senza il parametro b=1.
    """
    check_headers = {
        "User-Agent": default_headers["User-agent"],
        "Referer": default_vix
    }

    url_with_b_formatted = url_with_b.format(video_id, token, expires)
    url_without_b_formatted = url_without_b.format(video_id, token, expires)

    # 1. Prova prima con b=1
    try:
        res = requests.head(url_with_b_formatted, headers=check_headers, timeout=5, allow_redirects=True)
        if res.status_code == 200:
            return url_with_b_formatted
        print(f"[INFO] Formato con 'b=1' ha restituito status code {res.status_code}. Provo senza 'b=1'...")
    except Exception as e:
        print(f"[INFO] Errore testando il formato con 'b=1': {e}. Provo senza 'b=1'...")

    # 2. Se fallisce, prova il formato senza b=1
    try:
        res_clean = requests.head(url_without_b_formatted, headers=check_headers, timeout=5, allow_redirects=True)
        if res_clean.status_code == 200:
            print("[SUCCESS] Il formato senza 'b=1' è valido (HTTP 200)!")
            return url_without_b_formatted
        else:
            print(f"[ERRORE] Anche il formato senza 'b=1' ha dato errore {res_clean.status_code}")
    except Exception as e:
        print(f"[ERRORE] Errore durante il test del formato senza 'b=1': {e}")

    return None


def grabMovie(id) -> str:
    try:
        r = requests.get(default_link_dove_rubo.format("movie", id), headers=default_headers)
        r.raise_for_status()
        
        data = r.json()
        if 'src' not in data:
            print(f"[ERRORE] Proprietà 'src' non trovata nella risposta API per ID {id}")
            return None

        embed_url = default_vix + data['src']
        r = requests.get(embed_url, headers=default_headers)
        r.raise_for_status()

        token, expires, video_id = get_token(r.text)

        if not all([token, expires, video_id]):
            print(f"[ERRORE] Impossibile estrarre token/expires/video_id per ID {id}")
            return None

        valid_url = verify_and_clean_hls_url(video_id, token, expires)
        return valid_url

    except Exception as e:
        print(f"[ERRORE] Fallimento in grabMovie per ID {id}: {e}")
        return None


def getUrl(items) -> list:
    results = []
    for item in items:
        movie_id = item.get('id')
        media_type = item.get('media_type')
        title = item.get('title') or item.get('name') or f"Movie_{movie_id}"
        poster_path = item.get('poster_path')
        
        poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else ""

        if media_type == "movie":
            complete_url = grabMovie(movie_id)
            if complete_url:
                results.append({
                    "id": movie_id,
                    "title": title,
                    "url": complete_url,
                    "poster": poster_url
                })
            else:
                print(f"[ERRORE] Impossibile recuperare un link funzionante per '{title}' (ID {movie_id})")
    return results


def getFromDb() -> list:
    try:
        response = requests.get("https://api.themoviedb.org/3/list/8697282", headers=headers)
        response.raise_for_status()
        
        data = response.json()
        if 'items' not in data:
            print("[ERRORE] Nessun elemento 'items' trovato nella risposta di TMDB.")
            return []

        return data['items']
    except Exception as e:
        print(f"[ERRORE] Fallimento in getFromDb: {e}")
        return []


def writeOnGitHub(m3u_content) -> bool:
    try:
        auth = Auth.Token(GITHUB_TOKEN)
        g = Github(auth=auth)
        repo = g.get_repo(REPO_NAME)

        file_path = "list.m3u"
        commit_message = "Aggiornamento automatico playlist HLS"

        try:
            contents = repo.get_contents(file_path)
            repo.update_file(
                path=file_path,
                message=commit_message,
                content=m3u_content,
                sha=contents.sha
            )
            print("File list.m3u aggiornato con successo su GitHub!")
        except Exception:
            repo.create_file(
                path=file_path,
                message=commit_message,
                content=m3u_content
            )
            print("File list.m3u creato con successo su GitHub!")
        return True
    except Exception as e:
        print(f"[ERRORE] Errore durante la scrittura su GitHub: {e}")
        return False


if __name__ == "__main__":
    items = getFromDb()
    if not items:
        print("[ERRORE] Nessun dato recuperato da TMDB. Operazione annullata.")
    else:
        movie_data = getUrl(items)
        if not movie_data:
            print("[ERRORE] Nessun URL valido generato. Operazione annullata.")
        else:
            m3u_lines = ["#EXTM3U"]
            for item in movie_data:
                m3u_lines.append(
                    f'#EXTINF:-1 tvg-id="{item["id"]}" tvg-name="{item["title"]}" tvg-logo="{item["poster"]}" group-title="Film", {item["title"]}'
                )
                m3u_lines.append(item["url"])
            
            m3u_content = "\n".join(m3u_lines)
            writeOnGitHub(m3u_content)

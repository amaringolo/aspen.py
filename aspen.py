import time
from datetime import datetime
from androidtv import setup
import subprocess
import sqlite3
import logging
import argparse

# --- Argumentos ---
parser = argparse.ArgumentParser(description="Controla el volumen de la TV según horario y registra canciones de Aspen 102.3")
parser.add_argument("--initial-volume", type=int, default=None, help="Volumen inicial de referencia")
args = parser.parse_args()

INITIAL_VOLUME = args.initial_volume

# --- Configuración ---
TV_HOST = "192.168.1.129"
ADB_PORT = 5555
REDUCTION_FACTOR = 0.2
MARGIN_SECONDS = 10
STEP_DELAY = 0.3
CHECK_SONG_EVERY = 10  # segundos
STREAM_URL = "https://playerservices.streamtheworld.com/api/livestream-redirect/ASPEN.mp3?dist=infobae"

VOLUME_SCHEDULE = {
      8: [(16, 22), (46, 52)],
      9: [(16, 22), (46, 52)],
      10: [(16, 22), (46, 52)],
      11: [(16, 22), (46, 52)],
      12: [(16, 22), (46, 52)],
      13: [(16, 22), (46, 52)],
      14: [(16, 22), (46, 52)],
      15: [(16, 22), (46, 52)],
      16: [(16, 22), (46, 52)],
      17: [(16, 22), (46, 52)],
}

# --- Logging ---
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logging.info("Programa de control de volumen de TV según horario y registro de canciones de Aspen 102.3.")
logging.info("Cada canción se registra en SQLite y el volumen se reduce gradualmente durante periodos programados.")

# --- Base de datos SQLite ---
conn = sqlite3.connect("songs.db")
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS songs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    title TEXT NOT NULL
)
""")
conn.commit()

# --- Funciones ---
def is_within_scheduled_interval(now):
    intervals = VOLUME_SCHEDULE.get(now.hour, [])
    for start, end in intervals:
        if start <= now.minute <= end:
            return True
    return False

def gradual_volume(tv, current, target):
    if current == target:
        return
    if current > target:
        steps = current - target
        for _ in range(steps):
            tv.volume_down()
            time.sleep(STEP_DELAY)
    else:
        steps = target - current
        for _ in range(steps):
            tv.volume_up()
            time.sleep(STEP_DELAY)

def get_current_song():
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-show_entries", "format_tags=StreamTitle",
        "-of", "default=noprint_wrappers=1:nokey=1",
        STREAM_URL
    ]
    try:
        result = subprocess.check_output(cmd, timeout=15).decode().strip()
        return result or None
    except Exception as ex:
        print(str(ex))
        return None

def get_last_logged_song():
    cursor.execute("SELECT title FROM songs ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    return row[0] if row else None

def log_song(song_title):
    last_title = get_last_logged_song()
    if last_title == song_title:
        return False
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("INSERT INTO songs (timestamp, title) VALUES (?, ?)", (timestamp, song_title))
    conn.commit()
    logging.info(f"Sonando ahora: {song_title}")
    return True

# --- Main ---
def main():
    tv = setup(f"{TV_HOST}", adb_server_ip="127.0.0.1")

    muted = False
    original_volume = INITIAL_VOLUME  # si se pasa como parámetro, se usa
    last_song = None
    silence_applied_for_song = None
    last_song_check = time.time()

    if original_volume is not None:
        logging.info(f"Volumen inicial configurado a {original_volume}")

    try:
        while True:
            now = datetime.now()

            # --- Check current song ---
            if time.time() - last_song_check >= CHECK_SONG_EVERY:
                current_song = get_current_song()
                last_song_check = time.time()

                if current_song and current_song != last_song:
                    if log_song(current_song):
                        last_song = current_song
                        silence_applied_for_song = False  # reinicia flag

                        if muted:
                            current_vol = tv.volume() or 0
                            if original_volume is not None:
                                gradual_volume(tv, current_vol, original_volume)
                                logging.info(f"Volumen restaurado por cambio de canción a {original_volume}")
                            # No cambiar muted a False, solo resetear el flag de la canción

            # --- Control de volumen por horario ---
            if is_within_scheduled_interval(now):
                if not muted and not silence_applied_for_song:
                    current_vol = tv.volume() or 0
                    if original_volume is None:
                        original_volume = current_vol
                    reduced = max(1, int(original_volume * REDUCTION_FACTOR))

                    if current_vol > reduced:
                        gradual_volume(tv, current_vol, reduced)
                        muted = True
                        silence_applied_for_song = True
                        logging.info(f"Volumen bajado gradualmente a {reduced} (original {original_volume})")
            else:
                if muted:
                    current_vol = tv.volume() or 0
                    if original_volume is not None:
                        gradual_volume(tv, current_vol, original_volume)
                        logging.info(f"Volumen restaurado gradualmente a {original_volume}")
                    muted = False
                    silence_applied_for_song = None

            time.sleep(1)

    except KeyboardInterrupt:
        print("\nCtrl+C detectado. Saliendo...")
    finally:
        conn.close()

if __name__ == "__main__":
    main()

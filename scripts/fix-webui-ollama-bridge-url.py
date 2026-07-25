#!/usr/bin/env python3
"""Point Open WebUI's persisted Ollama URL at the backend auto-model bridge.

Open WebUI stores ollama.base_urls in webui.db after first start; the
OPEN_WEBUI_OLLAMA_URL / OLLAMA_BASE_URL env vars are ignored once that row exists.

Run inside the open-webui container:
  docker compose exec open-webui python /tmp/fix-webui-ollama-bridge-url.py

Or from the host after copying the script in.
"""

from __future__ import annotations

import sqlite3
import time

DB = "/app/backend/data/webui.db"
KEY = "ollama.base_urls"
VALUE = '["http://backend:8000/ollama"]'


def main() -> None:
    con = sqlite3.connect(DB)
    cur = con.cursor()
    before = cur.execute("select value from config where key=?", (KEY,)).fetchone()
    print("before", before)
    cur.execute(
        "update config set value=?, updated_at=? where key=?",
        (VALUE, int(time.time()), KEY),
    )
    if cur.rowcount == 0:
        cur.execute(
            "insert into config(key, value, updated_at) values (?, ?, ?)",
            (KEY, VALUE, int(time.time())),
        )
        print("inserted")
    else:
        print("updated", cur.rowcount)
    con.commit()
    after = cur.execute("select value from config where key=?", (KEY,)).fetchone()
    print("after", after)


if __name__ == "__main__":
    main()

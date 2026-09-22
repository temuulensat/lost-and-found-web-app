CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    is_admin INTEGER NOT NULL DEFAULT 0 CHECK (is_admin IN (0, 1))
);

CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    report_type TEXT NOT NULL CHECK (report_type IN ('lost', 'found')),
    item_name TEXT NOT NULL,
    category TEXT NOT NULL,
    color TEXT,
    location TEXT NOT NULL,
    country TEXT,
    region TEXT,
    city TEXT,
    area TEXT,
    date TEXT NOT NULL,
    description TEXT,
    image_filename TEXT,
    status TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lost_item_id INTEGER NOT NULL,
    found_item_id INTEGER NOT NULL,
    lost_user_id INTEGER NOT NULL,
    found_user_id INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (lost_item_id, found_item_id),
    FOREIGN KEY (lost_item_id) REFERENCES items (id),
    FOREIGN KEY (found_item_id) REFERENCES items (id),
    FOREIGN KEY (lost_user_id) REFERENCES users (id),
    FOREIGN KEY (found_user_id) REFERENCES users (id),
    CHECK (lost_user_id != found_user_id)
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL,
    sender_id INTEGER NOT NULL,
    body TEXT NOT NULL CHECK (LENGTH(TRIM(body)) > 0),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (conversation_id) REFERENCES conversations (id) ON DELETE CASCADE,
    FOREIGN KEY (sender_id) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS match_views (
    user_id INTEGER NOT NULL,
    lost_item_id INTEGER NOT NULL,
    found_item_id INTEGER NOT NULL,
    seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, lost_item_id, found_item_id),
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
    FOREIGN KEY (lost_item_id) REFERENCES items (id) ON DELETE CASCADE,
    FOREIGN KEY (found_item_id) REFERENCES items (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS conversation_reads (
    conversation_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    last_read_message_id INTEGER NOT NULL DEFAULT 0,
    read_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (conversation_id, user_id),
    FOREIGN KEY (conversation_id) REFERENCES conversations (id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS match_claims (
    lost_item_id INTEGER NOT NULL,
    found_item_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'possible'
        CHECK (status IN ('possible', 'claim_pending', 'confirmed', 'returned')),
    claimant_id INTEGER,
    claim_round INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (lost_item_id, found_item_id),
    FOREIGN KEY (lost_item_id) REFERENCES items (id) ON DELETE CASCADE,
    FOREIGN KEY (found_item_id) REFERENCES items (id) ON DELETE CASCADE,
    FOREIGN KEY (claimant_id) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS match_status_notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    lost_item_id INTEGER NOT NULL,
    found_item_id INTEGER NOT NULL,
    event_type TEXT NOT NULL
        CHECK (event_type IN ('claim_pending', 'accepted', 'rejected', 'returned')),
    claim_round INTEGER NOT NULL,
    message TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    seen_at TEXT,
    UNIQUE (user_id, lost_item_id, found_item_id, event_type, claim_round),
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
    FOREIGN KEY (lost_item_id, found_item_id)
        REFERENCES match_claims (lost_item_id, found_item_id) ON DELETE CASCADE
);

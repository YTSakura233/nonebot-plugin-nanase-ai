-- Original metadata schema EXAMPLE for MySQL/MariaDB; not the bot runtime schema.
-- Review on a new database before use. No migrations or writes run automatically.
CREATE TABLE kb_song (
    provider VARCHAR(32) NOT NULL,
    region VARCHAR(16) NOT NULL,
    source_song_id BIGINT UNSIGNED NOT NULL,
    title VARCHAR(512) NOT NULL,
    artist VARCHAR(1024) NOT NULL,
    genre VARCHAR(128) NOT NULL,
    snapshot_at DATETIME NOT NULL,
    PRIMARY KEY (provider, region, source_song_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE kb_chart (
    provider VARCHAR(32) NOT NULL,
    region VARCHAR(16) NOT NULL,
    source_song_id BIGINT UNSIGNED NOT NULL,
    chart_type VARCHAR(16) NOT NULL,
    difficulty TINYINT UNSIGNED NOT NULL,
    game_version INT UNSIGNED NOT NULL,
    display_level VARCHAR(16) NOT NULL,
    chart_constant DECIMAL(4,1) NULL,
    release_date DATE NULL,
    notes JSON NULL,
    PRIMARY KEY (provider, region, source_song_id, chart_type, difficulty, game_version),
    FOREIGN KEY (provider, region, source_song_id)
        REFERENCES kb_song(provider, region, source_song_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

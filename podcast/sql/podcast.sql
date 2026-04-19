DROP TABLE IF EXISTS podcast;

CREATE TABLE IF NOT EXISTS podcast (
    id INTEGER PRIMARY KEY,
    pid text NOT NULL,
    title text NOT NULL,
    author text NOT NULL,
    /*speakker: use ',' split*/
    speakers text NOT NULL,
    /*source: video_youtube | pdf | text(txt,md) | img(jpeg,png) | audio(mp3) */
    source text DEFAULT "",
    audio_url text NOT NULL,
    description text DEFAULT "",
    audio_content text DEFAULT "",
    cover_img_url text DEFAULT "",
    duration int DEFAULT 0,
    tags text DEFAULT "",
    /*category: 0: unknow 1:tech 2:education 3:food 4:travel 5:code 6:life 7:sport 8:music */
    category int DEFAULT 0,
    /*status: 0:init 1:edited 2:checking 3:passed 4:rejected 5:deleted */
    status int DEFAULT 0,
    is_published boolean DEFAULT false,
    create_time text NOT NULL,
    update_time text NOT NULL,
    audio_size int DEFAULT 0,
    /* Gemini-generated word-level subtitle artifacts (R2 URLs) */
    subtitle_json_url text DEFAULT "",
    subtitle_vtt_url text DEFAULT "",
    subtitle_lrc_url text DEFAULT "",
    subtitle_srt_url text DEFAULT ""
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_podcast_pid ON podcast (pid);

CREATE INDEX IF NOT EXISTS idx_podcast_ctime ON podcast (create_time);

CREATE INDEX IF NOT EXISTS idx_podcast_status ON podcast (
    is_published,
    category,
    status
)
where
    status != 5;

-- Migration for existing databases:
-- ALTER TABLE podcast ADD COLUMN subtitle_json_url text DEFAULT "";
-- ALTER TABLE podcast ADD COLUMN subtitle_vtt_url  text DEFAULT "";
-- ALTER TABLE podcast ADD COLUMN subtitle_lrc_url  text DEFAULT "";
-- ALTER TABLE podcast ADD COLUMN subtitle_srt_url  text DEFAULT "";
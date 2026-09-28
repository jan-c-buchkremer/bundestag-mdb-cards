-- The foundation store's tables that the cards read, dumped from the live store (bundestag-data-foundation
-- src/bdf/db.py; the election tables from PR #3). Refresh when the foundation schema changes.

CREATE TABLE person (
    id TEXT PRIMARY KEY,                -- Bundestag MdB id (MDB/ID == redner/@id)
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    name_prefix TEXT,                   -- Adel / Präfix ("von", "Freiherr von")
    academic_title TEXT,
    birth_date TEXT,                    -- ISO date
    birth_place TEXT,
    gender TEXT,
    party TEXT,
    is_mdb INTEGER NOT NULL DEFAULT 1,
    role TEXT,                          -- for non-MdB speakers: rolle_lang from the protocol
    dip_person_id TEXT,
    aw_politician_id INTEGER,
    wikidata_qid TEXT,
    source_url TEXT NOT NULL, source_document_id TEXT NOT NULL, retrieved_at TEXT NOT NULL
);

CREATE TABLE mandate (
    id TEXT PRIMARY KEY,                -- "<person_id>/<wp>"
    person_id TEXT NOT NULL REFERENCES person(id),
    wahlperiode INTEGER NOT NULL,
    from_date TEXT NOT NULL,
    to_date TEXT,
    mandate_type TEXT,                  -- Direktwahl | Landesliste
    constituency_number INTEGER,
    constituency_name TEXT,
    state TEXT,
    source_url TEXT NOT NULL, source_document_id TEXT NOT NULL, retrieved_at TEXT NOT NULL
);

CREATE TABLE membership (
    id TEXT PRIMARY KEY,                -- "<person_id>/<wp>/<n>"
    person_id TEXT NOT NULL REFERENCES person(id),
    wahlperiode INTEGER NOT NULL,
    kind TEXT NOT NULL,                 -- fraction | committee | other
    name TEXT NOT NULL,                 -- normalised fraction, or institution name
    role TEXT,                          -- FKT_LANG, e.g. "Vorsitzende"
    from_date TEXT,
    to_date TEXT,
    source_url TEXT NOT NULL, source_document_id TEXT NOT NULL, retrieved_at TEXT NOT NULL
);

CREATE TABLE sitting (
    id TEXT PRIMARY KEY,                -- "21/94"
    wahlperiode INTEGER NOT NULL,
    number INTEGER NOT NULL,
    date TEXT NOT NULL,
    start_time TEXT,
    end_time TEXT,
    xml_url TEXT NOT NULL,
    pdf_url TEXT NOT NULL,
    source_url TEXT NOT NULL, source_document_id TEXT NOT NULL, retrieved_at TEXT NOT NULL
);

CREATE TABLE agenda_item (
    id TEXT PRIMARY KEY,                -- "<sitting_id>/<position>"
    sitting_id TEXT NOT NULL REFERENCES sitting(id),
    position INTEGER NOT NULL,
    top_id TEXT NOT NULL,               -- XML top-id attribute, e.g. "Tagesordnungspunkt 3"
    title TEXT,
    drucksache_numbers TEXT NOT NULL,   -- JSON array of "21/7300"
    source_url TEXT NOT NULL, source_document_id TEXT NOT NULL, retrieved_at TEXT NOT NULL
);

CREATE TABLE speech (
    id TEXT PRIMARY KEY,                -- XML rede/@id, "-2", "-3" … when split
    sitting_id TEXT NOT NULL REFERENCES sitting(id),
    agenda_item_id TEXT REFERENCES agenda_item(id),
    position INTEGER NOT NULL,          -- order within the sitting
    person_id TEXT NOT NULL REFERENCES person(id),
    speaker_name TEXT NOT NULL,
    speaker_role TEXT,
    fraction TEXT,
    text TEXT NOT NULL,                 -- clean text: paragraphs of kind 'text', blank-line joined
    source_url TEXT NOT NULL, source_document_id TEXT NOT NULL, retrieved_at TEXT NOT NULL
);

CREATE TABLE speech_paragraph (
    id TEXT PRIMARY KEY,                -- "<speech_id>/<position>"
    speech_id TEXT NOT NULL REFERENCES speech(id),
    position INTEGER NOT NULL,
    kind TEXT NOT NULL,                 -- text | comment | chair | procedural
    text TEXT NOT NULL
);

CREATE TABLE roll_call_vote (
    id TEXT PRIMARY KEY,                -- "21/90/7"
    sitting_id TEXT REFERENCES sitting(id),
    number INTEGER NOT NULL,            -- Abstimmnr
    date TEXT NOT NULL,
    title TEXT NOT NULL,
    drucksache_number TEXT,
    vorgang_id TEXT REFERENCES vorgang(id),
    link_method TEXT,                   -- dip_beschluss | title_regex | manual
    yes INTEGER NOT NULL,
    no INTEGER NOT NULL,
    abstain INTEGER NOT NULL,
    invalid INTEGER NOT NULL,
    absent INTEGER NOT NULL,
    xlsx_url TEXT NOT NULL,
    pdf_url TEXT,
    source_url TEXT NOT NULL, source_document_id TEXT NOT NULL, retrieved_at TEXT NOT NULL
);

CREATE TABLE individual_vote (
    id TEXT PRIMARY KEY,                -- "<vote_id>/<row>"
    vote_id TEXT NOT NULL REFERENCES roll_call_vote(id),
    person_id TEXT REFERENCES person(id),
    last_name TEXT NOT NULL,
    first_name TEXT NOT NULL,
    fraction TEXT NOT NULL,
    vote TEXT NOT NULL                  -- yes | no | abstain | invalid | absent
);

CREATE TABLE vorgang (
    id TEXT PRIMARY KEY,                -- DIP id
    wahlperiode INTEGER NOT NULL,
    type TEXT,
    title TEXT NOT NULL,
    status TEXT,                        -- beratungsstand
    subjects TEXT NOT NULL,             -- JSON array (sachgebiet)
    initiators TEXT NOT NULL,           -- JSON array (initiative)
    source_url TEXT NOT NULL, source_document_id TEXT NOT NULL, retrieved_at TEXT NOT NULL
);

CREATE TABLE drucksache (
    id TEXT PRIMARY KEY,                -- DIP id
    number TEXT NOT NULL,               -- "21/7300"
    wahlperiode INTEGER NOT NULL,
    type TEXT,                          -- drucksachetyp
    title TEXT NOT NULL,
    date TEXT NOT NULL,
    pdf_url TEXT,
    publisher TEXT,                     -- herausgeber: BT | BR
    originators TEXT NOT NULL,          -- JSON array of urheber titles
    author_count INTEGER,
    source_url TEXT NOT NULL, source_document_id TEXT NOT NULL, retrieved_at TEXT NOT NULL
);

CREATE TABLE drucksache_author (
    id TEXT PRIMARY KEY,                -- "<drucksache_id>/<dip_person_id>"
    drucksache_id TEXT NOT NULL REFERENCES drucksache(id),
    dip_person_id TEXT NOT NULL,
    person_id TEXT REFERENCES person(id),
    name TEXT NOT NULL,
    activity_type TEXT,                 -- aktivitaetsart, e.g. "Antrag", "Kleine Anfrage"
    source_url TEXT NOT NULL, source_document_id TEXT NOT NULL, retrieved_at TEXT NOT NULL
);

CREATE TABLE vorgang_drucksache (
    vorgang_id TEXT NOT NULL REFERENCES vorgang(id),
    drucksache_id TEXT NOT NULL REFERENCES drucksache(id),
    PRIMARY KEY (vorgang_id, drucksache_id)
);

CREATE TABLE constituency (
    id TEXT PRIMARY KEY,                -- "<election>/<number>", e.g. "btw25/114"
    election TEXT NOT NULL,             -- "btw25"
    number INTEGER NOT NULL,
    name TEXT NOT NULL,
    state TEXT NOT NULL,                -- Land abbreviation, as mandate.state
    seat_party TEXT,                    -- party whose candidate got the seat; NULL: no Zweitstimmendeckung
    electorate INTEGER,
    voters INTEGER,
    source_url TEXT NOT NULL, source_document_id TEXT NOT NULL, retrieved_at TEXT NOT NULL
);

CREATE TABLE constituency_result (
    id TEXT PRIMARY KEY,                -- "<election>/<number>/<group order>/<vote>"
    election TEXT NOT NULL,
    constituency_number INTEGER NOT NULL,
    group_kind TEXT NOT NULL,           -- party | individual (Einzelbewerber)
    party TEXT NOT NULL,                -- Gruppenname, e.g. "SPD", "CSU", "GRÜNE"
    vote INTEGER NOT NULL,              -- 1 = Erststimme, 2 = Zweitstimme
    votes INTEGER NOT NULL,
    percent REAL,
    source_url TEXT NOT NULL, source_document_id TEXT NOT NULL, retrieved_at TEXT NOT NULL
);

CREATE TABLE election_candidacy (
    id TEXT PRIMARY KEY,                -- "<election>/<row in the Gewählte file>"
    election TEXT NOT NULL,
    person_id TEXT REFERENCES person(id),
    last_name TEXT NOT NULL,
    first_names TEXT NOT NULL,
    birth_year INTEGER,
    party TEXT NOT NULL,
    elected_via TEXT NOT NULL,          -- constituency | list
    constituency_number INTEGER,        -- won there, or stood there (list members)
    first_vote_percent REAL,            -- constituency winners only; others: constituency_result
    list_state TEXT,
    list_position INTEGER,
    occupation TEXT,
    source_url TEXT NOT NULL, source_document_id TEXT NOT NULL, retrieved_at TEXT NOT NULL
);

CREATE TABLE aw_profile (
    aw_politician_id INTEGER PRIMARY KEY,
    person_id TEXT REFERENCES person(id),
    url TEXT NOT NULL,                  -- the public profile page
    questions INTEGER,                  -- citizen questions on the profile, all periods (statistic_questions)
    questions_answered INTEGER,
    source_url TEXT NOT NULL, source_document_id TEXT NOT NULL, retrieved_at TEXT NOT NULL
);

CREATE TABLE interjection (
    id TEXT PRIMARY KEY,                -- "<speech_id>/<paragraph>/<part>/<actor>"
    speech_id TEXT NOT NULL REFERENCES speech(id),
    paragraph INTEGER NOT NULL,         -- speech_paragraph.position of the comment
    part INTEGER NOT NULL,              -- order of the part within the comment
    kind TEXT NOT NULL,                 -- beifall | zuruf | gegenruf | lachen | heiterkeit | widerspruch
                                        -- | zustimmung | unruhe | other
    actor TEXT NOT NULL,                -- fraction | members (some of the fraction) | person | house | unknown
    fraction TEXT,
    person_id TEXT REFERENCES person(id),
    name TEXT,                          -- printed name of a person
    text TEXT,                          -- the words of a Zuruf / Gegenruf, when printed
    to_person_id TEXT REFERENCES person(id),  -- addressee named in the comment ("an den Abg. …");
    to_name TEXT                        -- NULL: aimed at the speaker of speech_id
);


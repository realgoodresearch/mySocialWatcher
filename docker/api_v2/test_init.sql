CREATE TABLE collections (
    id serial PRIMARY KEY,
    name varchar(50) NOT NULL UNIQUE
);
CREATE TABLE tokens (
    contributor_id integer NOT NULL,
    token varchar(50) NOT NULL UNIQUE,
    write boolean NOT NULL DEFAULT false
);
INSERT INTO tokens (contributor_id, token, write) VALUES (1, 'v2-test-token', true);

CREATE TABLE facebook (
    collection_id integer,
    contributor_id integer,
    collection_date date NOT NULL,
    country char(2) NOT NULL,
    gender smallint NOT NULL,
    age_min smallint NOT NULL,
    age_max smallint NOT NULL,
    dau integer NOT NULL,
    mau integer,
    mau_lower integer,
    mau_upper integer,
    timestamp bigint NOT NULL,
    geo_locations jsonb NOT NULL,
    all_fields jsonb DEFAULT '{}'::jsonb,
    targeting jsonb DEFAULT '{}'::jsonb,
    response jsonb DEFAULT '{}'::jsonb
);
CREATE UNIQUE INDEX facebook_test_unique ON facebook (
    country, collection_date, gender, age_min, age_max, dau,
    md5(geo_locations::text), md5(targeting::text), md5(response::text)
);

CREATE TABLE facebook_invalid (LIKE facebook INCLUDING DEFAULTS);
CREATE UNIQUE INDEX facebook_invalid_test_unique ON facebook_invalid (
    country, collection_date, gender, age_min, age_max, dau,
    md5(geo_locations::text), md5(targeting::text), md5(response::text)
);
CREATE TABLE instagram (LIKE facebook INCLUDING DEFAULTS);
CREATE UNIQUE INDEX instagram_test_unique ON instagram (
    country, collection_date, gender, age_min, age_max, dau,
    md5(geo_locations::text), md5(targeting::text), md5(response::text)
);
CREATE TABLE instagram_invalid (LIKE facebook INCLUDING DEFAULTS);
CREATE UNIQUE INDEX instagram_invalid_test_unique ON instagram_invalid (
    country, collection_date, gender, age_min, age_max, dau,
    md5(geo_locations::text), md5(targeting::text), md5(response::text)
);

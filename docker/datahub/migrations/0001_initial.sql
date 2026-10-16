-- Original datahub schema, including country partitions and initial contributor.
CREATE TABLE collections (
	id serial PRIMARY KEY,
	created_on DATE NOT NULL DEFAULT CURRENT_DATE,
	name VARCHAR (50) NOT NULL,
	UNIQUE(name)
);
GRANT SELECT ON collections TO writer, reader;
GRANT INSERT ON collections TO writer;
GRANT USAGE,SELECT ON SEQUENCE collections_id_seq TO writer, reader;

CREATE TABLE contributors (
	id serial PRIMARY KEY,
	created_on DATE NOT NULL DEFAULT CURRENT_DATE,
	name VARCHAR(50) NOT NULL,
	email VARCHAR(50) NOT NULL,
	collaborators INTEGER[] NOT NULL DEFAULT '{}',
	collections INTEGER[] NOT NULL DEFAULT '{}',
	UNIQUE(name)
);
GRANT SELECT ON contributors TO writer, reader;
GRANT USAGE,SELECT ON SEQUENCE contributors_id_seq TO writer, reader;

INSERT INTO contributors (id, name, email)
VALUES
(1,'Doug Leasure','douglas.leasure@demography.ox.ac.uk');

CREATE TABLE tokens (
	id serial PRIMARY KEY,
	contributor_id INT NOT NULL
    REFERENCES contributors(id)
    ON DELETE SET NULL,
	created_on DATE NOT NULL DEFAULT CURRENT_DATE,
	write BOOLEAN NOT NULL DEFAULT FALSE,
	token VARCHAR(50) UNIQUE NOT NULL DEFAULT MD5(random()::text),
	UNIQUE(contributor_id, write)
);
GRANT SELECT ON tokens TO writer;
GRANT USAGE,SELECT ON SEQUENCE tokens_id_seq TO writer, reader;

INSERT INTO tokens (contributor_id, write) VALUES (1, True);

CREATE TABLE facebook (
	collection_id INT REFERENCES collections(id) ON DELETE SET NULL,
	contributor_id INT REFERENCES contributors(id) ON DELETE SET NULL,
  contributed_on TIMESTAMPTZ(0) NOT NULL DEFAULT CURRENT_TIMESTAMP(0),
  collection_date DATE NOT NULL,
  country CHAR(2) NOT NULL,
  gender SMALLINT NOT NULL,
	age_min SMALLINT NOT NULL DEFAULT 0,
	age_max SMALLINT NOT NULL DEFAULT 999,
	dau INT NOT NULL,
	mau INT,
	mau_lower INT,
	mau_upper INT,
	timestamp BIGINT NOT NULL,
  geo_locations jsonb NOT NULL,
	all_fields jsonb DEFAULT '{}'::jsonb,
	targeting jsonb DEFAULT '{}'::jsonb,
	response jsonb DEFAULT '{}'::jsonb
) PARTITION BY LIST (country);

create unique index unique_fb_idx
    on facebook (country, collection_date, gender, age_min, age_max, dau,
    md5(geo_locations::text),
	md5(targeting::text),
	md5(response::text));

CREATE INDEX contributor_fb_idx ON facebook(contributor_id);
CREATE INDEX collection_fb_idx ON facebook(collection_id);
CREATE INDEX date_fb_idx ON facebook(collection_date);
CREATE INDEX contributed_on_fb_idx ON facebook(contributed_on);
CREATE INDEX gender_fb_idx ON facebook(gender);
CREATE INDEX age_fb_idx ON facebook(age_min, age_max);

GRANT SELECT ON facebook TO reader;
GRANT SELECT,INSERT ON facebook TO writer;

CREATE TABLE facebook_AD PARTITION OF facebook FOR VALUES IN ('AD');

CREATE TABLE facebook_AE PARTITION OF facebook FOR VALUES IN ('AE');

CREATE TABLE facebook_AF PARTITION OF facebook FOR VALUES IN ('AF');

CREATE TABLE facebook_AG PARTITION OF facebook FOR VALUES IN ('AG');

CREATE TABLE facebook_AI PARTITION OF facebook FOR VALUES IN ('AI');

CREATE TABLE facebook_AL PARTITION OF facebook FOR VALUES IN ('AL');

CREATE TABLE facebook_AM PARTITION OF facebook FOR VALUES IN ('AM');

CREATE TABLE facebook_AN PARTITION OF facebook FOR VALUES IN ('AN');

CREATE TABLE facebook_AO PARTITION OF facebook FOR VALUES IN ('AO');

CREATE TABLE facebook_AQ PARTITION OF facebook FOR VALUES IN ('AQ');

CREATE TABLE facebook_AR PARTITION OF facebook FOR VALUES IN ('AR');

CREATE TABLE facebook_AS PARTITION OF facebook FOR VALUES IN ('AS');

CREATE TABLE facebook_AT PARTITION OF facebook FOR VALUES IN ('AT');

CREATE TABLE facebook_AU PARTITION OF facebook FOR VALUES IN ('AU');

CREATE TABLE facebook_AW PARTITION OF facebook FOR VALUES IN ('AW');

CREATE TABLE facebook_AX PARTITION OF facebook FOR VALUES IN ('AX');

CREATE TABLE facebook_AZ PARTITION OF facebook FOR VALUES IN ('AZ');

CREATE TABLE facebook_BA PARTITION OF facebook FOR VALUES IN ('BA');

CREATE TABLE facebook_BB PARTITION OF facebook FOR VALUES IN ('BB');

CREATE TABLE facebook_BD PARTITION OF facebook FOR VALUES IN ('BD');

CREATE TABLE facebook_BE PARTITION OF facebook FOR VALUES IN ('BE');

CREATE TABLE facebook_BF PARTITION OF facebook FOR VALUES IN ('BF');

CREATE TABLE facebook_BG PARTITION OF facebook FOR VALUES IN ('BG');

CREATE TABLE facebook_BH PARTITION OF facebook FOR VALUES IN ('BH');

CREATE TABLE facebook_BI PARTITION OF facebook FOR VALUES IN ('BI');

CREATE TABLE facebook_BJ PARTITION OF facebook FOR VALUES IN ('BJ');

CREATE TABLE facebook_BL PARTITION OF facebook FOR VALUES IN ('BL');

CREATE TABLE facebook_BM PARTITION OF facebook FOR VALUES IN ('BM');

CREATE TABLE facebook_BN PARTITION OF facebook FOR VALUES IN ('BN');

CREATE TABLE facebook_BO PARTITION OF facebook FOR VALUES IN ('BO');

CREATE TABLE facebook_BQ PARTITION OF facebook FOR VALUES IN ('BQ');

CREATE TABLE facebook_BR PARTITION OF facebook FOR VALUES IN ('BR');

CREATE TABLE facebook_BS PARTITION OF facebook FOR VALUES IN ('BS');

CREATE TABLE facebook_BT PARTITION OF facebook FOR VALUES IN ('BT');

CREATE TABLE facebook_BV PARTITION OF facebook FOR VALUES IN ('BV');

CREATE TABLE facebook_BW PARTITION OF facebook FOR VALUES IN ('BW');

CREATE TABLE facebook_BY PARTITION OF facebook FOR VALUES IN ('BY');

CREATE TABLE facebook_BZ PARTITION OF facebook FOR VALUES IN ('BZ');

CREATE TABLE facebook_CA PARTITION OF facebook FOR VALUES IN ('CA');

CREATE TABLE facebook_CC PARTITION OF facebook FOR VALUES IN ('CC');

CREATE TABLE facebook_CD PARTITION OF facebook FOR VALUES IN ('CD');

CREATE TABLE facebook_CF PARTITION OF facebook FOR VALUES IN ('CF');

CREATE TABLE facebook_CG PARTITION OF facebook FOR VALUES IN ('CG');

CREATE TABLE facebook_CH PARTITION OF facebook FOR VALUES IN ('CH');

CREATE TABLE facebook_CI PARTITION OF facebook FOR VALUES IN ('CI');

CREATE TABLE facebook_CK PARTITION OF facebook FOR VALUES IN ('CK');

CREATE TABLE facebook_CL PARTITION OF facebook FOR VALUES IN ('CL');

CREATE TABLE facebook_CM PARTITION OF facebook FOR VALUES IN ('CM');

CREATE TABLE facebook_CN PARTITION OF facebook FOR VALUES IN ('CN');

CREATE TABLE facebook_CO PARTITION OF facebook FOR VALUES IN ('CO');

CREATE TABLE facebook_CR PARTITION OF facebook FOR VALUES IN ('CR');

CREATE TABLE facebook_CU PARTITION OF facebook FOR VALUES IN ('CU');

CREATE TABLE facebook_CV PARTITION OF facebook FOR VALUES IN ('CV');

CREATE TABLE facebook_CW PARTITION OF facebook FOR VALUES IN ('CW');

CREATE TABLE facebook_CX PARTITION OF facebook FOR VALUES IN ('CX');

CREATE TABLE facebook_CY PARTITION OF facebook FOR VALUES IN ('CY');

CREATE TABLE facebook_CZ PARTITION OF facebook FOR VALUES IN ('CZ');

CREATE TABLE facebook_DE PARTITION OF facebook FOR VALUES IN ('DE');

CREATE TABLE facebook_DJ PARTITION OF facebook FOR VALUES IN ('DJ');

CREATE TABLE facebook_DK PARTITION OF facebook FOR VALUES IN ('DK');

CREATE TABLE facebook_DM PARTITION OF facebook FOR VALUES IN ('DM');

CREATE TABLE facebook_DO PARTITION OF facebook FOR VALUES IN ('DO');

CREATE TABLE facebook_DZ PARTITION OF facebook FOR VALUES IN ('DZ');

CREATE TABLE facebook_EC PARTITION OF facebook FOR VALUES IN ('EC');

CREATE TABLE facebook_EE PARTITION OF facebook FOR VALUES IN ('EE');

CREATE TABLE facebook_EG PARTITION OF facebook FOR VALUES IN ('EG');

CREATE TABLE facebook_EH PARTITION OF facebook FOR VALUES IN ('EH');

CREATE TABLE facebook_ER PARTITION OF facebook FOR VALUES IN ('ER');

CREATE TABLE facebook_ES PARTITION OF facebook FOR VALUES IN ('ES');

CREATE TABLE facebook_ET PARTITION OF facebook FOR VALUES IN ('ET');

CREATE TABLE facebook_FI PARTITION OF facebook FOR VALUES IN ('FI');

CREATE TABLE facebook_FJ PARTITION OF facebook FOR VALUES IN ('FJ');

CREATE TABLE facebook_FK PARTITION OF facebook FOR VALUES IN ('FK');

CREATE TABLE facebook_FM PARTITION OF facebook FOR VALUES IN ('FM');

CREATE TABLE facebook_FO PARTITION OF facebook FOR VALUES IN ('FO');

CREATE TABLE facebook_FR PARTITION OF facebook FOR VALUES IN ('FR');

CREATE TABLE facebook_GA PARTITION OF facebook FOR VALUES IN ('GA');

CREATE TABLE facebook_GB PARTITION OF facebook FOR VALUES IN ('GB');

CREATE TABLE facebook_GD PARTITION OF facebook FOR VALUES IN ('GD');

CREATE TABLE facebook_GE PARTITION OF facebook FOR VALUES IN ('GE');

CREATE TABLE facebook_GF PARTITION OF facebook FOR VALUES IN ('GF');

CREATE TABLE facebook_GG PARTITION OF facebook FOR VALUES IN ('GG');

CREATE TABLE facebook_GH PARTITION OF facebook FOR VALUES IN ('GH');

CREATE TABLE facebook_GI PARTITION OF facebook FOR VALUES IN ('GI');

CREATE TABLE facebook_GL PARTITION OF facebook FOR VALUES IN ('GL');

CREATE TABLE facebook_GM PARTITION OF facebook FOR VALUES IN ('GM');

CREATE TABLE facebook_GN PARTITION OF facebook FOR VALUES IN ('GN');

CREATE TABLE facebook_GP PARTITION OF facebook FOR VALUES IN ('GP');

CREATE TABLE facebook_GQ PARTITION OF facebook FOR VALUES IN ('GQ');

CREATE TABLE facebook_GR PARTITION OF facebook FOR VALUES IN ('GR');

CREATE TABLE facebook_GS PARTITION OF facebook FOR VALUES IN ('GS');

CREATE TABLE facebook_GT PARTITION OF facebook FOR VALUES IN ('GT');

CREATE TABLE facebook_GU PARTITION OF facebook FOR VALUES IN ('GU');

CREATE TABLE facebook_GW PARTITION OF facebook FOR VALUES IN ('GW');

CREATE TABLE facebook_GY PARTITION OF facebook FOR VALUES IN ('GY');

CREATE TABLE facebook_HK PARTITION OF facebook FOR VALUES IN ('HK');

CREATE TABLE facebook_HM PARTITION OF facebook FOR VALUES IN ('HM');

CREATE TABLE facebook_HN PARTITION OF facebook FOR VALUES IN ('HN');

CREATE TABLE facebook_HR PARTITION OF facebook FOR VALUES IN ('HR');

CREATE TABLE facebook_HT PARTITION OF facebook FOR VALUES IN ('HT');

CREATE TABLE facebook_HU PARTITION OF facebook FOR VALUES IN ('HU');

CREATE TABLE facebook_ID PARTITION OF facebook FOR VALUES IN ('ID');

CREATE TABLE facebook_IE PARTITION OF facebook FOR VALUES IN ('IE');

CREATE TABLE facebook_IL PARTITION OF facebook FOR VALUES IN ('IL');

CREATE TABLE facebook_IM PARTITION OF facebook FOR VALUES IN ('IM');

CREATE TABLE facebook_IN PARTITION OF facebook FOR VALUES IN ('IN');

CREATE TABLE facebook_IO PARTITION OF facebook FOR VALUES IN ('IO');

CREATE TABLE facebook_IQ PARTITION OF facebook FOR VALUES IN ('IQ');

CREATE TABLE facebook_IR PARTITION OF facebook FOR VALUES IN ('IR');

CREATE TABLE facebook_IS PARTITION OF facebook FOR VALUES IN ('IS');

CREATE TABLE facebook_IT PARTITION OF facebook FOR VALUES IN ('IT');

CREATE TABLE facebook_JE PARTITION OF facebook FOR VALUES IN ('JE');

CREATE TABLE facebook_JM PARTITION OF facebook FOR VALUES IN ('JM');

CREATE TABLE facebook_JO PARTITION OF facebook FOR VALUES IN ('JO');

CREATE TABLE facebook_JP PARTITION OF facebook FOR VALUES IN ('JP');

CREATE TABLE facebook_KE PARTITION OF facebook FOR VALUES IN ('KE');

CREATE TABLE facebook_KG PARTITION OF facebook FOR VALUES IN ('KG');

CREATE TABLE facebook_KH PARTITION OF facebook FOR VALUES IN ('KH');

CREATE TABLE facebook_KI PARTITION OF facebook FOR VALUES IN ('KI');

CREATE TABLE facebook_KM PARTITION OF facebook FOR VALUES IN ('KM');

CREATE TABLE facebook_KN PARTITION OF facebook FOR VALUES IN ('KN');

CREATE TABLE facebook_KP PARTITION OF facebook FOR VALUES IN ('KP');

CREATE TABLE facebook_KR PARTITION OF facebook FOR VALUES IN ('KR');

CREATE TABLE facebook_KW PARTITION OF facebook FOR VALUES IN ('KW');

CREATE TABLE facebook_KY PARTITION OF facebook FOR VALUES IN ('KY');

CREATE TABLE facebook_KZ PARTITION OF facebook FOR VALUES IN ('KZ');

CREATE TABLE facebook_LA PARTITION OF facebook FOR VALUES IN ('LA');

CREATE TABLE facebook_LB PARTITION OF facebook FOR VALUES IN ('LB');

CREATE TABLE facebook_LC PARTITION OF facebook FOR VALUES IN ('LC');

CREATE TABLE facebook_LI PARTITION OF facebook FOR VALUES IN ('LI');

CREATE TABLE facebook_LK PARTITION OF facebook FOR VALUES IN ('LK');

CREATE TABLE facebook_LR PARTITION OF facebook FOR VALUES IN ('LR');

CREATE TABLE facebook_LS PARTITION OF facebook FOR VALUES IN ('LS');

CREATE TABLE facebook_LT PARTITION OF facebook FOR VALUES IN ('LT');

CREATE TABLE facebook_LU PARTITION OF facebook FOR VALUES IN ('LU');

CREATE TABLE facebook_LV PARTITION OF facebook FOR VALUES IN ('LV');

CREATE TABLE facebook_LY PARTITION OF facebook FOR VALUES IN ('LY');

CREATE TABLE facebook_MA PARTITION OF facebook FOR VALUES IN ('MA');

CREATE TABLE facebook_MC PARTITION OF facebook FOR VALUES IN ('MC');

CREATE TABLE facebook_MD PARTITION OF facebook FOR VALUES IN ('MD');

CREATE TABLE facebook_ME PARTITION OF facebook FOR VALUES IN ('ME');

CREATE TABLE facebook_MF PARTITION OF facebook FOR VALUES IN ('MF');

CREATE TABLE facebook_MG PARTITION OF facebook FOR VALUES IN ('MG');

CREATE TABLE facebook_MH PARTITION OF facebook FOR VALUES IN ('MH');

CREATE TABLE facebook_MK PARTITION OF facebook FOR VALUES IN ('MK');

CREATE TABLE facebook_ML PARTITION OF facebook FOR VALUES IN ('ML');

CREATE TABLE facebook_MM PARTITION OF facebook FOR VALUES IN ('MM');

CREATE TABLE facebook_MN PARTITION OF facebook FOR VALUES IN ('MN');

CREATE TABLE facebook_MO PARTITION OF facebook FOR VALUES IN ('MO');

CREATE TABLE facebook_MP PARTITION OF facebook FOR VALUES IN ('MP');

CREATE TABLE facebook_MQ PARTITION OF facebook FOR VALUES IN ('MQ');

CREATE TABLE facebook_MR PARTITION OF facebook FOR VALUES IN ('MR');

CREATE TABLE facebook_MS PARTITION OF facebook FOR VALUES IN ('MS');

CREATE TABLE facebook_MT PARTITION OF facebook FOR VALUES IN ('MT');

CREATE TABLE facebook_MU PARTITION OF facebook FOR VALUES IN ('MU');

CREATE TABLE facebook_MV PARTITION OF facebook FOR VALUES IN ('MV');

CREATE TABLE facebook_MW PARTITION OF facebook FOR VALUES IN ('MW');

CREATE TABLE facebook_MX PARTITION OF facebook FOR VALUES IN ('MX');

CREATE TABLE facebook_MY PARTITION OF facebook FOR VALUES IN ('MY');

CREATE TABLE facebook_MZ PARTITION OF facebook FOR VALUES IN ('MZ');

CREATE TABLE facebook_NA PARTITION OF facebook FOR VALUES IN ('NA');

CREATE TABLE facebook_NC PARTITION OF facebook FOR VALUES IN ('NC');

CREATE TABLE facebook_NE PARTITION OF facebook FOR VALUES IN ('NE');

CREATE TABLE facebook_NF PARTITION OF facebook FOR VALUES IN ('NF');

CREATE TABLE facebook_NG PARTITION OF facebook FOR VALUES IN ('NG');

CREATE TABLE facebook_NI PARTITION OF facebook FOR VALUES IN ('NI');

CREATE TABLE facebook_NL PARTITION OF facebook FOR VALUES IN ('NL');

CREATE TABLE facebook_NO PARTITION OF facebook FOR VALUES IN ('NO');

CREATE TABLE facebook_NP PARTITION OF facebook FOR VALUES IN ('NP');

CREATE TABLE facebook_NR PARTITION OF facebook FOR VALUES IN ('NR');

CREATE TABLE facebook_NU PARTITION OF facebook FOR VALUES IN ('NU');

CREATE TABLE facebook_NZ PARTITION OF facebook FOR VALUES IN ('NZ');

CREATE TABLE facebook_OM PARTITION OF facebook FOR VALUES IN ('OM');

CREATE TABLE facebook_PA PARTITION OF facebook FOR VALUES IN ('PA');

CREATE TABLE facebook_PE PARTITION OF facebook FOR VALUES IN ('PE');

CREATE TABLE facebook_PF PARTITION OF facebook FOR VALUES IN ('PF');

CREATE TABLE facebook_PG PARTITION OF facebook FOR VALUES IN ('PG');

CREATE TABLE facebook_PH PARTITION OF facebook FOR VALUES IN ('PH');

CREATE TABLE facebook_PK PARTITION OF facebook FOR VALUES IN ('PK');

CREATE TABLE facebook_PL PARTITION OF facebook FOR VALUES IN ('PL');

CREATE TABLE facebook_PM PARTITION OF facebook FOR VALUES IN ('PM');

CREATE TABLE facebook_PN PARTITION OF facebook FOR VALUES IN ('PN');

CREATE TABLE facebook_PR PARTITION OF facebook FOR VALUES IN ('PR');

CREATE TABLE facebook_PS PARTITION OF facebook FOR VALUES IN ('PS');

CREATE TABLE facebook_PT PARTITION OF facebook FOR VALUES IN ('PT');

CREATE TABLE facebook_PW PARTITION OF facebook FOR VALUES IN ('PW');

CREATE TABLE facebook_PY PARTITION OF facebook FOR VALUES IN ('PY');

CREATE TABLE facebook_QA PARTITION OF facebook FOR VALUES IN ('QA');

CREATE TABLE facebook_RE PARTITION OF facebook FOR VALUES IN ('RE');

CREATE TABLE facebook_RO PARTITION OF facebook FOR VALUES IN ('RO');

CREATE TABLE facebook_RS PARTITION OF facebook FOR VALUES IN ('RS');

CREATE TABLE facebook_RU PARTITION OF facebook FOR VALUES IN ('RU');

CREATE TABLE facebook_RW PARTITION OF facebook FOR VALUES IN ('RW');

CREATE TABLE facebook_SA PARTITION OF facebook FOR VALUES IN ('SA');

CREATE TABLE facebook_SB PARTITION OF facebook FOR VALUES IN ('SB');

CREATE TABLE facebook_SC PARTITION OF facebook FOR VALUES IN ('SC');

CREATE TABLE facebook_SD PARTITION OF facebook FOR VALUES IN ('SD');

CREATE TABLE facebook_SE PARTITION OF facebook FOR VALUES IN ('SE');

CREATE TABLE facebook_SG PARTITION OF facebook FOR VALUES IN ('SG');

CREATE TABLE facebook_SH PARTITION OF facebook FOR VALUES IN ('SH');

CREATE TABLE facebook_SI PARTITION OF facebook FOR VALUES IN ('SI');

CREATE TABLE facebook_SJ PARTITION OF facebook FOR VALUES IN ('SJ');

CREATE TABLE facebook_SK PARTITION OF facebook FOR VALUES IN ('SK');

CREATE TABLE facebook_SL PARTITION OF facebook FOR VALUES IN ('SL');

CREATE TABLE facebook_SM PARTITION OF facebook FOR VALUES IN ('SM');

CREATE TABLE facebook_SN PARTITION OF facebook FOR VALUES IN ('SN');

CREATE TABLE facebook_SO PARTITION OF facebook FOR VALUES IN ('SO');

CREATE TABLE facebook_SR PARTITION OF facebook FOR VALUES IN ('SR');

CREATE TABLE facebook_SS PARTITION OF facebook FOR VALUES IN ('SS');

CREATE TABLE facebook_ST PARTITION OF facebook FOR VALUES IN ('ST');

CREATE TABLE facebook_SV PARTITION OF facebook FOR VALUES IN ('SV');

CREATE TABLE facebook_SX PARTITION OF facebook FOR VALUES IN ('SX');

CREATE TABLE facebook_SY PARTITION OF facebook FOR VALUES IN ('SY');

CREATE TABLE facebook_SZ PARTITION OF facebook FOR VALUES IN ('SZ');

CREATE TABLE facebook_TC PARTITION OF facebook FOR VALUES IN ('TC');

CREATE TABLE facebook_TD PARTITION OF facebook FOR VALUES IN ('TD');

CREATE TABLE facebook_TF PARTITION OF facebook FOR VALUES IN ('TF');

CREATE TABLE facebook_TG PARTITION OF facebook FOR VALUES IN ('TG');

CREATE TABLE facebook_TH PARTITION OF facebook FOR VALUES IN ('TH');

CREATE TABLE facebook_TJ PARTITION OF facebook FOR VALUES IN ('TJ');

CREATE TABLE facebook_TK PARTITION OF facebook FOR VALUES IN ('TK');

CREATE TABLE facebook_TL PARTITION OF facebook FOR VALUES IN ('TL');

CREATE TABLE facebook_TM PARTITION OF facebook FOR VALUES IN ('TM');

CREATE TABLE facebook_TN PARTITION OF facebook FOR VALUES IN ('TN');

CREATE TABLE facebook_TO PARTITION OF facebook FOR VALUES IN ('TO');

CREATE TABLE facebook_TR PARTITION OF facebook FOR VALUES IN ('TR');

CREATE TABLE facebook_TT PARTITION OF facebook FOR VALUES IN ('TT');

CREATE TABLE facebook_TV PARTITION OF facebook FOR VALUES IN ('TV');

CREATE TABLE facebook_TW PARTITION OF facebook FOR VALUES IN ('TW');

CREATE TABLE facebook_TZ PARTITION OF facebook FOR VALUES IN ('TZ');

CREATE TABLE facebook_UA PARTITION OF facebook FOR VALUES IN ('UA');

CREATE TABLE facebook_UG PARTITION OF facebook FOR VALUES IN ('UG');

CREATE TABLE facebook_UM PARTITION OF facebook FOR VALUES IN ('UM');

CREATE TABLE facebook_US PARTITION OF facebook FOR VALUES IN ('US');

CREATE TABLE facebook_UY PARTITION OF facebook FOR VALUES IN ('UY');

CREATE TABLE facebook_UZ PARTITION OF facebook FOR VALUES IN ('UZ');

CREATE TABLE facebook_VA PARTITION OF facebook FOR VALUES IN ('VA');

CREATE TABLE facebook_VC PARTITION OF facebook FOR VALUES IN ('VC');

CREATE TABLE facebook_VE PARTITION OF facebook FOR VALUES IN ('VE');

CREATE TABLE facebook_VG PARTITION OF facebook FOR VALUES IN ('VG');

CREATE TABLE facebook_VI PARTITION OF facebook FOR VALUES IN ('VI');

CREATE TABLE facebook_VN PARTITION OF facebook FOR VALUES IN ('VN');

CREATE TABLE facebook_VU PARTITION OF facebook FOR VALUES IN ('VU');

CREATE TABLE facebook_WF PARTITION OF facebook FOR VALUES IN ('WF');

CREATE TABLE facebook_WS PARTITION OF facebook FOR VALUES IN ('WS');

CREATE TABLE facebook_XK PARTITION OF facebook FOR VALUES IN ('XK');

CREATE TABLE facebook_YE PARTITION OF facebook FOR VALUES IN ('YE');

CREATE TABLE facebook_YT PARTITION OF facebook FOR VALUES IN ('YT');

CREATE TABLE facebook_ZA PARTITION OF facebook FOR VALUES IN ('ZA');

CREATE TABLE facebook_ZM PARTITION OF facebook FOR VALUES IN ('ZM');

CREATE TABLE facebook_ZW PARTITION OF facebook FOR VALUES IN ('ZW');

CREATE TABLE facebook_invalid (
	collection_id INT REFERENCES collections(id) ON DELETE SET NULL,
	contributor_id INT REFERENCES contributors(id) ON DELETE SET NULL,
  contributed_on TIMESTAMPTZ(0) NOT NULL DEFAULT CURRENT_TIMESTAMP(0),
  collection_date DATE NOT NULL,
  country CHAR(2) NOT NULL,
  gender SMALLINT NOT NULL,
	age_min SMALLINT NOT NULL DEFAULT 0,
	age_max SMALLINT NOT NULL DEFAULT 999,
	dau INT NOT NULL,
	mau INT,
	mau_lower INT,
	mau_upper INT,
	timestamp BIGINT NOT NULL,
  geo_locations jsonb NOT NULL,
	all_fields jsonb DEFAULT '{}'::jsonb,
	targeting jsonb DEFAULT '{}'::jsonb,
	response jsonb DEFAULT '{}'::jsonb
);
create unique index unique_fb_invalid_idx
    on facebook_invalid (country, collection_date, gender, age_min, age_max, dau,
    md5(geo_locations::text),
	md5(targeting::text),
	md5(response::text));

GRANT SELECT ON facebook_invalid TO reader;
GRANT SELECT,INSERT ON facebook_invalid TO writer;

CREATE TABLE instagram (
	collection_id INT REFERENCES collections(id) ON DELETE SET NULL,
	contributor_id INT REFERENCES contributors(id) ON DELETE SET NULL,
  contributed_on TIMESTAMPTZ(0) NOT NULL DEFAULT CURRENT_TIMESTAMP(0),
  collection_date DATE NOT NULL,
  country CHAR(2) NOT NULL,
  gender SMALLINT NOT NULL,
	age_min SMALLINT NOT NULL DEFAULT 0,
	age_max SMALLINT NOT NULL DEFAULT 999,
	dau INT NOT NULL,
	mau INT,
	mau_lower INT,
	mau_upper INT,
	timestamp BIGINT NOT NULL,
  geo_locations jsonb NOT NULL,
	all_fields jsonb DEFAULT '{}'::jsonb,
	targeting jsonb DEFAULT '{}'::jsonb,
	response jsonb DEFAULT '{}'::jsonb
) PARTITION BY LIST (country);
create unique index unique_ig_idx
    on instagram (country, collection_date, gender, age_min, age_max, dau,
    md5(geo_locations::text),
	md5(targeting::text),
	md5(response::text));
CREATE INDEX contributor_ig_idx ON instagram(contributor_id);
CREATE INDEX collection_ig_idx ON instagram(collection_id);
CREATE INDEX date_ig_idx ON instagram(collection_date);
CREATE INDEX contributed_on_ig_idx ON instagram(contributed_on);
CREATE INDEX gender_ig_idx ON instagram(gender);
CREATE INDEX age_ig_idx ON instagram(age_min, age_max);

GRANT SELECT ON instagram TO reader;
GRANT SELECT,INSERT ON instagram TO writer;

CREATE TABLE instagram_AD PARTITION OF instagram FOR VALUES IN ('AD');

CREATE TABLE instagram_AE PARTITION OF instagram FOR VALUES IN ('AE');

CREATE TABLE instagram_AF PARTITION OF instagram FOR VALUES IN ('AF');

CREATE TABLE instagram_AG PARTITION OF instagram FOR VALUES IN ('AG');

CREATE TABLE instagram_AI PARTITION OF instagram FOR VALUES IN ('AI');

CREATE TABLE instagram_AL PARTITION OF instagram FOR VALUES IN ('AL');

CREATE TABLE instagram_AM PARTITION OF instagram FOR VALUES IN ('AM');

CREATE TABLE instagram_AN PARTITION OF instagram FOR VALUES IN ('AN');

CREATE TABLE instagram_AO PARTITION OF instagram FOR VALUES IN ('AO');

CREATE TABLE instagram_AQ PARTITION OF instagram FOR VALUES IN ('AQ');

CREATE TABLE instagram_AR PARTITION OF instagram FOR VALUES IN ('AR');

CREATE TABLE instagram_AS PARTITION OF instagram FOR VALUES IN ('AS');

CREATE TABLE instagram_AT PARTITION OF instagram FOR VALUES IN ('AT');

CREATE TABLE instagram_AU PARTITION OF instagram FOR VALUES IN ('AU');

CREATE TABLE instagram_AW PARTITION OF instagram FOR VALUES IN ('AW');

CREATE TABLE instagram_AX PARTITION OF instagram FOR VALUES IN ('AX');

CREATE TABLE instagram_AZ PARTITION OF instagram FOR VALUES IN ('AZ');

CREATE TABLE instagram_BA PARTITION OF instagram FOR VALUES IN ('BA');

CREATE TABLE instagram_BB PARTITION OF instagram FOR VALUES IN ('BB');

CREATE TABLE instagram_BD PARTITION OF instagram FOR VALUES IN ('BD');

CREATE TABLE instagram_BE PARTITION OF instagram FOR VALUES IN ('BE');

CREATE TABLE instagram_BF PARTITION OF instagram FOR VALUES IN ('BF');

CREATE TABLE instagram_BG PARTITION OF instagram FOR VALUES IN ('BG');

CREATE TABLE instagram_BH PARTITION OF instagram FOR VALUES IN ('BH');

CREATE TABLE instagram_BI PARTITION OF instagram FOR VALUES IN ('BI');

CREATE TABLE instagram_BJ PARTITION OF instagram FOR VALUES IN ('BJ');

CREATE TABLE instagram_BL PARTITION OF instagram FOR VALUES IN ('BL');

CREATE TABLE instagram_BM PARTITION OF instagram FOR VALUES IN ('BM');

CREATE TABLE instagram_BN PARTITION OF instagram FOR VALUES IN ('BN');

CREATE TABLE instagram_BO PARTITION OF instagram FOR VALUES IN ('BO');

CREATE TABLE instagram_BQ PARTITION OF instagram FOR VALUES IN ('BQ');

CREATE TABLE instagram_BR PARTITION OF instagram FOR VALUES IN ('BR');

CREATE TABLE instagram_BS PARTITION OF instagram FOR VALUES IN ('BS');

CREATE TABLE instagram_BT PARTITION OF instagram FOR VALUES IN ('BT');

CREATE TABLE instagram_BV PARTITION OF instagram FOR VALUES IN ('BV');

CREATE TABLE instagram_BW PARTITION OF instagram FOR VALUES IN ('BW');

CREATE TABLE instagram_BY PARTITION OF instagram FOR VALUES IN ('BY');

CREATE TABLE instagram_BZ PARTITION OF instagram FOR VALUES IN ('BZ');

CREATE TABLE instagram_CA PARTITION OF instagram FOR VALUES IN ('CA');

CREATE TABLE instagram_CC PARTITION OF instagram FOR VALUES IN ('CC');

CREATE TABLE instagram_CD PARTITION OF instagram FOR VALUES IN ('CD');

CREATE TABLE instagram_CF PARTITION OF instagram FOR VALUES IN ('CF');

CREATE TABLE instagram_CG PARTITION OF instagram FOR VALUES IN ('CG');

CREATE TABLE instagram_CH PARTITION OF instagram FOR VALUES IN ('CH');

CREATE TABLE instagram_CI PARTITION OF instagram FOR VALUES IN ('CI');

CREATE TABLE instagram_CK PARTITION OF instagram FOR VALUES IN ('CK');

CREATE TABLE instagram_CL PARTITION OF instagram FOR VALUES IN ('CL');

CREATE TABLE instagram_CM PARTITION OF instagram FOR VALUES IN ('CM');

CREATE TABLE instagram_CN PARTITION OF instagram FOR VALUES IN ('CN');

CREATE TABLE instagram_CO PARTITION OF instagram FOR VALUES IN ('CO');

CREATE TABLE instagram_CR PARTITION OF instagram FOR VALUES IN ('CR');

CREATE TABLE instagram_CU PARTITION OF instagram FOR VALUES IN ('CU');

CREATE TABLE instagram_CV PARTITION OF instagram FOR VALUES IN ('CV');

CREATE TABLE instagram_CW PARTITION OF instagram FOR VALUES IN ('CW');

CREATE TABLE instagram_CX PARTITION OF instagram FOR VALUES IN ('CX');

CREATE TABLE instagram_CY PARTITION OF instagram FOR VALUES IN ('CY');

CREATE TABLE instagram_CZ PARTITION OF instagram FOR VALUES IN ('CZ');

CREATE TABLE instagram_DE PARTITION OF instagram FOR VALUES IN ('DE');

CREATE TABLE instagram_DJ PARTITION OF instagram FOR VALUES IN ('DJ');

CREATE TABLE instagram_DK PARTITION OF instagram FOR VALUES IN ('DK');

CREATE TABLE instagram_DM PARTITION OF instagram FOR VALUES IN ('DM');

CREATE TABLE instagram_DO PARTITION OF instagram FOR VALUES IN ('DO');

CREATE TABLE instagram_DZ PARTITION OF instagram FOR VALUES IN ('DZ');

CREATE TABLE instagram_EC PARTITION OF instagram FOR VALUES IN ('EC');

CREATE TABLE instagram_EE PARTITION OF instagram FOR VALUES IN ('EE');

CREATE TABLE instagram_EG PARTITION OF instagram FOR VALUES IN ('EG');

CREATE TABLE instagram_EH PARTITION OF instagram FOR VALUES IN ('EH');

CREATE TABLE instagram_ER PARTITION OF instagram FOR VALUES IN ('ER');

CREATE TABLE instagram_ES PARTITION OF instagram FOR VALUES IN ('ES');

CREATE TABLE instagram_ET PARTITION OF instagram FOR VALUES IN ('ET');

CREATE TABLE instagram_FI PARTITION OF instagram FOR VALUES IN ('FI');

CREATE TABLE instagram_FJ PARTITION OF instagram FOR VALUES IN ('FJ');

CREATE TABLE instagram_FK PARTITION OF instagram FOR VALUES IN ('FK');

CREATE TABLE instagram_FM PARTITION OF instagram FOR VALUES IN ('FM');

CREATE TABLE instagram_FO PARTITION OF instagram FOR VALUES IN ('FO');

CREATE TABLE instagram_FR PARTITION OF instagram FOR VALUES IN ('FR');

CREATE TABLE instagram_GA PARTITION OF instagram FOR VALUES IN ('GA');

CREATE TABLE instagram_GB PARTITION OF instagram FOR VALUES IN ('GB');

CREATE TABLE instagram_GD PARTITION OF instagram FOR VALUES IN ('GD');

CREATE TABLE instagram_GE PARTITION OF instagram FOR VALUES IN ('GE');

CREATE TABLE instagram_GF PARTITION OF instagram FOR VALUES IN ('GF');

CREATE TABLE instagram_GG PARTITION OF instagram FOR VALUES IN ('GG');

CREATE TABLE instagram_GH PARTITION OF instagram FOR VALUES IN ('GH');

CREATE TABLE instagram_GI PARTITION OF instagram FOR VALUES IN ('GI');

CREATE TABLE instagram_GL PARTITION OF instagram FOR VALUES IN ('GL');

CREATE TABLE instagram_GM PARTITION OF instagram FOR VALUES IN ('GM');

CREATE TABLE instagram_GN PARTITION OF instagram FOR VALUES IN ('GN');

CREATE TABLE instagram_GP PARTITION OF instagram FOR VALUES IN ('GP');

CREATE TABLE instagram_GQ PARTITION OF instagram FOR VALUES IN ('GQ');

CREATE TABLE instagram_GR PARTITION OF instagram FOR VALUES IN ('GR');

CREATE TABLE instagram_GS PARTITION OF instagram FOR VALUES IN ('GS');

CREATE TABLE instagram_GT PARTITION OF instagram FOR VALUES IN ('GT');

CREATE TABLE instagram_GU PARTITION OF instagram FOR VALUES IN ('GU');

CREATE TABLE instagram_GW PARTITION OF instagram FOR VALUES IN ('GW');

CREATE TABLE instagram_GY PARTITION OF instagram FOR VALUES IN ('GY');

CREATE TABLE instagram_HK PARTITION OF instagram FOR VALUES IN ('HK');

CREATE TABLE instagram_HM PARTITION OF instagram FOR VALUES IN ('HM');

CREATE TABLE instagram_HN PARTITION OF instagram FOR VALUES IN ('HN');

CREATE TABLE instagram_HR PARTITION OF instagram FOR VALUES IN ('HR');

CREATE TABLE instagram_HT PARTITION OF instagram FOR VALUES IN ('HT');

CREATE TABLE instagram_HU PARTITION OF instagram FOR VALUES IN ('HU');

CREATE TABLE instagram_ID PARTITION OF instagram FOR VALUES IN ('ID');

CREATE TABLE instagram_IE PARTITION OF instagram FOR VALUES IN ('IE');

CREATE TABLE instagram_IL PARTITION OF instagram FOR VALUES IN ('IL');

CREATE TABLE instagram_IM PARTITION OF instagram FOR VALUES IN ('IM');

CREATE TABLE instagram_IN PARTITION OF instagram FOR VALUES IN ('IN');

CREATE TABLE instagram_IO PARTITION OF instagram FOR VALUES IN ('IO');

CREATE TABLE instagram_IQ PARTITION OF instagram FOR VALUES IN ('IQ');

CREATE TABLE instagram_IR PARTITION OF instagram FOR VALUES IN ('IR');

CREATE TABLE instagram_IS PARTITION OF instagram FOR VALUES IN ('IS');

CREATE TABLE instagram_IT PARTITION OF instagram FOR VALUES IN ('IT');

CREATE TABLE instagram_JE PARTITION OF instagram FOR VALUES IN ('JE');

CREATE TABLE instagram_JM PARTITION OF instagram FOR VALUES IN ('JM');

CREATE TABLE instagram_JO PARTITION OF instagram FOR VALUES IN ('JO');

CREATE TABLE instagram_JP PARTITION OF instagram FOR VALUES IN ('JP');

CREATE TABLE instagram_KE PARTITION OF instagram FOR VALUES IN ('KE');

CREATE TABLE instagram_KG PARTITION OF instagram FOR VALUES IN ('KG');

CREATE TABLE instagram_KH PARTITION OF instagram FOR VALUES IN ('KH');

CREATE TABLE instagram_KI PARTITION OF instagram FOR VALUES IN ('KI');

CREATE TABLE instagram_KM PARTITION OF instagram FOR VALUES IN ('KM');

CREATE TABLE instagram_KN PARTITION OF instagram FOR VALUES IN ('KN');

CREATE TABLE instagram_KP PARTITION OF instagram FOR VALUES IN ('KP');

CREATE TABLE instagram_KR PARTITION OF instagram FOR VALUES IN ('KR');

CREATE TABLE instagram_KW PARTITION OF instagram FOR VALUES IN ('KW');

CREATE TABLE instagram_KY PARTITION OF instagram FOR VALUES IN ('KY');

CREATE TABLE instagram_KZ PARTITION OF instagram FOR VALUES IN ('KZ');

CREATE TABLE instagram_LA PARTITION OF instagram FOR VALUES IN ('LA');

CREATE TABLE instagram_LB PARTITION OF instagram FOR VALUES IN ('LB');

CREATE TABLE instagram_LC PARTITION OF instagram FOR VALUES IN ('LC');

CREATE TABLE instagram_LI PARTITION OF instagram FOR VALUES IN ('LI');

CREATE TABLE instagram_LK PARTITION OF instagram FOR VALUES IN ('LK');

CREATE TABLE instagram_LR PARTITION OF instagram FOR VALUES IN ('LR');

CREATE TABLE instagram_LS PARTITION OF instagram FOR VALUES IN ('LS');

CREATE TABLE instagram_LT PARTITION OF instagram FOR VALUES IN ('LT');

CREATE TABLE instagram_LU PARTITION OF instagram FOR VALUES IN ('LU');

CREATE TABLE instagram_LV PARTITION OF instagram FOR VALUES IN ('LV');

CREATE TABLE instagram_LY PARTITION OF instagram FOR VALUES IN ('LY');

CREATE TABLE instagram_MA PARTITION OF instagram FOR VALUES IN ('MA');

CREATE TABLE instagram_MC PARTITION OF instagram FOR VALUES IN ('MC');

CREATE TABLE instagram_MD PARTITION OF instagram FOR VALUES IN ('MD');

CREATE TABLE instagram_ME PARTITION OF instagram FOR VALUES IN ('ME');

CREATE TABLE instagram_MF PARTITION OF instagram FOR VALUES IN ('MF');

CREATE TABLE instagram_MG PARTITION OF instagram FOR VALUES IN ('MG');

CREATE TABLE instagram_MH PARTITION OF instagram FOR VALUES IN ('MH');

CREATE TABLE instagram_MK PARTITION OF instagram FOR VALUES IN ('MK');

CREATE TABLE instagram_ML PARTITION OF instagram FOR VALUES IN ('ML');

CREATE TABLE instagram_MM PARTITION OF instagram FOR VALUES IN ('MM');

CREATE TABLE instagram_MN PARTITION OF instagram FOR VALUES IN ('MN');

CREATE TABLE instagram_MO PARTITION OF instagram FOR VALUES IN ('MO');

CREATE TABLE instagram_MP PARTITION OF instagram FOR VALUES IN ('MP');

CREATE TABLE instagram_MQ PARTITION OF instagram FOR VALUES IN ('MQ');

CREATE TABLE instagram_MR PARTITION OF instagram FOR VALUES IN ('MR');

CREATE TABLE instagram_MS PARTITION OF instagram FOR VALUES IN ('MS');

CREATE TABLE instagram_MT PARTITION OF instagram FOR VALUES IN ('MT');

CREATE TABLE instagram_MU PARTITION OF instagram FOR VALUES IN ('MU');

CREATE TABLE instagram_MV PARTITION OF instagram FOR VALUES IN ('MV');

CREATE TABLE instagram_MW PARTITION OF instagram FOR VALUES IN ('MW');

CREATE TABLE instagram_MX PARTITION OF instagram FOR VALUES IN ('MX');

CREATE TABLE instagram_MY PARTITION OF instagram FOR VALUES IN ('MY');

CREATE TABLE instagram_MZ PARTITION OF instagram FOR VALUES IN ('MZ');

CREATE TABLE instagram_NA PARTITION OF instagram FOR VALUES IN ('NA');

CREATE TABLE instagram_NC PARTITION OF instagram FOR VALUES IN ('NC');

CREATE TABLE instagram_NE PARTITION OF instagram FOR VALUES IN ('NE');

CREATE TABLE instagram_NF PARTITION OF instagram FOR VALUES IN ('NF');

CREATE TABLE instagram_NG PARTITION OF instagram FOR VALUES IN ('NG');

CREATE TABLE instagram_NI PARTITION OF instagram FOR VALUES IN ('NI');

CREATE TABLE instagram_NL PARTITION OF instagram FOR VALUES IN ('NL');

CREATE TABLE instagram_NO PARTITION OF instagram FOR VALUES IN ('NO');

CREATE TABLE instagram_NP PARTITION OF instagram FOR VALUES IN ('NP');

CREATE TABLE instagram_NR PARTITION OF instagram FOR VALUES IN ('NR');

CREATE TABLE instagram_NU PARTITION OF instagram FOR VALUES IN ('NU');

CREATE TABLE instagram_NZ PARTITION OF instagram FOR VALUES IN ('NZ');

CREATE TABLE instagram_OM PARTITION OF instagram FOR VALUES IN ('OM');

CREATE TABLE instagram_PA PARTITION OF instagram FOR VALUES IN ('PA');

CREATE TABLE instagram_PE PARTITION OF instagram FOR VALUES IN ('PE');

CREATE TABLE instagram_PF PARTITION OF instagram FOR VALUES IN ('PF');

CREATE TABLE instagram_PG PARTITION OF instagram FOR VALUES IN ('PG');

CREATE TABLE instagram_PH PARTITION OF instagram FOR VALUES IN ('PH');

CREATE TABLE instagram_PK PARTITION OF instagram FOR VALUES IN ('PK');

CREATE TABLE instagram_PL PARTITION OF instagram FOR VALUES IN ('PL');

CREATE TABLE instagram_PM PARTITION OF instagram FOR VALUES IN ('PM');

CREATE TABLE instagram_PN PARTITION OF instagram FOR VALUES IN ('PN');

CREATE TABLE instagram_PR PARTITION OF instagram FOR VALUES IN ('PR');

CREATE TABLE instagram_PS PARTITION OF instagram FOR VALUES IN ('PS');

CREATE TABLE instagram_PT PARTITION OF instagram FOR VALUES IN ('PT');

CREATE TABLE instagram_PW PARTITION OF instagram FOR VALUES IN ('PW');

CREATE TABLE instagram_PY PARTITION OF instagram FOR VALUES IN ('PY');

CREATE TABLE instagram_QA PARTITION OF instagram FOR VALUES IN ('QA');

CREATE TABLE instagram_RE PARTITION OF instagram FOR VALUES IN ('RE');

CREATE TABLE instagram_RO PARTITION OF instagram FOR VALUES IN ('RO');

CREATE TABLE instagram_RS PARTITION OF instagram FOR VALUES IN ('RS');

CREATE TABLE instagram_RU PARTITION OF instagram FOR VALUES IN ('RU');

CREATE TABLE instagram_RW PARTITION OF instagram FOR VALUES IN ('RW');

CREATE TABLE instagram_SA PARTITION OF instagram FOR VALUES IN ('SA');

CREATE TABLE instagram_SB PARTITION OF instagram FOR VALUES IN ('SB');

CREATE TABLE instagram_SC PARTITION OF instagram FOR VALUES IN ('SC');

CREATE TABLE instagram_SD PARTITION OF instagram FOR VALUES IN ('SD');

CREATE TABLE instagram_SE PARTITION OF instagram FOR VALUES IN ('SE');

CREATE TABLE instagram_SG PARTITION OF instagram FOR VALUES IN ('SG');

CREATE TABLE instagram_SH PARTITION OF instagram FOR VALUES IN ('SH');

CREATE TABLE instagram_SI PARTITION OF instagram FOR VALUES IN ('SI');

CREATE TABLE instagram_SJ PARTITION OF instagram FOR VALUES IN ('SJ');

CREATE TABLE instagram_SK PARTITION OF instagram FOR VALUES IN ('SK');

CREATE TABLE instagram_SL PARTITION OF instagram FOR VALUES IN ('SL');

CREATE TABLE instagram_SM PARTITION OF instagram FOR VALUES IN ('SM');

CREATE TABLE instagram_SN PARTITION OF instagram FOR VALUES IN ('SN');

CREATE TABLE instagram_SO PARTITION OF instagram FOR VALUES IN ('SO');

CREATE TABLE instagram_SR PARTITION OF instagram FOR VALUES IN ('SR');

CREATE TABLE instagram_SS PARTITION OF instagram FOR VALUES IN ('SS');

CREATE TABLE instagram_ST PARTITION OF instagram FOR VALUES IN ('ST');

CREATE TABLE instagram_SV PARTITION OF instagram FOR VALUES IN ('SV');

CREATE TABLE instagram_SX PARTITION OF instagram FOR VALUES IN ('SX');

CREATE TABLE instagram_SY PARTITION OF instagram FOR VALUES IN ('SY');

CREATE TABLE instagram_SZ PARTITION OF instagram FOR VALUES IN ('SZ');

CREATE TABLE instagram_TC PARTITION OF instagram FOR VALUES IN ('TC');

CREATE TABLE instagram_TD PARTITION OF instagram FOR VALUES IN ('TD');

CREATE TABLE instagram_TF PARTITION OF instagram FOR VALUES IN ('TF');

CREATE TABLE instagram_TG PARTITION OF instagram FOR VALUES IN ('TG');

CREATE TABLE instagram_TH PARTITION OF instagram FOR VALUES IN ('TH');

CREATE TABLE instagram_TJ PARTITION OF instagram FOR VALUES IN ('TJ');

CREATE TABLE instagram_TK PARTITION OF instagram FOR VALUES IN ('TK');

CREATE TABLE instagram_TL PARTITION OF instagram FOR VALUES IN ('TL');

CREATE TABLE instagram_TM PARTITION OF instagram FOR VALUES IN ('TM');

CREATE TABLE instagram_TN PARTITION OF instagram FOR VALUES IN ('TN');

CREATE TABLE instagram_TO PARTITION OF instagram FOR VALUES IN ('TO');

CREATE TABLE instagram_TR PARTITION OF instagram FOR VALUES IN ('TR');

CREATE TABLE instagram_TT PARTITION OF instagram FOR VALUES IN ('TT');

CREATE TABLE instagram_TV PARTITION OF instagram FOR VALUES IN ('TV');

CREATE TABLE instagram_TW PARTITION OF instagram FOR VALUES IN ('TW');

CREATE TABLE instagram_TZ PARTITION OF instagram FOR VALUES IN ('TZ');

CREATE TABLE instagram_UA PARTITION OF instagram FOR VALUES IN ('UA');

CREATE TABLE instagram_UG PARTITION OF instagram FOR VALUES IN ('UG');

CREATE TABLE instagram_UM PARTITION OF instagram FOR VALUES IN ('UM');

CREATE TABLE instagram_US PARTITION OF instagram FOR VALUES IN ('US');

CREATE TABLE instagram_UY PARTITION OF instagram FOR VALUES IN ('UY');

CREATE TABLE instagram_UZ PARTITION OF instagram FOR VALUES IN ('UZ');

CREATE TABLE instagram_VA PARTITION OF instagram FOR VALUES IN ('VA');

CREATE TABLE instagram_VC PARTITION OF instagram FOR VALUES IN ('VC');

CREATE TABLE instagram_VE PARTITION OF instagram FOR VALUES IN ('VE');

CREATE TABLE instagram_VG PARTITION OF instagram FOR VALUES IN ('VG');

CREATE TABLE instagram_VI PARTITION OF instagram FOR VALUES IN ('VI');

CREATE TABLE instagram_VN PARTITION OF instagram FOR VALUES IN ('VN');

CREATE TABLE instagram_VU PARTITION OF instagram FOR VALUES IN ('VU');

CREATE TABLE instagram_WF PARTITION OF instagram FOR VALUES IN ('WF');

CREATE TABLE instagram_WS PARTITION OF instagram FOR VALUES IN ('WS');

CREATE TABLE instagram_XK PARTITION OF instagram FOR VALUES IN ('XK');

CREATE TABLE instagram_YE PARTITION OF instagram FOR VALUES IN ('YE');

CREATE TABLE instagram_YT PARTITION OF instagram FOR VALUES IN ('YT');

CREATE TABLE instagram_ZA PARTITION OF instagram FOR VALUES IN ('ZA');

CREATE TABLE instagram_ZM PARTITION OF instagram FOR VALUES IN ('ZM');

CREATE TABLE instagram_ZW PARTITION OF instagram FOR VALUES IN ('ZW');

CREATE TABLE instagram_invalid (
	collection_id INT REFERENCES collections(id) ON DELETE SET NULL,
	contributor_id INT REFERENCES contributors(id) ON DELETE SET NULL,
  contributed_on TIMESTAMPTZ(0) NOT NULL DEFAULT CURRENT_TIMESTAMP(0),
  collection_date DATE NOT NULL,
  country CHAR(2) NOT NULL,
  gender SMALLINT NOT NULL,
	age_min SMALLINT NOT NULL DEFAULT 0,
	age_max SMALLINT NOT NULL DEFAULT 999,
	dau INT NOT NULL,
	mau INT,
	mau_lower INT,
	mau_upper INT,
	timestamp BIGINT NOT NULL,
  geo_locations jsonb NOT NULL,
	all_fields jsonb DEFAULT '{}'::jsonb,
	targeting jsonb DEFAULT '{}'::jsonb,
	response jsonb DEFAULT '{}'::jsonb
);
create unique index unique_ig_invalid_idx
    on instagram_invalid (country, collection_date, gender, age_min, age_max, dau,
    md5(geo_locations::text),
	md5(targeting::text),
	md5(response::text));

GRANT SELECT ON instagram_invalid TO reader;
GRANT SELECT,INSERT ON instagram_invalid TO writer;

CREATE TABLE vkontakte (
	collection_id INT REFERENCES collections(id) ON DELETE SET NULL,
	contributor_id INT REFERENCES contributors(id) ON DELETE SET NULL,
  contributed_on TIMESTAMPTZ(0) NOT NULL DEFAULT CURRENT_TIMESTAMP(0),
  collection_date DATE NOT NULL,
  country CHAR(2) NOT NULL,
  gender SMALLINT NOT NULL,
	age_min SMALLINT NOT NULL DEFAULT 0,
	age_max SMALLINT NOT NULL DEFAULT 999,
	dau INT NOT NULL,
	timestamp BIGINT NOT NULL,
  geo_locations jsonb NOT NULL
);
create unique index unique_vk_idx
    on vkontakte (country, collection_date, gender, age_min, age_max, dau,
    md5(geo_locations::text));
CREATE INDEX contributor_vk_idx ON vkontakte(contributor_id);
CREATE INDEX collection_vk_idx ON vkontakte(collection_id);
CREATE INDEX date_vk_idx ON vkontakte(collection_date);
CREATE INDEX contributed_on_vk_idx ON vkontakte(contributed_on);
CREATE INDEX gender_vk_idx ON vkontakte(gender);
CREATE INDEX age_vk_idx ON vkontakte(age_min, age_max);

GRANT SELECT ON vkontakte TO reader;
GRANT SELECT,INSERT ON vkontakte TO writer;

CREATE TABLE vkontakte_invalid (
	collection_id INT REFERENCES collections(id) ON DELETE SET NULL,
	contributor_id INT REFERENCES contributors(id) ON DELETE SET NULL,
  contributed_on TIMESTAMPTZ(0) NOT NULL DEFAULT CURRENT_TIMESTAMP(0),
  collection_date DATE NOT NULL,
  country CHAR(2) NOT NULL,
  gender SMALLINT NOT NULL,
	age_min SMALLINT NOT NULL DEFAULT 0,
	age_max SMALLINT NOT NULL DEFAULT 999,
	dau INT NOT NULL,
	timestamp BIGINT NOT NULL,
  geo_locations jsonb NOT NULL
);
create unique index unique_vk_invalid_idx
    on vkontakte_invalid (country, collection_date, gender, age_min, age_max, dau,
    md5(geo_locations::text));
GRANT SELECT ON vkontakte_invalid TO reader;
GRANT SELECT,INSERT ON vkontakte_invalid TO writer;

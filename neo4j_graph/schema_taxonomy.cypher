// Taxonomy nodes (added for clade filtering and weighting)
CREATE CONSTRAINT taxon_inat_id IF NOT EXISTS
FOR (t:Taxon) REQUIRE t.inat_id IS UNIQUE;

CREATE INDEX taxon_name IF NOT EXISTS FOR (t:Taxon) ON (t.name);
CREATE INDEX taxon_rank IF NOT EXISTS FOR (t:Taxon) ON (t.rank);

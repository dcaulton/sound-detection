// ============================================
// Sound Detection - Neo4j Schema (v0.2.0)
// Focused on residency, migration, prairie/savanna indicators,
// bats, raptors, pollinators, and dietary specialization
// ============================================

// ---------- Constraints (Uniqueness) ----------
CREATE CONSTRAINT species_scientific_name IF NOT EXISTS
FOR (s:Species) REQUIRE s.scientific_name IS UNIQUE;

CREATE CONSTRAINT habitat_name IF NOT EXISTS
FOR (h:Habitat) REQUIRE h.name IS UNIQUE;

CREATE CONSTRAINT season_name IF NOT EXISTS
FOR (s:Season) REQUIRE s.name IS UNIQUE;

CREATE CONSTRAINT region_name IF NOT EXISTS
FOR (r:Region) REQUIRE r.name IS UNIQUE;

CREATE CONSTRAINT food_source_name IF NOT EXISTS
FOR (f:FoodSource) REQUIRE f.name IS UNIQUE;

// ---------- Indexes for common lookups ----------
CREATE INDEX species_common_name IF NOT EXISTS FOR (s:Species) ON (s.common_name);
CREATE INDEX species_taxon IF NOT EXISTS FOR (s:Species) ON (s.taxon);

// ---------- Optional: Full-text search on species ----------
CREATE FULLTEXT INDEX species_search IF NOT EXISTS
FOR (s:Species) ON EACH [s.common_name, s.scientific_name];

// ---------- Full-text search on chunks for RAG ----------
CREATE FULLTEXT INDEX chunk_text IF NOT EXISTS
FOR (c:Chunk) ON EACH [c.text];

// ============================================
// Relationships (no data yet — just schema)
// ============================================

// Residency & Migration
// (Species)-[:RESIDENT_IN {status: 'year_round' | 'breeding' | 'winter'}]->(Region)
// (Species)-[:MIGRATES_THROUGH {peak_months: [...] }]->(Region)
// (Species)-[:BREEDS_IN]->(Habitat)

// Habitat & Indicator relationships
// (Species)-[:INDICATOR_OF]->(Habitat)

// Dietary & Ecological relationships
// (Species)-[:POLLINATES]->(FoodSource)
// (Species)-[:PREFERS | SPECIALIZES_ON {strength: 'strong' | 'moderate'}]->(FoodSource)
// (Species)-[:EATS]->(FoodSource)
// (Insect)-[:VOCALIZES]->()   // self-relationship or just a property

// Similarity
// (Species)-[:SIMILAR_TO {reason: 'visual' | 'vocal' | 'behavioral'}]->(Species)

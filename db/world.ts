import { env } from "cloudflare:workers";

type Row = Record<string, string | number | null>;

const schemaStatements = [
  `CREATE TABLE IF NOT EXISTS entities (
    id TEXT PRIMARY KEY, kind TEXT NOT NULL, level TEXT NOT NULL, name TEXT NOT NULL,
    symbol TEXT, description TEXT, jurisdiction TEXT, valid_from TEXT, valid_to TEXT
  )`,
  `CREATE TABLE IF NOT EXISTS relations (
    id TEXT PRIMARY KEY, subject_id TEXT NOT NULL, predicate TEXT NOT NULL, object_id TEXT NOT NULL,
    coefficient REAL, unit TEXT, confidence REAL NOT NULL DEFAULT 1, source_id TEXT,
    valid_from TEXT, valid_to TEXT
  )`,
  `CREATE TABLE IF NOT EXISTS sources (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, url TEXT NOT NULL, license TEXT, retrieved_at TEXT NOT NULL
  )`,
  `CREATE TABLE IF NOT EXISTS external_identities (
    id TEXT PRIMARY KEY, entity_id TEXT NOT NULL, namespace TEXT NOT NULL, external_id TEXT NOT NULL,
    source_id TEXT NOT NULL, mapping_type TEXT NOT NULL, confidence REAL NOT NULL
  )`,
  `CREATE TABLE IF NOT EXISTS facilities (
    entity_id TEXT PRIMARY KEY, facility_type TEXT NOT NULL, status TEXT NOT NULL,
    latitude REAL, longitude REAL, nominal_capacity REAL, available_capacity REAL,
    capacity_unit TEXT, availability REAL NOT NULL
  )`,
  `CREATE TABLE IF NOT EXISTS capabilities (
    id TEXT PRIMARY KEY, owner_entity_id TEXT NOT NULL, action TEXT NOT NULL, output_entity_id TEXT NOT NULL,
    max_rate REAL NOT NULL, available_rate REAL NOT NULL, unit TEXT NOT NULL,
    confidence REAL NOT NULL, model_version TEXT NOT NULL
  )`,
  `CREATE TABLE IF NOT EXISTS dependencies (
    id TEXT PRIMARY KEY, capability_id TEXT NOT NULL, dependency_entity_id TEXT NOT NULL,
    dependency_type TEXT NOT NULL, required_amount REAL, unit TEXT,
    current_availability REAL NOT NULL, criticality REAL NOT NULL, recovery_days REAL
  )`,
  `CREATE TABLE IF NOT EXISTS observations (
    id TEXT PRIMARY KEY, subject_entity_id TEXT NOT NULL, property TEXT NOT NULL,
    value REAL NOT NULL, unit TEXT NOT NULL, reality_class TEXT NOT NULL,
    epistemic_status TEXT NOT NULL, valid_time TEXT NOT NULL, recorded_time TEXT NOT NULL,
    source_id TEXT NOT NULL, uncertainty_low REAL, uncertainty_high REAL
  )`,
  `CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY, event_type TEXT NOT NULL, name TEXT NOT NULL, actuality TEXT NOT NULL,
    status TEXT NOT NULL, started_at TEXT NOT NULL, ended_at TEXT, location_entity_id TEXT,
    actor_entity_id TEXT, model_version TEXT
  )`,
  `CREATE TABLE IF NOT EXISTS postings (
    id TEXT PRIMARY KEY, event_id TEXT NOT NULL, entity_id TEXT NOT NULL, role TEXT NOT NULL,
    direction TEXT NOT NULL, quantity REAL NOT NULL, unit TEXT NOT NULL,
    abstraction_level TEXT NOT NULL, source_id TEXT
  )`,
  `CREATE TABLE IF NOT EXISTS scenarios (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL, horizon TEXT NOT NULL,
    gas_availability REAL NOT NULL, grid_availability REAL NOT NULL,
    logistics_availability REAL NOT NULL, workforce_availability REAL NOT NULL,
    demand_growth REAL NOT NULL, probability REAL NOT NULL, model_version TEXT NOT NULL
  )`,
  `CREATE TABLE IF NOT EXISTS model_runs (
    id TEXT PRIMARY KEY, scenario_id TEXT NOT NULL, run_at TEXT NOT NULL, model_version TEXT NOT NULL,
    expected_output REAL NOT NULL, low_output REAL NOT NULL, high_output REAL NOT NULL,
    unit TEXT NOT NULL, confidence REAL NOT NULL, limiting_factor TEXT NOT NULL
  )`,
];

const seedStatements = [
  `INSERT OR IGNORE INTO sources VALUES
    ('src-iea','IEA Ammonia Technology Roadmap','https://www.iea.org/reports/ammonia-technology-roadmap','CC BY 4.0','2026-07-29'),
    ('src-faostat','FAOSTAT Fertilizers by Nutrient','https://www.fao.org/faostat/','FAO terms','2026-07-29'),
    ('src-chebi','ChEBI','https://www.ebi.ac.uk/chebi/','CC BY 4.0','2026-07-29'),
    ('src-orb','ORB pilot model','https://orb-srp-prototype.neokkv.chatgpt.site','Project data','2026-07-29')`,
  `INSERT OR IGNORE INTO entities VALUES
    ('country-ua','state','institutional','Украина','UA','Институциональная граница пилотного контура','UA','1991-08-24',NULL),
    ('company-azot','company','institutional','ORB Nitrogen Operations',NULL,'Демонстрационный оператор производственного контура','UA','2026-01-01',NULL),
    ('plant-cherkasy','facility','object','Черкасский азотный узел',NULL,'Модель производственного узла для проверки архитектуры','UA','2026-01-01',NULL),
    ('line-ammonia-1','production_line','object','Линия синтеза аммиака №1',NULL,'Критическая производственная линия','UA','2026-01-01',NULL),
    ('network-gas','infrastructure','object','Газоснабжение',NULL,'Вход природного газа в производственный контур','UA','2026-01-01',NULL),
    ('network-grid','infrastructure','object','Энергосистема',NULL,'Электроснабжение производственного контура','UA','2026-01-01',NULL),
    ('network-rail','infrastructure','object','Железнодорожная сеть',NULL,'Доставка удобрений в аграрные регионы','UA','2026-01-01',NULL),
    ('workforce-ammonia','workforce_pool','agent','Персонал аммиачного производства',NULL,'Агрегированный пул обязательных компетенций','UA','2026-01-01',NULL),
    ('n-atom','atom','atomic','Азот','N','Атомарное представление азота',NULL,NULL,NULL),
    ('h-atom','atom','atomic','Водород','H','Атомарное представление водорода',NULL,NULL,NULL),
    ('n2','chemical_entity','chemical','Азот молекулярный','N₂','Атмосферный азот',NULL,NULL,NULL),
    ('h2','chemical_entity','chemical','Водород','H₂','Технологический водород',NULL,NULL,NULL),
    ('nh3','chemical_entity','chemical','Аммиак','NH₃','Базовая химическая сущность азотного контура',NULL,NULL,NULL),
    ('urea','material','material','Карбамид','CO(NH₂)₂','Азотное удобрение',NULL,NULL,NULL),
    ('grain','material','material','Зерно','🌾','Агрегированный продукт растениеводства',NULL,NULL,NULL)`,
  `INSERT OR IGNORE INTO external_identities VALUES
    ('ext-n2-chebi','n2','ChEBI','CHEBI:17997','src-chebi','exact_match',1),
    ('ext-h2-chebi','h2','ChEBI','CHEBI:18276','src-chebi','exact_match',1),
    ('ext-nh3-chebi','nh3','ChEBI','CHEBI:16134','src-chebi','exact_match',1),
    ('ext-urea-chebi','urea','ChEBI','CHEBI:16199','src-chebi','close_match',0.95)`,
  `INSERT OR IGNORE INTO relations VALUES
    ('rel-country-plant','plant-cherkasy','located_in','country-ua',NULL,NULL,1,'src-orb','2026-01-01',NULL),
    ('rel-company-plant','company-azot','operates','plant-cherkasy',NULL,NULL,1,'src-orb','2026-01-01',NULL),
    ('rel-plant-line','plant-cherkasy','contains','line-ammonia-1',NULL,NULL,1,'src-orb','2026-01-01',NULL),
    ('rel-n2-n','n2','composed_of','n-atom',2,'atom/mol',1,'src-chebi',NULL,NULL),
    ('rel-h2-h','h2','composed_of','h-atom',2,'atom/mol',1,'src-chebi',NULL,NULL),
    ('rel-nh3-n','nh3','composed_of','n-atom',1,'atom/mol',1,'src-chebi',NULL,NULL),
    ('rel-nh3-h','nh3','composed_of','h-atom',3,'atom/mol',1,'src-chebi',NULL,NULL),
    ('rel-urea-n','urea','contains_element','n-atom',0.466,'kg/kg',0.99,'src-chebi',NULL,NULL)`,
  `INSERT OR IGNORE INTO facilities VALUES
    ('plant-cherkasy','chemical_plant','constrained',49.4444,32.0598,1200,840,'t NH3/day',0.70),
    ('line-ammonia-1','ammonia_line','active',49.4444,32.0598,1200,840,'t NH3/day',0.70)`,
  `INSERT OR IGNORE INTO capabilities VALUES
    ('cap-ammonia-1','line-ammonia-1','produce','nh3',1200,840,'t/day',0.72,'capability-v0.1')`,
  `INSERT OR IGNORE INTO dependencies VALUES
    ('dep-gas','cap-ammonia-1','network-gas','feedstock_energy',28,'GJ/t',0.74,1.0,7),
    ('dep-grid','cap-ammonia-1','network-grid','electricity',0.7,'MWh/t',0.88,0.82,2),
    ('dep-rail','cap-ammonia-1','network-rail','outbound_logistics',840,'t/day',0.67,0.76,4),
    ('dep-workforce','cap-ammonia-1','workforce-ammonia','required_skills',18,'qualified staff/shift',0.91,0.70,14)`,
  `INSERT OR IGNORE INTO observations VALUES
    ('obs-iea-energy','nh3','reference_energy_intensity',41,'GJ/t','observed','reported','2021-01-01','2026-07-29','src-iea',28,46),
    ('obs-line-capacity','line-ammonia-1','available_capacity',840,'t/day','estimated','modelled','2026-07-29','2026-07-29','src-orb',720,960),
    ('obs-demand','country-ua','annual_nitrogen_demand_index',100,'index','estimated','modelled','2026-07-29','2026-07-29','src-orb',88,115)`,
  `INSERT OR IGNORE INTO events VALUES
    ('evt-ammonia-001','transformation','Синтез аммиака — демонстрационная смена','observed','reconciled','2026-07-28T08:00:00Z','2026-07-28T16:00:00Z','plant-cherkasy','company-azot','haber-bosch-v0.1')`,
  `INSERT OR IGNORE INTO postings VALUES
    ('post-n2-in','evt-ammonia-001','n2','feedstock','out',164.7,'t','chemical','src-orb'),
    ('post-h2-in','evt-ammonia-001','h2','feedstock','out',35.3,'t','chemical','src-orb'),
    ('post-nh3-out','evt-ammonia-001','nh3','product','in',200,'t','chemical','src-orb'),
    ('post-energy-in','evt-ammonia-001','network-gas','energy_input','out',8200,'GJ','object','src-iea')`,
  `INSERT OR IGNORE INTO scenarios VALUES
    ('scenario-base','Базовый','Текущая доступность инфраструктуры и персонала','2027',0.74,0.88,0.67,0.91,0.03,0.55,'nitrogen-network-v0.1'),
    ('scenario-resilient','Устойчивый контур','Резервирование газа и железнодорожной логистики','2027',0.92,0.94,0.88,0.95,0.03,0.25,'nitrogen-network-v0.1'),
    ('scenario-stress','Логистический стресс','Ограничение газа и исходящей логистики','2027',0.48,0.79,0.42,0.86,0.03,0.20,'nitrogen-network-v0.1')`,
  `INSERT OR IGNORE INTO model_runs VALUES
    ('run-base','scenario-base','2026-07-29T00:00:00Z','nitrogen-network-v0.1',294000,246000,341000,'t NH3/year',0.67,'Железнодорожная сеть'),
    ('run-resilient','scenario-resilient','2026-07-29T00:00:00Z','nitrogen-network-v0.1',385000,351000,411000,'t NH3/year',0.81,'Газоснабжение'),
    ('run-stress','scenario-stress','2026-07-29T00:00:00Z','nitrogen-network-v0.1',184000,126000,229000,'t NH3/year',0.52,'Железнодорожная сеть')`,
];

async function ensureDatabase() {
  const db = env.DB;
  if (!db) throw new Error("D1 binding DB is unavailable");
  await db.batch(schemaStatements.map((statement) => db.prepare(statement)));
  for (const statement of seedStatements) {
    await db.prepare(statement).run();
  }
  return db;
}

async function all(db: D1Database, sql: string): Promise<Row[]> {
  const result = await db.prepare(sql).all<Row>();
  return result.results;
}

export type WorldSnapshot = Awaited<ReturnType<typeof getWorldSnapshot>>;

export async function getWorldSnapshot() {
  const db = await ensureDatabase();
  const [entities, relations, facilities, capabilities, dependencies, events, postings, scenarios, runs, sources, externalIdentities] =
    await Promise.all([
      all(db, "SELECT * FROM entities ORDER BY level, name"),
      all(db, "SELECT * FROM relations ORDER BY predicate"),
      all(db, "SELECT * FROM facilities ORDER BY entity_id"),
      all(db, "SELECT * FROM capabilities ORDER BY id"),
      all(db, `SELECT d.*, e.name AS dependency_name
        FROM dependencies d JOIN entities e ON e.id = d.dependency_entity_id
        ORDER BY d.criticality DESC`),
      all(db, "SELECT * FROM events ORDER BY started_at DESC"),
      all(db, `SELECT p.*, e.name AS entity_name, e.symbol
        FROM postings p JOIN entities e ON e.id = p.entity_id ORDER BY p.id`),
      all(db, "SELECT * FROM scenarios ORDER BY probability DESC"),
      all(db, "SELECT * FROM model_runs ORDER BY expected_output DESC"),
      all(db, "SELECT * FROM sources ORDER BY name"),
      all(db, "SELECT * FROM external_identities ORDER BY namespace"),
    ]);

  return {
    generatedAt: new Date().toISOString(),
    entities,
    relations,
    facilities,
    capabilities,
    dependencies,
    events,
    postings,
    scenarios,
    runs,
    sources,
    externalIdentities,
  };
}
